"""Pydantic schemas."""
import datetime
from pydantic import BaseModel, Field


# ---------- Auth ----------

class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    full_name: str
    must_change_password: bool


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=4)


# ---------- User management ----------

class DepartmentOut(BaseModel):
    id: int
    name: str
    code: str
    class Config:
        from_attributes = True


class UserServiceAccessOut(BaseModel):
    id: int
    user_id: int
    service_key: str
    access_level: str
    class Config:
        from_attributes = True


class UserServiceAccessIn(BaseModel):
    """An empty/None access_level removes the user's access to that service."""
    service_key: str
    access_level: str | None = None


class ServiceOut(BaseModel):
    key: str
    title: str
    subtitle: str
    has_dashboard: bool


class UserCreate(BaseModel):
    username: str
    full_name: str
    email: str | None = None
    position: str | None = None
    phone: str | None = None
    avatar: str | None = None
    role: str = "viewer"
    password: str
    # Selecting a primary service grants `edit_metrics` on it, so a new head of a
    # service can fill in its data without a second round of access edits.
    primary_service: str | None = None
    department_ids: list[int] = []
    must_change_password: bool = False


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    position: str | None = None
    phone: str | None = None
    avatar: str | None = None
    role: str | None = None
    is_active: bool | None = None
    primary_service: str | None = None
    department_ids: list[int] | None = None
    # An admin-set password is treated as temporary, so the user is asked to change it.
    password: str | None = None


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    email: str | None
    position: str | None = None
    phone: str | None = None
    avatar: str | None = None
    role: str
    is_active: bool
    must_change_password: bool
    departments: list[DepartmentOut] = []
    service_access: list[UserServiceAccessOut] = []
    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    """Fields a user may change on their own account."""
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = None
    position: str | None = None
    phone: str | None = None
    avatar: str | None = None


# ---------- Employee events ----------

class EmployeeEventBase(BaseModel):
    event_type: str  # hired | fired
    event_date: datetime.date
    full_name: str
    position: str = ""
    department: str = ""
    employment_type: str = ""


class EmployeeEventCreate(EmployeeEventBase):
    pass


class EmployeeEventOut(EmployeeEventBase):
    id: int
    month_record_id: int
    class Config:
        from_attributes = True


# ---------- Metrics ----------

class MetricDefinitionOut(BaseModel):
    key: str
    label: str
    unit: str
    category: str
    value_type: str
    aggregation: str
    direction: str
    description: str
    sort_order: int
    class Config:
        from_attributes = True


class MetricValueIn(BaseModel):
    metric_key: str
    numeric_value: float | None = None
    text_value: str = ""
    source_note: str = ""


class MetricValueOut(BaseModel):
    metric_key: str
    numeric_value: float | None
    text_value: str
    source_note: str
    class Config:
        from_attributes = True


# ---------- Month ----------

class MonthBase(BaseModel):
    year: int
    month: int
    notes: str = ""


class MonthUpdate(BaseModel):
    notes: str | None = None


class MonthCreate(MonthBase):
    pass


class MonthOut(BaseModel):
    id: int
    year: int
    month: int
    key: str
    label: str
    notes: str
    hired_count: int
    fired_count: int
    employees: list[EmployeeEventOut] = []
    metrics: list[MetricValueOut] = []
    class Config:
        from_attributes = True


# ---------- Notes ----------

class NoteCreate(BaseModel):
    content: str


class NoteOut(BaseModel):
    id: int
    month_record_id: int
    content: str
    author: str | None
    created_at: datetime.datetime
    class Config:
        from_attributes = True


# ---------- Traffic light ----------

class TrafficLightRuleOut(BaseModel):
    id: int
    metric_key: str
    green_threshold: float | None
    yellow_threshold: float | None
    direction: str
    enabled: bool
    class Config:
        from_attributes = True


class TrafficLightRuleUpdate(BaseModel):
    green_threshold: float | None = None
    yellow_threshold: float | None = None
    direction: str | None = None
    enabled: bool | None = None


# ---------- Benchmarks ----------

class BenchmarkOut(BaseModel):
    id: int
    metric_key: str
    metric_label: str
    unit: str
    label: str
    year: int
    target_value: float | None
    current_value: float | None
    current_month: str = ""
    diff: float | None
    status: str
    direction: str
    description: str = ""
    source: str = ""


class BenchmarkUpdate(BaseModel):
    target_value: float | None = None
    description: str | None = None
    source: str | None = None


class BenchmarkCreate(BaseModel):
    metric_key: str
    target_value: float
    description: str = ""
    source: str = ""


# ---------- Custom dashboards ----------

class DashboardWidgetIn(BaseModel):
    widget_type: str
    title: str = ""
    config: dict = {}
    sort_order: int = 0


