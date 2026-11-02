"""Интеграции: подключения (создание, изменение с правилами секретов, удаление, проверка) и ключи для
входящих вызовов (ADR-0011). Функции не фиксируют транзакцию — commit в обработчике запроса.

Секреты подключения:
- поля коннектора с secret=True шифруются вместе (app/core/secrets.py) и привязываются к адресу
  (Connector.secret_url: по умолчанию поле url_field; у коннектора с несколькими адресами — их сочетание,
  поля перечислены в secret_url_fields); в ответах — has_secret, secret_fields (какие заданы) и secret_problem;
- пустое значение секрета при сохранении оставляет сохранённое, только если адрес не изменился;
  адрес изменён — секреты нужно ввести заново («Адрес … изменён — введите токен или пароль заново»);
- clear_secrets — список полей, которые нужно стереть.

Включить подключение можно только после успешной проверки текущих настроек (409 check_required);
изменение настроек или секретов снимает отметку проверки.

Вид с Connector.admin_only (Confluence публикует полный сквозной отчёт) создаёт, изменяет (включение, настройки,
расписание), проверяет, запускает и удаляет только администратор (403 admin_only); остальные с integrations.manage
видят подключение только для чтения (can_manage: false, connector.admin_only_note).

Ключи: dash_ + token_urlsafe(32), показываются один раз; хранятся SHA-256 и префикс (12 символов);
сравнение — compare_digest; «выпустить заново» заменяет секрет того же ключа; «отозвать» — revoked_at
(ключ перестаёт работать сразу, запись остаётся для журнала и ссылок элементов входящих);
last_used_at обновляется не чаще раза в минуту. Частота вызовов (INBOUND_RATE_LIMIT в минуту на ключ) считается
в базе — общая для всех процессов: окно (rate_window_start) и счётчик (rate_count) ключа меняются одним атомарным
UPDATE … RETURNING (hit_rate_limit).
"""
from __future__ import annotations

import hashlib
import math
import secrets as pysecrets
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy import case, func, or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.db import utcnow
from ..core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from ..core.secrets import SecretError, normalize_url, problem, rebind_message, seal, unseal
from ..core.security import constant_time_equals
from ..integrations import base, runner
from ..integrations.base import Connector
from ..models import KEY_SCOPES, InboundKey, InboxItem, Integration, IntegrationRun, User
from . import audit
from .registry import INBOUND_SCOPE_HINTS, INBOUND_SCOPE_LABELS

KEY_PREFIX = "dash_"
KEY_PREFIX_LENGTH = 12
LAST_USED_EVERY = timedelta(minutes=1)
RATE_WINDOW = timedelta(minutes=1)


# ---------------------------------------------------------------- подключения

def kinds() -> list[dict]:
    """Виды подключений в порядке Connector.order."""
    return [c.meta() for c in base.all_connectors()]


def can_manage(user: User | None, cls: type[Connector] | None) -> bool:
    """Изменять, проверять, запускать и удалять подключение вида: вид admin_only — только администратор."""
    return user is None or cls is None or not cls.admin_only or user.is_admin


def require_manage(user: User | None, cls: type[Connector]) -> None:
    if not can_manage(user, cls):
        raise Forbidden(f"{cls.admin_only_note()} — подключение «{cls.title}» настраивает и запускает только "
                        "администратор", code="admin_only")


def get(db: Session, integration_id: int) -> Integration:
    row = db.get(Integration, integration_id)
    if row is None:
        raise NotFound("Подключение не найдено")
    return row


def _secret_fields(row: Integration) -> list[str]:
    return sorted(_current_secrets(row))


