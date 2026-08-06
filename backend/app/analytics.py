"""Analytics: aggregation and traffic-light logic."""
from sqlalchemy.orm import Session
from .models import (
    MonthRecord, EmployeeEvent, MetricValue, MetricDefinition,
    TrafficLightRule, Benchmark
)


def get_months_sorted(db: Session) -> list[MonthRecord]:
    return db.query(MonthRecord).order_by(MonthRecord.year, MonthRecord.month).all()


def month_key(mr: MonthRecord) -> str:
    return f"{mr.year}-{mr.month:02d}"


def month_label(mr: MonthRecord) -> str:
    _mn = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
           "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    return f"{_mn[mr.month]} {mr.year}"


def metric_values_map(mr: MonthRecord) -> dict[str, float | None]:
    out = {}
    for mv in mr.metric_values:
        out[mv.metric_key] = mv.numeric_value
    return out


def aggregate_months(months: list[MonthRecord]) -> dict:
    """Aggregate stats across a set of months."""
    hired = sum(len([e for e in m.employees if e.event_type == "hired"]) for m in months)
    fired = sum(len([e for e in m.employees if e.event_type == "fired"]) for m in months)
    # gather all metric keys
    all_keys = set()
    for m in months:
        for mv in m.metric_values:
            all_keys.add(mv.metric_key)
    defs = {}
    # metric aggregation
    agg_metrics = {}
    for key in all_keys:
        defn = None
        values = []
        for m in months:
            mv = next((x for x in m.metric_values if x.metric_key == key), None)
            if mv and mv.numeric_value is not None:
                values.append(mv.numeric_value)
        if not values:
            continue
        agg = "avg"
        # find definition
        defs_row = None
        # avg by default; latest for turnover-like
        if key in ("turnover", "turnover_company", "probation_pass_rate", "probation_pass_rate_adaptation", "offers_accepted_pct"):
            agg = "latest"
        if agg == "latest":
            val = values[-1]
        elif agg == "sum":
            val = sum(values)
        elif agg == "max":
            val = max(values)
        else:
            val = sum(values) / len(values)
        agg_metrics[key] = round(val, 4)
    return {
        "months_count": len(months),
        "hired": hired,
        "fired": fired,
        "net": hired - fired,
        "metrics": agg_metrics,
    }


def months_in_period(months: list[MonthRecord], year: int, ptype: str, index: int) -> list[MonthRecord]:
    if ptype == "quarter":
        lo, hi = (index - 1) * 3 + 1, index * 3
    elif ptype == "half":
        lo, hi = (1, 6) if index == 1 else (7, 12)
    else:
        lo, hi = 1, 12
    return [m for m in months if m.year == year and lo <= m.month <= hi]


def period_label(year: int, ptype: str, index: int) -> str:
    if ptype == "quarter":
        return f"Q{index} {year}"
    if ptype == "half":
        return (f"I полугодие {year}" if index == 1 else f"II полугодие {year}")
    return f"{year} год"


def traffic_light(value: float | None, rule: TrafficLightRule | None) -> str:
    """Return 'green' | 'yellow' | 'red' | 'gray'."""
    if value is None or rule is None or not rule.enabled:
        return "gray"
    lower_better = rule.direction == "lower_is_better"
    g, y = rule.green_threshold, rule.yellow_threshold
    if lower_better:
        if g is not None and value <= g:
            return "green"
        if y is not None and value <= y:
            return "yellow"
        return "red"
    else:
        if g is not None and value >= g:
            return "green"
        if y is not None and value >= y:
            return "yellow"
        return "red"


def traffic_light_for_metric(db: Session, metric_key: str, value: float | None) -> str:
    rule = db.query(TrafficLightRule).filter(TrafficLightRule.metric_key == metric_key).first()
    return traffic_light(value, rule)


def get_benchmarks(db: Session) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    for b in db.query(Benchmark).all():
        out.setdefault(b.metric_key, {})[b.year] = b.value
    return out


def metric_direction(db: Session, metric_key: str) -> str:
    """The traffic-light rule wins over the definition: it is what an admin edits."""
    rule = db.query(TrafficLightRule).filter(TrafficLightRule.metric_key == metric_key).first()
    if rule and rule.direction:
        return rule.direction
    defn = db.query(MetricDefinition).filter(MetricDefinition.key == metric_key).first()
    return defn.direction if defn and defn.direction else "higher_is_better"


# A metric within this fraction of its target is amber rather than red.
BENCHMARK_TOLERANCE = 0.1


def benchmark_status(current: float | None, target: float | None, lower_better: bool) -> str:
    if current is None or target is None:
        return "gray"
    if lower_better:
        if current <= target:
            return "green"
        return "yellow" if current <= target * (1 + BENCHMARK_TOLERANCE) else "red"
    if current >= target:
        return "green"
    return "yellow" if current >= target * (1 - BENCHMARK_TOLERANCE) else "red"


def latest_metric_values(db: Session) -> dict[str, tuple[float, str]]:
    """metric_key -> (most recent non-empty value, label of the month it came from)."""
    out: dict[str, tuple[float, str]] = {}
    for mr in get_months_sorted(db):
        for mv in mr.metric_values:
            if mv.numeric_value is not None:
                out[mv.metric_key] = (mv.numeric_value, mr.label)
    return out


def benchmark_rows(db: Session) -> list[dict]:
    """Benchmarks joined with the latest actual value, ordered like the metric list."""
    defs = {d.key: d for d in db.query(MetricDefinition).all()}
    latest = latest_metric_values(db)
    rows = []
    for b in db.query(Benchmark).all():
        d = defs.get(b.metric_key)
        direction = metric_direction(db, b.metric_key)
        current, month = latest.get(b.metric_key, (None, ""))
        target = b.target_value
        rows.append({
            "id": b.id,
            "metric_key": b.metric_key,
            "metric_label": d.label if d else b.metric_key,
            "unit": d.unit if d else "",
            "label": b.label or "",
            "year": b.year,
            "target_value": target,
            "current_value": current,
            "current_month": month,
            "diff": None if (current is None or target is None) else round(current - target, 4),
            "status": benchmark_status(current, target, direction == "lower_is_better"),
            "direction": direction,
            "description": b.description or "",
            "source": b.source or "",
        })
    rows.sort(key=lambda r: (defs[r["metric_key"]].sort_order if r["metric_key"] in defs else 9999,
                            r["metric_key"], r["year"]))
    return rows
