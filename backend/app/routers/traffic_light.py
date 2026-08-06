"""Traffic-light configuration router (admin only)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import TrafficLightRule, MetricDefinition, User, TL_DIRECTIONS
from ..deps import require_admin, get_current_user
from ..schemas import TrafficLightRuleOut, TrafficLightRuleUpdate
from ..audit import log_action

router = APIRouter(prefix="/api/traffic-light", tags=["traffic-light"])


@router.get("", response_model=list[TrafficLightRuleOut])
def list_rules(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(TrafficLightRule).all()


def _direction(rule: TrafficLightRule | None, defn: MetricDefinition) -> str:
    for value in ((rule.direction if rule else None), defn.direction):
        if value in TL_DIRECTIONS:
            return value
    return "higher_is_better"


@router.get("/with-metrics")
def list_with_metrics(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rules = {r.metric_key: r for r in db.query(TrafficLightRule).all()}
    defs = db.query(MetricDefinition).order_by(MetricDefinition.sort_order).all()
    out = []
    for d in defs:
        r = rules.get(d.key)
        out.append({
            "metric_key": d.key,
            "label": d.label,
            "unit": d.unit,
            "category": d.category or "",
            # The rule's direction is what the light actually uses; the definition is
            # only a fallback for metrics that have no rule yet. Definitions may say
            # "neutral", which is not a light direction — those default to higher.
            "direction": _direction(r, d),
            "green_threshold": r.green_threshold if r else None,
            "yellow_threshold": r.yellow_threshold if r else None,
            "enabled": r.enabled if r else False,
            "has_rule": r is not None,
        })
    return out


@router.put("/{metric_key}", response_model=TrafficLightRuleOut)
def update_rule(metric_key: str, body: TrafficLightRuleUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rule = db.query(TrafficLightRule).filter(TrafficLightRule.metric_key == metric_key).first()
    before = None
    if rule:
        before = {"green": rule.green_threshold, "yellow": rule.yellow_threshold, "enabled": rule.enabled}
    if not rule:
        rule = TrafficLightRule(metric_key=metric_key)
        db.add(rule)
    if body.green_threshold is not None:
        rule.green_threshold = body.green_threshold
    if body.yellow_threshold is not None:
        rule.yellow_threshold = body.yellow_threshold
    if body.direction is not None:
        if body.direction not in TL_DIRECTIONS:
            raise HTTPException(400, f"Неизвестное направление: {body.direction}")
        rule.direction = body.direction
    if body.enabled is not None:
        rule.enabled = body.enabled
    db.flush()
    log_action(db, admin, "traffic_light", metric_key, "update", before=before,
               after={"green": rule.green_threshold, "yellow": rule.yellow_threshold, "enabled": rule.enabled})
    db.commit()
    db.refresh(rule)
    return rule
