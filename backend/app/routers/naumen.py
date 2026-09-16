"""Naumen SD ticket analytics for the technical-support dashboard.

Endpoints
---------
GET  /api/tp/naumen/summary        — aggregates for the Naumen analytics page
GET  /api/tp/naumen/match          — weekly-report rows joined with Naumen
                                     weekly aggregates (cross-analytics)
POST /api/tp/naumen/import         — replace tickets from an xlsx export (admin)
"""
import io
import re
from collections import defaultdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import NaumenTicket, TpReportRow, User
from ..deps import can_view_service, can_admin_service, get_current_user

router = APIRouter(prefix="/api/tp/naumen", tags=["technical-support-naumen"])

SERVICE_KEY = "tech"


def _require_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> User:
    from ..models import RoleEnum
    if user.role == RoleEnum.ADMIN or can_view_service(db, user, SERVICE_KEY):
        return user
    raise HTTPException(status_code=403, detail="Нет доступа к сервису Техподдержка")


def _require_admin(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> User:
    from ..models import RoleEnum
    if user.role == RoleEnum.ADMIN or can_admin_service(db, user, SERVICE_KEY):
        return user
    raise HTTPException(status_code=403, detail="Требуются права админа")


def _iso_week(dt: Optional[datetime]):
    if not dt:
        return None
    y, w, _ = dt.isocalendar()
    return int(y), int(w)


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


# ---------- Aggregates ----------

@router.get("/summary")
def naumen_summary(_: User = Depends(_require_read), db: Session = Depends(get_db)):
    tickets = db.query(NaumenTicket).order_by(NaumenTicket.registered_at).all()
    if not tickets:
        return {"empty": True}

    total = len(tickets)
    closed = sum(1 for t in tickets if t.status in ("Закрыта", "Выполнена"))
    overdue = sum(1 for t in tickets if t.overdue)
    reopened = sum(1 for t in tickets if t.reopened)

    by_month = defaultdict(lambda: {"registered": 0, "solved": 0, "overdue": 0,
                                    "reopened": 0, "proc_hours": [], "resolve_hours": []})
    by_org = defaultdict(lambda: {"total": 0, "closed": 0, "overdue": 0, "proc_hours": []})
    by_channel = defaultdict(int)
    by_status = defaultdict(int)
    all_resolve_hours = []

    for t in tickets:
        reg = t.registered_at
        if reg:
            mkey = reg.strftime("%Y-%m")
            m = by_month[mkey]
            m["registered"] += 1
            if t.overdue:
                m["overdue"] += 1
            if t.reopened:
                m["reopened"] += 1
            if t.processing_hours is not None:
                m["proc_hours"].append(t.processing_hours)
        if t.solved_at:
            mkey2 = t.solved_at.strftime("%Y-%m")
            by_month[mkey2]["solved"] += 1
            if t.registered_at:
                by_month[mkey2]["resolve_hours"].append(
                    (t.solved_at - t.registered_at).total_seconds() / 3600)
                all_resolve_hours.append((t.solved_at - t.registered_at).total_seconds() / 3600)
        if t.org:
            o = by_org[t.org]
            o["total"] += 1
            if t.status in ("Закрыта", "Выполнена"):
                o["closed"] += 1
            if t.overdue:
                o["overdue"] += 1
            if t.processing_hours is not None:
                o["proc_hours"].append(t.processing_hours)
        by_channel[t.channel or "—"] += 1
        by_status[t.status or "—"] += 1

    months = []
    for key in sorted(by_month):
        m = by_month[key]
        months.append({
            "month": key,
            "registered": m["registered"],
            "solved": m["solved"],
            "overdue": m["overdue"],
            "overdue_pct": round(m["overdue"] / m["registered"] * 100, 1) if m["registered"] else None,
            "reopened": m["reopened"],
            "avg_proc_hours": _avg(m["proc_hours"]),
            "avg_resolve_hours": _avg(m["resolve_hours"]),
        })

    orgs = []
    for org, o in by_org.items():
        orgs.append({
            "org": org, "total": o["total"], "closed": o["closed"],
            "overdue": o["overdue"],
            "overdue_pct": round(o["overdue"] / o["total"] * 100, 1) if o["total"] else None,
            "avg_proc_hours": _avg(o["proc_hours"]),
        })
    orgs.sort(key=lambda x: -x["total"])

    return {
        "empty": False,
        "total": total,
        "closed": closed,
        "in_progress": total - closed,
        "overdue": overdue,
        "overdue_pct": round(overdue / total * 100, 1),
        "reopened": reopened,
        "reopened_pct": round(reopened / total * 100, 1),
        "avg_proc_hours": _avg([t.processing_hours for t in tickets]),
        "avg_resolve_hours": _avg(all_resolve_hours),
        "first": tickets[0].registered_at.isoformat() if tickets[0].registered_at else None,
        "last": tickets[-1].registered_at.isoformat() if tickets[-1].registered_at else None,
        "months": months,
        "orgs": orgs,
        "channels": [{"channel": k, "count": v} for k, v in
                     sorted(by_channel.items(), key=lambda x: -x[1])],
        "statuses": [{"status": k, "count": v} for k, v in
                     sorted(by_status.items(), key=lambda x: -x[1])],
    }


@router.get("/match")
def naumen_match(_: User = Depends(_require_read), db: Session = Depends(get_db)):
    """Join weekly-report rows with Naumen weekly ticket aggregates (ISO weeks)."""
    tp_rows = db.query(TpReportRow).order_by(TpReportRow.year, TpReportRow.week).all()
    tickets = db.query(NaumenTicket).all()

    reg_week = defaultdict(int)
    solved_week = defaultdict(int)
    overdue_week = defaultdict(int)
    resolve_hours = defaultdict(list)
    rushydro_week = defaultdict(int)  # tickets from RusHydro-family orgs

    RUSG_MARKERS = ("русгидро", "ргидро", "гэс", "энерго", "дск", "дгк", "гидро")
    for t in tickets:
        wk = _iso_week(t.registered_at)
        if wk:
            reg_week[wk] += 1
            if t.overdue:
                overdue_week[wk] += 1
            if t.solved_at and t.registered_at:
                resolve_hours[wk].append((t.solved_at - t.registered_at).total_seconds() / 3600)
        wk2 = _iso_week(t.solved_at)
        if wk2:
            solved_week[wk2] += 1
        org = (t.org or "").lower()
        if wk and any(mk in org for mk in RUSG_MARKERS):
            rushydro_week[wk] += 1

    weeks = []
    for row in tp_rows:
        key = (int(row.year), int(row.week))
        weeks.append({
            "period": row.period or f"{int(row.year)}-W{int(row.week):02d}",
            "year": int(row.year),
            "week": int(row.week),
            "tp_new_received": row.new_received,
            "tp_solved": row.total_solved_week,
            "tp_in_work": row.total_in_work,
            "tp_rushydro_hours": row.rushydro_hours,
            "tp_altos_avg_time": row.altos_avg_time,
            "naumen_registered": reg_week.get(key, 0),
            "naumen_solved": solved_week.get(key, 0),
            "naumen_overdue": overdue_week.get(key, 0),
            "naumen_rushydro": rushydro_week.get(key, 0),
            "naumen_avg_resolve_hours": _avg(resolve_hours.get(key, [])),
        })

    return {"weeks": weeks, "weeks_count": len(weeks)}


# ---------- xlsx import ----------

_IMPORT_COLUMNS = {
    "Номер": "number",
    "Название": "name",
    "Дата регистрации": "registered_at",
    "Дата решения": "solved_at",
    "Регламентное время закрытия заявки": "deadline_at",
    "Статус": "status",
    "Наименование организации": "org",
    "Ответственный (сотрудник)": "responsible",
    "Ответственный (команда)": "team",
    "Сотрудник первая линия": "first_line",
    "Способ обращения": "channel",
    "Просрочен": "overdue",
    "Возобновлялась": "reopened",
    "Время обработки заявки": "processing_hours",
}


def _hours(value) -> Optional[float]:
    if value is None or value == "":
        return None
    m = re.match(r"^\s*(\d+):(\d+)", str(value))
    if not m:
        return None
    return round(int(m.group(1)) + int(m.group(2)) / 60, 2)


def _parse_rows_xlsx(data: bytes) -> list[dict]:
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(500, detail="На сервере не установлен openpyxl")
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [str(c).strip() if c else "" for c in next(rows)]
    idx = {col: i for i, col in enumerate(header) if col in _IMPORT_COLUMNS}
    missing = [c for c in _IMPORT_COLUMNS if c not in idx]
    if "Дата регистрации" in missing:
        raise HTTPException(400, detail="Файл не похож на экспорт Naumen: нет колонки «Дата регистрации»")

    def _dt(v):
        if isinstance(v, datetime):
            return v
        if v:
            try:
                return datetime.fromisoformat(str(v).strip())
            except ValueError:
                return None
        return None

    out = []
    for r in rows:
        if not any(r):
            continue
        def g(col):
            i = idx.get(col)
            return r[i] if i is not None and i < len(r) else None
        reg = _dt(g("Дата регистрации"))
        if reg is None:
            continue
        out.append({
            "number": int(g("Номер")) if g("Номер") not in (None, "") else None,
            "name": str(g("Название") or "")[:50] or None,
            "registered_at": reg,
            "solved_at": _dt(g("Дата решения")),
            "deadline_at": _dt(g("Регламентное время закрытия заявки")),
            "status": str(g("Статус") or "")[:100] or None,
            "org": str(g("Наименование организации") or "")[:300] or None,
            "responsible": str(g("Ответственный (сотрудник)") or "")[:300] or None,
            "team": str(g("Ответственный (команда)") or "")[:200] or None,
            "first_line": str(g("Сотрудник первая линия") or "")[:300] or None,
            "channel": str(g("Способ обращения") or "")[:100] or None,
            "overdue": str(g("Просрочен") or "").strip().lower() == "просрочен",
            "reopened": str(g("Возобновлялась") or "").strip().lower() == "да",
            "processing_hours": _hours(g("Время обработки заявки")),
        })
    wb.close()
    if not out:
        raise HTTPException(400, detail="В файле не найдено ни одной заявки с датой регистрации")
    return out


@router.post("/import")
async def import_naumen_xlsx(
    file: UploadFile = File(...),
    _: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """Replace all stored Naumen tickets with the uploaded xlsx export."""
    data = await file.read()
    records = _parse_rows_xlsx(data)
    db.query(NaumenTicket).delete()
    for rec in records:
        db.add(NaumenTicket(**rec))
    db.commit()
    return {"ok": True, "count": len(records)}
