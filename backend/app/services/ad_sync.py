"""Синхронизация структуры и сотрудников с Active Directory (ADR-0008).

Читает пользователей каталога (ldap3, постраничный поиск) и превращает их в строки общего
планировщика app/services/org_import.py: внешний ключ — objectGUID, путь подразделения — из
атрибутов (по умолчанию company, division, department) или из OU в DN, руководитель — из атрибута
manager (DN), отключённые — по userAccountControl & 2. Руководители подразделений определяются
по подчинённым: у кого есть подчинённые в том же подразделении, а сам он подчиняется вне его.

Настройки — переменные AD_SYNC_*; пустые адрес, база поиска, служебная учётная запись,
CA-сертификат и StartTLS берутся из AUTH_LDAP_* (вход по домену). Секреты в API не попадают.
Для ldap:// с AD_SYNC_START_TLS или с CA-сертификатом соединение переводится на StartTLS
до привязки (в todo-planner сертификат при ldap:// не использовался).
"""
from __future__ import annotations

import contextlib
import re
import uuid
from dataclasses import dataclass, field

from ..core.config import Settings, settings
from ..core.errors import AppError
from .org_import import Row

ATTRIBUTES = ("objectGUID", "mail", "displayName", "cn", "sAMAccountName", "title", "manager",
              "userAccountControl", "distinguishedName")
UAC_DISABLED = 0x2
PAGE_SIZE = 500


class AdSyncError(AppError):
    """ldap3 не установлен или каталог недоступен."""

    status_code = 503
    code = "ad_unavailable"


class AdNotConfigured(AppError):
    status_code = 409
    code = "ad_not_configured"


@dataclass(frozen=True)
class AdConfig:
    url: str
    base_dn: str
    bind_dn: str = ""
    bind_password: str = field(default="", repr=False)
    user_filter: str = "(&(objectCategory=person)(objectClass=user)(mail=*))"
    path_source: str = "attributes"
    path_attributes: tuple[str, ...] = ("company", "division", "department")
    detect_heads: bool = True
    ca_file: str = ""
    start_tls: bool = False
    timeout: int = 5

    @classmethod
    def from_settings(cls, s: Settings | None = None) -> AdConfig | None:
        s = s or settings
        own_url = bool(s.ad_sync_url.strip())
        url = (s.ad_sync_url or s.auth_ldap_url).strip()
        base_dn = (s.ad_sync_base_dn or s.auth_ldap_base_dn).strip()
        if not url or not base_dn:
            return None
        # Служебная учётная запись — парой: своя для синхронизации или та же, что у входа
        if s.ad_sync_bind_dn.strip():
            bind_dn, password = s.ad_sync_bind_dn.strip(), s.ad_sync_bind_password
        else:
            bind_dn, password = s.auth_ldap_bind_dn.strip(), s.auth_ldap_bind_password
        attributes = tuple(a.strip() for a in s.ad_sync_path_attributes.split(",") if a.strip())
        return cls(
            url=url, base_dn=base_dn, bind_dn=bind_dn, bind_password=password,
            user_filter=s.ad_sync_user_filter or cls.user_filter, path_source=s.ad_sync_path_source,
            path_attributes=attributes or ("company", "division", "department"),
            detect_heads=s.ad_sync_detect_heads, ca_file=(s.ad_sync_ca_file or s.auth_ldap_ca_file).strip(),
            start_tls=s.ad_sync_start_tls or (not own_url and s.auth_ldap_start_tls),
            timeout=s.auth_ldap_timeout,
        )

    @property
    def is_ldaps(self) -> bool:
        return self.url.lower().startswith("ldaps://")

    @property
    def use_start_tls(self) -> bool:
        """StartTLS — для ldap:// по настройке или когда задан CA-сертификат."""
        return not self.is_ldaps and (self.start_tls or bool(self.ca_file))

    def describe(self) -> dict:
        """Без секретов — для страницы настроек."""
        return {"url": self.url, "base_dn": self.base_dn, "path_source": self.path_source,
                "path_attributes": list(self.path_attributes), "detect_heads": self.detect_heads,
                "start_tls": self.use_start_tls, "user_filter": self.user_filter}