def integration_out(db: Session, row: Integration, user: User | None = None) -> dict:
    """Подключение для API. schedule — записи расписания с подписью и следующим запуском каждой; next_run_at —
    ближайший; running — идёт запуск (прерванный, старше RUNNING_TIMEOUT, — нет); current_error — последняя ошибка,
    если она новее последнего успеха (иначе пусто: старая ошибка — только в журнале запусков); can_manage — user
    может изменять, проверять и запускать подключение (вид admin_only — только администратор)."""
    cls = base.find(row.kind)
    now = utcnow()
    last = db.scalar(select(IntegrationRun).where(IntegrationRun.integration_id == row.id)
                     .order_by(IntegrationRun.started_at.desc(), IntegrationRun.id.desc()).limit(1))
    secret_problem = problem(runner.PURPOSE, row.secret_encrypted, row.secret_bound_url,
                             runner.url_of(cls, row.config) if cls else "", owner=runner.owner(row.id)) \
        if cls else None
    running = runner.is_running(row, now)
    return {
        "id": row.id, "kind": row.kind, "name": row.name, "enabled": row.enabled,
        "config": cls.stored_config(row.config) if cls else (row.config or {}),
        "has_secret": bool(row.secret_encrypted), "secret_fields": _secret_fields(row),
        "secret_bound_url": row.secret_bound_url or None, "secret_problem": secret_problem,
        "schedule": runner.schedule_out(row), "schedule_label": runner.schedule_label(row.schedule, cls),
        "next_run_at": row.next_run_at if row.enabled else None, "running": running,
        "running_since": row.running_since if running else None,
        "verified_at": row.verified_at, "last_run_at": row.last_run_at, "last_ok_at": row.last_ok_at,
        "last_error_at": row.last_error_at, "last_error": row.last_error or "",
        "current_error": runner.current_error(row),
        "health": _health(row), "last_run": runner.run_out(last, now) if last else None,
        "created_at": row.created_at, "updated_at": row.updated_at,
        "can_manage": can_manage(user, cls),
        "connector": cls.meta() if cls else None,
    }


def _health(row: Integration) -> str:
    """ok · error · unknown · disabled — для значка на карточке: «ошибка» — только если последняя ошибка новее
    последнего успеха (runner.current_error)."""
    if not row.enabled:
        return "disabled"
    if row.last_error_at and (row.last_ok_at is None or row.last_error_at > row.last_ok_at):
        return "error"
    return "ok" if row.last_ok_at else "unknown"


def list_out(db: Session, user: User | None = None) -> list[dict]:
    """Подключения в порядке видов (Connector.order), внутри вида — по названию."""
    rows = list(db.scalars(select(Integration)))
    order = {c.kind: base.sort_key(c) for c in base.all_connectors(include_hidden=True)}
    rows.sort(key=lambda r: (order.get(r.kind, (10**6, r.kind)), r.name.casefold()))
    return [integration_out(db, r, user) for r in rows]


def _check_name(db: Session, name: str, exclude: int | None = None) -> str:
    name = " ".join((name or "").split())
    if not name:
        raise ValidationFailed("Укажите название", fields={"name": "Обязательное поле"})
    stmt = select(Integration.id).where(func.lower(Integration.name) == name.lower())
    if exclude:
        stmt = stmt.where(Integration.id != exclude)
    if db.scalar(stmt):
        raise Conflict("Подключение с таким названием уже есть", fields={"name": "Название занято"})
    return name[:200]


def _stored_config(cls: type[Connector], row: Integration) -> dict:
    """Сохранённые настройки в нынешнем виде (Connector.stored_config: поле, появившееся позже, — со значением,
    сохраняющим прежнее поведение) без полей, которых у коннектора больше нет (переименованы или убраны в новой
    версии): иначе их не удалось бы сохранить заново («Неизвестная настройка»)."""
    known = cls.config_keys()
    return {k: v for k, v in cls.stored_config(row.config).items() if k in known}


def _snapshot(row: Integration) -> dict:
    return {"name": row.name, "enabled": row.enabled, "config": row.config, "schedule": row.schedule,
            "has_secret": bool(row.secret_encrypted)}


def _seal(row: Integration, cls: type[Connector], values: dict[str, str]) -> None:
    if values:
        row.secret_encrypted, row.secret_bound_url = seal(runner.PURPOSE, values, runner.url_of(cls, row.config),
                                                          owner=runner.owner(row.id))
    else:
        row.secret_encrypted = row.secret_bound_url = None


def create(db: Session, actor: User, body: dict, request: Request | None = None) -> Integration:
    cls = base.get(body.get("kind") or "")
    if cls.hidden and not body.get("_allow_hidden"):
        raise ValidationFailed(f"Неизвестный вид подключения: {cls.kind}", fields={"kind": "Нет такого"})
    require_manage(actor, cls)
    if cls.singleton and db.scalar(select(Integration.id).where(Integration.kind == cls.kind)):
        raise Conflict(f"Подключение «{cls.title}» уже есть — оно может быть только одно", code="singleton")
    config = cls.validate_config(body.get("config") or {})
    values = cls.validate_secrets(body.get("secrets") or {})
    missing = cls.missing_secrets(config, values)
    if missing:
        raise ValidationFailed(f"Обязательное поле: {missing[0].label}",
                               fields={f"secrets.{missing[0].key}": "Обязательное поле"})
    if body.get("enabled"):
        raise Conflict("Сначала проверьте подключение: включить можно после успешной проверки", code="check_required")
    row = Integration(kind=cls.kind, name=_check_name(db, body.get("name") or cls.title), enabled=False,
                      config=config, schedule=runner.normalize_schedule(cls, body.get("schedule")), state={},
                      last_error="", created_by_id=actor.id, updated_by_id=actor.id)
    db.add(row)
    db.flush()
    _seal(row, cls, values)
    db.flush()
    audit.record(db, actor, entity_type="integration", entity_id=row.id, action="create",
                 summary=f"Создано подключение «{row.name}» ({cls.title})", after=_snapshot(row), request=request)
    return row


