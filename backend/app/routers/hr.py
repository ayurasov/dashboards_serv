"""HR data router: months, employees, metrics, notes, analytics."""
import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import (
    User, MonthRecord, EmployeeEvent, MetricValue, MetricDefinition,
    Note, RoleEnum, Benchmark
)
from ..deps import (
    get_current_user, require_edit, require_admin, require_metrics_edit, can_view_department
)
from ..schemas import (
    MonthCreate, MonthUpdate, MonthOut, EmployeeEventCreate, EmployeeEventOut,
    MetricValueIn, MetricValueOut, MetricDefinitionOut, NoteCreate, NoteOut,
    MonthAnalytics, PeriodSummary, MetricWithLight, BenchmarkOut, BenchmarkUpdate,
    BenchmarkCreate
)
from ..analytics import (
    get_months_sorted, month_label, metric_values_map, aggregate_months,
    months_in_period, period_label, traffic_light_for_metric, benchmark_rows
)
from ..audit import log_action

router = APIRouter(prefix="/api/hr", tags=["hr"])


def _serialize_month(mr: MonthRecord, user: User) -> dict:
    emps = mr.employees
    if user.role == RoleEnum.DEPT_VIEWER:
        emps = [e for e in emps if can_view_department(user, e.department)]
    return {
        "id": mr.id,
        "year": mr.year,
        "month": mr.month,
        "key": mr.key,
        "label": mr.label,
        "notes": mr.notes or "",
        "hired_count": len([e for e in mr.employees if e.event_type == "hired"]),
        "fired_count": len([e for e in mr.employees if e.event_type == "fired"]),
        "employees": emps,
        "metrics": mr.metric_values,
    }


# ---------- Months ----------

