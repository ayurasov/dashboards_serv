"""Производственный календарь РФ (ADR-0012, этап 3): ёмкость периода в часах.

Праздники и переносы — по постановлениям Правительства РФ на 2025–2027 годы; рабочий день — 8 ч,
предпраздничный — 7 ч. Корпоративные отличия — таблица calendar_overrides (0 — выходной),
она приоритетнее встроенного календаря. Вне 2025–2027 считается «будни по 8, выходные — 0» —
и помечается предупреждением в ответе API (данные постановлений нужно продлить).
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CalendarOverride

# Праздничные дни (нерабочие) по производственному календарю РФ
HOLIDAYS: set[date] = set()

# Даты, ставшие рабочими переносом (суббота/воскресенье → рабочий день)
TRANSFERRED_WORKDAYS: set[date] = set()


def _d(year: int, rows: str) -> set[date]:
    return {date(year, int(m), int(day)) for m, day in (pair.split("-") for pair in rows.split())}


# 2025: постановление № 1362
HOLIDAYS |= _d(2025, "01-01 01-02 01-03 01-04 01-05 01-06 01-07 01-08 02-23 03-08 05-01 05-02 05-08 05-09 "
                     "06-12 06-13 11-03 11-04 12-31")
TRANSFERRED_WORKDAYS |= _d(2025, "04-26 06-14 11-08 12-13")  # Saturdays → work

# 2026: проект календаря (структура праздников устойчива; уточняется постановлением)
HOLIDAYS |= _d(2026, "01-01 01-02 01-03 01-04 01-05 01-06 01-07 01-08 02-23 03-09 05-01 05-11 06-12 "
                     "11-02 11-03 11-04 12-31")
TRANSFERRED_WORKDAYS |= _d(2026, "01-31 06-06")

# 2027: аналогично — уточняется постановлением
HOLIDAYS |= _d(2027, "01-01 01-02 01-03 01-04 01-05 01-06 01-07 01-08 02-22 03-08 05-03 05-10 06-14 "
                     "11-06 11-08 12-31")
TRANSFERRED_WORKDAYS |= _d(2027, "02-06")


def day_hours(day: date, overrides: dict[date, float] | None = None) -> float:
    """Часы рабочего дня: 0 — выходной/праздник, 7 — предпраздничный, 8 — обычный рабочий."""
    if overrides and day in overrides:
        return overrides[day]
    if day in HOLIDAYS:
        return 0.0
    if day.weekday() >= 5 and day not in TRANSFERRED_WORKDAYS:
        return 0.0
    # Предпраздничный — 7 часов: завтра праздник и это не «компенсированный» выходной
    tomorrow = day + timedelta(days=1)
    if tomorrow in HOLIDAYS:
        return 7.0
    return 8.0


def capacity(db: Session | None, first: date, last: date) -> tuple[float, bool]:
    """Ёмкость периода в часах (рабочие дни × длительность, корпоративные отличия учтены).

    Возвращает (часы, точность_календаря): точность False — период выходит за 2025–2027,
    дни за пределами считаются по общему правилу «будни 8, выходные 0»."""
    overrides = {o.day: o.hours for o in db.scalars(select(CalendarOverride))} if db is not None else {}
    hours = 0.0
    precise = True
    day = first
    while day <= last:
        if not (date(2025, 1, 1) <= day <= date(2027, 12, 31)):
            precise = False
        hours += day_hours(day, overrides)
        day += timedelta(days=1)
    return hours, precise


def month_capacity(db: Session | None, month: date) -> tuple[float, bool]:
    """Ёмкость месяца в часах (month — любой день месяца)."""
    first = month.replace(day=1)
    return capacity(db, first, first.replace(day=monthrange(month.year, month.month)[1]))
