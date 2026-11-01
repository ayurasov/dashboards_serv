"""PDF-отчёты. Каждый отчёт проверяет доступ к своей службе."""
from __future__ import annotations

import asyncio
import weakref
from collections.abc import AsyncIterator
from contextlib import contextmanager

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.db import get_db
from ...models import User
from ...services import access
from ...services import partnerships as p_service
from ...services.pdf import reports
from ..deps import require_service
from ..uploads import file_response
from .hr import query_events
from .partnerships import _filtered

# Построение графиков нагружает процессор: в процессе одновременно строится не больше
# PDF_CONCURRENCY отчётов. Остальные ждут своей очереди до получения сессии базы данных —
# без потока и без места в очереди к базе, поэтому не мешают остальным запросам.
_pdf_queues: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = weakref.WeakKeyDictionary()


async def pdf_queue() -> AsyncIterator[None]:
    loop = asyncio.get_running_loop()
    queue = _pdf_queues.get(loop)
    if queue is None:
        queue = _pdf_queues[loop] = asyncio.Semaphore(settings.pdf_concurrency)
    async with queue:
        yield


# Зависимость роутера выполняется раньше зависимостей обработчика (сессии и проверки прав)
router = APIRouter(prefix="/api/pdf", tags=["PDF-отчёты"], dependencies=[Depends(pdf_queue)])


@contextmanager
def _pdf_slot(db: Session):
    db.commit()  # транзакция проверки прав завершается, отчёт читает данные в своей
    yield


@router.get("/hr/dashboard", summary="Служба персонала: дашборд")
def hr_dashboard(months: str = "", db: Session = Depends(get_db), user: User = Depends(require_service("hr"))):
    keys = [k for k in months.split(",") if k]
    with _pdf_slot(db):
        content = reports.hr_dashboard(db, keys, access.department_scope(user))
    return file_response(content, "Персонал — дашборд.pdf")


@router.get("/hr/summary", summary="Служба персонала: сводка по периодам")
def hr_summary(period_type: str = Query("quarter", pattern="^(month|quarter|half|year)$"),
               db: Session = Depends(get_db), user: User = Depends(require_service("hr"))):
    with _pdf_slot(db):
        content = reports.hr_summary(db, period_type, access.department_scope(user))
    return file_response(content, "Персонал — сводка.pdf")


@router.get("/hr/registry", summary="Служба персонала: реестр")
def hr_registry(month: str = "", year: int | None = None, event_type: str = Query("", pattern="^(|hired|fired)$"),
                department: str = "", search: str = "", db: Session = Depends(get_db),
                user: User = Depends(require_service("hr"))):
    events = query_events(month, year, event_type, department, search, db, user)
    filters = {"Месяц": month, "Год": str(year) if year else None,
               "Событие": {"hired": "приёмы", "fired": "увольнения"}.get(event_type), "Подразделение": department,
               "Поиск": search}
    with _pdf_slot(db):
        content = reports.hr_registry(db, events, filters)
    return file_response(content, "Персонал — реестр.pdf")


@router.get("/hr/targets", summary="Служба персонала: цели")
def hr_targets(db: Session = Depends(get_db), _: User = Depends(require_service("hr"))):
    with _pdf_slot(db):
        content = reports.hr_targets(db)
    return file_response(content, "Персонал — цели.pdf")


@router.get("/tp/dashboard", summary="Техподдержка: недельный отчёт")
def tp_dashboard(year: int | None = None, weeks: int | None = Query(None, ge=1, le=520),
                 week_from: int | None = Query(None, ge=1, le=53), week_to: int | None = Query(None, ge=1, le=53),
                 db: Session = Depends(get_db), _: User = Depends(require_service("tech"))):
    with _pdf_slot(db):
        content = reports.tp_dashboard(db, year, weeks, week_from, week_to)
    return file_response(content, "Техподдержка — отчёт.pdf")


@router.get("/tp/naumen", summary="Техподдержка: заявки Naumen")
def tp_naumen(year: int | None = None, org: str | None = None, months: int | None = Query(None, ge=1, le=120),
              db: Session = Depends(get_db), _: User = Depends(require_service("tech"))):
    with _pdf_slot(db):
        content = reports.naumen_report(db, year, org, months)
    return file_response(content, "Техподдержка — заявки Naumen.pdf")


@router.get("/partnerships/registry", summary="Партнёрства: реестр")
def partnerships_registry(year: int | None = None, status: str = "", almi_product: str = "", direction: str = "",
                          type: str = "", search: str = "", light: str = "", db: Session = Depends(get_db),
                          _: User = Depends(require_service("project_product"))):
    rules = p_service.rule_map(db)
    rows = [p_service.serialize(r, rules) for r in _filtered(
        db, year=year, status=status, almi_product=almi_product, direction=direction, type_=type, search=search,
        light=light)]
    filters = {"Год": str(year) if year else None, "Статус": status, "Продукт АЛМИ": almi_product,
               "Направление": direction, "Тип": type, "Поиск": search,
               "Светофор": {"green": "норма", "yellow": "внимание", "red": "критично"}.get(light)}
    with _pdf_slot(db):
        content = reports.partnerships_registry(db, rows, filters)
    return file_response(content, "Партнёрства — реестр.pdf")


@router.get("/partnerships/summary", summary="Партнёрства: сводка")
def partnerships_summary(db: Session = Depends(get_db), _: User = Depends(require_service("project_product"))):
    with _pdf_slot(db):
        content = reports.partnerships_summary(db)
    return file_response(content, "Партнёрства — сводка.pdf")