def update(db: Session, actor: User, row: Integration, body: dict, request: Request | None = None) -> Integration:
    cls = base.get(row.kind)
    require_manage(actor, cls)
    before = _snapshot(row)
    changed_settings = False
    if "name" in body and body["name"] is not None:
        row.name = _check_name(db, body["name"], row.id)
    if body.get("config") is not None:
        config = cls.validate_config({**_stored_config(cls, row), **body["config"]})
        if config != row.config:
            row.config, changed_settings = config, True
    new_url = runner.url_of(cls, row.config)
    incoming = cls.validate_secrets(body.get("secrets") or {})
    clear = set(body.get("clear_secrets") or [])
    unknown = clear - {f.key for f in cls.secret_fields()}
    if unknown:
        raise ValidationFailed(f"Неизвестный секрет: {sorted(unknown)[0]}", fields={"clear_secrets": "Нет такого"})
    current = _current_secrets(row)
    url_changed = bool(row.secret_encrypted) and normalize_url(new_url) != normalize_url(row.secret_bound_url)
    if url_changed:
        # Сохранённый секрет не уходит на новый адрес: его нужно ввести заново
        if not incoming and set(current) - clear:
            raise ValidationFailed(rebind_message(row.secret_bound_url, new_url), code="secret_rebind_required",
                                   fields={"secrets": "Введите заново"})
        current = {}
    if incoming or clear or url_changed:
        values = {k: v for k, v in {**current, **incoming}.items() if k not in clear}
        missing = cls.missing_secrets(row.config, values)
        if missing:
            raise ValidationFailed(f"Обязательное поле: {missing[0].label}",
                                   fields={f"secrets.{missing[0].key}": "Обязательное поле"})
        _seal(row, cls, values)
        changed_settings = True
    if changed_settings:
        row.verified_at = None
    if body.get("schedule") is not None:
        row.schedule = runner.normalize_schedule(cls, body["schedule"])
        runner.reschedule(row)
    if body.get("enabled") is not None and body["enabled"] != row.enabled:
        if body["enabled"] and row.verified_at is None:
            raise Conflict("Сначала проверьте подключение: включить можно после успешной проверки текущих "
                           "настроек", code="check_required")
        row.enabled = bool(body["enabled"])
        runner.reschedule(row)
    row.updated_by_id = actor.id
    row.updated_at = utcnow()
    db.flush()
    b, a = audit.diff(before, _snapshot(row))
    secrets_changed = bool(incoming or clear)
    if a or secrets_changed:
        audit.record(db, actor, entity_type="integration", entity_id=row.id, action="update",
                     summary=f"Изменено подключение «{row.name}»" + (" (секреты)" if secrets_changed else ""),
                     before=b, after={**a, **({"secrets": sorted(incoming) + [f"-{k}" for k in sorted(clear)]}
                                              if secrets_changed else {})}, request=request)
    return row


def _current_secrets(row: Integration) -> dict[str, str]:
    """Сохранённые секреты (расшифрованные для адреса, к которому привязаны); не читаются — пусто."""
    if not row.secret_encrypted:
        return {}
    try:
        return unseal(runner.PURPOSE, row.secret_encrypted, row.secret_bound_url, row.secret_bound_url,
                      owner=runner.owner(row.id))
    except SecretError:
        return {}


def delete(db: Session, actor: User, row: Integration, request: Request | None = None) -> None:
    cls = base.find(row.kind)
    if cls is not None:
        require_manage(actor, cls)
    if runner.is_running(row):
        raise Conflict("Подключение выполняет запуск — удалите его после окончания", code="run_in_progress")
    audit.record(db, actor, entity_type="integration", entity_id=row.id, action="delete",
                 summary=f"Удалено подключение «{row.name}»", before=_snapshot(row), request=request)
    db.delete(row)
    db.flush()


