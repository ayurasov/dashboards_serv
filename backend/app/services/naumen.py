"""Аналитика заявок Naumen SD и сопоставление с недельным отчётом ТП."""
from __future__ import annotations

import io
import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from ..core.errors import ValidationFailed
from ..models import NaumenTicket, TpWeeklyReport

CLOSED_STATUSES = ("Закрыта", "Выполнена")
# Признаки организаций группы РусГидро в названии
RUSHYDRO_MARKERS = ("русгидро", "ргидро", "гэс", "энерго", "дск", "дгк", "гидро")


def _avg(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def _pct(part: int, total: int) -> float | None:
    return round(part / total * 100, 1) if total else None


def _resolve_hours(t: NaumenTicket) -> float | None:
    if t.solved_at and t.registered_at:
        return (t.solved_at - t.registered_at).total_seconds() / 3600
    return None


def is_rushydro(org: str | None) -> bool:
    name = (org or "").lower()
    return any(marker in name for marker in RUSHYDRO_MARKERS)


def last_months_filter(tickets: Sequence[NaumenTicket], months: int) -> list[NaumenTicket]:
    keys = sorted({t.registered_at.strftime("%Y-%m") for t in tickets if t.registered_at})
    if not keys:
        return list(tickets)
    first = keys[max(0, len(keys) - months)]
    return [t for t in tickets if t.registered_at and t.registered_at.strftime("%Y-%m") >= first]


def summary(tickets: Sequence[NaumenTicket]) -> dict:
    if not tickets:
        return {"empty": True}
    total = len(tickets)
    closed = sum(1 for t in tickets if t.status in CLOSED_STATUSES)
    overdue = sum(1 for t in tickets if t.is_overdue)
    reopened = sum(1 for t in tickets if t.is_reopened)

    by_month: dict[str, dict] = defaultdict(lambda: {"registered": 0, "solved": 0, "overdue": 0, "reopened": 0,
                                                     "proc": [], "resolve": []})
    by_org: dict[str, dict] = defaultdict(lambda: {"total": 0, "closed": 0, "overdue": 0, "proc": []})
    by_channel: dict[str, int] = defaultdict(int)
    by_status: dict[str, int] = defaultdict(int)
    by_responsible: dict[str, dict] = defaultdict(lambda: {"total": 0, "overdue": 0})
    resolve_all = []
    for t in tickets:
        if t.registered_at:
            m = by_month[t.registered_at.strftime("%Y-%m")]
            m["registered"] += 1
            m["overdue"] += int(t.is_overdue)
            m["reopened"] += int(t.is_reopened)
            if t.processing_hours is not None:
                m["proc"].append(t.processing_hours)
        if t.solved_at:
            m = by_month[t.solved_at.strftime("%Y-%m")]
            m["solved"] += 1
            hours = _resolve_hours(t)
            if hours is not None:
                m["resolve"].append(hours)
                resolve_all.append(hours)
        if t.org:
            o = by_org[t.org]
            o["total"] += 1
            o["closed"] += int(t.status in CLOSED_STATUSES)
            o["overdue"] += int(t.is_overdue)
            if t.processing_hours is not None:
                o["proc"].append(t.processing_hours)
        if t.responsible:
            r = by_responsible[t.responsible]
            r["total"] += 1
            r["overdue"] += int(t.is_overdue)
        by_channel[t.channel or "—"] += 1
        by_status[t.status or "—"] += 1

    registered = [t.registered_at for t in tickets if t.registered_at]
    return {
        "empty": False,
        "total": total,
        "closed": closed,
        "in_progress": total - closed,
        "overdue": overdue,
        "overdue_pct": _pct(overdue, total),
        "reopened": reopened,
        "reopened_pct": _pct(reopened, total),
        "closed_pct": _pct(closed, total),
        "avg_proc_hours": _avg(t.processing_hours for t in tickets),
        "avg_resolve_hours": _avg(resolve_all),
        "first": min(registered).isoformat() if registered else None,
        "last": max(registered).isoformat() if registered else None,
        "months": [
            {"month": key, "registered": m["registered"], "solved": m["solved"], "overdue": m["overdue"],
             "overdue_pct": _pct(m["overdue"], m["registered"]), "reopened": m["reopened"],
             "reopened_pct": _pct(m["reopened"], m["registered"]),
             "avg_proc_hours": _avg(m["proc"]), "avg_resolve_hours": _avg(m["resolve"])}
            for key, m in sorted(by_month.items())
        ],
        "orgs": sorted(
            ({"org": org, "total": o["total"], "closed": o["closed"], "overdue": o["overdue"],
              "overdue_pct": _pct(o["overdue"], o["total"]), "avg_proc_hours": _avg(o["proc"])}
             for org, o in by_org.items()),
            key=lambda x: -x["total"]),
        "responsibles": sorted(
            ({"name": name, "total": r["total"], "overdue": r["overdue"], "overdue_pct": _pct(r["overdue"], r["total"])}
             for name, r in by_responsible.items()),
            key=lambda x: -x["total"])[:20],
        "channels": [{"channel": k, "count": v} for k, v in sorted(by_channel.items(), key=lambda x: -x[1])],
        "statuses": [{"status": k, "count": v} for k, v in sorted(by_status.items(), key=lambda x: -x[1])],
    }


def match(rows: Sequence[TpWeeklyReport], tickets: Sequence[NaumenTicket]) -> dict:
    """Недели отчёта ТП рядом с недельными (ISO) и месячными агрегатами Naumen."""
    reg_week: dict = defaultdict(int)
    solved_week: dict = defaultdict(int)
    overdue_week: dict = defaultdict(int)
    rush_week: dict = defaultdict(int)
    resolve_week: dict = defaultdict(list)
    month_nm: dict = defaultdict(lambda: {"registered": 0, "solved": 0, "overdue": 0, "rushydro": 0, "resolve": []})
    for t in tickets:
        if t.registered_at:
            y, w, _ = t.registered_at.isocalendar()
            key = (y, w)
            reg_week[key] += 1
            overdue_week[key] += int(t.is_overdue)
            rush_week[key] += int(is_rushydro(t.org))
            hours = _resolve_hours(t)
            if hours is not None:
                resolve_week[key].append(hours)
            m = month_nm[t.registered_at.strftime("%Y-%m")]
            m["registered"] += 1
            m["overdue"] += int(t.is_overdue)
            m["rushydro"] += int(is_rushydro(t.org))
            if hours is not None:
                m["resolve"].append(hours)
        if t.solved_at:
            y, w, _ = t.solved_at.isocalendar()
            solved_week[(y, w)] += 1
            month_nm[t.solved_at.strftime("%Y-%m")]["solved"] += 1

    weeks = []
    month_tp: dict = {}
    for row in rows:
        key = (row.year, row.week)
        weeks.append({
            "period": row.period, "year": row.year, "week": row.week,
            "tp_new_received": row.new_received, "tp_solved": row.total_solved_week, "tp_in_work": row.total_in_work,
            "tp_rushydro_hours": row.rushydro_hours, "tp_altos_avg_time": row.altos_avg_time,
            "naumen_registered": reg_week.get(key, 0), "naumen_solved": solved_week.get(key, 0),
            "naumen_overdue": overdue_week.get(key, 0), "naumen_rushydro": rush_week.get(key, 0),
            "naumen_avg_resolve_hours": _avg(resolve_week.get(key, [])),
        })
        try:
            month_key = datetime.fromisocalendar(row.year, row.week, 1).strftime("%Y-%m")
        except ValueError:
            continue
        m = month_tp.setdefault(month_key, {"new": 0.0, "solved": 0.0, "rush": 0.0, "in_work": [], "altos": []})
        m["new"] += row.new_received or 0
        m["solved"] += row.total_solved_week or 0
        m["rush"] += row.rushydro_hours or 0
        if row.total_in_work is not None:
            m["in_work"].append(row.total_in_work)
        if row.altos_avg_time is not None:
            m["altos"].append(row.altos_avg_time)

    months = []
    for key in sorted(set(month_tp) | set(month_nm)):
        tp, nm = month_tp.get(key), month_nm.get(key, {})
        months.append({
            "period": key, "year": int(key[:4]), "month": key,
            "tp_new_received": tp["new"] if tp else None, "tp_solved": tp["solved"] if tp else None,
            "tp_in_work": _avg(tp["in_work"]) if tp else None,
            "tp_rushydro_hours": tp["rush"] if tp else None,
            "tp_altos_avg_time": _avg(tp["altos"]) if tp else None,
            "naumen_registered": nm.get("registered", 0), "naumen_solved": nm.get("solved", 0),
            "naumen_overdue": nm.get("overdue", 0), "naumen_rushydro": nm.get("rushydro", 0),
            "naumen_avg_resolve_hours": _avg(nm.get("resolve", [])),
        })
    return {"weeks": weeks, "months": months, "weeks_count": len(weeks)}


# ---------- импорт выгрузки Naumen (xlsx) ----------

IMPORT_COLUMNS = {
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


def parse_hours(value) -> float | None:
    """«12:30» → 12.5; число — как есть."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    match_ = re.match(r"^\s*(\d+):(\d+)", str(value))
    if not match_:
        return None
    return round(int(match_.group(1)) + int(match_.group(2)) / 60, 2)


def _to_dt(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value:
        text = str(value).strip()
        for fmt in (None, "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
            try:
                return datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def parse_xlsx(raw: bytes) -> tuple[list[dict], int]:
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:
        raise ValidationFailed("Не удалось прочитать файл Excel") from exc
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [str(c).strip() if c else "" for c in next(rows, [])]
    index = {col: i for i, col in enumerate(header) if col in IMPORT_COLUMNS}
    if "Дата регистрации" not in index:
        raise ValidationFailed("Файл не похож на выгрузку Naumen: нет столбца «Дата регистрации»")

    def get(row, column):
        i = index.get(column)
        return row[i] if i is not None and i < len(row) else None

    out, skipped = [], 0
    for row in rows:
        if not row or not any(row):
            continue
        registered = _to_dt(get(row, "Дата регистрации"))
        if registered is None:
            skipped += 1
            continue
        number = get(row, "Номер")
        try:
            number = int(number) if number not in (None, "") else None
        except (TypeError, ValueError):
            number = None
        out.append({
            "number": number,
            "name": str(get(row, "Название") or "")[:50],
            "registered_at": registered,
            "solved_at": _to_dt(get(row, "Дата решения")),
            "deadline_at": _to_dt(get(row, "Регламентное время закрытия заявки")),
            "status": str(get(row, "Статус") or "")[:100],
            "org": str(get(row, "Наименование организации") or "")[:300],
            "responsible": str(get(row, "Ответственный (сотрудник)") or "")[:300],
            "team": str(get(row, "Ответственный (команда)") or "")[:200],
            "first_line": str(get(row, "Сотрудник первая линия") or "")[:300],
            "channel": str(get(row, "Способ обращения") or "")[:100],
            "is_overdue": str(get(row, "Просрочен") or "").strip().lower() in ("просрочен", "да", "1", "true"),
            "is_reopened": str(get(row, "Возобновлялась") or "").strip().lower() in ("да", "1", "true"),
            "processing_hours": parse_hours(get(row, "Время обработки заявки")),
        })
    wb.close()
    if not out:
        raise ValidationFailed("В файле нет ни одной заявки с датой регистрации")
    return out, skipped
