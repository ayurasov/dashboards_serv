"""PDF-отчёты. Каждый отчёт проверяет доступ к своей службе и право выгрузки (ADR-0009);
реестры — ещё и право на исходные записи (реестр персонала — и на персональные данные)."""
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
from ...services import reports as reports_service
from ...services.pdf import reports
from ..deps import require_export
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
hr_pdf = require_export("hr")
hr_registry_pdf = require_export("hr", records=True, data_class="personal")
tp_pdf = require_export("tech")
pp_pdf = require_export("project_product")
pp_registry_pdf = require_export("project_product", records=True)
# Сквозной отчёт — по области, глубине и классам данных пользователя; нужна только выгрузка
report_pdf = require_export()


@contextmanager
def _pdf_slot(db: Session):
    db.commit()  # транзакция проверки прав завершается, отчёт читает данные в своей
    yield


@router.get("/hr/dashboard", summary="Служба персонала: дашборд")
def hr_dashboard(months: str = "", db: Session = Depends(get_db), user: User = Depends(hr_pdf)):
    keys = [k for k in months.split(",") if k]
    with _pdf_slot(db):
        content = reports.hr_dashboard(db, keys, access.department_scope(db, user))
    return file_response(content, "Персонал — дашборд.pdf")


@router.get("/hr/summary", summary="Служба персонала: сводка по периодам")
def hr_summary(period_type: str = Query("quarter", pattern="^(month|quarter|half|year)$"),
               from_key: str = Query("", max_length=20, description="Первый период (ключ, как на странице)"),
               to_key: str = Query("", max_length=20, description="Последний период"),
               db: Session = Depends(get_db), user: User = Depends(hr_pdf)):
    with _pdf_slot(db):
        content = reports.hr_summary(db, period_type, access.department_scope(db, user), from_key, to_key)
    return file_response(content, "Персонал — сводка.pdf")


@router.get("/hr/registry", summary="Служба персонала: реестр")
def hr_registry(month: str = "", year: int | None = None, event_type: str = Query("", pattern="^(|hired|fired)$"),
                department: str = "", search: str = "", db: Session = Depends(get_db),
                user: User = Depends(hr_registry_pdf)):
    events = query_events(month, year, event_type, department, search, db, user)
    filters = {"Месяц": month, "Год": str(year) if year else None,
               "Событие": {"hired": "приёмы", "fired": "увольнения"}.get(event_type), "Подразделение": department,
               "Поиск": search}
    with _pdf_slot(db):
        content = reports.hr_registry(db, events, filters)
    return file_response(content, "Персонал — реестр.pdf")


@router.get("/hr/targets", summary="Служба персонала: цели")
def hr_targets(db: Session = Depends(get_db), _: User = Depends(hr_pdf)):
    with _pdf_slot(db):
        content = reports.hr_targets(db)
    return file_response(content, "Персонал — цели.pdf")


@router.get("/tp/dashboard", summary="Техподдержка: недельный отчёт")
def tp_dashboard(year: int | None = None, weeks: int | None = Query(None, ge=1, le=520),
                 week_from: int | None = Query(None, ge=1, le=53), week_to: int | None = Query(None, ge=1, le=53),
                 years: str = Query("", max_length=200, description="Несколько лет через запятую"),
                 db: Session = Depends(get_db), _: User = Depends(tp_pdf)):
    year_list = sorted({int(y) for y in years.split(",") if y.strip().isdigit()})
    with _pdf_slot(db):
        content = reports.tp_dashboard(db, year, weeks, week_from, week_to, year_list)
    return file_response(content, "Техподдержка — отчёт.pdf")


@router.get("/tp/naumen", summary="Техподдержка: заявки Naumen")
def tp_naumen(year: int | None = None, org: str | None = None, months: int | None = Query(None, ge=1, le=120),
              db: Session = Depends(get_db), _: User = Depends(tp_pdf)):
    with _pdf_slot(db):
        content = reports.naumen_report(db, year, org, months)
    return file_response(content, "Техподдержка — заявки Naumen.pdf")


@router.get("/partnerships/registry", summary="Партнёрства: реестр")
def partnerships_registry(year: int | None = None, status: str = "", almi_product: str = "", direction: str = "",
                          type: str = "", search: str = "", light: str = "", db: Session = Depends(get_db),
                          _: User = Depends(pp_registry_pdf)):
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
def partnerships_summary(year: int | None = None, status: str = "", almi_product: str = "",
                         db: Session = Depends(get_db), _: User = Depends(pp_pdf)):
    """Сводка с фильтрами дашборда партнёрств (год сертификации, статус, продукт АЛМИ)."""
    rows = _filtered(db, year=year, status=status, almi_product=almi_product)
    filters = {"Год": str(year) if year else None, "Статус": status, "Продукт АЛМИ": almi_product}
    with _pdf_slot(db):
        content = reports.partnerships_summary(db, rows, filters)
    return file_response(content, "Партнёрства — сводка.pdf")


@router.get("/reports/scorecard", summary="Сквозной отчёт")
def reports_scorecard(period: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
                                                 description="ГГГГ-ММ; по умолчанию — последний период с данными"),
                      root: int | None = Query(None, ge=1), db: Session = Depends(get_db),
                      user: User = Depends(report_pdf)):
    data = reports_service.scorecard(db, user, period, root)
    with _pdf_slot(db):
        content = reports.report_scorecard(db, data)
    return file_response(content, f"Сквозной отчёт {data['period']}.pdf")
