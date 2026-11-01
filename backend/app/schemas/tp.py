"""Схемы техподдержки."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field, create_model

from ..models import TP_METRIC_COLUMNS
from .common import Input, Schema

_metric_fields = {name: (float | None, None) for name in TP_METRIC_COLUMNS}

TpReportBase = create_model("TpReportBase", __base__=Input, **_metric_fields)


class TpReportIn(TpReportBase):  # type: ignore[misc, valid-type]
    year: int = Field(ge=2000, le=2100)
    week: int = Field(ge=1, le=53)
    note: str = Field(default="", max_length=2000)


class TpReportPatch(TpReportBase):  # type: ignore[misc, valid-type]
    year: int | None = Field(default=None, ge=2000, le=2100)
    week: int | None = Field(default=None, ge=1, le=53)
    note: str | None = Field(default=None, max_length=2000)


TpReportOutBase = create_model("TpReportOutBase", __base__=Schema, **_metric_fields)


class TpReportOut(TpReportOutBase):  # type: ignore[misc, valid-type]
    id: int
    year: int
    week: int
    period: str
    note: str = ""
    updated_at: datetime | None = None


class TpColumnOut(Schema):
    key: str
    label: str
    group: str
    group_label: str
    unit: str
