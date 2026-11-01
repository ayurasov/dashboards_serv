"""Вход по учётной записи домена: LDAP / Active Directory, FreeIPA, OpenLDAP (ADR-0008).

Порт подхода todo-planner (ADR-0051 там) с доработками: StartTLS для ldap:// (AUTH_LDAP_START_TLS),
профиль доступа по группам каталога при создании учётной записи, проверка подключения и поиска
логина для администратора.

Проверка пароля:
1. служебная привязка (AUTH_LDAP_BIND_DN) или анонимная; поиск по фильтру AUTH_LDAP_USER_FILTER,
   введённый логин экранируется (escape_filter_chars); ровно одна запись — иначе отказ;
2. привязка от имени DN найденной записи с паролем пользователя (DN из логина не собирается);
3. отключённая в AD запись (userAccountControl & 2) не входит.

Сопоставление с учётной записью системы: auth_external_id (objectGUID / entryUUID), затем
идентификатор синхронизации с AD (org_source = ad и external_id), затем единственный email без
учёта регистра. Логин не используется: одинаковый логин в разных системах может принадлежать
разным людям. Привязка переводит вход на каталог (auth_source = ldap) и удаляет локальный пароль;
данные системы не меняются, из каталога заполняются только пустые поля.

Секреты (пароль служебной учётной записи) в API и журнал не попадают. Фабрики сервера и
соединения подменяются в тестах (ldap3 MOCK_SYNC).
"""
from __future__ import annotations

import contextlib
import logging
import re
import ssl
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import Settings, settings
from ..core.db import utcnow
from ..models import AccessProfile, User
from . import audit

log = logging.getLogger("app.ldap")

UAC_DISABLED = 0x2
SOURCE_LOCAL, SOURCE_LDAP = "local", "ldap"
CREATE_MODES = ("active", "inactive")


class DirectoryUnavailable(RuntimeError):
    """Каталог не отвечает, не принял служебную учётную запись, или пакет ldap3 не установлен."""


def _dn_key(dn: str) -> str:
    """DN для сравнения: без регистра и пробелов вокруг «,» и «=»."""
    return re.sub(r"\s*([,=])\s*", r"\1", (dn or "").strip()).casefold()


def parse_group_profiles(value: str) -> tuple[tuple[str, str], ...]:
    """«DN группы=ключ профиля;DN группы=ключ профиля» → ((DN, ключ), …). DN сам содержит «=»,
    поэтому ключ профиля — после последнего «=»."""
    pairs: list[tuple[str, str]] = []
    for item in re.split(r"[;\n]", value or ""):
        item = item.strip()
        if not item:
            continue
        dn, sep, key = item.rpartition("=")
        if not sep or not dn.strip() or not key.strip():
            log.warning("AUTH_LDAP_GROUP_PROFILES: пропущена запись без «=ключ профиля»: %s", item)
            continue
        pairs.append((dn.strip(), key.strip()))
    return tuple(pairs)


