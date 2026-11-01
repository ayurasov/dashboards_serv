"""Схемы технологических партнёрств."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from .common import Input, Schema


class PartnershipIn(Input):
    partner: str = Field(min_length=1, max_length=300)
    product: str = Field(default="", max_length=300)
    direction: str = Field(default="", max_length=300)
    almi_product: str = Field(default="", max_length=200)
    almi_version: str = Field(default="", max_length=200)
    status: str = Field(default="В работе", max_length=60)
    cert_date: date | None = None
    nda: bool = False
    agreement: bool = False
    bitrix: str = Field(default="", max_length=500)
    website: str = Field(default="", max_length=500)
    comment: str = Field(default="", max_length=5000)
    type: str = Field(default="ПО", max_length=30)
    last_modified: date | None = None


class PartnershipPatch(Input):
    partner: str | None = Field(default=None, min_length=1, max_length=300)
    product: str | None = Field(default=None, max_length=300)
    direction: str | None = Field(default=None, max_length=300)
    almi_product: str | None = Field(default=None, max_length=200)
    almi_version: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=60)
    cert_date: date | None = None
    nda: bool | None = None
    agreement: bool | None = None
    bitrix: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=500)
    comment: str | None = Field(default=None, max_length=5000)
    type: str | None = Field(default=None, max_length=30)
    last_modified: date | None = None


class LightRuleOut(Schema):
    key: str
    group_key: str
    group: str
    label: str
    light: Literal["green", "yellow", "red", "gray"]
    threshold: float | None = None
    sort_order: int


class LightRuleChange(Input):
    key: str
    light: Literal["green", "yellow", "red", "gray"] | None = None
    threshold: float | None = Field(default=None, gt=0, le=50)
