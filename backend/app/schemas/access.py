"""Схемы модели доступа 2.0 (ADR-0009): справочник измерений, профили доступа, доступ пользователя."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from ..services.registry import MAX_DRILL_DEPTH
from .common import Input, Schema
from .users import AccessIn, AccessOut, Level, OrgScope, ProfileRef, UnitRef

DataClass = Literal["operational", "personal", "financial"]
PROFILE_KEY = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")


# ---------------------------------------------------------------- справочник

class LabelOut(Schema):
    key: str
    label: str
    hint: str = ""


class DataClassOut(LabelOut):
    always: bool = False


class ServiceMetaOut(Schema):
    key: str
    title: str
    short_title: str
    has_dashboard: bool
    levels: list[str]


class AccessMetaOut(Schema):
    data_classes: list[DataClassOut]
    org_scopes: list[LabelOut]
    dimensions: list[LabelOut]
    levels: list[LabelOut]
    capabilities: list[LabelOut]
    services: list[ServiceMetaOut]
    max_drill_depth: int


# ---------------------------------------------------------------- профили

class _ProfileFields(Input):
    @field_validator("data_classes", check_fields=False)
    @classmethod
    def _unique_classes(cls, v):
        return None if v is None else list(dict.fromkeys(v))


class ProfileCreateIn(_ProfileFields):
    key: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    sort_order: int = Field(default=100, ge=0, le=10_000)
    service_levels: dict[str, Level] = {}
    org_scope: OrgScope = "unit"
    data_classes: list[DataClass] = ["operational"]
    drill_depth: int | None = Field(default=None, ge=0, le=MAX_DRILL_DEPTH)
    can_view_records: bool = True
    can_export: bool = True

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        if not PROFILE_KEY.match(v):
            raise ValueError("Ключ — латинские строчные буквы, цифры, «_» и «-», начинается с буквы")
        return v


class ProfilePatchIn(_ProfileFields):
    """Изменение профиля: только переданные поля. Ключ не меняется — на него ссылаются настройки
    входа по домену (AUTH_LDAP_GROUP_PROFILES, AUTH_LDAP_DEFAULT_PROFILE)."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
    service_levels: dict[str, Level] | None = None
    org_scope: OrgScope | None = None
    data_classes: list[DataClass] | None = None
    drill_depth: int | None = Field(default=None, ge=0, le=MAX_DRILL_DEPTH)
    can_view_records: bool | None = None
    can_export: bool | None = None


class ProfileOut(Schema):
    id: int
    key: str
    name: str
    description: str
    is_system: bool
    sort_order: int
    service_levels: dict[str, str]
    org_scope: str
    data_classes: list[str]
    drill_depth: int | None
    can_view_records: bool
    can_export: bool
    users_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------- доступ пользователя

class AccessPolicyIn(Input):
    """Доступ пользователя. Меняются только переданные поля.

    overrides — личные значения измерений поверх профиля: ключ есть — задано лично, ключа нет —
    как в профиле; drill_depth: null — «без ограничения» поверх профиля."""

    profile_id: int | None = None
    overrides: dict[str, Any] | None = None
    services: list[AccessIn] | None = None
    extra_unit_ids: list[int] | None = None


class AccessPolicyOut(Schema):
    user_id: int
    is_admin: bool
    profile: ProfileRef | None
    overrides: dict[str, Any]
    services: list[AccessOut]
    extra_units: list[UnitRef]
    effective: dict[str, Any]
    # Подразделения действующей области (общей, без поправок служб); null — вся компания
    scope_units: list[UnitRef] | None