@dataclass(frozen=True)
class LdapConfig:
    url: str
    base_dn: str
    bind_dn: str = ""
    bind_password: str = field(default="", repr=False)
    user_filter: str = "(&(objectClass=person)(|(sAMAccountName={login})(userPrincipalName={login})(mail={login})))"
    attr_id: str = "objectGUID"
    attr_email: str = "mail"
    attr_name: str = "displayName"
    attr_login: str = "sAMAccountName"
    attr_position: str = "title"
    attr_groups: str = "memberOf"
    ca_file: str = ""
    start_tls: bool = False
    timeout: int = 5
    create_users: str = ""          # "", active, inactive
    default_profile: str = ""
    group_profiles: tuple[tuple[str, str], ...] = ()
    admin_group: str = ""
    login_hint: str = ""
    enabled: bool = True

    @classmethod
    def from_settings(cls, source: Settings | None = None, *, require_enabled: bool = True) -> LdapConfig | None:
        """Конфигурация или None: вход по домену выключен (require_enabled) или не заданы адрес и база поиска."""
        s = source or settings
        if require_enabled and not s.auth_ldap_enabled:
            return None
        url, base_dn = s.auth_ldap_url.strip(), s.auth_ldap_base_dn.strip()
        if not url or not base_dn:
            return None
        return cls(
            url=url, base_dn=base_dn, bind_dn=s.auth_ldap_bind_dn.strip(), bind_password=s.auth_ldap_bind_password,
            user_filter=s.auth_ldap_user_filter.strip() or cls.user_filter,
            attr_id=s.auth_ldap_attr_id.strip() or "objectGUID", attr_email=s.auth_ldap_attr_email.strip() or "mail",
            attr_name=s.auth_ldap_attr_name.strip() or "displayName",
            attr_login=s.auth_ldap_attr_login.strip() or "sAMAccountName",
            attr_position=s.auth_ldap_attr_position.strip(), attr_groups=s.auth_ldap_attr_groups.strip(),
            ca_file=s.auth_ldap_ca_file.strip(), start_tls=s.auth_ldap_start_tls, timeout=s.auth_ldap_timeout,
            create_users=s.auth_ldap_create_users if s.auth_ldap_create_users in CREATE_MODES else "",
            default_profile=s.auth_ldap_default_profile.strip(),
            group_profiles=parse_group_profiles(s.auth_ldap_group_profiles),
            admin_group=s.auth_ldap_admin_group.strip(), login_hint=s.auth_ldap_login_hint.strip(),
            enabled=s.auth_ldap_enabled,
        )

    @property
    def is_ldaps(self) -> bool:
        return self.url.lower().startswith("ldaps://")

    @property
    def use_start_tls(self) -> bool:
        """StartTLS — для ldap:// по настройке или когда задан CA-сертификат (как у синхронизации с AD)."""
        return not self.is_ldaps and (self.start_tls or bool(self.ca_file))

    @property
    def tls_mode(self) -> str:
        """ldaps · starttls · none (пароль идёт по сети открыто — только для проверки на стенде)."""
        if self.is_ldaps:
            return "ldaps"
        return "starttls" if self.use_start_tls else "none"

    def describe(self) -> dict:
        """Без секретов — для страницы администратора."""
        return {
            "url": self.url, "base_dn": self.base_dn, "bind_dn": self.bind_dn,
            "bind_password_set": bool(self.bind_password), "user_filter": self.user_filter,
            "attributes": {"id": self.attr_id, "email": self.attr_email, "name": self.attr_name,
                           "login": self.attr_login, "position": self.attr_position, "groups": self.attr_groups},
            "tls": self.tls_mode, "ca_file": self.ca_file, "timeout": self.timeout,
            "create_users": self.create_users or "no", "default_profile": self.default_profile,
            "group_profiles": [{"group": dn, "profile": key} for dn, key in self.group_profiles],
            "admin_group": self.admin_group, "hint": self.login_hint,
        }

    def profile_for(self, groups: Iterable[str], known: set[str] | None = None) -> str | None:
        """Ключ профиля по группам каталога: первое совпадение в порядке AUTH_LDAP_GROUP_PROFILES,
        иначе AUTH_LDAP_DEFAULT_PROFILE. known — существующие ключи (неизвестные пропускаются)."""
        member = {_dn_key(g) for g in groups}
        for dn, key in self.group_profiles:
            if _dn_key(dn) in member and (known is None or key in known):
                return key
        if self.default_profile and (known is None or self.default_profile in known):
            return self.default_profile
        return None

    def is_admin_member(self, groups: Iterable[str]) -> bool:
        return bool(self.admin_group) and _dn_key(self.admin_group) in {_dn_key(g) for g in groups}


@dataclass(frozen=True)
class DirectoryIdentity:
    """Запись каталога: сотрудник, чей пароль подтвердил каталог (или найденный при проверке)."""

    guid: str
    dn: str = ""
    email: str = ""
    name: str = ""
    login: str = ""
    position: str = ""
    groups: tuple[str, ...] = ()
    disabled: bool = False


# ---------------------------------------------------------------- ldap3

def _ldap3():
    try:
        import ldap3
    except ImportError as error:  # pragma: no cover - ldap3 входит в зависимости
        raise DirectoryUnavailable("Пакет ldap3 не установлен на сервере") from error
    return ldap3


def ldap3_version() -> str | None:
    try:
        import ldap3
    except ImportError:  # pragma: no cover
        return None
    return getattr(ldap3, "__version__", "") or "?"


def default_server(config: LdapConfig):
    ldap3 = _ldap3()
    tls = None
    if config.is_ldaps or config.use_start_tls:
        # Сертификат сервера проверяется всегда: своим CA-файлом или системными корневыми
        tls = ldap3.Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=config.ca_file or None)
    return ldap3.Server(config.url, get_info=ldap3.NONE, tls=tls, connect_timeout=config.timeout)