def ldap3_available() -> bool:
    try:
        import ldap3  # noqa: F401
    except ImportError:  # pragma: no cover - ldap3 в зависимостях сервера
        return False
    return True


def status() -> dict:
    config = AdConfig.from_settings()
    return {"configured": config is not None, "ldap3_available": ldap3_available(),
            "config": config.describe() if config else None}


# ---------------------------------------------------------------- чтение каталога

def connection_options(config: AdConfig) -> dict:
    """Параметры ldap3.Server и ldap3.Connection: TLS для ldaps:// и StartTLS для ldap://."""
    import ssl

    import ldap3

    tls = None
    if config.is_ldaps or config.use_start_tls:
        tls = ldap3.Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=config.ca_file or None)
    auto_bind = ldap3.AUTO_BIND_TLS_BEFORE_BIND if config.use_start_tls else ldap3.AUTO_BIND_NO_TLS
    return {"tls": tls, "auto_bind": auto_bind}


def connect(config: AdConfig):
    try:
        import ldap3
    except ImportError as exc:  # pragma: no cover - ldap3 в зависимостях сервера
        raise AdSyncError("Пакет ldap3 не установлен на сервере") from exc
    try:
        options = connection_options(config)
    except ldap3.core.exceptions.LDAPSSLConfigurationError as exc:
        raise AdSyncError(f"CA-сертификат каталога не найден или повреждён: {config.ca_file}") from exc
    try:
        server = ldap3.Server(config.url, get_info=ldap3.NONE, tls=options["tls"], connect_timeout=config.timeout)
        return ldap3.Connection(server, user=config.bind_dn or None, password=config.bind_password or None,
                                auto_bind=options["auto_bind"], receive_timeout=max(30, config.timeout),
                                read_only=True, raise_exceptions=False)
    except Exception as exc:  # noqa: BLE001 — ldap3 бросает разные исключения подключения и привязки
        raise AdSyncError(f"Не удалось подключиться к каталогу ({exc.__class__.__name__}): проверьте адрес, "
                          "сертификат и служебную учётную запись AD_SYNC_*") from exc


def fetch_entries(config: AdConfig, connection=None) -> list[dict]:
    """Записи пользователей: [{"dn", "attributes", "raw_attributes"}]. connection — готовое соединение
    (в тестах — ldap3 MOCK_SYNC); без него соединение открывается по настройкам."""
    conn = connection if connection is not None else connect(config)
    attributes = list(dict.fromkeys((*ATTRIBUTES, *(config.path_attributes if config.path_source == "attributes"
                                                    else ()))))
    try:
        entries = []
        for item in conn.extend.standard.paged_search(config.base_dn, config.user_filter, attributes=attributes,
                                                      paged_size=PAGE_SIZE, generator=True):
            if item.get("type") == "searchResEntry":
                entries.append({"dn": item.get("dn", ""), "attributes": dict(item.get("attributes") or {}),
                                "raw_attributes": dict(item.get("raw_attributes") or {})})
        return entries
    except Exception as exc:  # noqa: BLE001
        raise AdSyncError(f"Каталог не ответил на поиск ({exc.__class__.__name__}): проверьте AD_SYNC_BASE_DN "
                          "и AD_SYNC_USER_FILTER") from exc
    finally:
        with contextlib.suppress(Exception):   # соединение и так закрывается
            conn.unbind()


# ---------------------------------------------------------------- преобразование

def first(value) -> str:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    if isinstance(value, bytes):
        if len(value) == 16:
            return str(uuid.UUID(bytes_le=value))
        return value.decode("utf-8", "ignore").strip()
    if isinstance(value, uuid.UUID):
        return str(value)
    return "" if value is None else str(value).strip()


def guid(entry: dict, attrs: dict) -> str:
    """objectGUID: двоичное значение из raw_attributes (надёжнее), иначе строка «{…}»."""
    raw = {k.lower(): v for k, v in (entry.get("raw_attributes") or {}).items()}.get("objectguid")
    if isinstance(raw, (list, tuple)) and raw and isinstance(raw[0], bytes) and len(raw[0]) == 16:
        return str(uuid.UUID(bytes_le=raw[0]))
    text = first(attrs.get("objectguid")).strip("{}").lower()
    return text


