"""Приём по API для внешних систем (1С, скрипты): /api/inbound/v1, ADR-0011.

Аутентификация — заголовок Authorization: Bearer dash_… (ключ из «Интеграции → Ключи для входящих
вызовов»). Сессия и cookie не используются, поэтому CSRF-токен не нужен (проверка CSRF в app/api/deps.py
относится только к сессионному входу). Частота — не больше INBOUND_RATE_LIMIT запросов в минуту на ключ:
счётчик окна — в строке ключа в базе (integration_admin.hit_rate_limit), общий для всех процессов приложения;
превышение — 429 с Retry-After (секунд до конца окна).

Ошибки — в формате приложения {"detail", "code"} и, для совместимости с соглашениями «По Делу» и «Пульса»,
те же значения в полях {"error" (= code), "message" (= detail)}: 401 auth_required / invalid_key,
403 scope_forbidden, 413 payload_too_large, 422 validation_error, 429 rate_limited.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ... import APP_NAME, __version__
from ...core.config import settings
from ...core.db import get_db
from ...core.errors import Forbidden, NotFound, TooManyRequests, Unauthorized
from ...models import InboundKey, InboxItem
from ...services import inbox
from ...services import inbox_datasets as datasets
from ...services import integration_admin as admin
from ...services.registry import INBOX_STATUS_LABELS
from .inbox import parse_options, read_inbox_upload
from .org import _flag

router = APIRouter(prefix="/api/inbound/v1", tags=["Приём по API"])
BEARER = "bearer "


def _authenticate(request: Request, db: Session) -> InboundKey:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith(BEARER):
        raise Unauthorized("Нужен заголовок Authorization: Bearer dash_…", code="auth_required")
    key = admin.authenticate(db, header[len(BEARER):])
    if key is None:
        raise Unauthorized("Ключ недействителен или отозван", code="invalid_key")
    limit = settings.inbound_rate_limit
    wait = admin.hit_rate_limit(db, key, limit)
    db.commit()
    if wait:
        raise TooManyRequests(f"Не больше {limit} запросов в минуту — повторите через {wait} с",
                              code="rate_limited", headers={"Retry-After": str(wait)})
    return key


def inbound_key(scope: str | None = None):
    def dependency(request: Request, db: Session = Depends(get_db)) -> InboundKey:
        key = _authenticate(request, db)
        if scope and scope not in (key.scopes or []):
            raise Forbidden(f"Области ключа «{key.name}» не хватает: {scope}", code="scope_forbidden")
        return key

    dependency.__name__ = f"inbound_key_{scope or 'any'}"
    return dependency


def _label(key: InboundKey) -> str:
    return f"Ключ «{key.name}»"[:100]


def _item_out(item: InboxItem) -> dict:
    dataset = datasets.get(item.dataset)
    return {"ok": item.status not in ("error",), "id": item.id, "status": item.status,
            "status_label": INBOX_STATUS_LABELS[item.status], "dataset": item.dataset,
            "dataset_label": dataset.label if dataset else None, "filename": item.filename, "sha256": item.sha256,
            "duplicate_of": item.duplicate_of_id, "message": item.message, "error": item.error,
            "summary": item.summary, "errors": inbox.plan_errors(item.plan),
            "received_at": item.received_at, "processed_at": item.processed_at, "applied_at": item.applied_at}


@router.get("/ping", summary="Проверка ключа и связи")
def ping(key: InboundKey = Depends(inbound_key())):
    return {"ok": True, "app": "dashboards", "name": APP_NAME, "version": __version__,
            "key": {"name": key.name, "prefix": key.prefix, "scopes": key.scopes or []},
            "datasets": [d.key for d in datasets.all_datasets()]}


def _receive(db: Session, key: InboundKey, raw: bytes, filename: str, content_type: str, dataset: str | None,
             options: dict | None, apply: bool | None, request: Request):
    item = inbox.add(db, raw, filename, source="api", inbound_key_id=key.id, label=_label(key), dataset=dataset,
                     content_type=content_type, options=options, apply=apply, request=request)
    db.commit()
    return JSONResponse(jsonable_encoder(_item_out(item)), status_code=200 if item.status == "duplicate" else 201)


@router.post("/files", status_code=201, summary="Принять файл во входящие",
             description="Multipart: file; dataset — набор (иначе распознаётся по содержимому, имя по шаблону — "
                         "подсказка); apply=false — только план (ждать подтверждения), иначе — применить, если план "
                         "без ошибок и для источника «Приём по API» и набора включено «применять сразу»; options — "
                         "JSON параметров набора. 201 — файл принят (смотрите status: pending · applied · error · "
                         "received), 200 — повтор уже полученного файла (status: duplicate).")
async def receive(request: Request, file: UploadFile = File(...), dataset: str = Form(""), apply: str = Form(""),
                  options: str = Form(""), db: Session = Depends(get_db),
                  key: InboundKey = Depends(inbound_key("files"))):
    raw = await read_inbox_upload(file)
    if dataset:
        datasets.require(dataset)
    flag = None if apply.strip() == "" else _flag(apply)
    return await run_in_threadpool(_receive, db, key, raw, file.filename or "", file.content_type or "",
                                   dataset or None, parse_options(options), flag, request)


@router.get("/files/{item_id}", summary="Статус файла, принятого этим ключом")
def file_status(item_id: int, db: Session = Depends(get_db), key: InboundKey = Depends(inbound_key("status"))):
    item = db.get(InboxItem, item_id)
    if item is None or item.inbound_key_id != key.id:
        raise NotFound("Файл не найден")
    return _item_out(item)