def check(db: Session, actor: User, row: Integration, body: dict | None = None,
          request: Request | None = None) -> dict:
    """Проверка подключения. body {config, secrets} — проверить несохранённые значения (секреты, не
    введённые заново, берутся сохранённые — только если адрес тот же)."""
    cls = base.get(row.kind)
    require_manage(actor, cls)
    body = body or {}
    draft = bool(body.get("config") is not None or body.get("secrets"))
    config = secrets = None
    if draft:
        config = cls.validate_config({**_stored_config(cls, row), **(body.get("config") or {})})
        incoming = cls.validate_secrets(body.get("secrets") or {})
        same_url = normalize_url(runner.url_of(cls, config)) == normalize_url(row.secret_bound_url)
        secrets = {**(_current_secrets(row) if same_url else {}), **incoming}
        draft = config != _stored_config(cls, row) or bool(incoming)
    result = runner.check(row, detailed=True, config=config if draft else None, secrets=secrets if draft else None)
    now = utcnow()
    if not draft:
        from ..integrations.http import record_health

        record_health(row, ok=result.ok, error=result.message, now=now)
        row.verified_at = now if result.ok else None
    audit.record(db, actor, entity_type="integration", entity_id=row.id, action="check",
                 summary=f"Проверка подключения «{row.name}»: "
                         + ("ошибка" if not result.ok else "успешно, с замечаниями" if result.warnings else "успешно")
                         + (" (несохранённые настройки)" if draft else ""),
                 after={"ok": result.ok, "message": result.message[:300],
                        **({"warnings": [w[:300] for w in result.warnings[:10]]} if result.warnings else {})},
                 request=request)
    db.flush()
    return {**result.as_dict(), "checked_at": now, "draft": draft}


def check_draft(kind: str, config: dict, secrets: dict, user: User | None = None) -> dict:
    """Проверка ещё не созданного подключения."""
    cls = base.get(kind)
    require_manage(user, cls)
    row = Integration(id=None, kind=cls.kind, name=cls.title, config=cls.validate_config(config or {}))
    result = runner.check(row, detailed=True, config=row.config, secrets=cls.validate_secrets(secrets or {}))
    return {**result.as_dict(), "checked_at": utcnow(), "draft": True}


def run(user: User, row: Integration, action: str) -> dict:
    """Ручной запуск действия (синхронно, в процессе приложения): вид admin_only — только администратор."""
    require_manage(user, base.get(row.kind))
    return runner.run_action(row.id, action, trigger="manual", user=user)


def runs(db: Session, row: Integration, limit: int = 50) -> list[dict]:
    now = utcnow()
    return [runner.run_out(r, now) for r in db.scalars(
        select(IntegrationRun).where(IntegrationRun.integration_id == row.id)
        .order_by(IntegrationRun.started_at.desc(), IntegrationRun.id.desc()).limit(limit))]


# ---------------------------------------------------------------- ключи для входящих вызовов

def key_scopes() -> list[dict]:
    """Области ключа с подписями и подсказками — подписи интерфейс берёт отсюда (registry.INBOUND_SCOPE_LABELS)."""
    return [{"value": s, "label": INBOUND_SCOPE_LABELS.get(s, s), "hint": INBOUND_SCOPE_HINTS.get(s, "")}
            for s in KEY_SCOPES]


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return KEY_PREFIX + pysecrets.token_urlsafe(32)


def _scopes(values: list[str] | None) -> list[str]:
    values = list(dict.fromkeys(values or ["files"]))
    unknown = sorted(set(values) - set(KEY_SCOPES))
    if unknown or not values:
        raise ValidationFailed(f"Область ключа: {', '.join(KEY_SCOPES)}", fields={"scopes": "Недопустимо"})
    return values


def key_out(db: Session, row: InboundKey) -> dict:
    received = db.scalar(select(func.count()).select_from(InboxItem).where(InboxItem.inbound_key_id == row.id)) or 0
    return {"id": row.id, "name": row.name, "prefix": row.prefix, "scopes": row.scopes or [],
            "scope_labels": [INBOUND_SCOPE_LABELS.get(s, s) for s in row.scopes or []],
            "issued_at": row.issued_at, "issued_by": row.issued_by, "last_used_at": row.last_used_at,
            "revoked_at": row.revoked_at, "active": row.revoked_at is None, "items_received": received,
            # Частота вызовов ключа: не больше стольких запросов в минуту (INBOUND_RATE_LIMIT)
            "rate_limit": settings.inbound_rate_limit}


def keys_out(db: Session) -> list[dict]:
    return [key_out(db, k) for k in db.scalars(select(InboundKey).order_by(InboundKey.revoked_at.is_not(None),
                                                                          InboundKey.name))]


def get_key(db: Session, key_id: int) -> InboundKey:
    row = db.get(InboundKey, key_id)
    if row is None:
        raise NotFound("Ключ не найден")
    return row


