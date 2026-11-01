"""Схемы службы персонала."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from .common import Input, Schema


class MonthCreateIn(Input):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    comment: str = Field(default="", max_length=5000)


class MonthPatchIn(Input):
    comment: str = Field(default="", max_length=5000)


class MonthListItem(Schema):
    key: str
    label: str
    year: int
    month: int
    comment: str
    hired: int
    fired: int
    filled_metrics: int
    total_metrics: int
    updated_at: datetime


class EventIn(Input):
    event_type: Literal["hired", "fired"]
    event_date: date
    full_name: str = Field(min_length=1, max_length=300)
    position: str = Field(default="", max_length=300)
    department: str = Field(default="", max_length=200)
    employment_type: str = Field(default="", max_length=100)
    reason: str = Field(default="", max_length=300)


class EventOut(Schema):
    id: int
    month_key: str
    event_type: str
    event_date: date
    full_name: str
    position: str
    department: str
    employment_type: str
    reason: str


class MetricValueIn(Input):
    metric_key: str = Field(min_length=1, max_length=80)
    value: float | None = None
    source_note: str = Field(default="", max_length=2000)


class NoteIn(Input):
    content: str = Field(min_length=1, max_length=5000)


class NoteOut(Schema):
    id: int
    content: str
    created_at: datetime
    author: str = ""


class MetricDefinitionOut(Schema):
    key: str
    label: str
    unit: str
    category: str
    aggregation: str
    direction: str
    description: str
    sort_order: int


class TargetIn(Input):
    metric_key: str = Field(min_length=1, max_length=80)
    year: int = Field(ge=2000, le=2100)
    target_value: float | None = None
    reference_value: float | None = None
    label: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2000)
    source: str = Field(default="", max_length=300)


class TargetPatchIn(Input):
    target_value: float | None = None
    reference_value: float | None = None
    label: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    source: str | None = Field(default=None, max_length=300)
