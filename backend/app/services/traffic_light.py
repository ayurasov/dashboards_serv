"""Светофор числовых метрик: зелёный / жёлтый / красный / серый (нет данных или правило выключено)."""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import TrafficLightRule

LIGHT_LABELS = {"green": "Норма", "yellow": "Внимание", "red": "Критично", "gray": "Нет оценки"}
MISSING_LABEL = "Нет данных"


def is_missing(value: float | None, rule: TrafficLightRule | None) -> bool:
    """Значение не заполнено, а правило светофора включено — критичное нарушение полноты данных.
    Сам показатель при этом оценивается как «Нет данных» (серый), а не «Критично»: цвет
    говорит о значении, а не о его отсутствии."""
    return value is None and rule is not None and rule.enabled
LIGHT_ORDER = {"red": 0, "yellow": 1, "green": 2, "gray": 3}


def evaluate(value: float | None, rule: TrafficLightRule | None) -> str:
    if value is None or rule is None or not rule.enabled:
        return "gray"
    green, yellow = rule.green_threshold, rule.yellow_threshold
    if rule.direction == "lower_is_better":
        if green is not None and value <= green:
            return "green"
        if yellow is not None and value <= yellow:
            return "yellow"
        return "red" if green is not None or yellow is not None else "gray"
    if green is not None and value >= green:
        return "green"
    if yellow is not None and value >= yellow:
        return "yellow"
    return "red" if green is not None or yellow is not None else "gray"


def rules_for(db: Session, service_key: str) -> dict[str, TrafficLightRule]:
    return {r.metric_key: r for r in db.scalars(
        select(TrafficLightRule).where(TrafficLightRule.service_key == service_key))}


def worst(lights: Iterable[str]) -> str:
    """Худший цвет из набора (серый не учитывается, если есть оценённые)."""
    rated = [light for light in lights if light != "gray"]
    if not rated:
        return "gray"
    return min(rated, key=LIGHT_ORDER.__getitem__)


def counts(lights: Iterable[str]) -> dict[str, int]:
    out = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
    for light in lights:
        out[light] = out.get(light, 0) + 1
    return out
