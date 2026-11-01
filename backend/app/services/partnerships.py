"""Технологические партнёрства: светофор записей, аналитика, сводка по годам."""
from __future__ import annotations

import io
from collections import Counter
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Partnership, PartnershipLightRule
from . import traffic_light
from .registry import PARTNERSHIP_LIGHT_GROUPS

CERT_AGE_KEYS = ("cert_age:fresh", "cert_age:aging", "cert_age:stale")


def rule_map(db: Session) -> dict[str, PartnershipLightRule]:
    return {r.key: r for r in db.scalars(select(PartnershipLightRule).order_by(PartnershipLightRule.sort_order))}


def status_light(status: str | None, rules: dict[str, PartnershipLightRule]) -> str:
    rule = rules.get(f"status:{status or ''}")
    return rule.light if rule else "gray"


def cert_age_key(cert_date: date, rules: dict[str, PartnershipLightRule], today: date | None = None) -> str:
    today = today or date.today()
    years = (today - cert_date).days / 365.25
    for key in CERT_AGE_KEYS[:-1]:
        rule = rules.get(key)
        if rule and rule.threshold is not None and years <= rule.threshold:
            return key
    return CERT_AGE_KEYS[-1]


def record_light(p: Partnership, rules: dict[str, PartnershipLightRule], today: date | None = None) -> dict:
    """Светофор одной записи: худший из статуса, NDA, соглашения и срока сертификата."""
    parts = {
        "status": status_light(p.status, rules),
        "nda": rules["nda:yes" if p.nda else "nda:no"].light if rules else "gray",
        "agreement": rules["agreement:yes" if p.agreement else "agreement:no"].light if rules else "gray",
    }
    if p.cert_date:
        parts["cert_age"] = rules[cert_age_key(p.cert_date, rules, today)].light
    return {"light": traffic_light.worst(parts.values()), "parts": parts}


def serialize(p: Partnership, rules: dict[str, PartnershipLightRule]) -> dict:
    lights = record_light(p, rules) if rules else {"light": "gray", "parts": {}}
    return {
        "id": p.id, "partner": p.partner, "product": p.product, "direction": p.direction,
        "almi_product": p.almi_product, "almi_version": p.almi_version, "status": p.status,
        "cert_date": p.cert_date, "nda": p.nda, "agreement": p.agreement, "bitrix": p.bitrix,
        "website": p.website, "comment": p.comment, "type": p.type, "last_modified": p.last_modified,
        "created_at": p.created_at, "updated_at": p.updated_at,
        "light": lights["light"], "light_parts": lights["parts"],
        "status_light": lights["parts"].get("status", "gray"),
    }


def analytics(rows: Sequence[Partnership]) -> dict:
    return {
        "total": len(rows),
        "by_status": dict(Counter(r.status for r in rows if r.status)),
        "by_almi_product": dict(Counter(r.almi_product for r in rows if r.almi_product).most_common()),
        "by_year": dict(sorted(Counter(r.cert_date.year for r in rows if r.cert_date).items())),
        "by_direction": dict(Counter(r.direction for r in rows if r.direction).most_common(10)),
        "by_type": dict(Counter(r.type for r in rows if r.type)),
        "nda_count": sum(1 for r in rows if r.nda),
        "agreement_count": sum(1 for r in rows if r.agreement),
    }


def light_rows(rows: Sequence[Partnership], rules: dict[str, PartnershipLightRule]) -> list[dict]:
    total = len(rows) or 1

    def row(key, group_key, label, light, count):
        return {"key": key, "group_key": group_key, "group": PARTNERSHIP_LIGHT_GROUPS.get(group_key, group_key),
                "label": label, "light": light, "count": count, "share": round(count * 100 / total, 1)}

    out = []
    by_status = Counter(r.status for r in rows if r.status)
    status_rules = sorted((r for r in rules.values() if r.group_key == "status"), key=lambda r: r.sort_order)
    out += [row(r.key, "status", r.label, r.light, by_status.get(r.label, 0)) for r in status_rules]
    other = sum(v for k, v in by_status.items() if k not in {r.label for r in status_rules})
    if other:
        out.append(row("status:__other", "status", "Прочие статусы", "gray", other))
    nda = sum(1 for r in rows if r.nda)
    agreement = sum(1 for r in rows if r.agreement)
    for key, count in (("nda:yes", nda), ("nda:no", len(rows) - nda),
                       ("agreement:yes", agreement), ("agreement:no", len(rows) - agreement)):
        rule = rules[key]
        out.append(row(key, rule.group_key, rule.label, rule.light, count))
    ages = Counter(cert_age_key(r.cert_date, rules) for r in rows if r.cert_date)
    for key in CERT_AGE_KEYS:
        rule = rules[key]
        out.append(row(key, "cert_age", rule.label, rule.light, ages.get(key, 0)))
    return out


def summary_by_year(rows: Sequence[Partnership], rules: dict[str, PartnershipLightRule]) -> list[dict]:
    dated = [r for r in rows if r.cert_date]
    out = []
    for year in sorted({r.cert_date.year for r in dated}):
        group = [r for r in dated if r.cert_date.year == year]
        lights = Counter(record_light(r, rules)["light"] for r in group)
        out.append({
            "label": f"{year} год", "year": year, "total": len(group),
            "green": lights.get("green", 0), "yellow": lights.get("yellow", 0), "red": lights.get("red", 0),
            "nda_count": sum(1 for r in group if r.nda), "agreement_count": sum(1 for r in group if r.agreement),
            "by_status": dict(Counter(r.status for r in group if r.status)),
            "by_almi_product": dict(Counter(r.almi_product for r in group if r.almi_product).most_common(6)),
        })
    return out


def export_xlsx(rows: Sequence[dict]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    light_names = {"green": "Норма", "yellow": "Внимание", "red": "Критично", "gray": "—"}
    wb = Workbook()
    ws = wb.active
    ws.title = "Партнёрства"
    ws.append(["№", "Партнёр", "Продукт партнёра", "Направление", "Продукт АЛМИ", "Версия", "Тип", "Статус",
               "Дата сертификата", "NDA", "Соглашение", "Светофор", "Битрикс", "Сайт", "Комментарий"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        ws.append([r["id"], r["partner"], r["product"], r["direction"], r["almi_product"], r["almi_version"],
                   r["type"], r["status"], r["cert_date"], "да" if r["nda"] else "нет",
                   "да" if r["agreement"] else "нет", light_names[r["light"]], r["bitrix"], r["website"],
                   r["comment"]])
    widths = (6, 30, 30, 28, 16, 18, 8, 14, 14, 6, 10, 10, 24, 24, 40)
    for column, width in zip("ABCDEFGHIJKLMNO", widths, strict=True):
        ws.column_dimensions[column].width = width
    ws.freeze_panes = "C2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
