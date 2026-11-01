"""Техническая поддержка: недельный отчёт, импорт и экспорт, настройки дашборда."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.errors import Conflict, NotFound, ValidationFailed
from ...models import TP_METRIC_COLUMNS, DataImport, ServiceSetting, TpWeeklyReport, User
from ...schemas.common import ImportResult, Ok
from ...schemas.settings import SettingValue
from ...schemas.tp import TpColumnOut, TpReportIn, TpReportOut, TpReportPatch
from ...services import audit
from ...services import tp as tp_service
from ...services.cache import cached_json
from ..deps import require_service
from ..uploads import file_response, read_upload

router = APIRouter(prefix="/api/tp", tags=["Техподдержка: недельный отчёт"])
SERVICE = "tech"
read = require_service(SERVICE, "viewer")
edit = require_service(SERVICE, "editor")
manage = require_service(SERVICE, "manager")

SETTING_KEYS = {"block_settings", "dashboard"}


def _ordered(db: Session, year: int | None = None) -> list[TpWeeklyReport]:
    stmt = select(TpWeeklyReport).order_by(TpWeeklyReport.year, TpWeeklyReport.week)
    if year:
        stmt = stmt.where(TpWeeklyReport.year == year)
    return list(db.scalars(stmt))


def _get(db: Session, report_id: int) -> TpWeeklyReport:
    row = db.get(TpWeeklyReport, report_id)
    if row is None:
        raise NotFound("Неделя отчёта не найдена")
    return row


def _ensure_unique(db: Session, year: int, week: int, exclude_id: int | None = None) -> None:
    stmt = select(TpWeeklyReport.id).where(TpWeeklyReport.year == year, TpWeeklyReport.week == week)
    if exclude_id:
        stmt = stmt.where(TpWeeklyReport.id != exclude_id)
    if db.scalar(stmt):
        raise Conflict(f"Неделя {year}-W{week:02d} уже есть в отчёте", fields={"week": "Неделя уже заполнена"})


@router.get("/columns", response_model=list[TpColumnOut], summary="Показатели отчёта")
def columns(db: Session = Depends(get_db), _: User = Depends(read)):
    return cached_json(db, [SERVICE], ("tp.columns",), _columns)


def _columns():
    return [TpColumnOut(key=k, label=label, group=g, group_label=tp_service.TP_GROUPS[g], unit=u)
            for k, label, g, u in tp_service.COLUMN_META]


@router.get("/reports", response_model=list[TpReportOut], summary="Недели отчёта")
def list_reports(year: int | None = None, db: Session = Depends(get_db), _: User = Depends(read)):
    return cached_json(db, [SERVICE], ("tp.reports", year),
                       lambda: [tp_service.row_to_dict(r) for r in _ordered(db, year)])


@router.post("/reports", response_model=TpReportOut, status_code=201, summary="Добавить неделю")
def create_report(body: TpReportIn, request: Request, db: Session = Depends(get_db), user: User = Depends(edit)):
    _ensure_unique(db, body.year, body.week)
    row = TpWeeklyReport(**body.model_dump())
    db.add(row)
    db.flush()
    audit.record(db, user, service_key=SERVICE, entity_type="tp_week", entity_id=row.id, action="create",
                 summary=f"Добавлена неделя {row.period}", request=request)
    db.commit()
    return tp_service.row_to_dict(row)


@router.patch("/reports/{report_id}", response_model=TpReportOut, summary="Изменить неделю")
def update_report(report_id: int, body: TpReportPatch, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(edit)):
    row = _get(db, report_id)
    fields = body.model_dump(exclude_unset=True)
    year, week = fields.get("year") or row.year, fields.get("week") or row.week
    if (year, week) != (row.year, row.week):
        _ensure_unique(db, year, week, row.id)
    before = tp_service.row_to_dict(row)
    for key, value in fields.items():
        if key in ("year", "week") and value is None:
            continue
        setattr(row, key, "" if key == "note" and value is None else value)
    db.flush()
    b, a = audit.diff({k: before[k] for k in fields}, {k: getattr(row, k) for k in fields})
    if a:
        audit.record(db, user, service_key=SERVICE, entity_type="tp_week", entity_id=row.id, action="update",
                     summary=f"Изменена неделя {row.period}", before=b, after=a, request=request)
    db.commit()
    return tp_service.row_to_dict(row)


@router.delete("/reports/{report_id}", response_model=Ok, summary="Удалить неделю")
def delete_report(report_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(edit)):
    row = _get(db, report_id)
    audit.record(db, user, service_key=SERVICE, entity_type="tp_week", entity_id=row.id, action="delete",
                 summary=f"Удалена неделя {row.period}", before=tp_service.row_to_dict(row), request=request)
    db.delete(row)
    db.commit()
    return Ok(message="Неделя удалена")


@router.post("/reports/import", response_model=ImportResult, summary="Загрузить отчёт из xlsx или csv")
async def import_reports(request: Request, file: UploadFile = File(...),
                         mode: Literal["merge", "replace"] = Form("merge"),
                         db: Session = Depends(get_db), user: User = Depends(manage)):
    """merge — добавить новые недели и обновить совпадающие; replace — заменить отчёт целиком."""
    raw = await read_upload(file)
    records, skipped = tp_service.parse_upload(file.filename or "", raw)
    existing = {(r.year, r.week): r for r in _ordered(db)}
    created = updated = 0
    if mode == "replace":
        for row in existing.values():
            db.delete(row)
        db.flush()
        existing = {}
    for rec in records:
        row = existing.get((rec["year"], rec["week"]))
        values = {k: rec.get(k) for k in TP_METRIC_COLUMNS}
        if row is None:
            db.add(TpWeeklyReport(year=rec["year"], week=rec["week"], note=rec.get("note") or "", **values))
            created += 1
        else:
            for key, value in values.items():
                setattr(row, key, value)
            if rec.get("note") is not None:
                row.note = rec["note"]
            updated += 1
    db.add(DataImport(service_key=SERVICE, dataset="tp_weekly", filename=(file.filename or "")[:300], mode=mode,
                      rows_total=len(records) + skipped, rows_created=created, rows_updated=updated,
                      rows_skipped=skipped, user_id=user.id, username=user.username))
    audit.record(db, user, service_key=SERVICE, entity_type="tp_week", action="import",
                 summary=f"Загружен отчёт ТП «{file.filename}»: новых {created}, обновлено {updated}",
                 after={"mode": mode, "created": created, "updated": updated, "skipped": skipped}, request=request)
    db.commit()
    message = f"Новых недель: {created}, обновлено: {updated}"
    if skipped:
        message += f", пропущено строк: {skipped}"
    return ImportResult(dataset="tp_weekly", mode=mode, rows_total=len(records) + skipped, rows_created=created,
                        rows_updated=updated, rows_skipped=skipped, message=message)


@router.get("/reports/export.csv", summary="Выгрузить отчёт в CSV")
def export_csv(db: Session = Depends(get_db), _: User = Depends(read)):
    return file_response(tp_service.export_csv(_ordered(db)), "Отчёт ТП по неделям.csv")


@router.get("/reports/export.xlsx", summary="Выгрузить отчёт в Excel (формат исходного отчёта)")
def export_xlsx(db: Session = Depends(get_db), _: User = Depends(read)):
    return file_response(tp_service.export_xlsx(_ordered(db)), "Итоговый отчёт ТП по неделям.xlsx")


@router.get("/settings/{key}", summary="Настройка дашборда ТП")
def get_setting(key: str, db: Session = Depends(get_db), _: User = Depends(read)) -> Any:
    if key not in SETTING_KEYS:
        raise NotFound("Неизвестная настройка")
    row = db.get(ServiceSetting, (SERVICE, key))
    return {"key": key, "value": row.value if row else {}}


@router.put("/settings/{key}", summary="Сохранить настройку дашборда ТП")
def put_setting(key: str, body: SettingValue, request: Request, db: Session = Depends(get_db),
                user: User = Depends(manage)) -> Any:
    if key not in SETTING_KEYS:
        raise NotFound("Неизвестная настройка")
    if not isinstance(body.value, dict):
        raise ValidationFailed("Значение настройки — объект")
    row = db.get(ServiceSetting, (SERVICE, key))
    if row is None:
        row = ServiceSetting(service_key=SERVICE, key=key)
        db.add(row)
    before = row.value
    row.value = body.value
    row.updated_by_id = user.id
    audit.record(db, user, service_key=SERVICE, entity_type="service_setting", entity_id=key, action="update",
                 summary=f"Изменена настройка ТП «{key}»", before={"value": before}, after={"value": body.value},
                 request=request)
    db.commit()
    return {"key": key, "value": row.value}