def default_connection(server, *, user: str | None, password: str | None, config: LdapConfig):
    ldap3 = _ldap3()
    return ldap3.Connection(server, user=user, password=password, read_only=True, receive_timeout=config.timeout,
                            raise_exceptions=False)


# Подменяются в тестах (ldap3 MOCK_SYNC); в работе — ldap3.Server и ldap3.Connection
server_factory: Callable[[LdapConfig], Any] = default_server
connection_factory: Callable[..., Any] = default_connection


def _text(value) -> str:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    return "" if value is None else str(value).strip()


def _texts(value) -> tuple[str, ...]:
    if value is None:
        return ()
    items = value if isinstance(value, (list, tuple)) else [value]
    return tuple(t for t in (_text(v) for v in items) if t)


def _entry_id(raw, attribute: str) -> str:
    """Идентификатор записи: objectGUID (16 байт little-endian) → строка UUID, как у синхронизации с AD."""
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else None
    if isinstance(raw, bytes) and attribute.lower() == "objectguid" and len(raw) == 16:
        return str(uuid.UUID(bytes_le=raw))
    return _text(raw).strip("{}") if attribute.lower() == "objectguid" else _text(raw)


def identity_from_entry(entry: dict, config: LdapConfig) -> DirectoryIdentity:
    attrs = {k.lower(): v for k, v in (entry.get("attributes") or {}).items()}
    raw = {k.lower(): v for k, v in (entry.get("raw_attributes") or {}).items()}
    dn = entry.get("dn") or ""
    try:
        disabled = bool(int(_text(attrs.get("useraccountcontrol")) or 0) & UAC_DISABLED)
    except ValueError:
        disabled = False
    id_key = config.attr_id.lower()
    guid = _entry_id(raw.get(id_key, attrs.get(id_key)), config.attr_id) or dn
    return DirectoryIdentity(
        guid=guid, dn=dn,
        email=_text(attrs.get(config.attr_email.lower())).lower(),
        name=_text(attrs.get(config.attr_name.lower())),
        login=_text(attrs.get(config.attr_login.lower())),
        position=_text(attrs.get(config.attr_position.lower())) if config.attr_position else "",
        groups=_texts(attrs.get(config.attr_groups.lower())) if config.attr_groups else (),
        disabled=disabled,
    )


