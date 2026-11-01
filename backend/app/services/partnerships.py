"""Технологические партнёрства: светофор записей, аналитика, сводка по годам, загрузка реестра.

Загрузка реестра (Excel, CSV в формате выгрузки export_xlsx) — в два шага: plan_import без записи
в базу и apply_import одной транзакцией. Запись сопоставляется по «№» (id), иначе по партнёру,
продукту партнёра и версии продукта АЛМИ; пустая ячейка ничего не стирает.
"""
from __future__ import annotations

import io
import re
from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.timeutil import local_today
from ..models import PARTNERSHIP_STATUSES, DataImport, Partnership, PartnershipLightRule, User, name_key
from . import audit, traffic_light
from .registry import PARTNERSHIP_LIGHT_GROUPS

CERT_AGE_KEYS = ("cert_age:fresh", "cert_age:aging", "cert_age:stale")


def rule_map(db: Session) -> dict[str, PartnershipLightRule]:
    return {r.key: r for r in db.scalars(select(PartnershipLightRule).order_by(PartnershipLightRule.sort_order))}


def status_light(status: str | None, rules: dict[str, PartnershipLightRule]) -> str:
    rule = rules.get(f"status:{status or ''}")
    return rule.light if rule else "gray"


def cert_age_key(cert_date: date, rules: dict[str, PartnershipLightRule], today: date | None = None) -> str:
    today = today or local_today()
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


# ---------------------------------------------------------------- загрузка реестра

SERVICE = "project_product"
MAX_IMPORT_ROWS = 5000
IMPORT_ALIASES = {
    "id": ("№", "id", "номер", "n"),
    "partner": ("партнёр", "партнер", "partner"),
    "product": ("продукт партнёра", "продукт партнера", "product"),
    "direction": ("направление", "direction"),
    "almi_product": ("продукт алми", "almi_product"),
    "almi_version": ("версия", "версия алми", "almi_version"),
    "type": ("тип", "type"),
    "status": ("статус", "status"),
    "cert_date": ("дата сертификата", "дата сертификации", "cert_date"),
    "nda": ("nda",),
    "agreement": ("соглашение", "agreement"),
    "bitrix": ("битрикс", "bitrix"),
    "website": ("сайт", "website"),
    "comment": ("комментарий", "comment"),
    "last_modified": ("дата изменения", "изменено", "last_modified"),
}
TEXT_LIMITS = {"partner": 300, "product": 2000, "direction": 300, "almi_product": 200, "almi_version": 200,
               "status": 60, "type": 30, "bitrix": 500, "website": 500, "comment": 5000}
FIELD_LABELS = {"partner": "Партнёр", "product": "Продукт партнёра", "direction": "Направление",
                "almi_product": "Продукт АЛМИ", "almi_version": "Версия", "type": "Тип", "status": "Статус",
                "cert_date": "Дата сертификата", "nda": "NDA", "agreement": "Соглашение", "bitrix": "Битрикс",
                "website": "Сайт", "comment": "Комментарий", "last_modified": "Дата изменения"}
TRUE_TEXT = {"да", "yes", "true", "1", "+", "подписан", "подписано"}
FALSE_TEXT = {"нет", "no", "false", "0", "-", "—"}


def parse_upload(filename: str, raw: bytes) -> list[dict]:
    """Строки файла: {"line", поле → текст ячейки или None (столбца нет)}."""
    from .org_import import ImportFormatError, header_map, read_table

    table = read_table(filename, raw)
    while table and not any(table[0]):
        table = table[1:]
    if not table:
        raise ImportFormatError("Файл пустой")
    mapping = header_map(table[0], IMPORT_ALIASES)
    if "partner" not in mapping:
        raise ImportFormatError("Нужен столбец «Партнёр» (формат выгрузки реестра партнёрств)")
    rows = []
    for line, values in enumerate(table[1:], start=2):
        if not any((v or "").strip() for v in values):
            continue
        if len(rows) >= MAX_IMPORT_ROWS:
            raise ImportFormatError(f"Не больше {MAX_IMPORT_ROWS} строк за одну загрузку")
        rows.append({"line": line, **{k: (values[i].strip() if i < len(values) else "") for k, i in mapping.items()}})
    if not rows:
        raise ImportFormatError("В файле нет ни одной строки с партнёрствами")
    return rows


def _date(text: str) -> date:
    raw = text.strip()
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return datetime.strptime(raw, "%d.%m.%Y").date()


def _values(row: dict) -> tuple[dict, list[str]]:
    """Значения непустых ячеек строки и ошибки разбора."""
    values: dict = {}
    errors: list[str] = []
    for key, limit in TEXT_LIMITS.items():
        text = " ".join((row.get(key) or "").split()) if key != "comment" else (row.get(key) or "").strip()
        if text:
            if len(text) > limit:
                errors.append(f"«{FIELD_LABELS[key]}» длиннее {limit} символов")
            values[key] = text[:limit]
    for key in ("cert_date", "last_modified"):
        text = row.get(key) or ""
        if text.strip():
            try:
                values[key] = _date(text)
            except ValueError:
                errors.append(f"«{FIELD_LABELS[key]}» — дата ГГГГ-ММ-ДД или ДД.ММ.ГГГГ: {text}")
    for key in ("nda", "agreement"):
        text = (row.get(key) or "").strip().lower()
        if text in TRUE_TEXT:
            values[key] = True
        elif text in FALSE_TEXT:
            values[key] = False
        elif text:
            errors.append(f"«{FIELD_LABELS[key]}» — да или нет: {row.get(key)}")
    return values, errors


