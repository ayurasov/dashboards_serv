"""Technical-support dashboard router.

Mirrors the tp-report Flask app but uses the shared FastAPI auth / RBAC
infrastructure instead of the single-password session approach.

Endpoints
---------
GET  /api/tp/rows                 — list all week rows (any authenticated user with read)
POST /api/tp/rows                 — create a row (edit level required)
PUT  /api/tp/rows/{id}            — update a row (edit level required)
DEL  /api/tp/rows/{id}            — delete a row (edit level required)
POST /api/tp/rows/bulk_import     — replace all rows from JSON payload (admin)
GET  /api/tp/settings/{key}       — get a settings key
PUT  /api/tp/settings/{key}       — save a settings key (edit level required)
DEL  /api/tp/settings/color_palette  — reset colour palette (edit level required)
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..database import get_db
from ..models import TpReportRow, TpSettings, TP_DEFAULT_TRAFFIC_RULES, TP_DATA_COLUMNS, User
from ..deps import get_current_user, can_edit_service, can_admin_service

router = APIRouter(prefix="/api/tp", tags=["technical-support"])

SERVICE_KEY = "tech"


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
        # Merge defaults + overrides so the response always has all keys
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