class DashboardWidgetOut(DashboardWidgetIn):
    id: int
    class Config:
        from_attributes = True


class CustomDashboardCreate(BaseModel):
    name: str
    is_shared: bool = False
    widgets: list[DashboardWidgetIn] = []


class CustomDashboardOut(BaseModel):
    id: int
    name: str
    owner_id: int | None
    is_shared: bool
    widgets: list[DashboardWidgetOut] = []
    class Config:
        from_attributes = True


# ---------- Dashboard layout preferences ----------

class DashboardWidgetPref(BaseModel):
    """One widget's placement. `size` is small (1/3) | medium (1/2) | wide (2/3) | large (full).

    `settings` holds this chart's individual overrides (type, colours, legend,
    labels, height); they win over the global palette for that chart only.
    """
    key: str
    visible: bool = True
    size: str = "medium"
    sort_order: int = 0
    settings: dict = {}


class DashboardPreferenceIn(BaseModel):
    widgets: list[DashboardWidgetPref] = []


class DashboardPreferenceOut(BaseModel):
    service_key: str
    widgets: list[DashboardWidgetPref] = []


# ---------- Audit ----------

class AuditLogOut(BaseModel):
    id: int
    username: str
    entity_type: str
    entity_id: str | None
    action: str
    before_json: dict | None
    after_json: dict | None
    timestamp: datetime.datetime
    class Config:
        from_attributes = True


# ---------- Dashboard modules ----------

class DashboardModuleOut(BaseModel):
    id: int
    key: str
    title: str
    subtitle: str | None
    icon: str | None
    route_prefix: str
    enabled: bool
    sort_order: int
    class Config:
        from_attributes = True


# ---------- Partnerships ----------

class PartnershipBase(BaseModel):
    partner: str
    product: str = ""
    direction: str = ""
    almi_product: str = ""
    almi_version: str = ""
    status: str = "В работе"
    cert_date: datetime.date | None = None
    nda: bool = False
    agreement: bool = False
    bitrix: str | None = None
    website: str | None = None
    comment: str | None = None
    type: str = "ПО"
    last_modified: datetime.date | None = None


class PartnershipCreate(PartnershipBase):
    pass


class PartnershipUpdate(BaseModel):
    partner: str | None = None
    product: str | None = None
    direction: str | None = None
    almi_product: str | None = None
    almi_version: str | None = None
    status: str | None = None
    cert_date: datetime.date | None = None
    nda: bool | None = None
    agreement: bool | None = None
    bitrix: str | None = None
    website: str | None = None
    comment: str | None = None
    type: str | None = None
    last_modified: datetime.date | None = None


class PartnershipOut(PartnershipBase):
    id: int
    class Config:
        from_attributes = True


class PartnershipAnalytics(BaseModel):
    total: int
    by_status: dict[str, int]
    by_almi_product: dict[str, int]
    by_year: dict[str, int]
    by_direction: dict[str, int]
    nda_count: int
    agreement_count: int


class PartnershipLightRow(BaseModel):
    """One partnership traffic-light rule with how many records currently match it."""
    key: str
    group: str
    label: str
    light: str
    count: int
    share: float


class PartnershipLightRuleOut(BaseModel):
    """An editable partnership traffic-light rule."""
    id: int
    key: str
    group_key: str
    group: str
    label: str
    light: str
    threshold: float | None = None
    sort_order: int = 0


class PartnershipLightRuleIn(BaseModel):
    key: str
    light: str | None = None
    threshold: float | None = None


class PartnershipLightRulesIn(BaseModel):
    rules: list[PartnershipLightRuleIn] = []


class PartnershipPeriodRow(BaseModel):
    label: str
    year: int
    total: int
    green: int
    yellow: int
    red: int
    nda_count: int
    agreement_count: int
    by_status: dict[str, int]
    by_almi_product: dict[str, int]


# ---------- Color palette ----------

class ColorPaletteCreate(BaseModel):
    name: str
    scope: str = "global"
    module_key: str | None = None
    colors: dict = {}
    is_active: bool = False


class ColorPaletteOut(BaseModel):
    id: int
    name: str
    scope: str
    module_key: str | None
    colors: dict
    is_active: bool


# ---------- Analytics ----------

class MetricWithLight(BaseModel):
    key: str
    label: str
    unit: str
    category: str = ""
    value: float | None
    text_value: str | None = None
    source_note: str = ""
    light: str
    direction: str
    filled: bool = True


class MonthAnalytics(BaseModel):
    month_key: str
    label: str
    hired: int
    fired: int
    net: int
    metrics: list[MetricWithLight]


class PeriodSummary(BaseModel):
    label: str
    months_count: int
    hired: int
    fired: int
    net: int
    metrics: dict
