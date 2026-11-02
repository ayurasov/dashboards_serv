"""Сквозные отчёты (ADR-0010): отчёт по уровням структуры, подразделение с трендами, периоды, каталог
показателей, ввод и загрузка значений, заметки о статусе, подразделения служб, карточка «Обзора».

Отчёт видит любой вошедший пользователь — в пределах своей области, глубины детализации и классов
данных (ADR-0009). Каталог ведёт полномочие reports.manage (или администратор); значения вводят
пользователи с уровнем «Ввод данных» к службе-владельцу показателя в своей области структуры.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ...core.db import get_db
from ...models import User
from ...schemas.common import Ok
from ...schemas.reports import (
    IndicatorCreateIn,
    IndicatorOut,
    IndicatorUpdateIn,
    NoteIn,
    NoteResultOut,
    PeriodsOut,
    ReportSettingsOut,
    ReportsMetaOut,
    ReportSummaryOut,
    ScorecardOut,
    ServiceUnitsIn,
    UnitReportOut,
    ValuesImportIn,
    ValuesImportOut,
    ValuesIn,
    ValuesListOut,
    ValuesSaveOut,
)
from ...services import report_admin, reports
from ..deps import active_user, require_capability
from .org import _conflict, _flag, _payload, _validate

log = logging.getLogger("app.reports")
router = APIRouter(prefix="/api/reports", tags=["Сквозные отчёты"])
manage = require_capability("reports.manage")
PERIOD = r"^\d{4}-(0[1-9]|1[0-2])$"
PERIOD_HINT = "ГГГГ-ММ; по умолчанию — последний период с данными"
IMPORT_ERRORS = "Исправьте ошибки в файле — ничего не записано"
CONFLICT_RESPONSE = {409: {"description": "План с ошибками (code: import_has_errors) — ничего не записано"}}
IMPORT_BODY = {
    "requestBody": {"content": {
        "multipart/form-data": {"schema": {"type": "object", "properties": {
            "file": {"type": "string", "format": "binary"}, "apply": {"type": "boolean"}}}},
        "application/json": {"schema": ValuesImportIn.model_json_schema()},
    }},
}


# ---------------------------------------------------------------- отчёт

@router.get("/scorecard", response_model=ScorecardOut, summary="Сквозной отчёт за период",
            description="Вершины области пользователя (или выбранный видимый уровень root) с видимыми уровнями до "
                        "предела глубины: статус, нарушения полноты, показатели, объяснение, «детализация "
                        "недоступна», заметка; сведения о доступе. Показатели недоступных классов данных в ответ "
                        "не попадают, статусы считаются по доступным.")
def scorecard(period: str | None = Query(None, pattern=PERIOD, description=PERIOD_HINT),
              root: int | None = Query(None, ge=1, description="Видимое подразделение вместо вершин области"),
              db: Session = Depends(get_db), user: User = Depends(active_user)):
    return reports.scorecard_response(db, user, period, root)


@router.get("/units/{unit_id}", response_model=UnitReportOut, summary="Подразделение в отчёте: тренды за 12 месяцев",
            responses={403: {"description": "Вне области или глубже детализации (code: unit_out_of_scope)"}})
def unit(unit_id: int = Path(ge=1), period: str | None = Query(None, pattern=PERIOD, description=PERIOD_HINT),
         db: Session = Depends(get_db), user: User = Depends(active_user)):
    return reports.unit_response(db, user, unit_id, period)


@router.get("/periods", response_model=PeriodsOut, summary="Периоды с данными")
def periods(db: Session = Depends(get_db), user: User = Depends(active_user)):
    return reports.periods_data(db, user)


@router.get("/summary", response_model=ReportSummaryOut, summary="Карточка «Обзора»: статус области пользователя")
def summary(period: str | None = Query(None, pattern=PERIOD, description=PERIOD_HINT), db: Session = Depends(get_db),
            user: User = Depends(active_user)):
    return reports.summary_response(db, user, period)


@router.get("/meta", response_model=ReportsMetaOut, summary="Справочник для каталога: источники, правила, классы")
def meta(db: Session = Depends(get_db), _: User = Depends(active_user)):
    return report_admin.meta(db)


# ---------------------------------------------------------------- каталог показателей

@router.get("/indicators", response_model=list[IndicatorOut], summary="Каталог показателей",
            description="С полномочием «Сквозные отчёты» — весь каталог, иначе — активные показатели доступных "
                        "классов данных.")
def list_indicators(db: Session = Depends(get_db), user: User = Depends(active_user)):
    return report_admin.list_indicators(db, user)


@router.post("/indicators", response_model=IndicatorOut, status_code=201, summary="Добавить показатель")
def create_indicator(body: IndicatorCreateIn, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(manage)):
    row = report_admin.create_indicator(db, user, body, request)
    db.commit()
    return report_admin.indicator_out(row)


@router.patch("/indicators/{indicator_id}", response_model=IndicatorOut, summary="Изменить показатель")
def update_indicator(indicator_id: int, body: IndicatorUpdateIn, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(manage)):
    row = report_admin.update_indicator(db, user, report_admin.get_indicator(db, indicator_id), body, request)
    db.commit()
    return report_admin.indicator_out(row, report_admin.values_counts(db).get(row.id, 0))


@router.delete("/indicators/{indicator_id}", response_model=Ok, summary="Удалить показатель",
               responses={409: {"description": "Есть сохранённые значения (code: indicator_has_values)"}})
def delete_indicator(indicator_id: int, request: Request, force: bool = Query(False, description="Вместе со "
                                                                                                "значениями"),
                     db: Session = Depends(get_db), user: User = Depends(manage)):
    row = report_admin.get_indicator(db, indicator_id)
    name = row.name
    count = report_admin.delete_indicator(db, user, row, force=force, request=request)
    db.commit()
    return Ok(message=f"Показатель «{name}» удалён" + (f" вместе с {count} значениями" if count else ""))


# ---------------------------------------------------------------- ввод значений

@router.get("/values", response_model=ValuesListOut, summary="Ввод показателей: форма за месяц",
            responses={403: {"description": "Нет прав на ввод ни одного показателя (code: entry_forbidden)"}})
def get_values(period: str = Query(pattern=PERIOD, description="ГГГГ-ММ"),
               indicator: str | None = Query(None, max_length=200, description="Ключ, id или название"),
               unit: int | None = Query(None, ge=1), db: Session = Depends(get_db), user: User = Depends(active_user)):
    return report_admin.values_listing(db, user, period, indicator, unit)


@router.put("/values", response_model=ValuesSaveOut, summary="Сохранить значения за месяц")
def put_values(body: ValuesIn, request: Request, db: Session = Depends(get_db), user: User = Depends(active_user)):
    result = report_admin.save_values(db, user, body.period, body.items, request)
    db.commit()
    return result


def _import_job(db: Session, user: User, rows: list, apply: bool, filename: str, request: Request):
    if not apply:
        plan, _ = report_admin.plan_import(db, user, rows)
        return {**plan, "applied": False}
    result, applied = report_admin.apply_import(db, user, rows, filename, request)
    if not applied:
        db.rollback()
        return _conflict(result, IMPORT_ERRORS)
    db.commit()
    log.info("indicator values imported: %s", result["summary"])
    return result


@router.post("/values/import", response_model=ValuesImportOut, responses=CONFLICT_RESPONSE, openapi_extra=IMPORT_BODY,
             summary="Загрузить значения (Excel, CSV): проверка (apply=false) или применение",
             description="Столбцы: «Подразделение» (путь через «/» или код), «Показатель» (ключ или название), "
                         "«Период» (ГГГГ-ММ), «Значение», «Цель», «Комментарий», «Очистить». Пустая ячейка не "
                         "стирает сохранённое; «Очистить» = «да» (без значения, цели и комментария) удаляет "
                         "сохранённое значение за месяц (действие clear, в сводке cleared). Без изменений ничего "
                         "не записывается. Multipart: file, apply; или JSON: {content: текст CSV, apply}.")
async def import_values(request: Request, db: Session = Depends(get_db), user: User = Depends(active_user)):
    fields, file, raw = await _payload(request)
    if file is not None:
        apply, filename = _flag(fields.get("apply")), (file.filename or "")[:200]
        rows = await run_in_threadpool(report_admin.parse_upload, file.filename or "", raw)
    else:
        body = _validate(ValuesImportIn, fields)
        apply, filename = body.apply, ""
        rows = await run_in_threadpool(report_admin.parse_content, body.content)
    return await run_in_threadpool(_import_job, db, user, rows, apply, filename, request)


# ---------------------------------------------------------------- заметки и настройки

@router.put("/units/{unit_id}/note", response_model=NoteResultOut, summary="Заметка о статусе подразделения",
            description="Руководитель подразделения или полномочие «Сквозные отчёты»; status = null снимает заметку.")
def put_note(unit_id: int, body: NoteIn, request: Request, db: Session = Depends(get_db),
             user: User = Depends(active_user)):
    note = report_admin.save_note(db, user, unit_id, body, request)
    db.commit()
    return {"note": note}


@router.get("/settings", response_model=ReportSettingsOut, summary="Подразделения служб для вычисляемых показателей")
def get_settings(db: Session = Depends(get_db), _: User = Depends(active_user)):
    return report_admin.settings_out(db)


@router.put("/settings", response_model=ReportSettingsOut, summary="Изменить подразделения служб")
def put_settings(body: ServiceUnitsIn, request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    result = report_admin.save_settings(db, user, body, request)
    db.commit()
    return result

