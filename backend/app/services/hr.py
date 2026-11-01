"""Служба персонала: агрегаты по месяцам и периодам, светофор, цели."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.errors import NotFound, ValidationFailed
from ..models import HrEmployeeEvent, HrMetricDefinition, HrMonth, HrTarget, TrafficLightRule
from . import traffic_light
from .registry import HR_METRIC_CATEGORIES

PERIOD_TYPES = ("month", "quarter", "half", "year")


def parse_month_key(key: str) -> tuple[int, int]:
    try:
        year_s, month_s = key.split("-")
        year, month = int(year_s), int(month_s)
    except ValueError as exc:
        raise ValidationFailed("Месяц указывается в формате ГГГГ-ММ") from exc
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise ValidationFailed("Месяц указывается в формате ГГГГ-ММ")
    return year, month


def get_month(db: Session, key: str, *, full: bool = False) -> HrMonth:
    year, month = parse_month_key(key)
    stmt = select(HrMonth).where(HrMonth.year == year, HrMonth.month == month)
    if full:
        stmt = stmt.options(selectinload(HrMonth.values), selectinload(HrMonth.events), selectinload(HrMonth.notes))
    record = db.scalar(stmt)
    if record is None:
        raise NotFound(f"Месяц {key} не найден")
    return record


def months_sorted(db: Session) -> list[HrMonth]:
    return list(db.scalars(select(HrMonth).options(selectinload(HrMonth.values), selectinload(HrMonth.events))
                           .order_by(HrMonth.year, HrMonth.month)))


def definitions(db: Session, *, active_only: bool = True) -> list[HrMetricDefinition]:
    stmt = select(HrMetricDefinition).order_by(HrMetricDefinition.sort_order, HrMetricDefinition.id)
    if active_only:
        stmt = stmt.where(HrMetricDefinition.is_active.is_(True))
    return list(db.scalars(stmt))


def visible_events(events: Sequence[HrEmployeeEvent], scope: set[str] | None) -> list[HrEmployeeEvent]:
    if scope is None:
        return list(events)
    return [e for e in events if e.department in scope]


def values_map(month: HrMonth) -> dict[str, float | None]:
    return {v.metric_key: v.value for v in month.values}


def aggregate(values: list[float], method: str) -> float | None:
    if not values:
        return None
    if method == "sum":
        return round(sum(values), 4)
    if method == "latest":
        return values[-1]
    if method == "max":
        return max(values)
    return round(sum(values) / len(values), 4)


def light_for(value: float | None, rule: TrafficLightRule | None) -> str:
    """Незаполненная метрика под включённым правилом — красная (пробел в данных);
    метрика без правила — серая и на итоговый статус не влияет."""
    if value is None:
        return "red" if rule is not None and rule.enabled else "gray"
    return traffic_light.evaluate(value, rule)


def month_metrics(db: Session, month: HrMonth, previous: HrMonth | None,
                  defs: list[HrMetricDefinition] | None = None,
                  rules: dict[str, TrafficLightRule] | None = None,
                  targets: dict[str, float] | None = None) -> list[dict]:
    defs = defs if defs is not None else definitions(db)
    rules = rules if rules is not None else traffic_light.rules_for(db, "hr")
    targets = targets if targets is not None else targets_for_year(db, month.year)
    values = {v.metric_key: v for v in month.values}
    prev_values = values_map(previous) if previous else {}
    out = []
    for d in defs:
        item = values.get(d.key)
        value = item.value if item else None
        prev = prev_values.get(d.key)
        out.append({
            "key": d.key, "label": d.label, "unit": d.unit, "category": d.category,
            "category_label": HR_METRIC_CATEGORIES.get(d.category, d.category),
            "direction": d.direction, "description": d.description,
            "value": value, "previous": prev,
            "delta": None if value is None or prev is None else round(value - prev, 4),
            "source_note": item.source_note if item else "",
            "filled": value is not None,
            "light": light_for(value, rules.get(d.key)),
            "target": targets.get(d.key),
        })
    return out


def targets_for_year(db: Session, year: int) -> dict[str, float]:
    return {t.metric_key: t.target_value for t in db.scalars(
        select(HrTarget).where(HrTarget.year == year, HrTarget.target_value.is_not(None)))}


def month_counts(month: HrMonth, scope: set[str] | None) -> tuple[int, int]:
    events = visible_events(month.events, scope)
    hired = sum(1 for e in events if e.event_type == "hired")
    return hired, len(events) - hired


def period_bounds(period_type: str, index: int) -> tuple[int, int]:
    if period_type == "month":
        return index, index
    if period_type == "quarter":
        return (index - 1) * 3 + 1, index * 3
    if period_type == "half":
        return (1, 6) if index == 1 else (7, 12)
    return 1, 12


def period_label(year: int, period_type: str, index: int) -> str:
    from ..models import MONTH_NAMES

    if period_type == "month":
        return f"{MONTH_NAMES[index]} {year}"
    if period_type == "quarter":
        return f"{index} кв. {year}"
    if period_type == "half":
        return f"{'I' if index == 1 else 'II'} полугодие {year}"
    return f"{year} год"


def period_summary(db: Session, period_type: str, scope: set[str] | None) -> list[dict]:
    if period_type not in PERIOD_TYPES:
        raise ValidationFailed("Тип периода: month, quarter, half или year")
    months = months_sorted(db)
    defs = definitions(db)
    rules = traffic_light.rules_for(db, "hr")
    indices = {"month": range(1, 13), "quarter": range(1, 5), "half": range(1, 3), "year": range(1, 2)}[period_type]
    results = []
    for year in sorted({m.year for m in months}):
        for index in indices:
            lo, hi = period_bounds(period_type, index)
            chunk = [m for m in months if m.year == year and lo <= m.month <= hi]
            if not chunk:
                continue
            metrics = {}
            for d in defs:
                vals = [v for m in chunk if (v := values_map(m).get(d.key)) is not None]
                metrics[d.key] = aggregate(vals, d.aggregation)
            hired = fired = 0
            for m in chunk:
                h, f = month_counts(m, scope)
                hired, fired = hired + h, fired + f
            lights = {key: light_for(val, rules.get(key)) for key, val in metrics.items()}
            results.append({
                "key": f"{year}-{period_type[0].upper()}{index}",
                "label": period_label(year, period_type, index),
                "year": year, "index": index, "months": [m.key for m in chunk],
                "months_count": len(chunk), "hired": hired, "fired": fired, "net": hired - fired,
                "metrics": metrics, "lights": lights,
                "light_counts": traffic_light.counts(lights.values()),
            })
    return results


def dashboard(db: Session, keys: list[str], scope: set[str] | None) -> dict:
    """Данные главного дашборда службы персонала за выбранные месяцы (по умолчанию — все)."""
    months = months_sorted(db)
    if keys:
        wanted = set(keys)
        selected = [m for m in months if m.key in wanted]
    else:
        selected = months
    defs = definitions(db)
    rules = traffic_light.rules_for(db, "hr")
    by_key = {m.key: i for i, m in enumerate(months)}
    series = []
    for m in selected:
        idx = by_key[m.key]
        prev = months[idx - 1] if idx > 0 else None
        hired, fired = month_counts(m, scope)
        metrics = month_metrics(db, m, prev, defs, rules, targets_for_year(db, m.year))
        series.append({"key": m.key, "label": m.label, "year": m.year, "month": m.month,
                       "hired": hired, "fired": fired, "net": hired - fired,
                       "metrics": metrics,
                       "light_counts": traffic_light.counts(x["light"] for x in metrics)})
    # «Последний» — последний месяц с данными: только что добавленный пустой месяц не обнуляет карточки
    latest = next((s for s in reversed(series)
                   if s["hired"] or s["fired"] or any(m["filled"] for m in s["metrics"])),
                  series[-1] if series else None)
    total_hired = sum(s["hired"] for s in series)
    total_fired = sum(s["fired"] for s in series)
    by_department: dict[str, dict[str, int]] = {}
    for m in selected:
        for e in visible_events(m.events, scope):
            dep = e.department or "Без подразделения"
            bucket = by_department.setdefault(dep, {"hired": 0, "fired": 0})
            bucket[e.event_type] += 1
    return {
        "months": [{"key": m.key, "label": m.label} for m in months],
        "selected": [m.key for m in selected],
        "series": series,
        "latest": latest,
        "totals": {"hired": total_hired, "fired": total_fired, "net": total_hired - total_fired},
        "departments": sorted(({"department": k, **v} for k, v in by_department.items()),
                              key=lambda r: -(r["hired"] + r["fired"])),
        "categories": HR_METRIC_CATEGORIES,
    }


TARGET_TOLERANCE = 0.1  # в пределах 10% от цели — «внимание», дальше — «критично»


def target_status(current: float | None, target: float | None, lower_better: bool) -> str:
    if current is None or target is None:
        return "gray"
    if lower_better:
        if current <= target:
            return "green"
        return "yellow" if current <= target * (1 + TARGET_TOLERANCE) else "red"
    if current >= target:
        return "green"
    return "yellow" if current >= target * (1 - TARGET_TOLERANCE) else "red"


def target_rows(db: Session) -> list[dict]:
    defs = {d.key: d for d in definitions(db, active_only=False)}
    rules = traffic_light.rules_for(db, "hr")
    # Последний факт метрики — всего и внутри каждого года. Цель года оценивается по данным этого года:
    # прошлогодняя цель не «выполняется» данными текущего года, цель будущего года — «нет данных».
    # Справочное значение без цели (например, факт прошлого года) сравнивается с последним фактом.
    latest: dict[str, tuple[float, str]] = {}
    latest_in_year: dict[tuple[str, int], tuple[float, str]] = {}
    for m in months_sorted(db):
        for v in m.values:
            if v.value is not None:
                latest[v.metric_key] = (v.value, m.label)
                latest_in_year[(v.metric_key, m.year)] = (v.value, m.label)
    rows = []
    for t in db.scalars(select(HrTarget)):
        d = defs.get(t.metric_key)
        rule = rules.get(t.metric_key)
        direction = rule.direction if rule else (d.direction if d else "higher_is_better")
        if direction not in ("lower_is_better", "higher_is_better"):
            direction = "higher_is_better"
        target = t.target_value
        if target is not None:
            current, month = latest_in_year.get((t.metric_key, t.year), (None, ""))
        else:
            current, month = latest.get(t.metric_key, (None, ""))
        rows.append({
            "id": t.id, "metric_key": t.metric_key, "metric_label": d.label if d else t.metric_key,
            "unit": d.unit if d else "", "year": t.year, "label": t.label,
            "reference_value": t.reference_value, "target_value": target,
            "current_value": current, "current_month": month,
            "diff": None if current is None or target is None else round(current - target, 4),
            "status": target_status(current, target, direction == "lower_is_better"),
            "direction": direction, "description": t.description, "source": t.source,
        })
    rows.sort(key=lambda r: (defs[r["metric_key"]].sort_order if r["metric_key"] in defs else 9999, r["year"]))
    return rows


def default_event_date(year: int, month: int) -> date:
    return date(year, month, 1)
