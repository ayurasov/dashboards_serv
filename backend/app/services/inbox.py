"""Входящие данные — единый конвейер (ADR-0011).

Любой файл, откуда бы он ни пришёл (папка «Входящие», загрузка в интерфейсе, приём по API, коннектор),
становится элементом входящих (inbox_items) и проходит один путь:

1. add — получение: размер, SHA-256, распознавание набора (подпапка, имя, содержимое — inbox_datasets),
   повтор (тот же набор и SHA-256 у «живого» элемента) → статус «повтор», файл не применяется;
2. план — тот же движок, что у ручной загрузки набора, без записи в базу (статус «ожидает»);
3. применение — сразу, если план без ошибок и для источника и набора включено «применять сразу»
   (inbox_rules) или загрузивший попросил применить; иначе — по кнопке на экране «Входящие» (apply).
   Применение — в точке сохранения транзакции: при ошибке движка ничего не записывается;
4. итог — статус, план и результат хранятся; исходный файл — до срока INBOX_RETENTION_DAYS (purge).

От чьего имени работают движки (engine_actor): источник (папка, ключ, подключение) — «источник данных»
со всеми службами и классами данных, полномочиями org.manage и reports.manage, без роли администратора
и без users.manage (роли и профили доступа из файлов не применяются); пользователь с data.manage —
так же, но в журнале — он сам; остальные (редакторы служб, ведущие структуру) — со своими правами.

Функции не фиксируют транзакцию: commit — у вызывающего (обработчик запроса, папка, коннектор).
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import timedelta

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.db import utcnow
from ..core.errors import AppError, Conflict, Forbidden, NotFound, ValidationFailed
from ..models import INBOX_LIVE_STATUSES, INBOX_SOURCES, InboundKey, InboxItem, InboxRule, Integration, User
from . import access, audit
from . import inbox_datasets as datasets
from .registry import INBOX_RULE_SOURCES, INBOX_SOURCE_LABELS, INBOX_STATUS_LABELS

log = logging.getLogger("app.inbox")

SOURCE_CAPABILITIES = ("org.manage", "reports.manage")
APPLICABLE = ("pending",)
REJECTABLE = ("received", "recognized", "pending", "error")
RETRYABLE = ("received", "recognized", "pending", "error", "rejected")
FINISHED = ("applied", "rejected", "duplicate", "error")
INTERNAL_ERROR = "Не удалось обработать файл: внутренняя ошибка сервера — сообщите администратору"
_FILENAME_JUNK = re.compile(r"[\x00-\x1f\x7f/\\]+")


class PlanHasErrors(AppError):
    """Применить нельзя: в плане ошибки (или нерешённые вопросы). plan — свежий план."""

    status_code = 409
    code = "import_has_errors"

    def __init__(self, detail: str, plan: dict):
        super().__init__(detail)
        self.plan = plan


class _NotApplied(Exception):
    def __init__(self, result: dict):
        super().__init__("not applied")
        self.result = result


# ---------------------------------------------------------------- от чьего имени

def source_actor(username: str, full_name: str | None = None, *, user_id: int | None = None) -> User:
    """Временный (не сохраняемый) пользователь, от имени которого движки применяют данные источника.
    user_id — настоящий пользователь, если применяет человек с data.manage (журнал — на него)."""
    actor = User(username=username[:100], full_name=(full_name or username)[:200], role="user", is_active=True,
                 capabilities=list(SOURCE_CAPABILITIES), access_overrides={}, must_change_password=False)
    actor.id = user_id
    actor.__dict__["_effective_access"] = access.source_access()
    return actor


def engine_actor(user: User | None, label: str) -> User:
    if user is None:
        return source_actor(label)
    if user.is_admin or not user.can("data.manage"):
        return user
    return source_actor(user.username, user.full_name, user_id=user.id)


def source_label(item: InboxItem, db: Session | None = None) -> str:
    """Подпись источника для журнала: «Входящие · папка», «Ключ «1С»», «Подключение «По Делу»»."""
    if item.source == "api" and item.inbound_key_id and db is not None:
        key = db.get(InboundKey, item.inbound_key_id)
        if key is not None:
            return f"Ключ «{key.name}»"[:100]
    if item.source == "integration" and item.integration_id and db is not None:
        integration = db.get(Integration, item.integration_id)
        if integration is not None:
            return f"Подключение «{integration.name}»"[:100]
    return {"folder": "Входящие · папка", "api": "Входящие · API", "upload": "Входящие · загрузка",
            "integration": "Входящие · подключение"}.get(item.source, "Входящие")


# ---------------------------------------------------------------- доступ

def can_manage(user: User) -> bool:
    return user.can("data.manage")


def visible_datasets(user: User) -> list[str]:
    return [d.key for d in datasets.all_datasets() if d.can_view(user)]


def has_access(user: User) -> bool:
    return can_manage(user) or any(d.can_apply(user) for d in datasets.all_datasets())


def visibility(user: User):
    """Условие на элементы, которые пользователь видит: все — с data.manage; иначе наборы, которые он
    применяет, и загруженное им самим."""
    if can_manage(user):
        return None
    return or_(InboxItem.dataset.in_(visible_datasets(user) or [""]), InboxItem.received_by_id == user.id)


def can_see(user: User, item: InboxItem) -> bool:
    if can_manage(user) or (item.received_by_id is not None and item.received_by_id == user.id):
        return True
    dataset = datasets.get(item.dataset)
    return dataset is not None and dataset.can_view(user)


def can_apply(user: User, item: InboxItem) -> bool:
    dataset = datasets.get(item.dataset)
    return dataset is not None and dataset.can_apply(user)


def get_item(db: Session, item_id: int, user: User | None = None, *, lock: bool = False) -> InboxItem:
    stmt = select(InboxItem).where(InboxItem.id == item_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    item = db.scalar(stmt)
    if item is None or (user is not None and not can_see(user, item)):
        raise NotFound("Элемент входящих не найден")
    return item


# ---------------------------------------------------------------- правила

def rules(db: Session) -> dict[tuple[str, str], bool]:
    return {(r.source, r.dataset): r.auto_apply for r in db.scalars(select(InboxRule))}


def save_rules(db: Session, actor: User, items: list[dict], request: Request | None = None) -> None:
    current = {(r.source, r.dataset): r for r in db.scalars(select(InboxRule))}
    before, after = {}, {}
    for item in items:
        source, dataset, value = item["source"], item["dataset"], bool(item["auto_apply"])
        if source not in INBOX_RULE_SOURCES:
            raise ValidationFailed(f"Правило задаётся для источников: {', '.join(INBOX_RULE_SOURCES)}",
                                   fields={"source": "Недопустимый источник"})
        datasets.require(dataset)
        row = current.get((source, dataset))
        old = bool(row and row.auto_apply)
        if old == value:
            continue
        if row is None:
            row = InboxRule(source=source, dataset=dataset)
            db.add(row)
            current[(source, dataset)] = row
        row.auto_apply, row.updated_by_id, row.updated_at = value, actor.id, utcnow()
        before[f"{source}/{dataset}"], after[f"{source}/{dataset}"] = old, value
    if after:
        audit.record(db, actor, entity_type="inbox_rule", action="update",
                     summary=f"Изменены правила «применять сразу»: {len(after)}", before=before, after=after,
                     request=request)
    db.flush()


def _wait_reason(db: Session, item: InboxItem, apply: bool | None) -> tuple[bool, str]:
    """(применять ли сразу, почему ждёт)."""
    if apply is False:
        return False, "Ожидает подтверждения: отправитель попросил только план"
    if item.source == "upload":
        return bool(apply), "Ожидает подтверждения на экране «Входящие»"
    rule = db.get(InboxRule, (item.source, item.dataset))
    if rule is not None and rule.auto_apply:
        return True, ""
    dataset = datasets.get(item.dataset)
    return False, (f"Ожидает подтверждения: для источника «{INBOX_SOURCE_LABELS[item.source]}» и набора "
                   f"«{dataset.label if dataset else item.dataset}» не включено «применять сразу»")


# ---------------------------------------------------------------- получение

def clean_filename(name: str | None) -> str:
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = _FILENAME_JUNK.sub(" ", base).strip().lstrip(".")
    return base[:300] or "file"


def _live_twin(db: Session, sha: str, dataset: str | None, exclude: int | None = None) -> InboxItem | None:
    stmt = select(InboxItem).where(InboxItem.sha256 == sha, InboxItem.status.in_(INBOX_LIVE_STATUSES))
    stmt = stmt.where(InboxItem.dataset == dataset if dataset else InboxItem.dataset.is_(None))
    if exclude:
        stmt = stmt.where(InboxItem.id != exclude)
    return db.scalar(stmt.order_by(InboxItem.id).limit(1))


def _duplicate_message(twin: InboxItem) -> str:
    return (f"Повтор: этот файл уже получен — элемент №{twin.id} ({INBOX_STATUS_LABELS[twin.status].lower()}), "
            "повторно не применяется")


def add(db: Session, content: bytes, filename: str, *, source: str, source_ref: str = "",
        dataset: str | None = None, user: User | None = None, label: str | None = None,
        integration_id: int | None = None, inbound_key_id: int | None = None, content_type: str = "",
        options: dict | None = None, apply: bool | None = None, request: Request | None = None,
        restrict_to_user: bool = False) -> InboxItem:
    """Новый элемент входящих → распознавание → план → применение по правилу (или ожидание).

    user — кто загрузил (загрузка в интерфейсе); label — подпись источника в журнале; apply — True
    «применить, если план без ошибок» (загрузка и API — только при включённом правиле, кроме загрузки),
    False — только план. restrict_to_user — набор файла должен быть доступен загружающему (иначе 403,
    ничего не сохраняется)."""
    if source not in INBOX_SOURCES:  # pragma: no cover - ошибка программиста
        raise ValueError(source)
    now = utcnow()
    filename = clean_filename(filename)
    handler = datasets.require(dataset) if dataset else None
    item = InboxItem(source=source, source_ref=(source_ref or "")[:500], integration_id=integration_id,
                     inbound_key_id=inbound_key_id, filename=filename, content_type=(content_type or "")[:200],
                     size=len(content), sha256=hashlib.sha256(content).hexdigest(), options={},
                     received_at=now, received_by_id=user.id if user else None,
                     received_by=(user.username if user else (label or INBOX_SOURCE_LABELS[source]))[:100],
                     error="", message="", applied_by="")
    limit = settings.inbox_max_mb * 1024 * 1024
    if len(content) > limit or not content:
        item.status, item.processed_at = "error", now
        item.error = f"Файл больше {settings.inbox_max_mb} МБ" if content else "Файл пустой"
        item.dataset = handler.key if handler else None
        db.add(item)
        db.flush()
        _record(db, user, item, "receive", f"Не принят файл «{filename}»: {item.error}", request, label)
        return item
    if handler is None:
        handler, _scores = datasets.detect(filename, content)
    if handler is not None:
        item.options = handler.normalize_options(options)
        item.dataset = handler.key
        if restrict_to_user and user is not None and not handler.can_apply(user):
            raise Forbidden(f"Файл распознан как «{handler.label}» — этот набор вам недоступен",
                            code="dataset_forbidden")
    elif options:
        item.options = dict(options)
    twin = _live_twin(db, item.sha256, item.dataset)
    if twin is not None:
        return _as_duplicate(db, item, twin, user, request, label)
    item.status = "recognized" if handler else "received"
    item.content = content
    if handler is None:
        item.message = "Набор не распознан — выберите набор и нажмите «Повторить»"
    try:
        with db.begin_nested():
            db.add(item)
            db.flush()
    except IntegrityError:
        # Тот же файл одновременно принят другим процессом
        twin = _live_twin(db, item.sha256, item.dataset)
        item = InboxItem(**{c: getattr(item, c) for c in ("source", "source_ref", "integration_id", "inbound_key_id",
                                                          "filename", "content_type", "size", "sha256", "dataset",
                                                          "options", "received_at", "received_by_id",
                                                          "received_by")}, error="", message="", applied_by="")
        if twin is None:  # pragma: no cover - гонка без победителя невозможна
            raise
        return _as_duplicate(db, item, twin, user, request, label)
    _record(db, user, item, "receive", f"Получен файл «{filename}»" + (f" ({handler.label})" if handler else
                                                                       " — набор не распознан"), request, label)
    if handler is not None:
        process(db, item, user=user, apply=apply, request=request, label=label)
    return item


def add_failed(db: Session, filename: str, *, size: int, sha256: str, error: str, source: str,
               source_ref: str = "", dataset: str | None = None, label: str | None = None,
               request: Request | None = None) -> InboxItem:
    """Файл не принят до разбора (слишком большой, не читается): элемент «ошибка» без содержимого."""
    now = utcnow()
    item = InboxItem(source=source, source_ref=(source_ref or "")[:500], filename=clean_filename(filename),
                     size=size, sha256=sha256, dataset=dataset if datasets.get(dataset) else None, status="error",
                     options={}, error=error, message="", received_at=now, processed_at=now,
                     received_by=(label or INBOX_SOURCE_LABELS[source])[:100], applied_by="")
    db.add(item)
    db.flush()
    _record(db, None, item, "receive", f"Не принят файл «{item.filename}»: {error}", request, label)
    return item


def plan_errors(plan: dict | None, limit: int = 20) -> list[str]:
    """Первые ошибки плана любого движка: строки (rows, records, users, departments) и общие (errors)."""
    if not isinstance(plan, dict):
        return []
    out: list[str] = []
    general = plan.get("errors")
    if isinstance(general, list):
        out.extend(str(e) for e in general if isinstance(e, str))
    for key in ("rows", "records", "users", "departments"):
        for row in plan.get(key) or []:
            if not isinstance(row, dict) or not row.get("errors"):
                continue
            where = f"строка {row['line']}" if row.get("line") else (row.get("email") or row.get("path") or "")
            out.extend(f"{where}: {e}" if where else str(e) for e in row["errors"])
            if len(out) >= limit:
                return out[:limit]
    return out[:limit]


def _as_duplicate(db: Session, item: InboxItem, twin: InboxItem, user: User | None, request: Request | None,
                  label: str | None) -> InboxItem:
    item.status, item.duplicate_of_id, item.processed_at = "duplicate", twin.id, utcnow()
    item.content = None
    item.message = _duplicate_message(twin)
    db.add(item)
    db.flush()
    _record(db, user, item, "duplicate", f"Повтор файла «{item.filename}» (элемент №{twin.id})", request, label)
    return item


def _record(db: Session, user: User | None, item: InboxItem, action: str, summary: str, request: Request | None,
            label: str | None = None) -> None:
    actor = user if user is not None else source_actor(label or source_label(item, db))
    audit.record(db, actor, entity_type="inbox_item", entity_id=item.id, action=action, summary=summary,
                 after={"filename": item.filename, "dataset": item.dataset, "status": item.status,
                        "source": item.source, "sha256": item.sha256}, request=request)


# ---------------------------------------------------------------- план и применение

def _set_plan(item: InboxItem, plan: dict | None) -> None:
    """План движка и его сводка для списка (summary, plan_ok)."""
    if plan is None:
        item.plan = item.summary = item.plan_ok = None
        return
    item.plan = jsonable_encoder({k: v for k, v in plan.items() if k != "applied"})
    item.summary = item.plan.get("summary") if isinstance(item.plan.get("summary"), dict) else None
    item.plan_ok = bool(item.plan.get("can_apply"))


def _errors_message(plan: dict) -> str:
    summary = plan.get("summary") or {}
    count = summary.get("errors") or 0
    if count:
        return f"В плане ошибки: {count} — исправьте файл или данные и нажмите «Повторить»"
    if summary.get("unresolved"):
        return f"Нужны решения по сотрудникам: {summary['unresolved']} — ответьте на вопросы и примените"
    return "План нельзя применить — проверьте его на экране «Входящие»"


def process(db: Session, item: InboxItem, *, user: User | None = None, apply: bool | None = None,
            request: Request | None = None, label: str | None = None) -> InboxItem:
    """План элемента и, если положено, применение. Ошибки файла — статус «ошибка» с текстом."""
    handler = datasets.require(item.dataset)
    actor = engine_actor(user, label or source_label(item, db))
    item.status, item.error, item.message = "recognized", "", ""
    try:
        with db.begin_nested():
            data = handler.parse(item.filename, item.content or b"", item.options or {})
            plan = handler.plan(db, data, actor, item.options or {})
    except AppError as exc:
        item.status, item.error, item.processed_at = "error", exc.detail, utcnow()
        _set_plan(item, None)
        db.flush()
        return item
    except Exception:
        log.exception("inbox item %s: plan failed", item.id)
        item.status, item.error, item.processed_at = "error", INTERNAL_ERROR, utcnow()
        _set_plan(item, None)
        db.flush()
        return item
    _set_plan(item, plan)
    item.status = "pending"
    item.processed_at = utcnow()
    if not plan.get("can_apply"):
        item.message = _errors_message(plan)
        db.flush()
        return item
    auto, reason = _wait_reason(db, item, apply)
    if auto and (user is None or handler.can_apply(user)):
        # Разбор заново: движок применения не должен зависеть от того, что план сделал с данными
        _apply(db, item, handler, actor, user, request, label)
    else:
        item.message = reason or "Ожидает подтверждения на экране «Входящие»"
    db.flush()
    return item


def _apply(db: Session, item: InboxItem, handler: datasets.Dataset, actor: User, user: User | None,
           request: Request | None, label: str | None) -> bool:
    try:
        with db.begin_nested():
            data = handler.parse(item.filename, item.content or b"", item.options or {})
            result, applied = handler.apply(db, data, actor, item.options or {}, item.filename, request)
            if not applied:
                raise _NotApplied(result)
    except _NotApplied as exc:
        _set_plan(item, exc.result)
        item.status, item.message = "pending", _errors_message(exc.result)
        db.flush()
        return False
    except AppError as exc:
        item.status, item.error, item.processed_at = "error", exc.detail, utcnow()
        db.flush()
        return False
    except Exception:
        log.exception("inbox item %s: apply failed", item.id)
        item.status, item.error, item.processed_at = "error", INTERNAL_ERROR, utcnow()
        db.flush()
        return False
    now = utcnow()
    item.status, item.result, item.error = "applied", jsonable_encoder(result), ""
    item.applied_at = item.processed_at = now
    item.applied_by_id = user.id if user else None
    item.applied_by = (user.username if user else (label or source_label(item, db)))[:100]
    item.message = result.get("message") or "Применён"
    db.flush()
    _record(db, user, item, "apply", f"Применён файл «{item.filename}» ({handler.label})"
            + ("" if user else " автоматически"), request, label)
    return True


def apply(db: Session, item_id: int, user: User, *, options: dict | None = None,
          request: Request | None = None) -> InboxItem:
    """Применить ожидающий элемент. PlanHasErrors — в свежем плане ошибки (ничего не записано)."""
    item = get_item(db, item_id, user, lock=True)
    if item.status not in APPLICABLE:
        raise Conflict(f"Элемент в статусе «{INBOX_STATUS_LABELS[item.status]}» — применять нечего",
                       code="wrong_status")
    handler = datasets.get(item.dataset)
    if handler is None or not handler.can_apply(user):
        raise Forbidden("Применять этот набор вам недоступно", code="dataset_forbidden")
    if not item.has_content:
        raise Conflict("Исходный файл уже удалён по сроку хранения", code="content_purged")
    if options is not None:
        item.options = handler.normalize_options(options)
    actor = engine_actor(user, source_label(item, db))
    if not _apply(db, item, handler, actor, user, request, None) and item.status == "pending":
        raise PlanHasErrors(item.message, item.plan or {})
    return item


def reject(db: Session, item_id: int, user: User, reason: str = "", request: Request | None = None) -> InboxItem:
    item = get_item(db, item_id, user, lock=True)
    if item.status not in REJECTABLE:
        raise Conflict(f"Элемент в статусе «{INBOX_STATUS_LABELS[item.status]}» — отклонить нельзя",
                       code="wrong_status")
    if item.dataset and not can_apply(user, item) and not can_manage(user):
        raise Forbidden("Отклонять этот набор вам недоступно", code="dataset_forbidden")
    item.status, item.processed_at = "rejected", utcnow()
    item.message = f"Отклонён: {reason.strip()}"[:2000] if reason.strip() else "Отклонён"
    db.flush()
    _record(db, user, item, "reject", f"Отклонён файл «{item.filename}»" + (f": {reason.strip()}"
                                                                           if reason.strip() else ""), request)
    return item


def retry(db: Session, item_id: int, user: User, *, dataset: str | None = None, options: dict | None = None,
          apply: bool | None = None, request: Request | None = None) -> InboxItem:
    """Заново распознать (или взять указанный набор) и построить план по текущим данным системы."""
    item = get_item(db, item_id, user, lock=True)
    if item.status not in RETRYABLE:
        raise Conflict(f"Элемент в статусе «{INBOX_STATUS_LABELS[item.status]}» — повторять нечего",
                       code="wrong_status")
    if not item.has_content:
        raise Conflict("Исходного файла нет (не сохранён или удалён по сроку хранения)", code="content_purged")
    content = item.content or b""
    handler = datasets.require(dataset) if dataset else (datasets.get(item.dataset) or
                                                         datasets.detect(item.filename, content)[0])
    if handler is None:
        item.status, item.message, item.dataset = "received", "Набор не распознан — выберите набор", None
        db.flush()
        return item
    if not handler.can_apply(user):
        raise Forbidden(f"Набор «{handler.label}» вам недоступен", code="dataset_forbidden")
    new_options = handler.normalize_options(options if options is not None else
                                            (item.options if handler.key == item.dataset else None))
    twin = _live_twin(db, item.sha256, handler.key, exclude=item.id)
    if twin is not None:
        item.status, item.duplicate_of_id, item.dataset = "duplicate", twin.id, handler.key
        item.message, item.processed_at = _duplicate_message(twin), utcnow()
        db.flush()
        return item
    item.dataset, item.options, item.duplicate_of_id, item.result = handler.key, new_options, None, None
    _record(db, user, item, "retry", f"Повторная обработка файла «{item.filename}» ({handler.label})", request)
    process(db, item, user=user, apply=bool(apply), request=request)
    return item


# ---------------------------------------------------------------- список и вывод

def query(db: Session, user: User, *, status: str | None = None, dataset: str | None = None,
          source: str | None = None, search: str = "", date_from=None, date_to=None, integration_id=None,
          page: int = 1, page_size: int = 50) -> dict:
    conditions = []
    seen = visibility(user)
    if seen is not None:
        conditions.append(seen)
    if dataset:
        conditions.append(InboxItem.dataset.is_(None) if dataset == "none" else InboxItem.dataset == dataset)
    if source:
        conditions.append(InboxItem.source == source)
    if integration_id:
        conditions.append(InboxItem.integration_id == integration_id)
    if search.strip():
        conditions.append(func.lower(InboxItem.filename).like(f"%{search.strip().lower()}%"))
    if date_from:
        conditions.append(InboxItem.received_at >= date_from)
    if date_to:
        conditions.append(InboxItem.received_at < date_to)
    where = and_(*conditions) if conditions else None
    counts_stmt = select(InboxItem.status, func.count()).group_by(InboxItem.status)
    if where is not None:
        counts_stmt = counts_stmt.where(where)
    counts = {s: 0 for s in INBOX_STATUS_LABELS} | dict(db.execute(counts_stmt).all())
    stmt = select(InboxItem)
    if where is not None:
        stmt = stmt.where(where)
    if status:
        stmt = stmt.where(InboxItem.status.in_(status.split(",")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(stmt.order_by(InboxItem.received_at.desc(), InboxItem.id.desc())
                           .offset((page - 1) * page_size).limit(page_size)))
    names = _names(db, rows)
    return {"items": [item_out(i, user, names) for i in rows], "total": total, "page": page,
            "page_size": page_size, "counts": counts}


def _names(db: Session, items: list[InboxItem]) -> dict:
    integration_ids = {i.integration_id for i in items if i.integration_id}
    key_ids = {i.inbound_key_id for i in items if i.inbound_key_id}
    out: dict = {"integrations": {}, "keys": {}}
    if integration_ids:
        out["integrations"] = dict(db.execute(select(Integration.id, Integration.name)
                                              .where(Integration.id.in_(integration_ids))).all())
    if key_ids:
        out["keys"] = dict(db.execute(select(InboundKey.id, InboundKey.name).where(InboundKey.id.in_(key_ids))).all())
    return out


def item_out(item: InboxItem, user: User | None, names: dict | None = None, *, full: bool = False) -> dict:
    names = names or {"integrations": {}, "keys": {}}
    handler = datasets.get(item.dataset)
    plan_ok = bool(item.plan_ok)
    may_apply = user is not None and handler is not None and handler.can_apply(user)
    out = {
        "id": item.id, "source": item.source, "source_label": INBOX_SOURCE_LABELS.get(item.source, item.source),
        "source_ref": item.source_ref,
        "integration": {"id": item.integration_id, "name": names["integrations"].get(item.integration_id, "")}
        if item.integration_id else None,
        "inbound_key": {"id": item.inbound_key_id, "name": names["keys"].get(item.inbound_key_id, "")}
        if item.inbound_key_id else None,
        "filename": item.filename, "content_type": item.content_type, "size": item.size, "sha256": item.sha256,
        "dataset": item.dataset, "dataset_label": handler.label if handler else None,
        "status": item.status, "status_label": INBOX_STATUS_LABELS[item.status],
        "summary": item.summary, "plan_can_apply": plan_ok, "message": item.message, "error": item.error,
        "duplicate_of": item.duplicate_of_id, "received_at": item.received_at, "received_by": item.received_by,
        "processed_at": item.processed_at, "applied_at": item.applied_at, "applied_by": item.applied_by,
        "has_content": bool(item.has_content),
        "actions": {
            "apply": may_apply and item.status in APPLICABLE and plan_ok and bool(item.has_content),
            "reject": item.status in REJECTABLE and (may_apply or (user is not None and can_manage(user))),
            "retry": item.status in RETRYABLE and bool(item.has_content)
            and (may_apply or (user is not None and can_manage(user))),
            "download": bool(item.has_content),
        },
    }
    if full:
        out.update({"plan": item.plan, "result": item.result, "options": item.options or {},
                    "option_fields": [o.as_dict() for o in handler.option_fields] if handler else []})
    return out


def detail(db: Session, item: InboxItem, user: User) -> dict:
    return item_out(item, user, _names(db, [item]), full=True)


def datasets_out(db: Session, user: User) -> list[dict]:
    current = rules(db)
    return [{**d.meta(), "can_apply": d.can_apply(user),
             "rules": {source: current.get((source, d.key), False) for source in INBOX_RULE_SOURCES}}
            for d in datasets.all_datasets()]


# ---------------------------------------------------------------- срок хранения

def purge(db: Session, now=None) -> int:
    """Удаляет исходные файлы обработанных элементов старше INBOX_RETENTION_DAYS (строки остаются)."""
    now = now or utcnow()
    border = now - timedelta(days=settings.inbox_retention_days)
    result = db.execute(update(InboxItem).where(
        InboxItem.content.is_not(None), InboxItem.status.in_(FINISHED),
        func.coalesce(InboxItem.processed_at, InboxItem.received_at) < border)
        .values(content=None, content_purged_at=now).execution_options(synchronize_session=False))
    return result.rowcount or 0