class LdapDirectory:
    def __init__(self, config: LdapConfig, *, make_server: Callable | None = None,
                 make_connection: Callable | None = None):
        self.config = config
        self._make_server = make_server or server_factory
        self._make_connection = make_connection or connection_factory

    def _errors(self):
        _ldap3()
        from ldap3.core.exceptions import LDAPException

        return LDAPException

    def _open(self, server, user: str | None, password: str | None):
        """Соединение; для ldap:// с AUTH_LDAP_START_TLS или CA-сертификатом — StartTLS до привязки
        (пароль не идёт открытым текстом)."""
        LDAPException = self._errors()
        try:
            conn = self._make_connection(server, user=user, password=password, config=self.config)
            conn.open()
            if self.config.use_start_tls and not conn.start_tls():
                raise DirectoryUnavailable("Каталог не выполнил StartTLS")
        except LDAPException as error:
            raise DirectoryUnavailable(f"Каталог недоступен: {error.__class__.__name__}") from error
        return conn

    def _service(self, server):
        LDAPException = self._errors()
        config = self.config
        conn = self._open(server, config.bind_dn or None, config.bind_password or None)
        try:
            bound = conn.bind()
        except LDAPException as error:
            raise DirectoryUnavailable(f"Каталог недоступен: {error.__class__.__name__}") from error
        if not bound:
            _close(conn)
            raise DirectoryUnavailable("Каталог не принял служебную учётную запись (AUTH_LDAP_BIND_DN)")
        return conn

    def _attributes(self) -> list[str]:
        c = self.config
        names = (c.attr_id, c.attr_email, c.attr_name, c.attr_login, c.attr_position, c.attr_groups,
                 "userAccountControl")
        return list(dict.fromkeys(n for n in names if n))

    def _search(self, conn, login: str) -> list[dict]:
        from ldap3.utils.conv import escape_filter_chars

        LDAPException = self._errors()
        search_filter = self.config.user_filter.replace("{login}", escape_filter_chars(login.strip()))
        try:
            conn.search(self.config.base_dn, search_filter, attributes=self._attributes(), size_limit=2)
        except LDAPException as error:
            raise DirectoryUnavailable(f"Поиск в каталоге не выполнен: {error.__class__.__name__}") from error
        return [item for item in conn.response or [] if item.get("type") == "searchResEntry"]

    def find(self, login: str) -> list[dict]:
        """Записи каталога по логину (не больше двух) — служебной привязкой."""
        server = self._make_server(self.config)
        conn = self._service(server)
        try:
            return self._search(conn, login)
        finally:
            _close(conn)

    def authenticate(self, login: str, password: str) -> DirectoryIdentity | None:
        """Запись каталога, если он подтвердил пароль; None — неверный логин или пароль, логин
        неоднозначен или запись отключена. DirectoryUnavailable — каталог не отвечает."""
        # Пустой пароль многие серверы принимают как анонимную привязку — такой вход недопустим
        if not login or not login.strip() or not password:
            return None
        LDAPException = self._errors()
        server = self._make_server(self.config)
        conn = self._service(server)
        try:
            entries = self._search(conn, login)
        finally:
            _close(conn)
        if len(entries) != 1:
            return None   # нет такого сотрудника или логин неоднозначен
        entry = entries[0]
        user_conn = self._open(server, entry["dn"], password)
        try:
            bound = user_conn.bind()
        except LDAPException as error:
            raise DirectoryUnavailable(f"Каталог недоступен: {error.__class__.__name__}") from error
        finally:
            _close(user_conn)
        if not bound:
            return None
        identity = identity_from_entry(entry, self.config)
        return None if identity.disabled else identity

    def check(self, login: str | None) -> dict:
        """Проверка для администратора: подключение, служебная привязка и (если задан логин) поиск
        записи. Пароль сотрудника не проверяется никогда."""
        server = self._make_server(self.config)
        conn = self._service(server)
        try:
            entries = self._search(conn, login) if login else None
        finally:
            _close(conn)
        return {"entries": None if entries is None else [identity_from_entry(e, self.config) for e in entries]}


def _close(conn) -> None:
    with contextlib.suppress(Exception):  # соединение закрывается в любом случае
        conn.unbind()


def current_config() -> LdapConfig | None:
    return LdapConfig.from_settings()


def directory_for(config: LdapConfig) -> LdapDirectory:
    return LdapDirectory(config)


# ---------------------------------------------------------------- сопоставление и привязка

def find_account(db: Session, identity: DirectoryIdentity) -> tuple[User | None, str | None]:
    """Учётная запись системы для записи каталога: (user, how) или (None, None); how — directory ·
    ad_sync · email. Учётная запись, привязанная к другой записи каталога, не перепривязывается."""
    candidates: list[tuple[str, User | None]] = []
    if identity.guid:
        candidates.append(("directory", db.scalar(select(User).where(User.auth_external_id == identity.guid))))
        candidates.append(("ad_sync", db.scalar(select(User).where(User.org_source == "ad",
                                                                   User.external_id == identity.guid).limit(1))))
    if identity.email:
        matches = list(db.scalars(select(User).where(func.lower(User.email) == identity.email.lower())))
        exact = [u for u in matches if (u.email or "") == identity.email] or matches
        candidates.append(("email", exact[0] if len(exact) == 1 else None))
    for how, user in candidates:
        if user is None:
            continue
        if user.auth_external_id and identity.guid and user.auth_external_id != identity.guid:
            continue
        return user, how
    return None, None


def link_account(db: Session, user: User, identity: DirectoryIdentity, how: str | None,
                 request: Request | None = None) -> bool:
    """Перевести вход на каталог; True — учётная запись привязана сейчас. Данные системы не меняются:
    из каталога заполняются только пустые поля (должность), локальный пароль удаляется."""
    linked = user.auth_source != SOURCE_LDAP or user.auth_external_id != (identity.guid or None)
    if linked:
        before = {"auth_source": user.auth_source or SOURCE_LOCAL, "has_password": user.has_password}
        user.auth_source = SOURCE_LDAP
        user.auth_external_id = identity.guid or None
        user.auth_linked_at = utcnow()
        user.password_hash = None
        user.must_change_password = False
        matched = {"directory": "по записи каталога", "ad_sync": "по синхронизации с AD",
                   "email": "по e-mail"}.get(how or "", "")
        audit.record(db, user, entity_type="user", entity_id=user.id, action="link",
                     summary=f"Вход по учётной записи домена: {user.username} привязан к каталогу {matched}".strip(),
                     before=before, after={"auth_source": SOURCE_LDAP, "matched_by": how, "dn": identity.dn},
                     request=request)
        log.info("ldap login: account linked", extra={"user_id": user.id, "matched_by": how})
    elif user.password_hash:
        user.password_hash = None  # пароль доменной учётной записи в системе не хранится
    if not user.position and identity.position:
        user.position = identity.position[:200]
    return linked


