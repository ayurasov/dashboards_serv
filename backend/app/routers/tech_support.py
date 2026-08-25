"""Tech Support dashboard router.

Endpoints
---------
GET  /api/tech-support/weeks              — list rows (filters: client, year, week)
POST /api/tech-support/weeks              — create one row (edit access required)
PUT  /api/tech-support/weeks/{id}         — update row (edit access)
DELETE /api/tech-support/weeks/{id}       — delete row (edit access)
POST /api/tech-support/weeks/bulk         — upsert many rows / import CSV (edit)
GET  /api/tech-support/analytics/clients  — per-client summary
GET  /api/tech-support/analytics/weeks    — per-week summary
GET  /api/tech-support/traffic-light/rules  — list rules (read)
PUT  /api/tech-support/traffic-light/rules  — save rules (admin)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..models_tech_support import TechSupportWeek, TechSupportTrafficRule
from ..deps import get_current_user, can_edit_service, can_admin_service
from ..schemas_tech_support import (
    TechSupportWeekCreate, TechSupportWeekUpdate, TechSupportWeekOut,
    TechSupportBulkImport,
    TsTrafficRuleOut, TsTrafficRulesBulk,
    TsClientSummary, TsWeekSummary,
)
from ..audit import log_action

router = APIRouter(prefix="/api/tech-support", tags=["tech_support"])

SERVICE_KEY = "tech_support"

# Default traffic-light rules seeded lazily
TS_RULE_DEFAULTS = [
    # metric_key, label, green, yellow, direction
    ("sla_pct",        "SLA выполнен (%)",           95.0, 85.0, "higher_is_better"),
    ("avg_response_h", "Ср. время реакции (ч)",        1.0,  4.0, "lower_is_better"),
    ("avg_resolution_h","Ср. время решения (ч)",       8.0, 24.0, "lower_is_better"),
    ("nps",            "NPS / CSI",                   80.0, 60.0, "higher_is_better"),
    ("incidents_critical", "Критических инцидентов",   2.0,  5.0, "lower_is_better"),
]


# ---------- helpers ----------

def _ensure_rules(db: Session) -> list[TechSupportTrafficRule]:
    rows = db.query(TechSupportTrafficRule).all()
    known = {r.metric_key for r in rows}
    added = False
    for key, label, green, yellow, direction in TS_RULE_DEFAULTS:
        if key in known:
            continue
        db.add(TechSupportTrafficRule(
            metric_key=key, label=label,
            green_threshold=green, yellow_threshold=yellow,
            direction=direction, enabled=True,
        ))
        added = True
    if added:
        db.commit()
        rows = db.query(TechSupportTrafficRule).all()
    return rows


def _light(value: float | None, rule: TechSupportTrafficRule | None) -> str:
    if value is None or rule is None or not rule.enabled:
        return "gray"
    g, y = rule.green_threshold, rule.yellow_threshold
    if rule.direction == "higher_is_better":
        if g is not None and value >= g:
            return "green"
        if y is not None and value >= y:
            return "yellow"
        return "red"
    else:  # lower_is_better
        if g is not None and value <= g:
            return "green"
        if y is not None and value <= y:
            return "yellow"
        return "red"


def _require_edit(db: Session, user: User):
    if not can_edit_service(db, user, SERVICE_KEY):
        raise HTTPException(403, "Требуются права на редактирование tech_support")


def _require_admin(db: Session, user: User):
    if not can_admin_service(db, user, SERVICE_KEY):
        raise HTTPException(403, "Требуются права администратора tech_support")


def _get_or_404(db: Session, row_id: int) -> TechSupportWeek:
    row = db.query(TechSupportWeek).filter(TechSupportWeek.id == row_id).first()
    if not row:
        raise HTTPException(404, "Запись не найдена")
    return row


def _snapshot(r: TechSupportWeek) -> dict:
    return {
        "client": r.client, "year": r.year, "week": r.week,
        "sla_pct": r.sla_pct, "incidents_total": r.incidents_total,
        "incidents_critical": r.incidents_critical, "avg_response_h": r.avg_response_h,
        "avg_resolution_h": r.avg_resolution_h, "nps": r.nps,
    }


# ---------- week rows ----------

@router.get("/weeks", response_model=list[TechSupportWeekOut])
def list_weeks(
    client: str | None = None,
    year: int | None = None,
    week: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(TechSupportWeek)
    if client:
        q = q.filter(TechSupportWeek.client == client)
    if year:
        q = q.filter(TechSupportWeek.year == year)
    if week:
        q = q.filter(TechSupportWeek.week == week)
    return q.order_by(TechSupportWeek.year.desc(), TechSupportWeek.week.desc(),
                      TechSupportWeek.client).all()


@router.post("/weeks", response_model=TechSupportWeekOut)
def create_week(
    body: TechSupportWeekCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_edit(db, user)
    existing = (db.query(TechSupportWeek)
                .filter(TechSupportWeek.client == body.client,
                        TechSupportWeek.year == body.year,
                        TechSupportWeek.week == body.week)
                .first())
    if existing:
        raise HTTPException(409, f"Запись для {body.client} неделя {body.year}-W{body.week:02d} уже существует")
    row = TechSupportWeek(**body.model_dump())
    db.add(row)
    db.flush()
    log_action(db, user, "ts_week", row.id, "create", after=_snapshot(row))
    db.commit()
    db.refresh(row)
    return row


@router.put("/weeks/{row_id}", response_model=TechSupportWeekOut)
def update_week(
    row_id: int,
    body: TechSupportWeekUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_edit(db, user)
    row = _get_or_404(db, row_id)
    before = _snapshot(row)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.flush()
    log_action(db, user, "ts_week", row.id, "update", before=before, after=_snapshot(row))
    db.commit()
    db.refresh(row)
    return row


@router.delete("/weeks/{row_id}")
def delete_week(
    row_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_edit(db, user)
    row = _get_or_404(db, row_id)
    log_action(db, user, "ts_week", row.id, "delete", before=_snapshot(row))
    db.delete(row)
    db.commit()
    return {"deleted": row_id}


@router.post("/weeks/bulk", response_model=list[TechSupportWeekOut])
def bulk_import(
    body: TechSupportBulkImport,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upsert a batch of rows — used by CSV import."""
    _require_edit(db, user)
    result = []
    for item in body.rows:
        existing = (db.query(TechSupportWeek)
                    .filter(TechSupportWeek.client == item.client,
                            TechSupportWeek.year == item.year,
                            TechSupportWeek.week == item.week)
                    .first())
        if existing:
            before = _snapshot(existing)
            for f, v in item.model_dump(exclude={"client", "year", "week"}).items():
                if v is not None:
                    setattr(existing, f, v)
            log_action(db, user, "ts_week", existing.id, "update",
                       before=before, after=_snapshot(existing))
            result.append(existing)
        else:
            row = TechSupportWeek(**item.model_dump())
            db.add(row)
            db.flush()
            log_action(db, user, "ts_week", row.id, "create", after=_snapshot(row))
            result.append(row)
    db.commit()
    return result


