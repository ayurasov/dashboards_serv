"""Входящие данные (ADR-0011): элементы, план и применение, загрузка файла, наборы и правила, папка.

Доступно пользователю с полномочием data.manage (все элементы, правила, папка) и тем, кто применяет
хотя бы один набор (редакторы служб, ведущие структуру и отчёты) — для своих наборов и своих загрузок.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ...core.config import settings
from ...core.db import get_db
from ...core.errors import AppError, Forbidden, NotFound, ValidationFailed
from ...core.timeutil import day_end_utc, day_start_utc
from ...models import AppSetting, User
from ...schemas.integrations import InboxApplyIn, InboxRejectIn, InboxRetryIn, InboxRulesIn
from ...services import inbox, inbox_folder
from ...services import inbox_datasets as datasets
from ...services.registry import INBOX_RULE_SOURCES, INBOX_SOURCE_LABELS, INBOX_STATUS_LABELS
from ..deps import active_user, require_capability
from ..uploads import ascii_filename
from .org import _flag

router = APIRouter(prefix="/api/inbox", tags=["Входящие данные"])
manage = require_capability("data.manage")
SAFE_TYPES = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12", "csv": "text/csv; charset=utf-8",
              "txt": "text/plain; charset=utf-8", "json": "application/json"}
CONFLICT = {409: {"description": "В плане ошибки (code: import_has_errors) или статус не тот (wrong_status)"}}


async def inbox_user(user: User = Depends(active_user)) -> User:
    if not inbox.has_access(user):
        raise Forbidden("Входящие данные вам недоступны: нужно полномочие «Входящие данные» или ввод данных службы")
    return user


async def read_inbox_upload(file: UploadFile) -> bytes:
    limit = settings.inbox_max_mb * 1024 * 1024
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise AppError(f"Файл больше {settings.inbox_max_mb} МБ", code="payload_too_large", status_code=413)
    if not raw:
        raise ValidationFailed("Файл пустой", fields={"file": "Пустой файл"})
    return raw


def parse_options(text: str | None) -> dict | None:
    if not text:
        return None
    try:
        value = json.loads(text)
    except ValueError:
        raise ValidationFailed("options: ожидается JSON-объект", fields={"options": "Некорректный JSON"}) from None
    if not isinstance(value, dict):
        raise ValidationFailed("options: ожидается JSON-объект", fields={"options": "Ожидается объект"})
    return value


def _day(value: date | None, end: bool = False) -> datetime | None:
    if value is None:
        return None
    return day_end_utc(value) if end else day_start_utc(value)


# ---------------------------------------------------------------- справочники и правила

@router.get("/datasets", summary="Наборы данных, источники и статусы (для фильтров и правил)")
def list_datasets(db: Session = Depends(get_db), user: User = Depends(inbox_user)):
    return {
        "datasets": inbox.datasets_out(db, user),
        "sources": [{"key": k, "label": v, "has_rules": k in INBOX_RULE_SOURCES}
                    for k, v in INBOX_SOURCE_LABELS.items()],
        "statuses": [{"key": k, "label": v} for k, v in INBOX_STATUS_LABELS.items()],
        "max_mb": settings.inbox_max_mb, "retention_days": settings.inbox_retention_days,
        "can_manage": inbox.can_manage(user),
    }


def _rules_out(db: Session) -> list[dict]:
    current = inbox.rules(db)
    return [{"source": s, "source_label": INBOX_SOURCE_LABELS[s], "dataset": d.key, "dataset_label": d.label,
             "auto_apply": current.get((s, d.key), False)}
            for d in datasets.all_datasets() for s in INBOX_RULE_SOURCES]


@router.get("/rules", summary="Правила «применять сразу»: источник × набор")
def get_rules(db: Session = Depends(get_db), _: User = Depends(manage)):
    return _rules_out(db)


@router.put("/rules", summary="Изменить правила «применять сразу»")
def put_rules(body: InboxRulesIn, request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    inbox.save_rules(db, user, [r.model_dump() for r in body.rules], request)
    db.commit()
    return _rules_out(db)


@router.get("/folder", summary="Папка «Входящие»: настройка, состояние, последний разбор, планировщик")
def folder_status(db: Session = Depends(get_db), _: User = Depends(manage)):
    last = db.get(AppSetting, inbox_folder.STATUS_SETTING)
    worker = db.get(AppSetting, "worker_status")
    return {**inbox_folder.status(), "last_scan": last.value if last else None,
            "worker": worker.value if worker else None}


@router.post("/folder/scan", summary="Разобрать папку «Входящие» сейчас")
async def folder_scan(_: User = Depends(manage)):
    result = await run_in_threadpool(inbox_folder.scan)
    if not result.enabled:
        raise ValidationFailed("Папка «Входящие» не настроена: задайте INBOX_DIR", code="inbox_dir_not_set")
    return result.as_dict()


# ---------------------------------------------------------------- элементы

@router.get("", summary="Элементы входящих: фильтры и страницы",
            description="status — один или несколько через запятую; dataset=none — нераспознанные; date_from/date_to "
                        "— дни получения по часовому поясу компании. В ответе counts — число элементов по статусам "
                        "(с остальными фильтрами).")
def list_items(status: str | None = Query(None, max_length=200), dataset: str | None = Query(None, max_length=40),
               source: str | None = Query(None, max_length=20), q: str = Query("", max_length=200),
               date_from: date | None = None, date_to: date | None = None, integration_id: int | None = None,
               page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
               db: Session = Depends(get_db), user: User = Depends(inbox_user)):
    if status and set(status.split(",")) - set(INBOX_STATUS_LABELS):
        raise ValidationFailed("Неизвестный статус", fields={"status": "Недопустимое значение"})
    return inbox.query(db, user, status=status, dataset=dataset, source=source, search=q,
                       date_from=_day(date_from), date_to=_day(date_to, end=True), integration_id=integration_id,
                       page=page, page_size=page_size)


def _upload_job(db: Session, user: User, raw: bytes, filename: str, content_type: str, dataset: str | None,
                options: dict | None, apply: bool, request: Request) -> dict:
    item = inbox.add(db, raw, filename, source="upload", user=user, dataset=dataset or None,
                     content_type=content_type, options=options, apply=apply, request=request, restrict_to_user=True)
    db.commit()
    return inbox.detail(db, item, user)


@router.post("", status_code=201, summary="Загрузить файл во входящие",
             description="Multipart: file; dataset — набор (иначе распознаётся); apply — применить сразу, если план "
                         "без ошибок; options — JSON параметров набора. Файл набора, который вам недоступен, не "
                         "принимается (403).")
async def upload(request: Request, file: UploadFile = File(...), dataset: str = Form(""), apply: str = Form("false"),
                 options: str = Form(""), db: Session = Depends(get_db), user: User = Depends(inbox_user)):
    raw = await read_inbox_upload(file)
    if dataset:
        datasets.require(dataset)
    return await run_in_threadpool(_upload_job, db, user, raw, file.filename or "", file.content_type or "",
                                   dataset or None, parse_options(options), _flag(apply), request)


@router.get("/{item_id}", summary="Элемент входящих: план, итог, параметры")
def get_item(item_id: int, db: Session = Depends(get_db), user: User = Depends(inbox_user)):
    return inbox.detail(db, inbox.get_item(db, item_id, user), user)


@router.get("/{item_id}/file", summary="Скачать исходный файл", response_class=Response)
def download(item_id: int, db: Session = Depends(get_db), user: User = Depends(inbox_user)):
    item = inbox.get_item(db, item_id, user)
    if not item.has_content:
        raise NotFound("Исходного файла нет: не сохранён или удалён по сроку хранения", code="content_purged")
    # Тип — по расширению из короткого списка, а не со слов отправителя
    media = SAFE_TYPES.get(item.filename.rsplit(".", 1)[-1].lower(), "application/octet-stream")
    ascii_name = ascii_filename(item.filename) or f"inbox-{item.id}"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(item.filename)}"
    return Response(content=item.content or b"", media_type=media,
                    headers={"Content-Disposition": disposition, "Cache-Control": "no-store"})


def _action_job(db: Session, fn, *args, **kwargs):
    user = args[1]
    try:
        item = fn(db, *args, **kwargs)
    except inbox.PlanHasErrors as exc:
        db.commit()  # свежий план сохраняется: на экране — актуальные ошибки
        item = inbox.get_item(db, args[0], user)
        return JSONResponse(jsonable_encoder({"detail": exc.detail, "code": exc.code,
                                              "item": inbox.detail(db, item, user)}), status_code=409)
    db.commit()
    return inbox.detail(db, item, user)


@router.post("/{item_id}/apply", summary="Применить план", responses=CONFLICT)
async def apply_item(item_id: int, request: Request, body: InboxApplyIn | None = None,
                     db: Session = Depends(get_db), user: User = Depends(inbox_user)):
    return await run_in_threadpool(_action_job, db, inbox.apply, item_id, user,
                                   options=body.options if body else None, request=request)


@router.post("/{item_id}/reject", summary="Отклонить элемент", responses=CONFLICT)
def reject_item(item_id: int, request: Request, body: InboxRejectIn | None = None, db: Session = Depends(get_db),
                user: User = Depends(inbox_user)):
    return _action_job(db, inbox.reject, item_id, user, body.reason if body else "", request=request)


@router.post("/{item_id}/retry", summary="Повторить: распознать заново (или с указанным набором) и построить план",
             responses=CONFLICT)
async def retry_item(item_id: int, request: Request, body: InboxRetryIn | None = None,
                     db: Session = Depends(get_db), user: User = Depends(inbox_user)):
    body = body or InboxRetryIn()
    return await run_in_threadpool(_action_job, db, inbox.retry, item_id, user, dataset=body.dataset,
                                   options=body.options, apply=body.apply, request=request)
