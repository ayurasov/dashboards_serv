"""Местное время компании (TIMEZONE). В базе время хранится в UTC без зоны."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import settings


@lru_cache(maxsize=4)
def _zone(name: str):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


def local_zone():
    return _zone(settings.timezone)


def local_now() -> datetime:
    return datetime.now(local_zone())


def local_today() -> date:
    return local_now().date()


def day_start_utc(day: date) -> datetime:
    """Начало местного дня в UTC без зоны — для сравнения с временем в базе."""
    return datetime.combine(day, time.min, local_zone()).astimezone(UTC).replace(tzinfo=None)


def day_end_utc(day: date) -> datetime:
    """Начало следующего местного дня в UTC (граница «меньше»)."""
    return day_start_utc(day + timedelta(days=1))