def _unique_username(db: Session, base: str) -> str:
    base = re.sub(r"[^a-z0-9._-]", "", (base or "").lower())[:90] or "user"
    if len(base) < 2:
        base = f"{base}user"
    taken = {u.lower() for u in db.scalars(select(User.username).where(func.lower(User.username).like(f"{base}%")))}
    username, counter = base, 1
    while username.lower() in taken:
        counter += 1
        username = f"{base}{counter}"
    return username


def create_account(db: Session, identity: DirectoryIdentity, config: LdapConfig,
                   request: Request | None = None) -> User:
    """Учётная запись при первом входе (AUTH_LDAP_CREATE_USERS): профиль доступа — по группам каталога
    или AUTH_LDAP_DEFAULT_PROFILE; группа AUTH_LDAP_ADMIN_GROUP — роль администратора (только здесь)."""
    profiles = {p.key: p for p in db.scalars(select(AccessProfile))}
    profile_key = config.profile_for(identity.groups, set(profiles))
    for _dn, key in config.group_profiles:
        if key not in profiles:
            log.warning("AUTH_LDAP_GROUP_PROFILES: профиль доступа «%s» не найден", key)
    is_admin = config.is_admin_member(identity.groups)
    login = identity.login or identity.email.split("@")[0]
    user = User(
        username=_unique_username(db, login), full_name=(identity.name or identity.email or login)[:200],
        email=identity.email or None, position=identity.position[:200] or None,
        role="admin" if is_admin else "user", is_active=config.create_users == "active",
        auth_source=SOURCE_LDAP, auth_external_id=identity.guid or None, auth_linked_at=utcnow(),
        password_hash=None, access_profile=profiles.get(profile_key) if profile_key else None,
    )
    db.add(user)
    db.flush()
    audit.record(db, user, entity_type="user", entity_id=user.id, action="create",
                 summary=f"Создан пользователь {user.username} (первый вход по домену)",
                 after={"username": user.username, "full_name": user.full_name, "email": user.email,
                        "role": user.role, "is_active": user.is_active, "profile": profile_key,
                        "auth_source": SOURCE_LDAP, "dn": identity.dn}, request=request)
    log.info("ldap login: account created", extra={"user_id": user.id, "profile": profile_key})
    return user


@dataclass
class DirectoryLogin:
    """Итог проверки в каталоге: учётная запись (привязанная или созданная), ошибка или пусто —
    каталог пароль не подтвердил (или вход по домену выключен), и проверяется пароль системы."""

    user: User | None = None
    error: str | None = None        # no_account · directory_unavailable
    matched_by: str | None = None   # directory · ad_sync · email · created
    linked: bool = False


def authenticate(db: Session, login: str, password: str, request: Request | None = None) -> DirectoryLogin:
    """Вход по домену. Сначала сетевая проверка (без обращений к базе), затем сопоставление и
    привязка в транзакции вызывающего — фиксирует её обработчик входа."""
    config = current_config()
    if config is None:
        return DirectoryLogin()
    try:
        identity = directory_for(config).authenticate(login, password)
    except DirectoryUnavailable as error:
        log.warning("ldap login: directory unavailable: %s", error)
        return DirectoryLogin(error="directory_unavailable")
    if identity is None:
        return DirectoryLogin()
    user, how = find_account(db, identity)
    if user is None:
        if not config.create_users or not identity.email:
            return DirectoryLogin(error="no_account")
        taken = db.scalar(select(User.id).where(func.lower(User.email) == identity.email.lower()).limit(1))
        if taken is not None:
            return DirectoryLogin(error="no_account")   # email занят учётной записью другой записи каталога
        return DirectoryLogin(user=create_account(db, identity, config, request), matched_by="created", linked=True)
    return DirectoryLogin(user=user, matched_by=how, linked=link_account(db, user, identity, how, request))


