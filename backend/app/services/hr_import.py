"""Служба персонала: загрузка метрик месяцев и реестра приёмов и увольнений (Excel, CSV), выгрузка метрик.

Загрузка в два шага, как у остальных наборов: план без записи в базу, затем то же самое одной
транзакцией с журналом. Пустая ячейка ничего не стирает. Месяцы, которых ещё нет, создаются.

Метрики месяцев — два вида таблицы:
- «широкая» (как выгрузка export_months_xlsx): строки — метрики, столбцы — месяцы.
  Столбцы «Метрика» (название) и/или «Ключ», затем месяцы: «2026-01», «01.2026», «Январь 2026»
  или дата; «Единица» и «Категория» не читаются;
- «длинная»: столбцы «Месяц», «Метрика» (название или ключ), «Значение», необязательно «Примечание».

Реестр — в формате выгрузки /api/hr/events/export.xlsx: «Месяц», «Событие» (Приём / Увольнение),
«Дата», «ФИО», «Должность», «Подразделение», «Тип занятости», «Причина». Запись сопоставляется
с реестром по событию, дате и ФИО (без учёта регистра); совпавшая — дополняется и изменяется.
"""
from __future__ import annotations

import io
import re
from collections import defaultdict
from datetime import date

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import MONTH_NAMES, DataImport, HrEmployeeEvent, HrMetricValue, HrMonth, User, name_key
from . import audit
from . import hr as hr_service
from .org_import import ImportFormatError, header_map, read_table

