"""Tech-support weekly metrics router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import SupportWeekRecord, User
from ..deps import get_current_user, require_edit
from ..schemas import SupportWeekOut, SupportWeekCreate, SupportWeekUpdate
from ..audit import log_action

router = APIRouter(prefix="/api/support", tags=["support"])


def _get_or_404(db: Session, rid: int) -> SupportWeekRecord:
    row = db.query(SupportWeekRecord).filter(SupportWeekRecord.id == rid).first()
    if not row:
        raise HTTPException(404, "Запись не найдена")
    return row


def _snapshot(r: SupportWeekRecord) -> dict:
    return {
        "period": r.period, "year": r.year, "week": r.week,
        "totalinwork": r.totalinwork, "availtotal": r.availtotal,
        "newreceived": r.newreceived, "renewed": r.renewed,
        "totalsolvedweek": r.totalsolvedweek, "ratiosolvedreceived": r.ratiosolvedreceived,
        "rushydrohours": r.rushydrohours, "transnefthours": r.transnefthours,
        "roscosmoshours": r.roscosmoshours, "bryanskhours": r.bryanskhours,
        "mchshours": r.mchshours, "internalsaleshours": r.internalsaleshours,
        "altosavgtime": r.altosavgtime, "altofficeavgtime": r.altofficeavgtime,
        "altostotal": r.altostotal, "altos12line": r.altos12line, "altos3line": r.altos3line,
        "altofficetotal": r.altofficetotal, "altoffice12line": r.altoffice12line, "altoffice3line": r.altoffice3line,
        "altosavailtotal": r.altosavailtotal, "altofficeavailtotal": r.altofficeavailtotal,
        "altosavail13": r.altosavail13, "altosavail47": r.altosavail47, "altosavail810": r.altosavail810,
        "altofficeavail13": r.altofficeavail13, "altofficeavail47": r.altofficeavail47, "altofficeavail810": r.altofficeavail810,
        "projservertaken": r.projservertaken, "projserversolved": r.projserversolved, "projserveravail": r.projserveravail,
        "altosrusgemail": r.altosrusgemail, "altosrusgtf": r.altosrusgtf,
        "altosotheremail": r.altosotheremail, "altosothertf": r.altosothertf,
        "altofficerusgemail": r.altofficerusgemail, "altofficerusgtf": r.altofficerusgtf,
        "altofficeotheremail": r.altofficeotheremail, "altofficeothertf": r.altofficeothertf,
        "extra": r.extra,
    }


@router.get("", response_model=list[SupportWeekOut])
def list_records(
    year: int | None = None,
    week_from: int | None = None,
    week_to: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(SupportWeekRecord)
    if year:
        q = q.filter(SupportWeekRecord.year == year)
    if week_from:
        q = q.filter(SupportWeekRecord.week >= week_from)
    if week_to:
        q = q.filter(SupportWeekRecord.week <= week_to)
    return q.order_by(SupportWeekRecord.year, SupportWeekRecord.week).all()


@router.get("/years")
def list_years(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    from sqlalchemy import distinct
    years = db.query(distinct(SupportWeekRecord.year)).order_by(SupportWeekRecord.year).all()
    return [y[0] for y in years]


@router.get("/{record_id}", response_model=SupportWeekOut)
def get_record(record_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _get_or_404(db, record_id)


@router.post("", response_model=SupportWeekOut)
def create_record(body: SupportWeekCreate, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    existing = db.query(SupportWeekRecord).filter(
        SupportWeekRecord.year == body.year,
        SupportWeekRecord.week == body.week,
    ).first()
    if existing:
        raise HTTPException(409, f"Запись {body.year}-W{body.week:02d} уже существует")
    r = SupportWeekRecord(**body.model_dump())
    r.period = f"{body.year}-W{body.week:02d}"
    db.add(r)
    db.flush()
    log_action(db, user, "support_week", r.id, "create", after=_snapshot(r))
    db.commit()
    db.refresh(r)
    return r


@router.put("/{record_id}", response_model=SupportWeekOut)
def update_record(
    record_id: int, body: SupportWeekUpdate,
    db: Session = Depends(get_db), user: User = Depends(require_edit),
):
    r = _get_or_404(db, record_id)
    before = _snapshot(r)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(r, field, value)
    if 'year' in body.model_fields_set or 'week' in body.model_fields_set:
        r.period = f"{r.year}-W{r.week:02d}"
    db.flush()
    log_action(db, user, "support_week", r.id, "update", before=before, after=_snapshot(r))
    db.commit()
    db.refresh(r)
    return r


@router.delete("/{record_id}")
def delete_record(record_id: int, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    r = _get_or_404(db, record_id)
    log_action(db, user, "support_week", r.id, "delete", before=_snapshot(r))
    db.delete(r)
    db.commit()
    return {"deleted": record_id}
