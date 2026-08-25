"""Pydantic schemas for the Tech Support module."""
import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ---------- Week row ----------

class TechSupportWeekBase(BaseModel):
    client: str
    year: int
    week: int = Field(ge=1, le=53)
    sla_pct: Optional[float] = None
    incidents_total: Optional[int] = None
    incidents_critical: Optional[int] = None
    incidents_resolved: Optional[int] = None
    avg_response_h: Optional[float] = None
    avg_resolution_h: Optional[float] = None
    nps: Optional[float] = None
    notes: str = ""


class TechSupportWeekCreate(TechSupportWeekBase):
    pass


class TechSupportWeekUpdate(BaseModel):
    sla_pct: Optional[float] = None
    incidents_total: Optional[int] = None
    incidents_critical: Optional[int] = None
    incidents_resolved: Optional[int] = None
    avg_response_h: Optional[float] = None
    avg_resolution_h: Optional[float] = None
    nps: Optional[float] = None
    notes: Optional[str] = None


class TechSupportWeekOut(TechSupportWeekBase):
    id: int
    period_key: str

    class Config:
        from_attributes = True


# ---------- Bulk import ----------

class TechSupportBulkImport(BaseModel):
    """Replace-or-insert a list of week rows. Existing (client, year, week) rows
    are updated; new ones are created."""
    rows: list[TechSupportWeekCreate]


# ---------- Traffic-light rules ----------

class TsTrafficRuleOut(BaseModel):
    id: int
    metric_key: str
    label: str
    green_threshold: Optional[float]
    yellow_threshold: Optional[float]
    direction: str
    enabled: bool

    class Config:
        from_attributes = True


class TsTrafficRuleUpdate(BaseModel):
    green_threshold: Optional[float] = None
    yellow_threshold: Optional[float] = None
    direction: Optional[str] = None
    enabled: Optional[bool] = None


class TsTrafficRulesBulk(BaseModel):
    rules: list[dict]  # [{metric_key, green_threshold, yellow_threshold, direction, enabled}]


# ---------- Analytics ----------

class TsClientSummary(BaseModel):
    client: str
    weeks_count: int
    avg_sla: Optional[float]
    avg_response_h: Optional[float]
    avg_resolution_h: Optional[float]
    total_incidents: int
    total_critical: int
    avg_nps: Optional[float]
    sla_light: str   # green | yellow | red | gray


class TsWeekSummary(BaseModel):
    period_key: str
    year: int
    week: int
    clients_count: int
    avg_sla: Optional[float]
    total_incidents: int
    sla_light: str