def issue_key(db: Session, actor: User, name: str, scopes: list[str] | None,
              request: Request | None = None) -> tuple[InboundKey, str]:
    name = " ".join((name or "").split())[:120]
    if not name:
        raise ValidationFailed("Укажите название ключа (например, «1С: ЗУП»)", fields={"name": "Обязательное поле"})
    token = _new_token()
    row = InboundKey(name=name, sha256=_digest(token), prefix=token[:KEY_PREFIX_LENGTH], scopes=_scopes(scopes),
                     issued_at=utcnow(), issued_by_id=actor.id, issued_by=actor.username)
    db.add(row)
    db.flush()
    audit.record(db, actor, entity_type="inbound_key", entity_id=row.id, action="create",
                 summary=f"Выпущен ключ «{row.name}» ({row.prefix}…)", after={"scopes": row.scopes,
                                                                              "prefix": row.prefix},
                 request=request)
    return row, token


def reissue_key(db: Session, actor: User, row: InboundKey, request: Request | None = None) -> str:
    if row.revoked_at is not None:
        raise Conflict("Ключ отозван — выпустите новый", code="key_revoked")
    token = _new_token()
    old = row.prefix
    row.sha256, row.prefix, row.issued_at = _digest(token), token[:KEY_PREFIX_LENGTH], utcnow()
    row.issued_by_id, row.issued_by, row.last_used_at = actor.id, actor.username, None
    db.flush()
    audit.record(db, actor, entity_type="inbound_key", entity_id=row.id, action="reissue",
                 summary=f"Ключ «{row.name}» выпущен заново: {old}… больше не работает",
                 before={"prefix": old}, after={"prefix": row.prefix}, request=request)
    return token


def revoke_key(db: Session, actor: User, row: InboundKey, request: Request | None = None) -> None:
    if row.revoked_at is not None:
        return
    row.revoked_at = utcnow()
    db.flush()
    audit.record(db, actor, entity_type="inbound_key", entity_id=row.id, action="revoke",
                 summary=f"Отозван ключ «{row.name}» ({row.prefix}…)", request=request)


def authenticate(db: Session, token: str) -> InboundKey | None:
    """Действующий ключ по значению из заголовка Authorization: Bearer dash_…"""
    token = (token or "").strip()
    if not token.startswith(KEY_PREFIX) or len(token) > 200:
        return None
    digest = _digest(token)
    row = db.scalar(select(InboundKey).where(InboundKey.sha256 == digest))
    if row is None or not constant_time_equals(row.sha256, digest) or row.revoked_at is not None:
        return None
    now = utcnow()
    if row.last_used_at is None or now - row.last_used_at >= LAST_USED_EVERY:
        row.last_used_at = now
        db.flush()
    return row


def hit_rate_limit(db: Session, key: InboundKey, limit: int | None = None, now: datetime | None = None) -> int:
    """Учесть вызов ключа и вернуть, сколько секунд ждать (0 — вызов разрешён). Окно — минута с первого вызова
    окна: одним UPDATE начало окна сбрасывается (окно истекло) или счётчик растёт, RETURNING отдаёт итог — счёт общий
    для всех процессов приложения (gunicorn); гонки нет: на PostgreSQL второй вызов ждёт блокировку строки ключа, на
    SQLite записи идут по очереди. Без RETURNING (SQLite до 3.35) итог читается тем же соединением в той же
    транзакции — строка уже занята этим UPDATE. Транзакцию фиксирует вызывающий — сразу: держится блокировка
    строки ключа."""
    limit = settings.inbound_rate_limit if limit is None else limit
    now = now or utcnow()
    fresh = or_(InboundKey.rate_window_start.is_(None), InboundKey.rate_window_start <= now - RATE_WINDOW)
    stmt = (sql_update(InboundKey).where(InboundKey.id == key.id)
            .values(rate_window_start=case((fresh, now), else_=InboundKey.rate_window_start),
                    rate_count=case((fresh, 1), else_=InboundKey.rate_count + 1))
            .execution_options(synchronize_session=False))
    if db.get_bind().dialect.update_returning:
        start, count = db.execute(stmt.returning(InboundKey.rate_window_start, InboundKey.rate_count)).one()
    else:
        db.execute(stmt)
        start, count = db.execute(select(InboundKey.rate_window_start, InboundKey.rate_count)
                                  .where(InboundKey.id == key.id)).one()
    if count <= limit:
        return 0
    return max(1, math.ceil((start + RATE_WINDOW - now).total_seconds()))