def _match_key(partner: str, product: str, version: str) -> tuple:
    return name_key(partner), name_key(product), name_key(version)


def _snapshot(p: Partnership) -> dict:
    return {k: getattr(p, k) for k in FIELD_LABELS}


def plan_import(db: Session, rows: list[dict]) -> dict:
    """План загрузки без записи в базу: что создастся, изменится, ошибки строк."""
    return _plan(db, rows)[0]


def _plan(db: Session, rows: list[dict]) -> tuple[dict, list[dict]]:
    current = list(db.scalars(select(Partnership).order_by(Partnership.id)))
    by_id = {p.id: p for p in current}
    by_key: dict[tuple, list[Partnership]] = {}
    for p in current:
        by_key.setdefault(_match_key(p.partner, p.product, p.almi_version), []).append(p)
    seen: dict = {}
    out = []
    for row in rows:
        values, errors = _values(row)
        warnings: list[str] = []
        target: Partnership | None = None
        ref = (row.get("id") or "").strip()
        if ref:
            try:
                target = by_id.get(int(float(ref)))
            except ValueError:
                errors.append(f"«№» — число: {ref}")
            if target is None and not errors:
                warnings.append(f"записи №{ref} нет — будет создана новая")
        partner = values.get("partner") or (target.partner if target else "")
        if target is None and not errors:
            matches = by_key.get(_match_key(partner, values.get("product", ""), values.get("almi_version", "")), [])
            if len(matches) > 1:
                errors.append("несколько записей с этим партнёром, продуктом и версией — укажите «№»")
            elif matches:
                target = matches[0]
        if not partner:
            errors.append("не указан партнёр")
        status = values.get("status")
        if status and status not in PARTNERSHIP_STATUSES:
            warnings.append(f"статус «{status}» не из справочника — светофор статуса будет серым")
        identity = ("id", target.id) if target is not None else ("key", _match_key(
            partner, values.get("product", ""), values.get("almi_version", "")))
        if not errors and identity in seen:
            errors.append(f"повтор: эта запись уже есть в строке {seen[identity]}")
        elif not errors:
            seen[identity] = row["line"]
        changes = []
        if target is not None:
            changes = [{"field": FIELD_LABELS[k], "before": getattr(target, k), "after": v}
                       for k, v in values.items() if getattr(target, k) != v]
        action = "error" if errors else ("create" if target is None else ("update" if changes else "unchanged"))
        out.append({"line": row["line"], "id": target.id if target else None, "partner": partner,
                    "product": values.get("product", target.product if target else ""), "action": action,
                    "changes": changes, "errors": errors, "warnings": warnings, "_values": values})
    actions = [r["action"] for r in out]
    errors = actions.count("error")
    summary = {"rows": len(out), "create": actions.count("create"), "update": actions.count("update"),
               "unchanged": actions.count("unchanged"), "errors": errors}
    public = [{k: v for k, v in r.items() if k != "_values"} for r in out]
    return {"dataset": "partnerships", "summary": summary, "rows": public, "can_apply": errors == 0}, out


def apply_import(db: Session, actor: User | None, rows: list[dict], filename: str = "",
                 request: Request | None = None) -> tuple[dict, bool]:
    plan, internal = _plan(db, rows)
    if not plan["can_apply"]:
        return {**plan, "applied": False}, False
    created = updated = 0
    for item in internal:
        values = item["_values"]
        if item["action"] == "create":
            p = Partnership(partner=values.get("partner") or item["partner"], product=values.get("product", ""),
                            direction=values.get("direction", ""), almi_product=values.get("almi_product", ""),
                            almi_version=values.get("almi_version", ""), status=values.get("status", "В работе"),
                            cert_date=values.get("cert_date"), nda=values.get("nda", False),
                            agreement=values.get("agreement", False), bitrix=values.get("bitrix", ""),
                            website=values.get("website", ""), comment=values.get("comment", ""),
                            type=values.get("type", "ПО"), last_modified=values.get("last_modified"))
            db.add(p)
            db.flush()
            created += 1
            audit.record(db, actor, service_key=SERVICE, entity_type="partnership", entity_id=p.id, action="create",
                         summary=f"Добавлено партнёрство: {p.partner} (загрузка реестра)", after=_snapshot(p),
                         request=request)
        elif item["action"] == "update":
            p = db.get(Partnership, item["id"])
            before = _snapshot(p)
            for key, value in values.items():
                setattr(p, key, value)
            b, a = audit.diff(before, _snapshot(p))
            updated += 1
            audit.record(db, actor, service_key=SERVICE, entity_type="partnership", entity_id=p.id, action="update",
                         summary=f"Изменено партнёрство: {p.partner} (загрузка реестра)", before=b, after=a,
                         request=request)
    summary = plan["summary"]
    db.add(DataImport(service_key=SERVICE, dataset="partnerships", filename=(filename or "")[:300], mode="merge",
                      rows_total=summary["rows"], rows_created=created, rows_updated=updated,
                      rows_skipped=summary["unchanged"], user_id=actor.id if actor else None,
                      username=actor.username if actor else "system"))
    audit.record(db, actor, service_key=SERVICE, entity_type="partnership", action="import",
                 summary=f"Загружен реестр партнёрств «{filename}»: новых {created}, изменено {updated}",
                 after=summary, request=request)
    db.flush()
    return {**plan, "applied": True, "created": created, "updated": updated,
            "message": f"Новых записей: {created}, изменено: {updated}"}, True