# ---------- analytics ----------

@router.get("/analytics/clients", response_model=list[TsClientSummary])
def analytics_clients(
    year: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(TechSupportWeek)
    if year:
        q = q.filter(TechSupportWeek.year == year)
    rows = q.all()
    rules = {r.metric_key: r for r in _ensure_rules(db)}

    clients: dict[str, list[TechSupportWeek]] = {}
    for r in rows:
        clients.setdefault(r.client, []).append(r)

    result = []
    for client, items in sorted(clients.items()):
        sla_vals = [r.sla_pct for r in items if r.sla_pct is not None]
        resp_vals = [r.avg_response_h for r in items if r.avg_response_h is not None]
        resol_vals = [r.avg_resolution_h for r in items if r.avg_resolution_h is not None]
        nps_vals = [r.nps for r in items if r.nps is not None]
        avg_sla = round(sum(sla_vals) / len(sla_vals), 1) if sla_vals else None
        result.append(TsClientSummary(
            client=client,
            weeks_count=len(items),
            avg_sla=avg_sla,
            avg_response_h=round(sum(resp_vals)/len(resp_vals), 2) if resp_vals else None,
            avg_resolution_h=round(sum(resol_vals)/len(resol_vals), 2) if resol_vals else None,
            total_incidents=sum(r.incidents_total or 0 for r in items),
            total_critical=sum(r.incidents_critical or 0 for r in items),
            avg_nps=round(sum(nps_vals)/len(nps_vals), 1) if nps_vals else None,
            sla_light=_light(avg_sla, rules.get("sla_pct")),
        ))
    return result


@router.get("/analytics/weeks", response_model=list[TsWeekSummary])
def analytics_weeks(
    year: int | None = None,
    client: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(TechSupportWeek)
    if year:
        q = q.filter(TechSupportWeek.year == year)
    if client:
        q = q.filter(TechSupportWeek.client == client)
    rows = q.order_by(TechSupportWeek.year, TechSupportWeek.week).all()
    rules = {r.metric_key: r for r in _ensure_rules(db)}

    weeks: dict[tuple, list[TechSupportWeek]] = {}
    for r in rows:
        weeks.setdefault((r.year, r.week), []).append(r)

    result = []
    for (yr, wk), items in sorted(weeks.items()):
        sla_vals = [r.sla_pct for r in items if r.sla_pct is not None]
        avg_sla = round(sum(sla_vals)/len(sla_vals), 1) if sla_vals else None
        result.append(TsWeekSummary(
            period_key=f"{yr}-W{wk:02d}",
            year=yr,
            week=wk,
            clients_count=len(items),
            avg_sla=avg_sla,
            total_incidents=sum(r.incidents_total or 0 for r in items),
            sla_light=_light(avg_sla, rules.get("sla_pct")),
        ))
    return result


# ---------- traffic-light rules ----------

@router.get("/traffic-light/rules", response_model=list[TsTrafficRuleOut])
def list_rules(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _ensure_rules(db)


@router.put("/traffic-light/rules")
def save_rules(
    body: TsTrafficRulesBulk,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(db, user)
    rule_map = {r.metric_key: r for r in _ensure_rules(db)}
    before, after = {}, {}
    for item in body.rules:
        key = item.get("metric_key")
        rule = rule_map.get(key)
        if not rule:
            continue
        before[key] = {"green": rule.green_threshold, "yellow": rule.yellow_threshold}
        if "green_threshold" in item:
            rule.green_threshold = item["green_threshold"]
        if "yellow_threshold" in item:
            rule.yellow_threshold = item["yellow_threshold"]
        if "direction" in item:
            rule.direction = item["direction"]
        if "enabled" in item:
            rule.enabled = item["enabled"]
        after[key] = {"green": rule.green_threshold, "yellow": rule.yellow_threshold}
    log_action(db, user, "ts_traffic_rule", "all", "update", before=before, after=after)
    db.commit()
    return list_rules(db, user)