SERVICE = "hr"
MAX_ROWS = 10000
MONTH_WORDS = {name.casefold(): index for index, name in enumerate(MONTH_NAMES) if name}
# Родительный падеж и сокращения: «января 2026», «янв 2026»
MONTH_WORDS.update({"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6, "июля": 7,
                    "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12})
MONTH_WORDS.update({name.casefold()[:3]: index for index, name in enumerate(MONTH_NAMES) if name})

METRIC_ALIASES = {
    "metric": ("метрика", "показатель", "metric", "название"),
    "key": ("ключ", "key", "ключ метрики"),
    "month": ("месяц", "month", "период"),
    "value": ("значение", "value", "факт"),
    "note": ("примечание", "источник", "note", "комментарий"),
}
SKIPPED_COLUMNS = {"единица", "unit", "категория", "category", "ед.", "ед. изм."}
EVENT_ALIASES = {
    "month": ("месяц", "month"),
    "event": ("событие", "event", "тип события", "event_type"),
    "date": ("дата", "date", "дата события"),
    "full_name": ("фио", "full_name", "сотрудник", "имя"),
    "position": ("должность", "position"),
    "department": ("подразделение", "department", "отдел"),
    "employment_type": ("тип занятости", "employment_type", "оформление"),
    "reason": ("причина", "reason", "причина увольнения"),
}
EVENT_WORDS = {"приём": "hired", "прием": "hired", "принят": "hired", "принята": "hired", "найм": "hired",
               "hired": "hired", "увольнение": "fired", "уволен": "fired", "уволена": "fired", "fired": "fired"}
EVENT_LABELS = {"hired": "Приём", "fired": "Увольнение"}
EVENT_LIMITS = {"full_name": 300, "position": 300, "department": 200, "employment_type": 100, "reason": 300}
EVENT_FIELD_LABELS = {"position": "Должность", "department": "Подразделение", "employment_type": "Тип занятости",
                      "reason": "Причина"}


# ---------------------------------------------------------------- общее

def _table(filename: str, raw: bytes) -> list[list[str]]:
    table = read_table(filename, raw)
    while table and not any((v or "").strip() for v in table[0]):
        table = table[1:]
    if not table:
        raise ImportFormatError("Файл пустой")
    return table


def parse_month(text: str) -> str | None:
    """«2026-01», «2026-1», «01.2026», «Январь 2026», «2026-01-01T00:00:00» → «2026-01»; иначе None."""
    raw = " ".join((text or "").split()).casefold().rstrip(".").removesuffix(" г").removesuffix(" год")
    if not raw:
        return None
    year = month = None
    if match := re.match(r"^(\d{4})-(\d{1,2})(?:-\d{1,2}(?:[t ].*)?)?$", raw):
        year, month = int(match.group(1)), int(match.group(2))
    elif match := re.match(r"^(\d{1,2})[./](\d{4})$", raw):
        month, year = int(match.group(1)), int(match.group(2))
    elif match := re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", raw):
        month, year = int(match.group(2)), int(match.group(3))
    elif match := re.match(r"^([а-яё]+)\.?\s+(\d{4})$", raw):
        month, year = MONTH_WORDS.get(match.group(1)), int(match.group(2))
    if month is None or year is None or not (1 <= month <= 12 and 2000 <= year <= 2100):
        return None
    return f"{year:04d}-{month:02d}"


def _number(text: str) -> float:
    from .report_admin import parse_number

    return parse_number(text)


def _month_label(key: str) -> str:
    year, month = int(key[:4]), int(key[5:7])
    return f"{MONTH_NAMES[month]} {year}"


def _months(db: Session) -> dict[str, HrMonth]:
    return {m.key: m for m in db.scalars(select(HrMonth))}


def _create_months(db: Session, actor: User | None, keys: list[str], request: Request | None) -> dict[str, HrMonth]:
    months = _months(db)
    for key in sorted(keys):
        if key in months:
            continue
        month = HrMonth(year=int(key[:4]), month=int(key[5:7]), comment="")
        db.add(month)
        db.flush()
        months[key] = month
        audit.record(db, actor, service_key=SERVICE, entity_type="hr_month", entity_id=key, action="create",
                     summary=f"Добавлен месяц {month.label} (загрузка файла)", request=request)
    return months


def _log_import(db: Session, actor: User | None, dataset: str, filename: str, summary: dict, created: int,
                updated: int) -> None:
    db.add(DataImport(service_key=SERVICE, dataset=dataset, filename=(filename or "")[:300], mode="merge",
                      rows_total=summary["rows"], rows_created=created, rows_updated=updated,
                      rows_skipped=summary.get("unchanged", 0), user_id=actor.id if actor else None,
                      username=actor.username if actor else "system"))


# ---------------------------------------------------------------- метрики месяцев

def parse_months_upload(filename: str, raw: bytes) -> list[dict]:
    """Ячейки файла: [{"line", "month" (ГГГГ-ММ или None), "month_text", "metric", "value", "note"}]."""
    table = _table(filename, raw)
    header = [(h or "").strip() for h in table[0]]
    mapping = header_map(header, METRIC_ALIASES)
    cells: list[dict] = []
    def metric_of(values: list[str]) -> str:
        """Ключ метрики, если столбец «Ключ» заполнен, иначе название."""
        for column in ("key", "metric"):
            index = mapping.get(column)
            if index is not None and index < len(values) and (values[index] or "").strip():
                return values[index].strip()
        return ""

    if "month" in mapping and "value" in mapping and ("metric" in mapping or "key" in mapping):
        for line, values in enumerate(table[1:], start=2):
            if not any((v or "").strip() for v in values):
                continue

            def cell(column: str, vals=values) -> str:
                index = mapping.get(column)
                return (vals[index] if index is not None and index < len(vals) else "").strip()

            month_text = cell("month")
            cells.append({"line": line, "month": parse_month(month_text), "month_text": month_text,
                          "metric": metric_of(values), "value": cell("value"),
                          "note": cell("note") if "note" in mapping else None})
    elif "metric" in mapping or "key" in mapping:
        month_columns: list[tuple[int, str, str | None]] = []
        for index, title in enumerate(header):
            if index in mapping.values() or title.strip().casefold() in SKIPPED_COLUMNS or not title.strip():
                continue
            month_columns.append((index, title, parse_month(title)))
        bad = [title for _, title, key in month_columns if key is None]
        if bad:
            raise ImportFormatError(f"Столбец «{bad[0]}» — не месяц: укажите месяц как ГГГГ-ММ или «Январь 2026»")
        if not month_columns:
            raise ImportFormatError("Нет столбцов месяцев: после «Метрика» укажите месяцы (ГГГГ-ММ)")
        for line, values in enumerate(table[1:], start=2):
            if not any((v or "").strip() for v in values):
                continue
            metric = metric_of(values)
            for index, title, key in month_columns:
                value = (values[index] if index < len(values) else "").strip()
                if value:
                    cells.append({"line": line, "month": key, "month_text": title, "metric": metric, "value": value,
                                  "note": None})
    else:
        raise ImportFormatError("Нужен столбец «Метрика» (строки — метрики, столбцы — месяцы) или столбцы «Месяц», "
                                "«Метрика», «Значение»")
    if len(cells) > MAX_ROWS:
        raise ImportFormatError(f"Не больше {MAX_ROWS} значений за одну загрузку")
    if not cells:
        raise ImportFormatError("В файле нет ни одного значения метрик")
    return cells


def _metric_resolver(db: Session):
    defs = hr_service.definitions(db, active_only=False)
    by_key = {d.key.casefold(): d for d in defs}
    by_label = {name_key(d.label): d for d in defs}

    def resolve(text: str):
        return by_key.get((text or "").strip().casefold()) or by_label.get(name_key(text or ""))

    return resolve


def _plan_months(db: Session, cells: list[dict]) -> tuple[dict, list[dict]]:
    resolve = _metric_resolver(db)
    months = {m.key: m for m in hr_service.months_sorted(db)}
    current = {(key, v.metric_key): v for key, m in months.items() for v in m.values}
    seen: dict[tuple, int] = {}
    rows: list[dict] = []
    for cell in cells:
        errors: list[str] = []
        definition = resolve(cell["metric"])
        if definition is None:
            errors.append(f"Метрика «{cell['metric']}» не найдена — укажите название или ключ метрики")
        if cell["month"] is None:
            errors.append(f"Месяц «{cell['month_text']}» не распознан — укажите ГГГГ-ММ")
        value = None
        if cell["value"] in ("-", "—"):
            continue
        try:
            value = _number(cell["value"]) if cell["value"] else None
        except ValueError:
            errors.append(f"«{cell['value']}» — не число")
        if value is None and not errors and not cell["note"]:
            continue
        key = (cell["month"], definition.key if definition else None)
        if not errors:
            if key in seen:
                errors.append(f"Повтор: значение этой метрики за месяц уже задано в строке {seen[key]}")
            else:
                seen[key] = cell["line"]
        existing = current.get(key) if not errors else None
        before = None if existing is None else {"value": existing.value, "note": existing.source_note or ""}
        after = dict(before or {"value": None, "note": ""})
        if value is not None:
            after["value"] = value
        if cell["note"]:
            after["note"] = cell["note"]
        action = "error" if errors else ("create" if existing is None else
                                        ("unchanged" if before == after else "update"))
        rows.append({"line": cell["line"], "month": cell["month"], "month_label": _month_label(cell["month"])
                     if cell["month"] else cell["month_text"], "metric_key": definition.key if definition else None,
                     "metric_label": definition.label if definition else cell["metric"], "before": before,
                     "after": after if not errors else None, "action": action, "errors": errors})
    new_months = sorted({r["month"] for r in rows if r["action"] != "error" and r["month"] not in months})
    actions = [r["action"] for r in rows]
    errors = actions.count("error")
    summary = {"rows": len(rows), "create": actions.count("create"), "update": actions.count("update"),
               "unchanged": actions.count("unchanged"), "errors": errors, "create_months": len(new_months)}
    plan = {"dataset": "hr_months", "summary": summary, "months": [{"key": k, "label": _month_label(k)}
                                                                  for k in new_months],
            "rows": rows, "can_apply": errors == 0}
    return plan, rows


def plan_months(db: Session, cells: list[dict]) -> dict:
    """План загрузки метрик: что создастся, изменится, ошибки; без записи в базу."""
    return _plan_months(db, cells)[0]


def apply_months(db: Session, actor: User | None, cells: list[dict], filename: str = "",
                 request: Request | None = None) -> tuple[dict, bool]:
    plan, rows = _plan_months(db, cells)
    if not plan["can_apply"]:
        return {**plan, "applied": False}, False
    changed = [r for r in rows if r["action"] in ("create", "update")]
    months = _create_months(db, actor, [m["key"] for m in plan["months"]], request)
    current = {(v.month_id, v.metric_key): v for v in db.scalars(select(HrMetricValue).where(
        HrMetricValue.month_id.in_([months[r["month"]].id for r in changed] or [0])))}
    by_month: dict[str, list[dict]] = defaultdict(list)
    for row in changed:
        by_month[row["month"]].append(row)
    for key, month_rows in sorted(by_month.items()):
        month = months[key]
        before, after = {}, {}
        for row in month_rows:
            value = current.get((month.id, row["metric_key"]))
            if value is None:
                db.add(HrMetricValue(month_id=month.id, metric_key=row["metric_key"], value=row["after"]["value"],
                                     source_note=row["after"]["note"]))
            else:
                value.value, value.source_note = row["after"]["value"], row["after"]["note"]
            before[row["metric_key"]] = (row["before"] or {}).get("value")
            after[row["metric_key"]] = row["after"]["value"]
        month.updated_at = utcnow()
        audit.record(db, actor, service_key=SERVICE, entity_type="hr_metrics", entity_id=key, action="update",
                     summary=f"Изменены метрики за {month.label}: {len(month_rows)} (загрузка файла)",
                     before=before, after=after, request=request)
    summary = plan["summary"]
    _log_import(db, actor, "hr_months", filename, summary, summary["create"], summary["update"])
    audit.record(db, actor, service_key=SERVICE, entity_type="hr_metrics", action="import",
                 summary=f"Загружены метрики «{filename}»: новых {summary['create']}, изменено {summary['update']}, "
                         f"месяцев добавлено {summary['create_months']}", after=summary, request=request)
    db.flush()
    message = f"Новых значений: {summary['create']}, изменено: {summary['update']}"
    return {**plan, "applied": True, "message": message}, True


def export_months_xlsx(db: Session) -> bytes:
    """Метрики месяцев «широкой» таблицей: строки — метрики, столбцы — месяцы (формат загрузки)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    months = hr_service.months_sorted(db)
    wb = Workbook()
    ws = wb.active
    ws.title = "Метрики"
    ws.append(["Метрика", "Ключ", "Единица", *[m.key for m in months]])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for d in hr_service.definitions(db):
        values = [hr_service.values_map(m).get(d.key) for m in months]
        ws.append([d.label, d.key, d.unit, *values])
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 30
    ws.freeze_panes = "D2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- реестр приёмов и увольнений

def parse_events_upload(filename: str, raw: bytes) -> list[dict]:
    table = _table(filename, raw)
    mapping = header_map(table[0], EVENT_ALIASES)
    missing = [title for column, title in (("event", "Событие"), ("date", "Дата"), ("full_name", "ФИО"))
               if column not in mapping]
    if missing:
        raise ImportFormatError(f"Нужен столбец «{missing[0]}» (столбцы выгрузки реестра: Месяц, Событие, Дата, ФИО, "
                                "Должность, Подразделение, Тип занятости, Причина)")
    rows = []
    for line, values in enumerate(table[1:], start=2):
        if not any((v or "").strip() for v in values):
            continue
        if len(rows) >= MAX_ROWS:
            raise ImportFormatError(f"Не больше {MAX_ROWS} записей за одну загрузку")
        rows.append({"line": line, **{k: (values[i].strip() if i < len(values) else "") for k, i in mapping.items()}})
    if not rows:
        raise ImportFormatError("В файле нет ни одной записи реестра")
    return rows


def _event_date(text: str) -> date:
    raw = (text or "").strip()
    if match := re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw):
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    if match := re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", raw):
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    raise ValueError(raw)


def _event_key(event_type: str, event_date: date, full_name: str) -> tuple:
    return event_type, event_date, name_key(full_name)


def _plan_events(db: Session, rows: list[dict]) -> tuple[dict, list[dict]]:
    months = _months(db)
    existing: dict[tuple, HrEmployeeEvent] = {}
    for event in db.scalars(select(HrEmployeeEvent)):
        existing.setdefault(_event_key(event.event_type, event.event_date, event.full_name), event)
    seen: dict[tuple, int] = {}
    out: list[dict] = []
    for row in rows:
        errors: list[str] = []
        warnings: list[str] = []
        event_type = EVENT_WORDS.get((row.get("event") or "").strip().casefold())
        if event_type is None:
            errors.append(f"Событие «{row.get('event') or ''}» — «Приём» или «Увольнение»")
        event_date = None
        try:
            event_date = _event_date(row.get("date") or "")
        except ValueError:
            errors.append(f"Дата «{row.get('date') or ''}» — в формате ГГГГ-ММ-ДД или ДД.ММ.ГГГГ")
        full_name = " ".join((row.get("full_name") or "").split())
        if not full_name:
            errors.append("Не указано ФИО")
        month = f"{event_date.year:04d}-{event_date.month:02d}" if event_date else None
        if row.get("month") and event_date is not None:
            stated = parse_month(row["month"])
            if stated is None:
                errors.append(f"Месяц «{row['month']}» не распознан — укажите ГГГГ-ММ")
            elif stated != month:
                errors.append(f"Дата {event_date.isoformat()} вне месяца {_month_label(stated)}")
        values = {}
        for key, limit in EVENT_LIMITS.items():
            if key == "full_name":
                continue
            text = " ".join((row.get(key) or "").split())
            if text:
                if len(text) > limit:
                    warnings.append(f"«{EVENT_FIELD_LABELS[key]}» сокращено до {limit} символов")
                values[key] = text[:limit]
        if len(full_name) > EVENT_LIMITS["full_name"]:
            errors.append("ФИО длиннее 300 символов")
        key = _event_key(event_type, event_date, full_name) if not errors else None
        if key is not None:
            if key in seen:
                errors.append(f"Повтор: эта запись уже есть в строке {seen[key]}")
            else:
                seen[key] = row["line"]
        target = existing.get(key) if not errors else None
        changes = [] if target is None else [
            {"field": EVENT_FIELD_LABELS[k], "before": getattr(target, k), "after": v}
            for k, v in values.items() if (getattr(target, k) or "") != v]
        action = "error" if errors else ("create" if target is None else ("update" if changes else "unchanged"))
        out.append({"line": row["line"], "event_type": event_type, "event_label": EVENT_LABELS.get(event_type, ""),
                    "event_date": event_date.isoformat() if event_date else (row.get("date") or ""),
                    "month": month, "full_name": full_name, "id": target.id if target else None, "action": action,
                    "changes": changes, "errors": errors, "warnings": warnings, "_values": values})
    new_months = sorted({r["month"] for r in out if r["action"] == "create" and r["month"] not in months})
    actions = [r["action"] for r in out]
    errors = actions.count("error")
    summary = {"rows": len(out), "create": actions.count("create"), "update": actions.count("update"),
               "unchanged": actions.count("unchanged"), "errors": errors, "create_months": len(new_months),
               "hired": sum(1 for r in out if r["action"] == "create" and r["event_type"] == "hired"),
               "fired": sum(1 for r in out if r["action"] == "create" and r["event_type"] == "fired")}
    public = [{k: v for k, v in r.items() if k != "_values"} for r in out]
    plan = {"dataset": "hr_events", "summary": summary,
            "months": [{"key": k, "label": _month_label(k)} for k in new_months], "rows": public,
            "can_apply": errors == 0}
    return plan, out


def plan_events(db: Session, rows: list[dict]) -> dict:
    return _plan_events(db, rows)[0]


def apply_events(db: Session, actor: User | None, rows: list[dict], filename: str = "",
                 request: Request | None = None) -> tuple[dict, bool]:
    plan, internal = _plan_events(db, rows)
    if not plan["can_apply"]:
        return {**plan, "applied": False}, False
    months = _create_months(db, actor, [m["key"] for m in plan["months"]], request)
    created = updated = 0
    for item in internal:
        values = item["_values"]
        if item["action"] == "create":
            event = HrEmployeeEvent(month_id=months[item["month"]].id, event_type=item["event_type"],
                                    event_date=date.fromisoformat(item["event_date"]), full_name=item["full_name"],
                                    position=values.get("position", ""), department=values.get("department", ""),
                                    employment_type=values.get("employment_type", ""),
                                    reason=values.get("reason", ""))
            db.add(event)
            db.flush()
            created += 1
            audit.record(db, actor, service_key=SERVICE, entity_type="hr_event", entity_id=event.id, action="create",
                         summary=f"{item['event_label']}: {event.full_name} (загрузка файла)",
                         after={"event_type": event.event_type, "event_date": event.event_date,
                                "full_name": event.full_name, **values}, request=request)
        elif item["action"] == "update":
            event = db.get(HrEmployeeEvent, item["id"])
            before = {k: getattr(event, k) for k in values}
            for key, value in values.items():
                setattr(event, key, value)
            b, a = audit.diff(before, values)
            updated += 1
            audit.record(db, actor, service_key=SERVICE, entity_type="hr_event", entity_id=event.id, action="update",
                         summary=f"Изменена запись: {event.full_name} (загрузка файла)", before=b, after=a,
                         request=request)
    summary = plan["summary"]
    _log_import(db, actor, "hr_events", filename, summary, created, updated)
    audit.record(db, actor, service_key=SERVICE, entity_type="hr_event", action="import",
                 summary=f"Загружен реестр «{filename}»: приёмов {summary['hired']}, увольнений {summary['fired']}, "
                         f"изменено {updated}", after=summary, request=request)
    db.flush()
    return {**plan, "applied": True, "created": created, "updated": updated,
            "message": f"Новых записей: {created}, изменено: {updated}"}, True