@router.get("/months", response_model=list[MonthOut])
def list_months(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    months = get_months_sorted(db)
    return [_serialize_month(m, user) for m in months]


@router.get("/months/{month_key}", response_model=MonthOut)
def get_month(month_key: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        y, m = month_key.split("-")
        y, m = int(y), int(m)
    except Exception:
        raise HTTPException(400, "Неверный формат месяца. Используйте YYYY-MM")
    mr = db.query(MonthRecord).filter(MonthRecord.year == y, MonthRecord.month == m).first()
    if not mr:
        raise HTTPException(404, "Месяц не найден")
    return _serialize_month(mr, user)


@router.post("/months", response_model=MonthOut)
def create_month(body: MonthCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    if not (1 <= body.month <= 12):
        raise HTTPException(400, "Месяц должен быть 1-12")
    existing = db.query(MonthRecord).filter(MonthRecord.year == body.year, MonthRecord.month == body.month).first()
    if existing:
        raise HTTPException(400, "Месяц уже существует")
    mr = MonthRecord(year=body.year, month=body.month, notes=body.notes)
    db.add(mr)
    db.flush()
    log_action(db, user, "month", mr.key, "create", after={"year": mr.year, "month": mr.month}, ip=request.client.host if request.client else "")
    db.commit()
    db.refresh(mr)
    return _serialize_month(mr, user)


@router.put("/months/{month_key}", response_model=MonthOut)
def update_month(month_key: str, body: MonthUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    try:
        y, m = month_key.split("-")
        y, m = int(y), int(m)
    except Exception:
        raise HTTPException(400, "Неверный формат месяца")
    mr = db.query(MonthRecord).filter(MonthRecord.year == y, MonthRecord.month == m).first()
    if not mr:
        raise HTTPException(404, "Месяц не найден")
    before = {"notes": mr.notes}
    if body.notes is not None:
        mr.notes = body.notes
    log_action(db, user, "month", mr.key, "update", before=before, after={"notes": mr.notes}, ip=request.client.host if request.client else "")
    db.commit()
    db.refresh(mr)
    return _serialize_month(mr, user)


@router.delete("/months/{month_key}")
def delete_month(month_key: str, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require_metrics_edit("hr"))):
    """Removes the month together with its metric values, employee events and notes."""
    try:
        y, m = month_key.split("-")
        y, m = int(y), int(m)
    except Exception:
        raise HTTPException(400, "Неверный формат месяца")
    mr = db.query(MonthRecord).filter(MonthRecord.year == y, MonthRecord.month == m).first()
    if not mr:
        raise HTTPException(404, "Месяц не найден")
    before = {"label": mr.label, "metrics": len(mr.metric_values), "employees": len(mr.employees)}
    log_action(db, user, "month", mr.key, "delete", before=before, ip=request.client.host if request.client else "")
    db.delete(mr)
    db.commit()
    return {"ok": True}


# ---------- Employees ----------

@router.post("/months/{month_key}/employees", response_model=EmployeeEventOut)
def add_employee(month_key: str, body: EmployeeEventCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    try:
        y, m = month_key.split("-")
        y, m = int(y), int(m)
    except Exception:
        raise HTTPException(400, "Неверный формат месяца")
    mr = db.query(MonthRecord).filter(MonthRecord.year == y, MonthRecord.month == m).first()
    if not mr:
        raise HTTPException(404, "Месяц не найден")
    if body.event_type not in ("hired", "fired"):
        raise HTTPException(400, "Тип должен быть 'hired' или 'fired'")
    emp = EmployeeEvent(month_record_id=mr.id, event_type=body.event_type, event_date=body.event_date,
                        full_name=body.full_name, position=body.position, department=body.department,
                        employment_type=body.employment_type)
    db.add(emp)
    db.flush()
    log_action(db, user, "employee", str(emp.id), "create", after={"name": emp.full_name, "type": emp.event_type}, ip=request.client.host if request.client else "")
    db.commit()
    db.refresh(emp)
    return emp


@router.put("/employees/{emp_id}", response_model=EmployeeEventOut)
def update_employee(emp_id: int, body: EmployeeEventCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    emp = db.query(EmployeeEvent).get(emp_id)
    if not emp:
        raise HTTPException(404, "Запись не найдена")
    before = {"name": emp.full_name, "position": emp.position, "department": emp.department}
    emp.event_type = body.event_type
    emp.event_date = body.event_date
    emp.full_name = body.full_name
    emp.position = body.position
    emp.department = body.department
    emp.employment_type = body.employment_type
    log_action(db, user, "employee", str(emp.id), "update", before=before, after={"name": emp.full_name}, ip=request.client.host if request.client else "")
    db.commit()
    db.refresh(emp)
    return emp


@router.delete("/employees/{emp_id}")
def delete_employee(emp_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    emp = db.query(EmployeeEvent).get(emp_id)
    if not emp:
        raise HTTPException(404, "Запись не найдена")
    log_action(db, user, "employee", str(emp.id), "delete", before={"name": emp.full_name}, ip=request.client.host if request.client else "")
    db.delete(emp)
    db.commit()
    return {"ok": True}


# ---------- Metrics ----------

@router.get("/metric-definitions", response_model=list[MetricDefinitionOut])
def list_metric_defs(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(MetricDefinition).order_by(MetricDefinition.sort_order).all()


@router.put("/months/{month_key}/metrics")
def set_month_metrics(month_key: str, body: list[MetricValueIn], request: Request, db: Session = Depends(get_db), user: User = Depends(require_metrics_edit("hr"))):
    try:
        y, m = month_key.split("-")
        y, m = int(y), int(m)
    except Exception:
        raise HTTPException(400, "Неверный формат месяца")
    mr = db.query(MonthRecord).filter(MonthRecord.year == y, MonthRecord.month == m).first()
    if not mr:
        raise HTTPException(404, "Месяц не найден")
    before = {mv.metric_key: mv.numeric_value for mv in mr.metric_values}
    # remove existing
    for mv in mr.metric_values:
        db.delete(mv)
    db.flush()
    for item in body:
        db.add(MetricValue(month_record_id=mr.id, metric_key=item.metric_key,
                           numeric_value=item.numeric_value, text_value=item.text_value,
                           source_note=item.source_note))
    log_action(db, user, "metrics", mr.key, "update", before={"values": before}, ip=request.client.host if request.client else "")
    db.commit()
    return {"ok": True}


# ---------- Notes ----------

@router.get("/months/{month_key}/notes", response_model=list[NoteOut])
def list_notes(month_key: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        y, m = month_key.split("-")
        y, m = int(y), int(m)
    except Exception:
        raise HTTPException(400, "Неверный формат месяца")
    mr = db.query(MonthRecord).filter(MonthRecord.year == y, MonthRecord.month == m).first()
    if not mr:
        raise HTTPException(404, "Месяц не найден")
    return mr.notes_rel


@router.post("/months/{month_key}/notes", response_model=NoteOut)
def add_note(month_key: str, body: NoteCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    try:
        y, m = month_key.split("-")
        y, m = int(y), int(m)
    except Exception:
        raise HTTPException(400, "Неверный формат месяца")
    mr = db.query(MonthRecord).filter(MonthRecord.year == y, MonthRecord.month == m).first()
    if not mr:
        raise HTTPException(404, "Месяц не найден")
    note = Note(month_record_id=mr.id, author_id=user.id, content=body.content)
    db.add(note)
    db.flush()
    log_action(db, user, "note", str(note.id), "create", after={"content": body.content[:200]}, ip=request.client.host if request.client else "")
    db.commit()
    db.refresh(note)
    return note


@router.delete("/notes/{note_id}")
def delete_note(note_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    note = db.query(Note).get(note_id)
    if not note:
        raise HTTPException(404, "Заметка не найдена")
    log_action(db, user, "note", str(note.id), "delete", before={"content": note.content[:200]}, ip=request.client.host if request.client else "")
    db.delete(note)
    db.commit()
    return {"ok": True}


# ---------- Analytics ----------

@router.get("/analytics/month/{month_key}", response_model=MonthAnalytics)
def month_analytics(month_key: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        y, m = month_key.split("-")
        y, m = int(y), int(m)
    except Exception:
        raise HTTPException(400, "Неверный формат месяца")
    mr = db.query(MonthRecord).filter(MonthRecord.year == y, MonthRecord.month == m).first()
    if not mr:
        raise HTTPException(404, "Месяц не найден")
    emps = mr.employees
    if user.role == RoleEnum.DEPT_VIEWER:
        emps = [e for e in emps if can_view_department(user, e.department)]
    hired = len([e for e in emps if e.event_type == "hired"])
    fired = len([e for e in emps if e.event_type == "fired"])
    # Every defined metric is reported, filled or not: an unfilled metric is a data
    # gap the service has to close, so it reads red instead of silently vanishing.
    values = {mv.metric_key: mv for mv in mr.metric_values}
    metrics = []
    for d in db.query(MetricDefinition).order_by(MetricDefinition.sort_order, MetricDefinition.id).all():
        mv = values.get(d.key)
        filled = mv is not None and mv.numeric_value is not None
        metrics.append(MetricWithLight(
            key=d.key, label=d.label, unit=d.unit, category=d.category,
            value=mv.numeric_value if mv else None,
            text_value=(mv.text_value if mv else None),
            source_note=(mv.source_note if mv else None) or "",
            direction=d.direction, filled=filled,
            light=traffic_light_for_metric(db, d.key, mv.numeric_value) if filled else "red",
        ))
    return MonthAnalytics(month_key=mr.key, label=mr.label, hired=hired, fired=fired,
                          net=hired - fired, metrics=metrics)


@router.get("/analytics/summary", response_model=list[PeriodSummary])
def period_summary(period_type: str = "quarter", from_period: str = "", to_period: str = "",
                   db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """`from_period` / `to_period` are period labels (e.g. «Q2 2026»). Omitting both
    returns every period, which is the historical behaviour."""
    if period_type not in ("quarter", "half", "year"):
        raise HTTPException(400, "Тип периода: quarter, half, year")
    months = get_months_sorted(db)
    years = sorted(set(m.year for m in months))
    results = []
    for year in years:
        if period_type == "quarter":
            indices = [1, 2, 3, 4]
        elif period_type == "half":
            indices = [1, 2]
        else:
            indices = [1]
        for idx in indices:
            ms = months_in_period(months, year, period_type, idx)
            if not ms:
                continue
            agg = aggregate_months(ms)
            results.append(PeriodSummary(
                label=period_label(year, period_type, idx),
                months_count=agg["months_count"],
                hired=agg["hired"], fired=agg["fired"], net=agg["net"],
                metrics=agg["metrics"],
            ))

    labels = [r.label for r in results]
    for bound in (from_period, to_period):
        if bound and bound not in labels:
            raise HTTPException(400, f"Период не найден: {bound}")
    lo = labels.index(from_period) if from_period else 0
    hi = labels.index(to_period) if to_period else len(results) - 1
    if lo > hi:
        lo, hi = hi, lo
    return results[lo:hi + 1]


@router.get("/benchmarks", response_model=list[BenchmarkOut])
def benchmarks(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return benchmark_rows(db)


@router.post("/benchmarks", response_model=BenchmarkOut)
def create_benchmark(body: BenchmarkCreate, request: Request,
                     db: Session = Depends(get_db), user: User = Depends(require_admin)):
    md = db.query(MetricDefinition).filter(MetricDefinition.key == body.metric_key).first()
    if not md:
        raise HTTPException(400, f"Метрика не найдена: {body.metric_key}")
    # The unique constraint is (metric_key, year); new targets are set for the current year.
    year = datetime.datetime.now().year
    if db.query(Benchmark).filter(Benchmark.metric_key == body.metric_key,
                                  Benchmark.year == year).first():
        raise HTTPException(400, f"Бенчмарк для этой метрики на {year} год уже существует")
    b = Benchmark(
        metric_key=body.metric_key,
        label=f"Цель {year}",
        year=year,
        # `value` is the legacy column the PDF turnover chart reads; keep it in
        # step with the target exactly as the update handler does.
        value=body.target_value,
        target_value=body.target_value,
        description=body.description,
        source=body.source,
    )
    db.add(b)
    db.flush()
    log_action(db, user, "benchmark", str(b.id), "create", before=None,
               after={"metric_key": b.metric_key, "year": b.year, "target_value": b.target_value},
               ip=request.client.host if request.client else "")
    db.commit()
    row = next((r for r in benchmark_rows(db) if r["id"] == b.id), None)
    if row is None:
        raise HTTPException(404, "Бенчмарк не найден")
    return row


@router.put("/benchmarks/{benchmark_id}", response_model=BenchmarkOut)
def update_benchmark(benchmark_id: int, body: BenchmarkUpdate, request: Request,
                     db: Session = Depends(get_db), user: User = Depends(require_admin)):
    b = db.query(Benchmark).get(benchmark_id)
    if not b:
        raise HTTPException(404, "Бенчмарк не найден")
    before = {"target_value": b.target_value}
    if body.target_value is not None:
        b.target_value = body.target_value
        # `value` is the legacy column the PDF turnover chart reads.
        b.value = body.target_value
    if body.description is not None:
        b.description = body.description
    if body.source is not None:
        b.source = body.source
    log_action(db, user, "benchmark", str(b.id), "update", before=before,
               after={"target_value": b.target_value}, ip=request.client.host if request.client else "")
    db.commit()
    row = next((r for r in benchmark_rows(db) if r["id"] == benchmark_id), None)
    if row is None:
        raise HTTPException(404, "Бенчмарк не найден")
    return row