_HEX = re.compile(r"^[0-9A-Fa-f]{2}$")


def split_dn(dn: str) -> list[str]:
    """DN → компоненты с учётом экранирования («\\,» и «\\2C», в том числе UTF-8 байтами)."""
    parts: list[str] = []
    current = bytearray()
    i, text = 0, dn or ""
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            pair = text[i + 1:i + 3]
            if _HEX.match(pair):
                current.append(int(pair, 16))
                i += 3
                continue
            current.extend(text[i + 1].encode())
            i += 2
            continue
        if char == ",":
            parts.append(current.decode("utf-8", "replace").strip())
            current = bytearray()
        else:
            current.extend(char.encode())
        i += 1
    if current.decode("utf-8", "replace").strip():
        parts.append(current.decode("utf-8", "replace").strip())
    return parts


def path_from_ou(dn: str, base_dn: str) -> list[str]:
    base = [p.lower() for p in split_dn(base_dn)]
    parts = split_dn(dn)[1:]   # без CN самого пользователя
    if base and [p.lower() for p in parts[-len(base):]] == base:
        parts = parts[:len(parts) - len(base)]
    names = [p.split("=", 1)[1].strip() for p in parts if p.lower().startswith("ou=") and "=" in p]
    return list(reversed(names))


def uac_disabled(value) -> bool:
    try:
        return bool(int(first(value) or 0) & UAC_DISABLED)
    except ValueError:
        return False


def entries_to_rows(entries: list[dict], config: AdConfig) -> tuple[list[Row], dict[str, str]]:
    """Записи каталога → (строки импорта, DN руководителя → objectGUID)."""
    rows: list[Row] = []
    refs: dict[str, str] = {}
    for index, entry in enumerate(entries, start=1):
        attrs = {k.lower(): v for k, v in (entry.get("attributes") or {}).items()}
        dn = entry.get("dn") or first(attrs.get("distinguishedname"))
        ident = guid(entry, attrs) or dn.lower()
        refs[dn.lower()] = ident
        if config.path_source == "ou":
            path = path_from_ou(dn, config.base_dn)
        else:
            path = [first(attrs.get(name.lower())) for name in config.path_attributes]
        rows.append(Row(
            line=index, email=first(attrs.get("mail")).lower(),
            name=" ".join((first(attrs.get("displayname")) or first(attrs.get("cn"))).split()),
            login=first(attrs.get("samaccountname")),
            department=[" ".join(p.split())[:200] for p in path if p and p.strip()],
            position=first(attrs.get("title")) or None, manager_ref=first(attrs.get("manager")).lower(),
            external_id=ident, disabled=uac_disabled(attrs.get("useraccountcontrol")),
        ))
    if config.detect_heads:
        mark_heads(rows, refs)
    return rows, refs


def mark_heads(rows: list[Row], refs: dict[str, str]) -> None:
    """Руководитель подразделения — у кого есть подчинённые в том же подразделении, а его
    собственный руководитель — вне этого подразделения (или его нет)."""
    by_id = {row.external_id: row for row in rows}

    def manager_of(row: Row) -> Row | None:
        return by_id.get(refs.get(row.manager_ref, "")) if row.manager_ref else None

    local_reports: set[str] = set()
    for row in rows:
        manager = manager_of(row)
        if manager is not None and manager is not row and manager.department == row.department and row.department:
            local_reports.add(manager.external_id)
    for row in rows:
        manager = manager_of(row)
        outside = manager is None or manager.department != row.department
        if row.external_id in local_reports and outside and not row.disabled and row.department:
            row.is_head = True


def load_rows(config: AdConfig | None = None, entries: list[dict] | None = None) -> tuple[list[Row], dict]:
    config = config or AdConfig.from_settings()
    if config is None:
        raise AdNotConfigured("Синхронизация с AD не настроена: задайте AD_SYNC_URL и AD_SYNC_BASE_DN "
                              "(или адрес и базу поиска входа по домену AUTH_LDAP_*)")
    if entries is None:
        entries = fetch_entries(config)
    return entries_to_rows(entries, config)
