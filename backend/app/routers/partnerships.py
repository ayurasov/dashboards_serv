"""Technology partnerships router (Продуктовый отдел)."""
import datetime
from collections import Counter
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import (
    Partnership, User, PartnershipLightRule, PARTNERSHIP_LIGHT_DEFAULTS,
    PARTNERSHIP_LIGHT_GROUPS,
)
from ..deps import get_current_user, require_edit, require_admin
from ..schemas import (
    PartnershipCreate, PartnershipUpdate, PartnershipOut, PartnershipAnalytics,
    PartnershipLightRow, PartnershipPeriodRow, PartnershipLightRuleOut,
    PartnershipLightRulesIn,
)
from ..audit import log_action

router = APIRouter(prefix="/api/partnerships", tags=["partnerships"])

LIGHTS = ("green", "yellow", "red", "gray")

# Shipped defaults. They seed the editable rule table and remain the fallback for
# a status an admin has not configured.
STATUS_LIGHTS = {
    "Завершено": "green",
    "В работе": "yellow",
    "Отложено": "yellow",
    "Не подписывают": "red",
}


def ensure_light_rules(db: Session) -> list[PartnershipLightRule]:
    """Rules are seeded lazily so an existing database needs no migration."""
    rows = db.query(PartnershipLightRule).order_by(PartnershipLightRule.sort_order).all()
    known = {r.key for r in rows}
    added = False
    for i, (key, group_key, label, light, threshold) in enumerate(PARTNERSHIP_LIGHT_DEFAULTS):
        if key in known:
            continue
        db.add(PartnershipLightRule(key=key, group_key=group_key, label=label,
                                    light=light, threshold=threshold, sort_order=i))
        added = True
    if added:
        db.commit()
        rows = db.query(PartnershipLightRule).order_by(PartnershipLightRule.sort_order).all()
    return rows


def _rule_map(db: Session) -> dict[str, PartnershipLightRule]:
    return {r.key: r for r in ensure_light_rules(db)}


def status_light(status: str | None, rules: dict[str, PartnershipLightRule] | None = None) -> str:
    name = status or ""
    if rules is not None:
        rule = rules.get(f"status:{name}")
        if rule:
            return rule.light
    return STATUS_LIGHTS.get(name, "gray")


CERT_AGE_KEYS = ("cert_age:fresh", "cert_age:aging", "cert_age:stale")


def cert_age_key(cert_date, rules: dict[str, PartnershipLightRule],
                 today: datetime.date | None = None) -> str:
    """Fresh/aging/stale by certificate age; the thresholds are admin-editable."""
    today = today or datetime.date.today()
    years = (today - cert_date).days / 365.25
    for key in CERT_AGE_KEYS[:-1]:
        rule = rules.get(key)
        if rule and rule.threshold is not None and years <= rule.threshold:
            return key
    return CERT_AGE_KEYS[-1]


def _filtered(db: Session, year: int | None, status: str | None, almi_product: str | None):
    rows = db.query(Partnership).all()
    if year:
        rows = [r for r in rows if r.cert_date and r.cert_date.year == year]
    if status:
        rows = [r for r in rows if r.status == status]
    if almi_product:
        rows = [r for r in rows if r.almi_product == almi_product]
    return rows


def _snapshot(p: Partnership) -> dict:
    return {
        "partner": p.partner, "product": p.product, "status": p.status,
        "almi_product": p.almi_product, "almi_version": p.almi_version,
        "type": p.type, "nda": p.nda, "agreement": p.agreement,
        "cert_date": p.cert_date.isoformat() if p.cert_date else None,
    }


def _get_or_404(db: Session, pid: int) -> Partnership:
    p = db.query(Partnership).filter(Partnership.id == pid).first()
    if not p:
        raise HTTPException(status_code=404, detail="Партнёрство не найдено")
    return p


