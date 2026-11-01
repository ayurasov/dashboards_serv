"""PDF-отчёты. Каждый отчёт проверяет доступ к своей службе."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...models import User
from ...services import access
from ...services import partnerships as p_service
from ...services.pdf import reports
from ..deps import require_service
from ..uploads import file_response
from .hr import query_events
from .partnerships import _filtered

router = APIRouter(prefix="/api/pdf", tags=["PDF-отчёты"])


@router.get("/hr/dashboard", summary="Служба персонала: дашборд")
def hr_dashboard(months: str = "", db: Session = Depends(get_db), user: User = Depends(require_service("hr"))):
    keys = [k for k in months.split(",") if k]
    return file_response(reports.hr_dashboard(db, keys, access.department_scope(user)), "Персонал — дашборд.pdf")


@router.get("/hr/summary", summary="Служба персонала: сводка по периодам")
def hr_summary(period_type: str = Query("quarter", pattern="^(month|quarter|half|year)$"),
               db: Session = Depends(get_db), user: User = Depends(require_service("hr"))):
    return file_response(reports.hr_summary(db, period_type, access.department_scope(user)), "Персонал — сводка.pdf")


@router.get("/hr/registry", summary="Служба персонала: реестр")
def hr_registry(month: str = "", year: int | None = None, event_type: str = Query("", pattern="^(|hired|fired)$"),
                department: str = "", search: str = "", db: Session = Depends(get_db),
                user: User = Depends(require_service("hr"))):
    events = query_events(month, year, event_type, department, search, db, user)
    filters = {"Месяц": month, "Год": str(year) if year else None,
               "Событие": {"hired": "приёмы", "fired": "увольнения"}.get(event_type), "Подразделение": department,
               "Поиск": search}
    return file_response(reports.hr_registry(db, events, filters), "Персонал — реестр.pdf")


@router.get("/hr/targets", summary="Служба персонала: цели")
def hr_targets(db: Session = Depends(get_db), _: User = Depends(require_service("hr"))):
    return file_response(reports.hr_targets(db), "Персонал — цели.pdf")


@router.get("/tp/dashboard", summary="Техподдержка: недельный отчёт")
def tp_dashboard(year: int | None = None, weeks: int | None = Query(None, ge=1, le=520),
                 db: Session = Depends(get_db), _: User = Depends(require_service("tech"))):
    return file_response(reports.tp_dashboard(db, year, weeks), "Техподдержка — отчёт.pdf")


@router.get("/tp/naumen", summary="Техподдержка: заявки Naumen")
def tp_naumen(year: int | None = None, org: str | None = None, months: int | None = Query(None, ge=1, le=120),
              db: Session = Depends(get_db), _: User = Depends(require_service("tech"))):
    return file_response(reports.naumen_report(db, year, org, months), "Техподдержка — заявки Naumen.pdf")


@router.get("/partnerships/registry", summary="Партнёрства: реестр")
def partnerships_registry(year: int | None = None, status: str = "", almi_product: str = "", direction: str = "",
                          type: str = "", search: str = "", light: str = "", db: Session = Depends(get_db),
                          _: User = Depends(require_service("project_product"))):
    rules = p_service.rule_map(db)
    rows = [p_service.serialize(r, rules) for r in _filtered(
        db, year=year, status=status, almi_product=almi_product, direction=direction, type_=type, search=search,
        light=light)]
    filters = {"Год": str(year) if year else None, "Статус": status, "Продукт АЛМИ": almi_product,
               "Направление": direction, "Тип": type, "Поиск": search}
    return file_response(reports.partnerships_registry(db, rows, filters), "Партнёрства — реестр.pdf")


@router.get("/partnerships/summary", summary="Партнёрства: сводка")
def partnerships_summary(db: Session = Depends(get_db), _: User = Depends(require_service("project_product"))):
    return file_response(reports.partnerships_summary(db), "Партнёрства — сводка.pdf")
