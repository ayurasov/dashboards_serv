"""Схемы структуры компании: подразделения, руководители, оргсхема, перенос, синхронизация (ADR-0007)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from ..services.registry import ORG_VIEWS
from .common import Input, Schema

UNIT_KIND_PATTERN = r"^[a-z][a-z0-9_-]{0,31}$"
COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"
OrgView = Literal[ORG_VIEWS]  # type: ignore[valid-type]
NewUsers = Literal["active", "inactive", "no_access"]


def _clean_name(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    if not value:
        raise ValueError("Название не может быть пустым")
    return value


# ---------------------------------------------------------------- настройки структуры

class UnitKindIn(Input):
    value: str = Field(pattern=UNIT_KIND_PATTERN, description="Ключ типа: латиница, цифры, «_» и «-»")
    label: str = Field(min_length=1, max_length=60)
    color: str = Field(default="#64748b", pattern=COLOR_PATTERN)


class UnitKindOut(Schema):
    value: str
    label: str
    color: str


class OrgSettingsIn(Input):
    unit_kinds: list[UnitKindIn] | None = Field(default=None, min_length=1, max_length=30)
    max_depth: int | None = Field(default=None, ge=2, le=30)
    default_view: OrgView | None = None


class OrgSettingsOut(Schema):
    unit_kinds: list[UnitKindOut]
    max_depth: int
    default_view: str
    views: list[str] = list(ORG_VIEWS)
    current_depth: int = 0                      # уровней в структуре сейчас (предел не может быть меньше)
    used_kinds: dict[str, int] = {}             # тип → число подразделений этого типа


# ---------------------------------------------------------------- подразделения

class DepartmentHeadOut(Schema):
    user_id: int
    full_name: str
    position: str | None = None
    is_primary: bool = False
    is_active: bool = True


class DepartmentOut(Schema):
    id: int
    name: str
    code: str | None = None
    parent_id: int | None = None
    kind: str
    sort_order: int = 0
    level: int = Field(description="Уровень: 1 — верхний")
    path: str = Field(description="Путь от верхнего уровня через « / »")
    external_id: str | None = None
    org_source: str = "manual"
    child_count: int = 0
    heads: list[DepartmentHeadOut] = []
    primary_head_id: int | None = Field(default=None, description="Отмеченный основным руководитель")
    employee_count: int = 0
    branch_employee_count: int = 0


class DepartmentCreateIn(Input):
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=50)
    parent_id: int | None = None
    kind: str | None = Field(default=None, max_length=32)
    sort_order: int = Field(default=0, ge=-100000, le=100000)

    _name = field_validator("name")(_clean_name)


class DepartmentUpdateIn(Input):
    """Изменяются только переданные поля; parent_id: null — перенести на верхний уровень."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=50)
    parent_id: int | None = None
    kind: str | None = Field(default=None, max_length=32)
    sort_order: int | None = Field(default=None, ge=-100000, le=100000)

    _name = field_validator("name")(_clean_name)


class HeadsIn(Input):
    user_ids: list[int] = Field(default_factory=list, max_length=50)
    primary_id: int | None = None


# ---------------------------------------------------------------- оргсхема

class TreeSettingsOut(Schema):
    unit_kinds: list[UnitKindOut]
    max_depth: int
    default_view: str


class TreeUnitOut(Schema):
    id: int
    name: str
    code: str | None = None
    parent_id: int | None = None
    kind: str
    sort_order: int
    level: int = Field(description="Уровень: 1 — верхний")
    child_count: int
    head_ids: list[int]
    primary_head_id: int | None = Field(description="Основной активный руководитель (по нему строится подчинение)")
    staff_count: int = Field(description="Сотрудники уровня без его руководителей")
    employee_count: int = Field(description="Сотрудники, для которых уровень основной (с руководителями)")
    branch_employee_count: int
    branch_unit_count: int


