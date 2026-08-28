"""Technical-support dashboard router.

Mirrors the tp-report Flask app but uses the shared FastAPI auth / RBAC
infrastructure instead of the single-password session approach.

Endpoints
---------
GET  /api/tp/rows                 — list all week rows (read)
POST /api/tp/rows                 — create a row (edit)
PUT  /api/tp/rows/{id}            — update a row (edit)
DEL  /api/tp/rows/{id}            — delete a row (edit)
POST /api/tp/rows/bulk_import     — replace all rows from JSON payload (admin)
GET  /api/tp/columns              — column metadata (label, group) for UI rendering
GET  /api/tp/summary              — aggregated KPIs: last-week values + 4-week trends
GET  /api/tp/export               — download all rows as CSV
GET  /api/tp/settings/{key}       — get a settings key
PUT  /api/tp/settings/{key}       — save a settings key (edit)
DEL  /api/tp/settings/color_palette  — reset colour palette (edit)
"""
import csv
import io
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..database import get_db
from ..models import TpReportRow, TpSettings, TP_DEFAULT_TRAFFIC_RULES, TP_DATA_COLUMNS, User
from ..deps import get_current_user, can_edit_service, can_admin_service

router = APIRouter(prefix="/api/tp", tags=["technical-support"])

SERVICE_KEY = "tech"

# ---------------------------------------------------------------------------
# Column metadata — label + logical group for the frontend.
# Groups drive section headers in the registry table and summary cards.
# ---------------------------------------------------------------------------
COLUMN_META: list[dict] = [
    # time
    {"key": "year",                  "label": "Год",                          "group": "time"},
    {"key": "week",                  "label": "Неделя",                       "group": "time"},
    {"key": "period",               "label": "Период",                       "group": "time"},
    # load
    {"key": "total_in_work",        "label": "В работе (всего)",             "group": "load"},
    {"key": "avail_total",          "label": "Доступность (ч.)",             "group": "load"},
    # client hours
    {"key": "rushydro_hours",       "label": "РусГидро (ч.)",               "group": "client_hours"},
    {"key": "transneft_hours",      "label": "Транснефть (ч.)",             "group": "client_hours"},
    {"key": "roscosmos_hours",      "label": "Роскосмос (ч.)",              "group": "client_hours"},
    {"key": "bryansk_hours",        "label": "Брянск (ч.)",                 "group": "client_hours"},
    {"key": "mchs_hours",           "label": "МЧС (ч.)",                   "group": "client_hours"},
    {"key": "internal_sales_hours", "label": "Внутренние продажи (ч.)",    "group": "client_hours"},
    # ticket flow
    {"key": "new_received",         "label": "Новые обращения",             "group": "tickets"},
    {"key": "renewed",              "label": "Возобновлённые",              "group": "tickets"},
    {"key": "ratio_solved_received","label": "Решено / Получено",           "group": "tickets"},
    {"key": "total_solved_week",    "label": "Решено за неделю",            "group": "tickets"},
    # AltOS channels
    {"key": "altos_rusg_email",     "label": "AltOS РУСГ e-mail",           "group": "altos_channels"},
    {"key": "altos_rusg_tf",        "label": "AltOS РУСГ TF",               "group": "altos_channels"},
    {"key": "altos_other_email",    "label": "AltOS прочие e-mail",         "group": "altos_channels"},
    {"key": "altos_other_tf",       "label": "AltOS прочие TF",             "group": "altos_channels"},
    # AltOffice channels
    {"key": "altoffice_rusg_email", "label": "AltOffice РУСГ e-mail",       "group": "altoffice_channels"},
    {"key": "altoffice_rusg_tf",    "label": "AltOffice РУСГ TF",           "group": "altoffice_channels"},
    {"key": "altoffice_other_email","label": "AltOffice прочие e-mail",     "group": "altoffice_channels"},
    {"key": "altoffice_other_tf",   "label": "AltOffice прочие TF",         "group": "altoffice_channels"},
    # ProjServer
    {"key": "projserver_taken",     "label": "ProjServer принято",          "group": "projserver"},
    {"key": "projserver_solved",    "label": "ProjServer решено",           "group": "projserver"},
    {"key": "projserver_avail",     "label": "ProjServer доступность (ч.)","group": "projserver"},
    # AltOS SLA
    {"key": "altos_avg_time",       "label": "AltOS среднее время (ч.)",    "group": "altos_sla"},
    {"key": "altos_total",          "label": "AltOS всего",                 "group": "altos_sla"},
    {"key": "altos_1_2line",        "label": "AltOS 1-2 линия",             "group": "altos_sla"},
    {"key": "altos_3line",          "label": "AltOS 3 линия",               "group": "altos_sla"},
    # AltOffice SLA
    {"key": "altoffice_avg_time",   "label": "AltOffice среднее время (ч.)","group": "altoffice_sla"},
    {"key": "altoffice_total",      "label": "AltOffice всего",             "group": "altoffice_sla"},
    {"key": "altoffice_1_2line",    "label": "AltOffice 1-2 линия",         "group": "altoffice_sla"},
    {"key": "altoffice_3line",      "label": "AltOffice 3 линия",           "group": "altoffice_sla"},
    # Availability buckets — AltOS
    {"key": "altos_avail_total",    "label": "AltOS доступность (ч.)",      "group": "altos_avail"},
    {"key": "altos_avail_1_3",      "label": "AltOS доступность 1-3 дн.",   "group": "altos_avail"},
    {"key": "altos_avail_4_7",      "label": "AltOS доступность 4-7 дн.",   "group": "altos_avail"},
    {"key": "altos_avail_8_10",     "label": "AltOS доступность 8-10 дн.",  "group": "altos_avail"},
    # Availability buckets — AltOffice
    {"key": "altoffice_avail_total","label": "AltOffice доступность (ч.)",  "group": "altoffice_avail"},
    {"key": "altoffice_avail_1_3",  "label": "AltOffice доступность 1-3 дн.","group": "altoffice_avail"},
    {"key": "altoffice_avail_4_7",  "label": "AltOffice доступность 4-7 дн.","group": "altoffice_avail"},
    {"key": "altoffice_avail_8_10", "label": "AltOffice доступность 8-10 дн.","group": "altoffice_avail"},
    # extra
    {"key": "extra",               "label": "Примечание",                  "group": "extra"},
]

