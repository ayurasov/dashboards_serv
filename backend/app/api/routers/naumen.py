"""Техническая поддержка: аналитика заявок Naumen SD."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...models import DataImport, NaumenTicket, TpWeeklyReport, User
from ...schemas.common import ImportResult
from ...services import access
from ...services import naumen as naumen_service
from ...services.cache import cached_json
from ..deps import require_service
from ..uploads import read_upload

router = APIRouter(prefix="/api/tp/naumen", tags=["Техподдержка: заявки Naumen"])
SERVICE = "tech"
read = require_service(SERVICE, "viewer")
manage = require_service(SERVICE, "manager")


@router.get("/filters", summary="Значения для фильтров: годы и организации")
def filters(db: Session = Depends(get_db), _: User = Depends(read)):
    return cached_json(db, [SERVICE], ("naumen.filters",), lambda: _filters(db))


def _filters(db: Session) -> dict:
    years = sorted(int(y) for y in db.scalars(
        select(extract("year", NaumenTicket.registered_at)).where(NaumenTicket.registered_at.is_not(None)).distinct()))
    orgs = list(db.execute(
        select(NaumenTicket.org, func.count()).where(NaumenTicket.org != "")
        .group_by(NaumenTicket.org).order_by(func.count().desc())).all())
    last_import = db.scalar(select(DataImport).where(DataImport.dataset == "naumen")
                            .order_by(DataImport.created_at.desc()).limit(1))
    return {
        "years": years,
        "orgs": [{"org": org, "count": count} for org, count in orgs],
        "last_import": None if last_import is None else {
            "created_at": last_import.created_at, "filename": last_import.filename,
            "username": last_import.username, "rows": last_import.rows_total},
    }


@router.get("/summary", summary="Сводная аналитика заявок")
def summary(year: int | None = Query(None, ge=2000, le=2100), org: str | None = None,
            months: int | None = Query(None, ge=1, le=120),
            db: Session = Depends(get_db), user: User = Depends(read)):
    """Без права на персональные данные — без разбивки по ответственным сотрудникам (ФИО)."""
    personal = access.effective(user).allows("personal")
    return cached_json(db, [SERVICE], ("naumen.summary", year, org, months, personal),
                       lambda: _summary(db, year, org, months, personal))


def _summary(db: Session, year: int | None, org: str | None, months: int | None, personal: bool = True) -> dict:
    stmt = select(NaumenTicket).order_by(NaumenTicket.registered_at)
    if year:
        stmt = stmt.where(extract("year", NaumenTicket.registered_at) == year)
    if org:
        stmt = stmt.where(NaumenTicket.org == org)
    tickets = list(db.scalars(stmt))
    if months:
        tickets = naumen_service.last_months_filter(tickets, months)
    data = naumen_service.summary(tickets)
    if not personal and not data.get("empty"):
        data["responsibles"] = []
        data["responsibles_hidden"] = True
    return data


@router.get("/match", summary="Отчёт ТП в сравнении с заявками Naumen")
def match(db: Session = Depends(get_db), _: User = Depends(read)):
    def compute():
        rows = list(db.scalars(select(TpWeeklyReport).order_by(TpWeeklyReport.year, TpWeeklyReport.week)))
        return naumen_service.match(rows, list(db.scalars(select(NaumenTicket))))

    return cached_json(db, [SERVICE], ("naumen.match",), compute)


@router.post("/import", response_model=ImportResult, summary="Загрузить выгрузку Naumen (xlsx)")
async def import_tickets(request: Request, file: UploadFile = File(...),
                         mode: Literal["merge", "replace"] = Form("merge"),
                         db: Session = Depends(get_db), user: User = Depends(manage)):
    """merge — заявки сопоставляются по номеру: новые добавляются, известные обновляются;
    replace — все заявки заменяются содержимым файла."""
    raw = await read_upload(file)
    records, skipped = naumen_service.parse_xlsx(raw)
    result, _ = naumen_service.apply_import(db, user, records, skipped, mode, file.filename or "", request)
    db.commit()
    return ImportResult(dataset="naumen", mode=mode, rows_total=result["summary"]["rows"],
                        rows_created=result["created"], rows_updated=result["updated"],
                        rows_skipped=result["skipped"], message=result["message"])