@router.get("/analytics", response_model=PartnershipAnalytics)
def analytics(
    year: int | None = None,
    status: str | None = None,
    almi_product: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = _filtered(db, year, status, almi_product)
    by_direction = Counter(r.direction for r in rows if r.direction)
    return PartnershipAnalytics(
        total=len(rows),
        by_status=dict(Counter(r.status for r in rows if r.status)),
        by_almi_product=dict(Counter(r.almi_product for r in rows if r.almi_product)),
        by_year=dict(Counter(str(r.cert_date.year) for r in rows if r.cert_date)),
        by_direction=dict(by_direction.most_common(8)),
        nda_count=sum(1 for r in rows if r.nda),
        agreement_count=sum(1 for r in rows if r.agreement),
    )


@router.get("/traffic-light/rules", response_model=list[PartnershipLightRuleOut])
def list_light_rules(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [
        PartnershipLightRuleOut(
            id=r.id, key=r.key, group_key=r.group_key,
            group=PARTNERSHIP_LIGHT_GROUPS.get(r.group_key, r.group_key),
            label=r.label, light=r.light, threshold=r.threshold, sort_order=r.sort_order,
        )
        for r in ensure_light_rules(db)
    ]


@router.put("/traffic-light/rules", response_model=list[PartnershipLightRuleOut])
def set_light_rules(body: PartnershipLightRulesIn, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    """Admins set which category reads which light, and the certificate-age thresholds."""
    rules = _rule_map(db)
    before, after = {}, {}
    for item in body.rules:
        rule = rules.get(item.key)
        if not rule:
            raise HTTPException(400, f"Неизвестное правило: {item.key}")
        if item.light is not None:
            if item.light not in LIGHTS:
                raise HTTPException(400, f"Неизвестный цвет светофора: {item.light}")
            before[rule.key] = rule.light
            rule.light = item.light
            after[rule.key] = item.light
        if item.threshold is not None:
            if rule.group_key != "cert_age":
                raise HTTPException(400, "Порог задаётся только для срока сертификата")
            if item.threshold <= 0:
                raise HTTPException(400, "Порог должен быть больше нуля")
            before[f"{rule.key}:threshold"] = rule.threshold
            rule.threshold = item.threshold
            after[f"{rule.key}:threshold"] = item.threshold
    log_action(db, admin, "partnership_light_rule", "all", "update", before=before, after=after)
    db.commit()
    return list_light_rules(db, admin)


@router.get("/traffic-light", response_model=list[PartnershipLightRow])
def traffic_light_rows(
    year: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = _filtered(db, year, None, None)
    rules = _rule_map(db)
    total = len(rows) or 1

    def row(key, group_key, label, light, count):
        return PartnershipLightRow(key=key, group=PARTNERSHIP_LIGHT_GROUPS.get(group_key, group_key),
                                   label=label, light=light,
                                   count=count, share=round(count * 100 / total, 1))

    by_status = Counter(r.status for r in rows if r.status)
    status_rules = [r for r in rules.values() if r.group_key == "status"]
    status_rules.sort(key=lambda r: r.sort_order)
    out = [row(r.key, "status", r.label, r.light, by_status.get(r.label, 0)) for r in status_rules]
    named = {r.label for r in status_rules}
    other = sum(v for k, v in by_status.items() if k not in named)
    if other:
        out.append(row("status:__other", "status", "Прочие статусы", "gray", other))

    nda = sum(1 for r in rows if r.nda)
    agr = sum(1 for r in rows if r.agreement)
    counts = {"nda:yes": nda, "nda:no": len(rows) - nda,
              "agreement:yes": agr, "agreement:no": len(rows) - agr}
    for key, count in counts.items():
        rule = rules[key]
        out.append(row(key, rule.group_key, rule.label, rule.light, count))

    ages = Counter(cert_age_key(r.cert_date, rules) for r in rows if r.cert_date)
    for key in CERT_AGE_KEYS:
        rule = rules[key]
        out.append(row(key, "cert_age", rule.label, rule.light, ages.get(key, 0)))
    return out


@router.get("/summary", response_model=list[PartnershipPeriodRow])
def summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Per-year partnership analytics; records without a certificate date are skipped."""
    rows = [r for r in db.query(Partnership).all() if r.cert_date]
    rules = _rule_map(db)
    out = []
    for year in sorted({r.cert_date.year for r in rows}):
        group = [r for r in rows if r.cert_date.year == year]
        lights = Counter(status_light(r.status, rules) for r in group)
        out.append(PartnershipPeriodRow(
            label=f"{year} год",
            year=year,
            total=len(group),
            green=lights.get("green", 0),
            yellow=lights.get("yellow", 0),
            red=lights.get("red", 0),
            nda_count=sum(1 for r in group if r.nda),
            agreement_count=sum(1 for r in group if r.agreement),
            by_status=dict(Counter(r.status for r in group if r.status)),
            by_almi_product=dict(Counter(r.almi_product for r in group if r.almi_product).most_common(6)),
        ))
    return out


@router.get("/timeline", response_model=list[PartnershipOut])
def timeline(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.query(Partnership).all()
    return sorted(
        (r for r in rows if r.last_modified or r.cert_date),
        key=lambda r: r.last_modified or r.cert_date,
        reverse=True,
    )


@router.get("", response_model=list[PartnershipOut])
def list_partnerships(
    status: str | None = None,
    almi_product: str | None = None,
    type: str | None = None,
    search: str | None = None,
    direction: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Partnership)
    if status:
        q = q.filter(Partnership.status == status)
    if almi_product:
        q = q.filter(Partnership.almi_product == almi_product)
    if type:
        q = q.filter(Partnership.type == type)
    if direction:
        q = q.filter(Partnership.direction == direction)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            Partnership.partner.ilike(like),
            Partnership.product.ilike(like),
            Partnership.direction.ilike(like),
            Partnership.comment.ilike(like),
        ))
    return q.order_by(Partnership.id).all()


@router.get("/{partnership_id}", response_model=PartnershipOut)
def get_partnership(partnership_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _get_or_404(db, partnership_id)


@router.post("", response_model=PartnershipOut)
def create_partnership(body: PartnershipCreate, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    p = Partnership(**body.model_dump())
    db.add(p)
    db.flush()
    log_action(db, user, "partnership", p.id, "create", after=_snapshot(p))
    db.commit()
    db.refresh(p)
    return p


@router.put("/{partnership_id}", response_model=PartnershipOut)
def update_partnership(partnership_id: int, body: PartnershipUpdate,
                       db: Session = Depends(get_db), user: User = Depends(require_edit)):
    p = _get_or_404(db, partnership_id)
    before = _snapshot(p)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    db.flush()
    log_action(db, user, "partnership", p.id, "update", before=before, after=_snapshot(p))
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{partnership_id}")
def delete_partnership(partnership_id: int, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    p = _get_or_404(db, partnership_id)
    log_action(db, user, "partnership", p.id, "delete", before=_snapshot(p))
    db.delete(p)
    db.commit()
    return {"deleted": partnership_id}