# Map key -> meta for fast lookup
_META_BY_KEY = {m["key"]: m for m in COLUMN_META}


# ---------- helpers ----------

def _require_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> User:
    """Any authenticated user with at least read access to the tech service."""
    from ..models import RoleEnum
    from ..deps import can_view_service
    if user.role == RoleEnum.ADMIN or can_view_service(db, user, SERVICE_KEY):
        return user
    raise HTTPException(status_code=403, detail="Нет доступа к сервису Техподдержка")


def _require_edit(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> User:
    from ..models import RoleEnum
    if user.role == RoleEnum.ADMIN or can_edit_service(db, user, SERVICE_KEY):
        return user
    raise HTTPException(status_code=403, detail="Требуются права на редактирование")


def _require_admin(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> User:
    from ..models import RoleEnum
    if user.role == RoleEnum.ADMIN or can_admin_service(db, user, SERVICE_KEY):
        return user
    raise HTTPException(status_code=403, detail="Требуются права админа")


def _row_to_dict(row: TpReportRow) -> dict:
    d = {c: getattr(row, c, None) for c in TP_DATA_COLUMNS}
    d["id"] = row.id
    d["period"] = row.period
    return d


def _get_setting(db: Session, key: str, default=None):
    row = db.query(TpSettings).filter(TpSettings.key == key).first()
    if row:
        return json.loads(row.value)
    return default


def _set_setting(db: Session, key: str, value) -> None:
    row = db.query(TpSettings).filter(TpSettings.key == key).first()
    if row:
        row.value = json.dumps(value, ensure_ascii=False)
    else:
        db.add(TpSettings(key=key, value=json.dumps(value, ensure_ascii=False)))
    db.commit()


def _ensure_defaults(db: Session) -> None:
    """Seed default settings on first request if not present."""
    defaults = {
        "traffic_rules": TP_DEFAULT_TRAFFIC_RULES,
        "block_settings": {},
        "color_palette": {},
    }
    for k, v in defaults.items():
        if not db.query(TpSettings).filter(TpSettings.key == k).first():
            db.add(TpSettings(key=k, value=json.dumps(v, ensure_ascii=False)))
    db.commit()


def _traffic_light(value: Optional[float], rule: dict) -> str:
    """Return 'green' | 'yellow' | 'red' | 'gray' for a single KPI value."""
    if value is None or not rule.get("enabled"):
        return "gray"
    direction = rule.get("direction", "less")
    green = rule.get("green")
    yellow = rule.get("yellow")
    if direction == "less":
        if green is not None and value <= green:
            return "green"
        if yellow is not None and value <= yellow:
            return "yellow"
        return "red"
    else:  # "more"
        if green is not None and value >= green:
            return "green"
        if yellow is not None and value >= yellow:
            return "yellow"
        return "red"


# ---------- Pydantic ----------

class TpRowIn(BaseModel):
    year: float | None = None
    week: float | None = None
    period: str | None = None
    total_in_work: float | None = None
    avail_total: float | None = None
    rushydro_hours: float | None = None
    transneft_hours: float | None = None
    roscosmos_hours: float | None = None
    bryansk_hours: float | None = None
    mchs_hours: float | None = None
    internal_sales_hours: float | None = None
    new_received: float | None = None
    renewed: float | None = None
    ratio_solved_received: float | None = None
    altos_rusg_email: float | None = None
    altos_rusg_tf: float | None = None
    altos_other_email: float | None = None
    altos_other_tf: float | None = None
    altoffice_rusg_email: float | None = None
    altoffice_rusg_tf: float | None = None
    altoffice_other_email: float | None = None
    altoffice_other_tf: float | None = None
    projserver_taken: float | None = None
    projserver_solved: float | None = None
    projserver_avail: float | None = None
    total_solved_week: float | None = None
    altos_avg_time: float | None = None
    altos_total: float | None = None
    altos_1_2line: float | None = None
    altos_3line: float | None = None
    altoffice_avg_time: float | None = None
    altoffice_total: float | None = None
    altoffice_1_2line: float | None = None
    altoffice_3line: float | None = None
    altos_avail_total: float | None = None
    altos_avail_1_3: float | None = None
    altos_avail_4_7: float | None = None
    altos_avail_8_10: float | None = None
    altoffice_avail_total: float | None = None
    altoffice_avail_1_3: float | None = None
    altoffice_avail_4_7: float | None = None
    altoffice_avail_8_10: float | None = None
    extra: str | None = None


class BulkImportIn(BaseModel):
    rows: list[TpRowIn] = []


# ---------- Column metadata ----------

@router.get("/columns")
def list_columns(_: User = Depends(_require_read)):
    """Return column metadata (key, label, group) for frontend rendering."""
    return COLUMN_META


# ---------- Rows ----------

@router.get("/rows")
def list_rows(
    db: Session = Depends(get_db),
    _: User = Depends(_require_read),
):
    _ensure_defaults(db)
    rows = db.query(TpReportRow).order_by(TpReportRow.year, TpReportRow.week).all()
    return [_row_to_dict(r) for r in rows]


@router.post("/rows", status_code=201)
def create_row(
    body: TpRowIn,
    db: Session = Depends(get_db),
    _: User = Depends(_require_edit),
):
    row = TpReportRow(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


@router.put("/rows/{row_id}")
def update_row(
    row_id: int,
    body: TpRowIn,
    db: Session = Depends(get_db),
    _: User = Depends(_require_edit),
):
    row = db.query(TpReportRow).filter(TpReportRow.id == row_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Строка не найдена")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


@router.delete("/rows/{row_id}")
def delete_row(
    row_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_require_edit),
):
    row = db.query(TpReportRow).filter(TpReportRow.id == row_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Строка не найдена")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/rows/bulk_import")
def bulk_import(
    body: BulkImportIn,
    db: Session = Depends(get_db),
    _: User = Depends(_require_admin),
):
    """Replace all rows with the submitted list. Admin-only."""
    db.query(TpReportRow).delete()
    for item in body.rows:
        db.add(TpReportRow(**item.model_dump()))
    db.commit()
    return {"ok": True, "count": len(body.rows)}


# ---------- Summary (aggregated KPIs for dashboard cards) ----------

@router.get("/summary")
def get_summary(
    weeks: int = Query(default=4, ge=1, le=52,
                       description="Number of recent weeks for trend window"),
    db: Session = Depends(get_db),
    _: User = Depends(_require_read),
):
    """Return aggregated dashboard data:

    - ``last_week``  — dict of all numeric fields for the most recent row
    - ``trend``      — simple week-over-week delta (last_week - prev_week) for
                       each KPI; null when fewer than 2 rows
    - ``chart``      — last `weeks` rows ordered asc (for sparklines / charts)
    - ``traffic``    — traffic-light colour per KPI for the last-week values
    - ``meta``       — column metadata (same as /columns)
    """
    _ensure_defaults(db)
    all_rows = (
        db.query(TpReportRow)
        .order_by(TpReportRow.year, TpReportRow.week)
        .all()
    )

    if not all_rows:
        return {
            "last_week": None,
            "prev_week": None,
            "trend": {},
            "chart": [],
            "traffic": {},
            "meta": COLUMN_META,
        }

    last = all_rows[-1]
    prev = all_rows[-2] if len(all_rows) >= 2 else None
    chart_rows = all_rows[-weeks:]

    last_dict = _row_to_dict(last)
    prev_dict = _row_to_dict(prev) if prev else None

    # Trend: positive = improved or increased (sign is raw, frontend decides meaning)
    trend: dict = {}
    if prev_dict:
        for key in TP_DATA_COLUMNS:
            lv = last_dict.get(key)
            pv = prev_dict.get(key)
            if isinstance(lv, (int, float)) and isinstance(pv, (int, float)):
                trend[key] = round(lv - pv, 4)

    # Traffic-light evaluation against current rules
    rules = {**TP_DEFAULT_TRAFFIC_RULES, **_get_setting(db, "traffic_rules", {})}
    traffic: dict = {}
    for key, rule in rules.items():
        value = last_dict.get(key)
        traffic[key] = _traffic_light(value, rule)

    return {
        "last_week": last_dict,
        "prev_week": prev_dict,
        "trend": trend,
        "chart": [_row_to_dict(r) for r in chart_rows],
        "traffic": traffic,
        "meta": COLUMN_META,
    }


# ---------- Export (CSV) ----------

@router.get("/export")
def export_csv(
    db: Session = Depends(get_db),
    _: User = Depends(_require_read),
):
    """Stream all TP rows as a UTF-8 CSV file (BOM for Excel compatibility)."""
    rows = (
        db.query(TpReportRow)
        .order_by(TpReportRow.year, TpReportRow.week)
        .all()
    )

    headers = ["id"] + list(TP_DATA_COLUMNS) + ["period"]
    # Build human-readable header row using COLUMN_META where available
    display_headers = []
    for h in headers:
        meta = _META_BY_KEY.get(h)
        display_headers.append(meta["label"] if meta else h)

    buf = io.StringIO()
    buf.write("\ufeff")  # UTF-8 BOM so Excel opens Russian text correctly
    writer = csv.writer(buf, dialect="excel")
    writer.writerow(display_headers)
    for row in rows:
        d = _row_to_dict(row)
        writer.writerow([d.get(h) for h in headers])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="tp_report.csv"'},
    )


# ---------- Settings ----------

SETTING_KEYS = {"traffic_rules", "block_settings", "color_palette"}


@router.get("/settings/{key}")
def get_setting_ep(
    key: str,
    db: Session = Depends(get_db),
    _: User = Depends(_require_read),
):
    if key not in SETTING_KEYS:
        raise HTTPException(400, detail="Неизвестный ключ настроек")
    _ensure_defaults(db)
    if key == "traffic_rules":
        overrides = _get_setting(db, "traffic_rules", {})
        return {**TP_DEFAULT_TRAFFIC_RULES, **overrides}
    return _get_setting(db, key, {})


@router.put("/settings/{key}")
def put_setting_ep(
    key: str,
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(_require_edit),
):
    if key not in SETTING_KEYS:
        raise HTTPException(400, detail="Неизвестный ключ настроек")
    _set_setting(db, key, body)
    return {"ok": True}


@router.delete("/settings/color_palette")
def reset_color_palette(
    db: Session = Depends(get_db),
    _: User = Depends(_require_edit),
):
    _set_setting(db, "color_palette", {})
    return {"ok": True}