# ---------------------------------------------------------------- страница администратора

def status(db: Session) -> dict:
    """Состояние входа по домену: включён ли, настроен ли, ldap3, настройки без секретов, замечания."""
    config = LdapConfig.from_settings(require_enabled=False)
    version = ldap3_version()
    problems: list[str] = []
    if settings.auth_ldap_enabled and config is None:
        problems.append("Вход по домену включён, но не заданы AUTH_LDAP_URL и AUTH_LDAP_BASE_DN")
    if version is None:  # pragma: no cover - ldap3 входит в зависимости
        problems.append("Пакет ldap3 не установлен на сервере")
    if config is not None:
        known = set(db.scalars(select(AccessProfile.key)))
        for dn, key in config.group_profiles:
            if key not in known:
                problems.append(f"AUTH_LDAP_GROUP_PROFILES: профиль «{key}» для группы «{dn}» не найден")
        if config.default_profile and config.default_profile not in known:
            problems.append(f"AUTH_LDAP_DEFAULT_PROFILE: профиль «{config.default_profile}» не найден")
        if config.ca_file and not Path(config.ca_file).is_file():
            problems.append(f"AUTH_LDAP_CA_FILE: файл {config.ca_file} не найден")
        if config.tls_mode == "none":
            problems.append("Пароли передаются без шифрования: используйте ldaps:// или AUTH_LDAP_START_TLS")
        if config.bind_dn and not config.bind_password:
            problems.append("Задан AUTH_LDAP_BIND_DN, но не задан AUTH_LDAP_BIND_PASSWORD")
        if "{login}" not in config.user_filter:
            problems.append("AUTH_LDAP_USER_FILTER не содержит {login}")
    return {"enabled": bool(settings.auth_ldap_enabled and config is not None),
            "configured": config is not None, "ldap3_available": version is not None, "ldap3_version": version,
            "config": config.describe() if config else None, "problems": problems}


def check_connection(db: Session, login: str | None) -> dict:
    """«Проверить подключение» и «Проверить вход» без сохранения: подключение, служебная привязка,
    поиск записи по логину и с какой учётной записью системы она будет сопоставлена."""
    config = LdapConfig.from_settings(require_enabled=False)
    if config is None:
        return {"ok": False, "message": "Вход по домену не настроен: задайте AUTH_LDAP_URL и AUTH_LDAP_BASE_DN",
                "login": login, "entries": None}
    try:
        result = directory_for(config).check((login or "").strip() or None)
    except DirectoryUnavailable as error:
        return {"ok": False, "message": str(error), "login": login, "entries": None}
    entries = result["entries"]
    if entries is None:
        return {"ok": True, "message": "Подключение установлено, служебная учётная запись принята",
                "login": None, "entries": None}
    known = set(db.scalars(select(AccessProfile.key)))
    out = []
    for identity in entries:
        user, how = find_account(db, identity)
        would_create = user is None and bool(config.create_users) and bool(identity.email)
        out.append({
            "dn": identity.dn, "guid": identity.guid, "login": identity.login, "email": identity.email,
            "name": identity.name, "position": identity.position, "groups": list(identity.groups),
            "disabled": identity.disabled,
            "account": None if user is None else {"id": user.id, "username": user.username,
                                                  "full_name": user.full_name, "matched_by": how,
                                                  "auth_source": user.auth_source, "is_active": user.is_active},
            "would_create": would_create,
            "profile": config.profile_for(identity.groups, known) if would_create else None,
            "admin": config.is_admin_member(identity.groups) if would_create else False,
        })
    if not out:
        message = "Запись с таким логином в каталоге не найдена"
    elif len(out) > 1:
        message = "Логину соответствует несколько записей каталога — вход будет отклонён; уточните фильтр"
    elif out[0]["disabled"]:
        message = "Запись найдена, но отключена в каталоге — вход будет отклонён"
    elif out[0]["account"] is not None:
        message = f"Запись найдена и сопоставлена с пользователем {out[0]['account']['username']}"
    elif out[0]["would_create"]:
        message = "Запись найдена; учётная запись будет создана при первом входе"
    else:
        message = "Запись найдена, но учётной записи в системе нет — вход будет отклонён"
    return {"ok": True, "message": message, "login": login, "entries": out}