class TreePersonOut(Schema):
    id: int
    full_name: str
    position: str | None = None
    department_id: int | None = None
    home_unit_id: int | None = None
    manager_id: int | None = Field(default=None, description="Явный руководитель")
    direct_manager_id: int | None = None
    manager_source: Literal["explicit", "structure", "top", "none"]
    reports_to_none: bool = False
    is_active: bool = True
    head_of: list[int] = []
    report_count: int = 0
    branch_count: int = 0
    has_avatar: bool = False
    # Только для ведущих структуру (org.manage) и администратора
    email: str | None = None
    username: str | None = None
    external_id: str | None = None
    org_source: str | None = None


class TreeMeOut(Schema):
    id: int
    home_unit_id: int | None = None


class OrgTreeOut(Schema):
    revision: int
    settings: TreeSettingsOut
    units: list[TreeUnitOut]
    people: list[TreePersonOut]
    me: TreeMeOut


class PersonRef(Schema):
    id: int
    full_name: str
    position: str | None = None
    is_active: bool = True


class UnitRef(Schema):
    id: int
    name: str
    kind: str


class HeadOfOut(UnitRef):
    primary: bool = False
    path: str = ""


class PersonCardOut(Schema):
    id: int
    full_name: str
    position: str | None = None
    department_id: int | None = None
    home_unit_id: int | None = None
    manager_id: int | None = None
    reports_to_none: bool = False
    is_active: bool = True
    has_avatar: bool = False
    manager: PersonRef | None = Field(default=None, description="Непосредственный руководитель")
    manager_source: Literal["explicit", "structure", "top", "none"]
    structure_manager: PersonRef | None = Field(default=None, description="Руководитель по структуре")
    chain: list[PersonRef] = Field(default=[], description="Цепочка руководителей снизу вверх")
    direct_reports: list[PersonRef] = []
    subordinates_count: int = 0
    department_path: list[UnitRef] = []
    home_unit_path: list[UnitRef] = []
    head_of: list[HeadOfOut] = []
    email: str | None = None
    username: str | None = None
    external_id: str | None = None
    org_source: str | None = None


class HeadOfIn(Input):
    department_id: int
    primary: bool = False


class PersonOrgIn(Input):
    """Поля подчинения сотрудника; изменяются только переданные."""

    department_id: int | None = None
    manager_id: int | None = None
    reports_to_none: bool | None = None
    position: str | None = Field(default=None, max_length=200)
    head_of: list[HeadOfIn] | None = Field(default=None, max_length=50)


# ---------------------------------------------------------------- история

class OrgHistoryOut(Schema):
    id: int
    occurred_at: datetime
    user_id: int | None = None
    username: str
    entity_type: str
    entity_id: str | None = None
    action: str
    summary: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


# ---------------------------------------------------------------- перенос структуры

class StructureImportIn(Input):
    bundle: dict[str, Any] | str = Field(description="Содержимое файла dashboards.org-structure (объект или текст)")
    apply_settings: bool = True
    apply: bool = False


class SettingChangeOut(Schema):
    key: str
    label: str
    current: str
    incoming: str


class FieldChangeOut(Schema):
    field: str
    old: Any = None
    new: Any = None


class StructureDepartmentOut(Schema):
    key: str
    path: str
    action: Literal["create", "update", "unchanged"]
    changes: list[FieldChangeOut] = []


class StructureHeadOut(Schema):
    department_key: str
    path: str
    email: str
    name: str = ""
    primary: bool = False
    action: Literal["add", "exists", "pending"]
    user_id: int | None = None


class StructureSummaryOut(Schema):
    departments: int
    create: int
    update: int
    unchanged: int
    settings: int
    add_heads: int
    existing_heads: int
    pending_heads: int
    missing_in_file: int
    errors: int


class StructurePlanOut(Schema):
    summary: StructureSummaryOut
    settings: list[SettingChangeOut]
    departments: list[StructureDepartmentOut]
    heads: list[StructureHeadOut]
    missing_in_file: list[str]
    errors: list[str]
    can_apply: bool
    applied: bool = False
    settings_applied: bool = False


