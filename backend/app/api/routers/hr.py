"""Служба персонала: месяцы, метрики, приёмы и увольнения, заметки, аналитика, цели."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...core.db import get_db, utcnow
from ...core.errors import Conflict, NotFound, ValidationFailed
from ...models import HrEmployeeEvent, HrMetricValue, HrMonth, HrMonthNote, HrTarget, User
from ...schemas.common import Ok
from ...schemas.hr import (
    EventIn,
    EventOut,
    MetricDefinitionOut,
    MetricValueIn,
    MonthCreateIn,
    MonthListItem,
    MonthPatchIn,
    NoteIn,
    NoteOut,
    TargetIn,
    TargetPatchIn,
)
from ...services import access, audit
from ...services import hr as hr_service
from ...services.cache import cached_json
from ..deps import require_service
from ..uploads import file_response

router = APIRouter(prefix="/api/hr", tags=["Служба персонала"])
SERVICE = "hr"
read = require_service(SERVICE, "viewer")
edit = require_service(SERVICE, "editor")
manage = require_service(SERVICE, "manager")


def _event_out(e: HrEmployeeEvent, month_key: str | None = None) -> EventOut:
    return EventOut(id=e.id, month_key=month_key or e.month_record.key, event_type=e.event_type,
                    event_date=e.event_date, full_name=e.full_name, position=e.position,
                    department=e.department, employment_type=e.employment_type, reason=e.reason)


def _check_event_date(month: HrMonth, body: EventIn) -> None:
    if (body.event_date.year, body.event_date.month) != (month.year, month.month):
        raise ValidationFailed(f"Дата должна относиться к месяцу «{month.label}»",
                               fields={"event_date": "Дата вне месяца"})


# ---------- справочники ----------

@router.get("/metrics", response_model=list[MetricDefinitionOut], summary="Метрики службы персонала")
def metric_definitions(db: Session = Depends(get_db), _: User = Depends(read)):
    return cached_json(db, [SERVICE], ("hr.metrics",),
                       lambda: [MetricDefinitionOut.model_validate(d) for d in hr_service.definitions(db)])


def _scope_key(user: User) -> tuple | None:
    scope = access.department_scope(user)
    return None if scope is None else tuple(sorted(scope))


@router.get("/departments", summary="Подразделения, встречающиеся в реестре")
def departments(db: Session = Depends(get_db), user: User = Depends(read)):
    def compute():
        scope = access.department_scope(user)
        names = sorted({d for d in db.scalars(select(HrEmployeeEvent.department).distinct()) if d})
        return [n for n in names if n in scope] if scope is not None else names

    return cached_json(db, [SERVICE], ("hr.departments", _scope_key(user)), compute)


# ---------- месяцы ----------

@router.get("/months", response_model=list[MonthListItem], summary="Месяцы с данными")
def list_months(db: Session = Depends(get_db), user: User = Depends(read)):
    def compute():
        scope = access.department_scope(user)
        total = len(hr_service.definitions(db))
        out = []
        for m in hr_service.months_sorted(db):
            hired, fired = hr_service.month_counts(m, scope)
            out.append(MonthListItem(key=m.key, label=m.label, year=m.year, month=m.month, comment=m.comment,
                                     hired=hired, fired=fired, total_metrics=total, updated_at=m.updated_at,
                                     filled_metrics=sum(1 for v in m.values if v.value is not None)))
        return out

    return cached_json(db, [SERVICE], ("hr.months", _scope_key(user)), compute)


@router.post("/months", response_model=MonthListItem, status_code=201, summary="Добавить месяц")
def create_month(body: MonthCreateIn, request: Request, db: Session = Depends(get_db), user: User = Depends(edit)):
    if db.scalar(select(HrMonth.id).where(HrMonth.year == body.year, HrMonth.month == body.month)):
        raise Conflict("Этот месяц уже добавлен")
    month = HrMonth(year=body.year, month=body.month, comment=body.comment)
    db.add(month)
    db.flush()
    audit.record(db, user, service_key=SERVICE, entity_type="hr_month", entity_id=month.key, action="create",
                 summary=f"Добавлен месяц {month.label}", request=request)
    db.commit()
    return MonthListItem(key=month.key, label=month.label, year=month.year, month=month.month,
                         comment=month.comment, hired=0, fired=0, filled_metrics=0,
                         total_metrics=len(hr_service.definitions(db)), updated_at=month.updated_at)


@router.get("/months/{key}", summary="Месяц: метрики, приёмы и увольнения, заметки")
def get_month(key: str, db: Session = Depends(get_db), user: User = Depends(read)):
    month = hr_service.get_month(db, key, full=True)
    previous = db.scalar(select(HrMonth).where(
        or_(HrMonth.year < month.year, (HrMonth.year == month.year) & (HrMonth.month < month.month)))
        .order_by(HrMonth.year.desc(), HrMonth.month.desc()).limit(1))
    scope = access.department_scope(user)
    events = hr_service.visible_events(month.events, scope)
    return {
        "key": month.key, "label": month.label, "year": month.year, "month": month.month,
        "comment": month.comment, "updated_at": month.updated_at,
        "previous_key": previous.key if previous else None,
        "metrics": hr_service.month_metrics(db, month, previous),
        "events": [_event_out(e, month.key) for e in events],
        "notes": [NoteOut(id=n.id, content=n.content, created_at=n.created_at,
                          author=n.author.full_name if n.author else "") for n in month.notes],
        "department_scope": sorted(scope) if scope is not None else None,
    }


@router.patch("/months/{key}", response_model=Ok, summary="Изменить комментарий месяца")
def patch_month(key: str, body: MonthPatchIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(edit)):
    month = hr_service.get_month(db, key)
    before = month.comment
    month.comment = body.comment
    audit.record(db, user, service_key=SERVICE, entity_type="hr_month", entity_id=month.key, action="update",
                 summary=f"Изменён комментарий к месяцу {month.label}", before={"comment": before},
                 after={"comment": month.comment}, request=request)
    db.commit()
    return Ok(message="Комментарий сохранён")


@router.delete("/months/{key}", response_model=Ok, summary="Удалить месяц со всеми данными")
def delete_month(key: str, request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    month = hr_service.get_month(db, key, full=True)
    audit.record(db, user, service_key=SERVICE, entity_type="hr_month", entity_id=month.key, action="delete",
                 summary=f"Удалён месяц {month.label}",
                 before={"metrics": len(month.values), "events": len(month.events), "notes": len(month.notes)},
                 request=request)
    db.delete(month)
    db.commit()
    return Ok(message=f"Месяц {month.label} удалён")


@router.put("/months/{key}/metrics", response_model=Ok, summary="Сохранить значения метрик месяца")
def save_metrics(key: str, body: list[MetricValueIn], request: Request, db: Session = Depends(get_db),
                 user: User = Depends(edit)):
    month = hr_service.get_month(db, key, full=True)
    known = {d.key for d in hr_service.definitions(db, active_only=False)}
    unknown = sorted({item.metric_key for item in body} - known)
    if unknown:
        raise ValidationFailed(f"Неизвестные метрики: {', '.join(unknown)}")
    current = {v.metric_key: v for v in month.values}
    before, after = {}, {}
    for item in body:
        row = current.get(item.metric_key)
        if row is None:
            if item.value is None and not item.source_note:
                continue
            db.add(HrMetricValue(month_id=month.id, metric_key=item.metric_key, value=item.value,
                                 source_note=item.source_note))
            before[item.metric_key], after[item.metric_key] = None, item.value
        elif row.value != item.value or row.source_note != item.source_note:
            before[item.metric_key], after[item.metric_key] = row.value, item.value
            row.value, row.source_note = item.value, item.source_note
    if after:
        month.updated_at = utcnow()
        audit.record(db, user, service_key=SERVICE, entity_type="hr_metrics", entity_id=month.key, action="update",
                     summary=f"Изменены метрики за {month.label}: {len(after)}", before=before, after=after,
                     request=request)
    db.commit()
    return Ok(message=f"Сохранено значений: {len(after)}" if after else "Изменений нет")


# ---------- приёмы и увольнения ----------

def query_events(month: str = "", year: int | None = None, event_type: str = Query("", pattern="^(|hired|fired)$"),
                department: str = "", search: str = "", db: Session = Depends(get_db), user: User = Depends(read)):
    stmt = select(HrEmployeeEvent).join(HrMonth).order_by(HrEmployeeEvent.event_date.desc(), HrEmployeeEvent.id.desc())
    if month:
        y, m = hr_service.parse_month_key(month)
        stmt = stmt.where(HrMonth.year == y, HrMonth.month == m)
    if year:
        stmt = stmt.where(HrMonth.year == year)
    if event_type:
        stmt = stmt.where(HrEmployeeEvent.event_type == event_type)
    if department:
        stmt = stmt.where(HrEmployeeEvent.department == department)
    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(HrEmployeeEvent.full_name).like(like),
                              func.lower(HrEmployeeEvent.position).like(like)))
    return [_event_out(e) for e in hr_service.visible_events(list(db.scalars(stmt)), access.department_scope(user))]



@router.get("/events", response_model=list[EventOut], summary="Реестр приёмов и увольнений")
def list_events(month: str = "", year: int | None = None, event_type: str = Query("", pattern="^(|hired|fired)$"),
                department: str = "", search: str = "", db: Session = Depends(get_db), user: User = Depends(read)):
    key = ("hr.events", month, year, event_type, department, search.strip().lower(), _scope_key(user))
    return cached_json(db, [SERVICE], key,
                       lambda: query_events(month, year, event_type, department, search, db, user))


@router.get("/events/export.xlsx", summary="Выгрузить реестр в Excel")
def export_events(month: str = "", year: int | None = None, event_type: str = "", department: str = "",
                  search: str = "", db: Session = Depends(get_db), user: User = Depends(read)):
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Font

    events = query_events(month, year, event_type, department, search, db, user)
    wb = Workbook()
    ws = wb.active
    ws.title = "Реестр"
    ws.append(["Месяц", "Событие", "Дата", "ФИО", "Должность", "Подразделение", "Тип занятости", "Причина"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for e in events:
        ws.append([e.month_key, "Приём" if e.event_type == "hired" else "Увольнение", e.event_date, e.full_name,
                   e.position, e.department, e.employment_type, e.reason])
    for column, width in zip("ABCDEFGH", (10, 12, 12, 38, 40, 32, 16, 30), strict=False):
        ws.column_dimensions[column].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return file_response(buf.getvalue(), "Реестр приёмов и увольнений.xlsx")


@router.post("/months/{key}/events", response_model=EventOut, status_code=201, summary="Добавить приём или увольнение")
def add_event(key: str, body: EventIn, request: Request, db: Session = Depends(get_db), user: User = Depends(edit)):
    month = hr_service.get_month(db, key)
    _check_event_date(month, body)
    event = HrEmployeeEvent(month_id=month.id, **body.model_dump())
    db.add(event)
    db.flush()
    kind = "Приём" if event.event_type == "hired" else "Увольнение"
    audit.record(db, user, service_key=SERVICE, entity_type="hr_event", entity_id=event.id, action="create",
                 summary=f"{kind}: {event.full_name}", after=body.model_dump(), request=request)
    db.commit()
    return _event_out(event, month.key)


@router.patch("/events/{event_id}", response_model=EventOut, summary="Изменить запись реестра")
def update_event(event_id: int, body: EventIn, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(edit)):
    event = db.get(HrEmployeeEvent, event_id)
    if event is None:
        raise NotFound("Запись реестра не найдена")
    _check_event_date(event.month_record, body)
    before = {k: getattr(event, k) for k in body.model_dump()}
    for k, v in body.model_dump().items():
        setattr(event, k, v)
    b, a = audit.diff(before, body.model_dump())
    if a:
        audit.record(db, user, service_key=SERVICE, entity_type="hr_event", entity_id=event.id, action="update",
                     summary=f"Изменена запись: {event.full_name}", before=b, after=a, request=request)
    db.commit()
    return _event_out(event)


@router.delete("/events/{event_id}", response_model=Ok, summary="Удалить запись реестра")
def delete_event(event_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(edit)):
    event = db.get(HrEmployeeEvent, event_id)
    if event is None:
        raise NotFound("Запись реестра не найдена")
    audit.record(db, user, service_key=SERVICE, entity_type="hr_event", entity_id=event.id, action="delete",
                 summary=f"Удалена запись: {event.full_name}",
                 before={"full_name": event.full_name, "event_type": event.event_type,
                         "event_date": event.event_date}, request=request)
    db.delete(event)
    db.commit()
    return Ok(message="Запись удалена")


# ---------- заметки ----------

@router.post("/months/{key}/notes", response_model=NoteOut, status_code=201, summary="Добавить заметку к месяцу")
def add_note(key: str, body: NoteIn, request: Request, db: Session = Depends(get_db), user: User = Depends(edit)):
    month = hr_service.get_month(db, key)
    note = HrMonthNote(month_id=month.id, author_id=user.id, content=body.content)
    db.add(note)
    db.flush()
    audit.record(db, user, service_key=SERVICE, entity_type="hr_note", entity_id=note.id, action="create",
                 summary=f"Заметка к месяцу {month.label}", after={"content": body.content[:300]}, request=request)
    db.commit()
    return NoteOut(id=note.id, content=note.content, created_at=note.created_at, author=user.full_name)


@router.delete("/notes/{note_id}", response_model=Ok, summary="Удалить заметку")
def delete_note(note_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(edit)):
    note = db.get(HrMonthNote, note_id)
    if note is None:
        raise NotFound("Заметка не найдена")
    audit.record(db, user, service_key=SERVICE, entity_type="hr_note", entity_id=note.id, action="delete",
                 summary="Удалена заметка", before={"content": note.content[:300]}, request=request)
    db.delete(note)
    db.commit()
    return Ok(message="Заметка удалена")


# ---------- аналитика ----------

@router.get("/analytics/dashboard", summary="Данные дашборда службы персонала")
def analytics_dashboard(months: str = "", db: Session = Depends(get_db), user: User = Depends(read)):
    keys = [k for k in months.split(",") if k]
    for k in keys:
        hr_service.parse_month_key(k)
    return cached_json(db, [SERVICE], ("hr.dashboard", tuple(keys), _scope_key(user)),
                       lambda: hr_service.dashboard(db, keys, access.department_scope(user)))


@router.get("/analytics/summary", summary="Сводка по периодам")
def analytics_summary(period_type: str = "quarter", db: Session = Depends(get_db), user: User = Depends(read)):
    if period_type not in hr_service.PERIOD_TYPES:
        hr_service.period_summary(db, period_type, None)  # единое сообщение об ошибке
    return cached_json(db, [SERVICE], ("hr.summary", period_type, _scope_key(user)),
                       lambda: hr_service.period_summary(db, period_type, access.department_scope(user)))


# ---------- цели ----------

@router.get("/targets", summary="Цели и бенчмарки")
def list_targets(db: Session = Depends(get_db), _: User = Depends(read)):
    return cached_json(db, [SERVICE], ("hr.targets",), lambda: hr_service.target_rows(db))


@router.post("/targets", status_code=201, summary="Добавить цель")
def create_target(body: TargetIn, request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    if body.metric_key not in {d.key for d in hr_service.definitions(db)}:
        raise ValidationFailed("Метрика не найдена", fields={"metric_key": "Неизвестная метрика"})
    if db.scalar(select(HrTarget.id).where(HrTarget.metric_key == body.metric_key, HrTarget.year == body.year)):
        raise Conflict(f"Цель по этой метрике на {body.year} год уже задана")
    target = HrTarget(**body.model_dump())
    if not target.label:
        target.label = f"Цель {body.year}" if body.target_value is not None else f"{body.year} год"
    db.add(target)
    db.flush()
    audit.record(db, user, service_key=SERVICE, entity_type="hr_target", entity_id=target.id, action="create",
                 summary=f"Цель «{target.metric_key}» на {target.year}", after=body.model_dump(), request=request)
    db.commit()
    return next(r for r in hr_service.target_rows(db) if r["id"] == target.id)


@router.patch("/targets/{target_id}", summary="Изменить цель")
def update_target(target_id: int, body: TargetPatchIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(manage)):
    target = db.get(HrTarget, target_id)
    if target is None:
        raise NotFound("Цель не найдена")
    fields = body.model_dump(exclude_unset=True)
    before = {k: getattr(target, k) for k in fields}
    for k, v in fields.items():
        setattr(target, k, v if v is not None or k in ("target_value", "reference_value") else "")
    b, a = audit.diff(before, {k: getattr(target, k) for k in fields})
    if a:
        audit.record(db, user, service_key=SERVICE, entity_type="hr_target", entity_id=target.id, action="update",
                     summary=f"Изменена цель «{target.metric_key}» на {target.year}", before=b, after=a,
                     request=request)
    db.commit()
    return next(r for r in hr_service.target_rows(db) if r["id"] == target.id)


@router.delete("/targets/{target_id}", response_model=Ok, summary="Удалить цель")
def delete_target(target_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    target = db.get(HrTarget, target_id)
    if target is None:
        raise NotFound("Цель не найдена")
    audit.record(db, user, service_key=SERVICE, entity_type="hr_target", entity_id=target.id, action="delete",
                 summary=f"Удалена цель «{target.metric_key}» на {target.year}", request=request)
    db.delete(target)
    db.commit()
    return Ok(message="Цель удалена")
