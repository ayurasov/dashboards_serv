"""Схемы служб, настроек, светофора, палитр, раскладок, журнала."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from .common import Input, Schema

Light = Literal["green", "yellow", "red", "gray"]
Direction = Literal["lower_is_better", "higher_is_better"]


class ServiceOut(Schema):
    key: str
    title: str
    short_title: str
    description: str
    icon: str
    route_prefix: str
    has_dashboard: bool
    level: str | None = None
    data_updated_at: datetime | None = None


class TrafficRuleOut(Schema):
    metric_key: str
    label: str
    unit: str = ""
    group: str = ""
    direction: Direction
    green_threshold: float | None = None
    yellow_threshold: float | None = None
    enabled: bool
    has_rule: bool = False
    updated_at: datetime | None = None


class TrafficRuleIn(Input):
    direction: Direction
    green_threshold: float | None = None
    yellow_threshold: float | None = None
    enabled: bool = True


class PaletteOut(Schema):
    id: int
    name: str
    colors: dict[str, Any]
    is_active: bool
    is_preset: bool


class PaletteIn(Input):
    name: str = Field(min_length=1, max_length=200)
    colors: dict[str, Any]

    @field_validator("colors")
    @classmethod
    def _colors(cls, value: dict) -> dict:
        tl = value.get("traffic_light", {})
        charts = value.get("charts", [])
        if not isinstance(tl, dict) or not isinstance(charts, list):
            raise ValueError("Ожидаются разделы traffic_light и charts")
        for color in [*tl.values(), *charts, *value.get("brand", {}).values()]:
            if not (isinstance(color, str) and color.startswith("#") and len(color) in (4, 7)):
                raise ValueError(f"Некорректный цвет: {color}")
        return value


class LayoutWidget(Input):
    key: str = Field(min_length=1, max_length=80)
    size: Literal["small", "medium", "wide", "large"] = "medium"
    visible: bool = True
    order: int = 0


class LayoutIn(Input):
    widgets: list[LayoutWidget] = []


class LayoutOut(Schema):
    service_key: str
    widgets: list[dict[str, Any]] = []


class AuditOut(Schema):
    id: int
    occurred_at: datetime
    username: str
    service_key: str | None = None
    entity_type: str
    entity_id: str | None = None
    action: str
    summary: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    ip_address: str = ""


class DataImportOut(Schema):
    id: int
    service_key: str
    dataset: str
    filename: str
    mode: str
    rows_total: int
    rows_created: int
    rows_updated: int
    rows_skipped: int
    created_at: datetime
    username: str


class WidgetIn(Input):
    widget_type: Literal["metric_card", "line_chart", "bar_chart", "table", "note"]
    title: str = Field(default="", max_length=200)
    config: dict[str, Any] = {}


class CustomDashboardIn(Input):
    name: str = Field(min_length=1, max_length=200)
    is_shared: bool = False
    widgets: list[WidgetIn] = []


class WidgetOut(Schema):
    id: int
    widget_type: str
    title: str
    config: dict[str, Any]
    sort_order: int


class CustomDashboardOut(Schema):
    id: int
    name: str
    is_shared: bool
    owner_id: int | None = None
    owner_name: str = ""
    can_edit: bool = False
    created_at: datetime
    updated_at: datetime
    widgets: list[WidgetOut] = []


class SettingValue(Input):
    value: Any