# ---------------------------------------------------------------- перенос сотрудников

class FieldDecisionIn(Input):
    choice: Literal["current", "incoming", "merge", "custom"] = "current"
    value: Any = None


class EmployeeDecisionIn(Input):
    identity: Literal["same", "new"] | None = Field(
        default=None, description="Email не найден, а логин занят: тот же сотрудник (same) или новый (new)")
    fields: dict[str, FieldDecisionIn] = {}


class EmployeesImportIn(Input):
    """Загрузка сотрудников телом JSON (вместо файла): content — документ dashboards.employees,
    список записей или текст CSV (format="csv")."""

    format: Literal["json", "csv"] = "json"
    content: dict[str, Any] | list[Any] | str
    apply: bool = False
    new_users: NewUsers = "no_access"
    decisions: dict[str, EmployeeDecisionIn] = {}


class EmployeeConflictOut(Schema):
    field: str
    label: str
    kind: str = "text"
    current: Any = None
    incoming: Any = None
    merged: Any = None
    choices: list[str]
    choice: str
    value: Any = None
    note: str | None = None


class EmployeeChangeOut(Schema):
    field: str
    label: str
    old: Any = None
    new: Any = None


class EmployeeRecordOut(Schema):
    key: str
    line: int
    action: Literal["create", "update", "unchanged", "skip"]
    user_id: int | None = None
    name: str = ""
    email: str = ""
    identity: dict[str, Any] | None = None
    unresolved: bool = False
    changes: list[EmployeeChangeOut] = []
    conflicts: list[EmployeeConflictOut] = []
    errors: list[str] = []
    warnings: list[str] = []


class EmployeeSummaryOut(Schema):
    records: int
    create: int
    update: int
    unchanged: int
    skip: int
    conflicts: int
    unresolved: int
    errors: int
    create_departments: int


class PlannedDepartmentOut(Schema):
    key: str
    path: str
    name: str = ""
    kind: str = "department"


class EmployeePlanOut(Schema):
    summary: EmployeeSummaryOut
    departments: list[PlannedDepartmentOut]
    records: list[EmployeeRecordOut]
    notes: list[str] = []
    can_apply: bool
    applied: bool = False
    user_ids: dict[str, int] = Field(default={}, description="После применения: email → id сотрудника")


# ---------------------------------------------------------------- загрузка списком и синхронизация с AD

class ListImportIn(Input):
    """Быстрая загрузка списком телом JSON: content — текст CSV."""

    content: str = Field(max_length=10_000_000)
    create_missing: bool = False
    apply: bool = False


class AdSyncIn(Input):
    create_missing: bool = False
    deactivate_missing: bool = False
    apply: bool = False


class AdConfigOut(Schema):
    url: str
    base_dn: str
    path_source: str
    path_attributes: list[str]
    detect_heads: bool
    start_tls: bool = False
    user_filter: str = ""


class AdStatusOut(Schema):
    configured: bool
    ldap3_available: bool
    config: AdConfigOut | None = None


class ImportUserOut(Schema):
    line: int
    user_id: int | None = None
    name: str = ""
    email: str = ""
    department: str = ""
    manager: str = ""
    manager_explicit: bool = False
    action: Literal["create", "update", "unchanged", "error"]
    changes: list[FieldChangeOut] = []
    errors: list[str] = []
    warnings: list[str] = []


class DeactivateOut(Schema):
    user_id: int
    name: str
    email: str | None = None


class ImportSummaryOut(Schema):
    rows: int
    create_departments: int
    create_users: int
    update_users: int
    unchanged: int
    deactivate_users: int
    errors: int
    warnings: int


class ImportPlanOut(Schema):
    source: str
    summary: ImportSummaryOut
    departments: list[PlannedDepartmentOut]
    users: list[ImportUserOut]
    deactivate: list[DeactivateOut]
    cycles: list[str]
    can_apply: bool
    applied: bool = False
