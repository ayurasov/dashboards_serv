"""Database models."""
import enum
import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, Date,
    ForeignKey, Enum, JSON, Table, UniqueConstraint, func
)
from sqlalchemy.orm import relationship
from .database import Base


# ---------- Auth / RBAC ----------

class RoleEnum(str, enum.Enum):
    ADMIN = "admin"
    HR_HEAD = "hr_head"
    VIEWER = "viewer"
    DEPT_VIEWER = "department_viewer"


# Registry of the nine company services. Only `hr` and `project_product` have
# dashboard content today; the rest are seeded disabled so access can be granted
# before the content exists.
# key, title, subtitle, icon, route_prefix, has_dashboard
SERVICES = [
    ("apparat_gd", "Аппарат ГД", "Аппарат ГД", "🏛", "/apparat_gd", False),
    ("tech", "Техническая поддержка", "Техподдержка", "🎧", "/tp", True),
    ("it", "ИТ служба", "ИТ", "💻", "/it", False),
    ("commercial", "Коммерческая служба", "Коммерческая", "💼", "/commercial", False),
    ("marketing", "Служба маркетинга", "Маркетинг", "📣", "/marketing", False),
    ("hr", "Служба персонала", "Персонал", "📊", "/", True),
    # Keeps the /product prefix: the partnership dashboards live under it.
    ("project_product", "Проектный и продуктовый офис", "Технологические партнёрства", "🤝", "/product", True),
    ("finance", "Финансовая служба", "Финансы", "💰", "/finance", False),
    ("legal", "Юридическая служба", "Юристы", "⚖", "/legal", False),
]
SERVICE_KEYS = [s[0] for s in SERVICES]
SERVICE_TITLES = {s[0]: s[1] for s in SERVICES}

ACCESS_LEVELS = ("read", "edit", "edit_metrics", "admin")


# Many-to-many: user <-> department
user_departments = Table(
    "user_departments", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("department_id", Integer, ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
)


class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    users = relationship("User", secondary=user_departments, back_populates="departments")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    full_name = Column(String(200), nullable=False)
    email = Column(String(200), unique=True, nullable=True)
    position = Column(String(200), nullable=True)
    phone = Column(String(50), nullable=True)
    avatar = Column(Text, nullable=True)  # data URL (base64), shown in the sidebar/profile
    role = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.VIEWER)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    must_change_password = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    departments = relationship("Department", secondary=user_departments, back_populates="users")
    service_access = relationship("UserServiceAccess", back_populates="user",
                                 cascade="all, delete-orphan", lazy="selectin")


class UserServiceAccess(Base):
    """Per-service access level. `User.role` stays the global role — ADMIN is superadmin."""
    __tablename__ = "user_service_access"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    service_key = Column(String(80), nullable=False, index=True)
    access_level = Column(String(30), nullable=False, default="read")
    __table_args__ = (UniqueConstraint("user_id", "service_key", name="uq_user_service"),)

    user = relationship("User", back_populates="service_access")


# ---------- HR Data ----------

class MonthRecord(Base):
    """One row per month (e.g. 2026-06)."""
    __tablename__ = "month_records"
    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)  # 1-12
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    __table_args__ = (UniqueConstraint("year", "month", name="uq_year_month"),)

    employees = relationship("EmployeeEvent", back_populates="month_record", cascade="all, delete-orphan")
    metric_values = relationship("MetricValue", back_populates="month_record", cascade="all, delete-orphan")
    notes_rel = relationship("Note", back_populates="month_record", cascade="all, delete-orphan")

    @property
    def key(self):
        return f"{self.year}-{self.month:02d}"

    @property
    def label(self):
        _mn = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
               "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
        return f"{_mn[self.month]} {self.year}"


class EmployeeEvent(Base):
    """Hire or termination event."""
    __tablename__ = "employee_events"
    id = Column(Integer, primary_key=True)
    month_record_id = Column(Integer, ForeignKey("month_records.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(10), nullable=False)  # 'hired' | 'fired'
    event_date = Column(Date, nullable=False)
    full_name = Column(String(300), nullable=False)
    position = Column(String(300), default="")
    department = Column(String(200), default="")
    employment_type = Column(String(100), default="")  # only for hired
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    month_record = relationship("MonthRecord", back_populates="employees")


class MetricDefinition(Base):
    """Extensible metric catalogue."""
    __tablename__ = "metric_definitions"
    id = Column(Integer, primary_key=True)
    key = Column(String(80), unique=True, nullable=False, index=True)
    label = Column(String(200), nullable=False)
    unit = Column(String(30), default="")  # '%', 'дн.', 'чел.', ''
    category = Column(String(80), default="general")  # hiring, adaptation, turnover, general
    value_type = Column(String(20), default="numeric")  # numeric | text
    aggregation = Column(String(30), default="avg")  # sum | avg | latest | max
    direction = Column(String(30), default="lower_is_better")  # lower_is_better | higher_is_better | neutral
    description = Column(Text, default="")
    sort_order = Column(Integer, default=0)


class MetricValue(Base):
    """Actual metric value for a month."""
    __tablename__ = "metric_values"
    id = Column(Integer, primary_key=True)
    month_record_id = Column(Integer, ForeignKey("month_records.id", ondelete="CASCADE"), nullable=False)
    metric_key = Column(String(80), nullable=False, index=True)
    numeric_value = Column(Float, nullable=True)
    text_value = Column(Text, default="")
    source_note = Column(Text, default="")
    __table_args__ = (UniqueConstraint("month_record_id", "metric_key", name="uq_month_metric"),)

    month_record = relationship("MonthRecord", back_populates="metric_values")


class Note(Base):
    """Text notes attached to a month (for HR head)."""
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    month_record_id = Column(Integer, ForeignKey("month_records.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    month_record = relationship("MonthRecord", back_populates="notes_rel")
    author = relationship("User")


# ---------- Traffic light ----------

class TrafficLightRule(Base):
    """Configurable thresholds per metric."""
    __tablename__ = "traffic_light_rules"
    id = Column(Integer, primary_key=True)
    metric_key = Column(String(80), unique=True, nullable=False, index=True)
    green_threshold = Column(Float, nullable=True)   # <= green (if lower_is_better) or >= (higher)
    yellow_threshold = Column(Float, nullable=True)  # <= yellow
    # red is anything beyond yellow
    direction = Column(String(30), default="higher_is_better")  # higher_is_better | lower_is_better
    enabled = Column(Boolean, default=True)


TL_DIRECTIONS = ("higher_is_better", "lower_is_better")


# ---------- Custom dashboards ----------

class CustomDashboard(Base):
    __tablename__ = "custom_dashboards"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_shared = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    widgets = relationship("DashboardWidget", back_populates="dashboard",
                           cascade="all, delete-orphan", order_by="DashboardWidget.sort_order")
    owner = relationship("User")


class DashboardWidget(Base):
    __tablename__ = "dashboard_widgets"
    id = Column(Integer, primary_key=True)
    dashboard_id = Column(Integer, ForeignKey("custom_dashboards.id", ondelete="CASCADE"), nullable=False)
    widget_type = Column(String(40), nullable=False)  # metric_card|line_chart|bar_chart|table|note
    title = Column(String(200), default="")
    config = Column(JSON, default=dict)  # metric keys, period, etc.
    sort_order = Column(Integer, default=0)
    dashboard = relationship("CustomDashboard", back_populates="widgets")


WIDGET_TYPES = ("metric_card", "line_chart", "bar_chart", "table", "note")


class UserDashboardPreference(Base):
    """Per-user widget order, sizes and visibility for a service dashboard."""
    __tablename__ = "user_dashboard_preferences"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    service_key = Column(String(80), nullable=False, index=True)
    preferences_json = Column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("user_id", "service_key", name="uq_user_service_prefs"),)


# ---------- Audit log ----------

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String(100), default="system")
    entity_type = Column(String(60), nullable=False)
    entity_id = Column(String(100), nullable=True)
    action = Column(String(30), nullable=False)  # create|update|delete
    before_json = Column(JSON, nullable=True)
    after_json = Column(JSON, nullable=True)
    ip_address = Column(String(50), default="")
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship("User")


# ---------- Modular dashboard ----------

class DashboardModule(Base):
    """A dashboard area/module (HR, product partnerships, ...)."""
    __tablename__ = "dashboard_modules"
    id = Column(Integer, primary_key=True)
    key = Column(String(80), unique=True, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    subtitle = Column(String(200), nullable=True)
    icon = Column(String(2000), nullable=True)  # SVG path data or emoji
    route_prefix = Column(String(120), nullable=False, default="/")
    enabled = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)


class Partnership(Base):
    """Technology partnership / certification record."""
    __tablename__ = "partnerships"
    id = Column(Integer, primary_key=True)
    partner = Column(String(300), nullable=False)
    product = Column(String(300), nullable=False, default="")
    direction = Column(String(300), nullable=False, default="")
    almi_product = Column(String(200), nullable=False, default="")
    almi_version = Column(String(200), nullable=False, default="")
    status = Column(String(60), nullable=False, default="В работе")
    cert_date = Column(Date, nullable=True)
    nda = Column(Boolean, default=False)
    agreement = Column(Boolean, default=False)
    bitrix = Column(String(500), nullable=True)
    website = Column(String(500), nullable=True)
    comment = Column(Text, nullable=True)
    type = Column(String(30), nullable=False, default="ПО")
    last_modified = Column(Date, nullable=True)


class PartnershipLightRule(Base):
    """Editable traffic-light rule for partnership records.

    Partnership statuses are categorical, so a rule maps a category to a light
    rather than thresholding a number. The `cert_age` group is the exception: its
    `threshold` is an age in years, and the rules are matched cheapest-first.
    """
    __tablename__ = "partnership_light_rules"
    id = Column(Integer, primary_key=True)
    key = Column(String(80), unique=True, nullable=False, index=True)
    group_key = Column(String(40), nullable=False)  # status | nda | agreement | cert_age
    label = Column(String(200), nullable=False)
    light = Column(String(20), nullable=False, default="gray")
    threshold = Column(Float, nullable=True)
    sort_order = Column(Integer, default=0)


PARTNERSHIP_LIGHT_GROUPS = {
    "status": "Статус",
    "nda": "NDA",
    "agreement": "Соглашение",
    "cert_age": "Срок сертификата",
}

# Shipped defaults; rows are created on first read so no migration is needed.
PARTNERSHIP_LIGHT_DEFAULTS = [
    ("status:Завершено", "status", "Завершено", "green", None),
    ("status:В работе", "status", "В работе", "yellow", None),
    ("status:Отложено", "status", "Отложено", "yellow", None),
    ("status:Не подписывают", "status", "Не подписывают", "red", None),
    ("nda:yes", "nda", "NDA подписан", "green", None),
    ("nda:no", "nda", "NDA не подписан", "yellow", None),
    ("agreement:yes", "agreement", "Соглашение подписано", "green", None),
    ("agreement:no", "agreement", "Соглашение не подписано", "yellow", None),
    ("cert_age:fresh", "cert_age", "Сертификат актуален", "green", 2.0),
    ("cert_age:aging", "cert_age", "Сертификат устаревает", "yellow", 4.0),
    ("cert_age:stale", "cert_age", "Сертификат устарел", "red", None),
]


class ColorPalette(Base):
    """Customizable colour settings, global or per module."""
    __tablename__ = "color_palettes"
    id = Column(Integer, primary_key=True)
    scope = Column(String(30), nullable=False, default="global")  # global | module
    module_key = Column(String(80), nullable=True)
    name = Column(String(200), nullable=False)
    colors_json = Column(Text, nullable=False, default="{}")
    is_active = Column(Boolean, default=True)


# ---------- Benchmarks ----------

class Benchmark(Base):
    """Reference values for comparison, e.g. 2025 turnover."""
    __tablename__ = "benchmarks"
    id = Column(Integer, primary_key=True)
    metric_key = Column(String(80), nullable=False, index=True)
    label = Column(String(200), default="")
    year = Column(Integer, nullable=False)
    value = Column(Float, nullable=False)
    # Target the metric should reach; null on purely historical reference rows.
    target_value = Column(Float, nullable=True)
    description = Column(Text, default="")
    source = Column(String(300), default="")
    __table_args__ = (UniqueConstraint("metric_key", "year", name="uq_benchmark_metric_year"),)


# ---------- Technical Support (TP) ----------

# Column names matching tp-report seed_data.json exactly
TP_DATA_COLUMNS = [
    "year", "week", "total_in_work", "avail_total",
    "rushydro_hours", "transneft_hours", "roscosmos_hours", "bryansk_hours",
    "mchs_hours", "internal_sales_hours",
    "new_received", "renewed", "ratio_solved_received",
    "altos_rusg_email", "altos_rusg_tf", "altos_other_email", "altos_other_tf",
    "altoffice_rusg_email", "altoffice_rusg_tf", "altoffice_other_email", "altoffice_other_tf",
    "projserver_taken", "total_solved_week",
    "altos_avg_time", "altos_total", "altos_1_2line", "altos_3line",
    "altoffice_avg_time", "altoffice_total", "altoffice_1_2line", "altoffice_3line",
    "projserver_solved",
    "altos_avail_total", "altos_avail_1_3", "altos_avail_4_7", "altos_avail_8_10",
    "altoffice_avail_total", "altoffice_avail_1_3", "altoffice_avail_4_7", "altoffice_avail_8_10",
    "projserver_avail", "extra",
]

# Default traffic-light rules (mirrors tp-report DEFAULT_TRAFFIC_RULES)
TP_DEFAULT_TRAFFIC_RULES = {
    "total_in_work":        {"direction": "less", "green": 180, "yellow": 220, "enabled": True},
    "avail_total":          {"direction": "less", "green": 350, "yellow": 420, "enabled": True},
    "new_received":         {"direction": "less", "green": 25,  "yellow": 35,  "enabled": False},
    "total_solved_week":    {"direction": "more", "green": 25,  "yellow": 18,  "enabled": True},
    "ratio_solved_received":{"direction": "more", "green": 1,   "yellow": 0.8, "enabled": True},
    "altos_avg_time":       {"direction": "less", "green": 24,  "yellow": 48,  "enabled": True},
    "altoffice_avg_time":   {"direction": "less", "green": 36,  "yellow": 72,  "enabled": True},
    "altos_avail_total":    {"direction": "more", "green": 90,  "yellow": 70,  "enabled": False},
    "altoffice_avail_total":{"direction": "more", "green": 110, "yellow": 90,  "enabled": False},
}


class TpReportRow(Base):
    """One week of technical-support data (mirrors tp-report report_rows table)."""
    __tablename__ = "tp_report_rows"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Time dimensions
    year   = Column(Float, nullable=True)
    week   = Column(Float, nullable=True)
    period = Column(String(50), nullable=True)
    # Load / availability
    total_in_work  = Column(Float, nullable=True)
    avail_total    = Column(Float, nullable=True)
    # Client hours
    rushydro_hours        = Column(Float, nullable=True)
    transneft_hours       = Column(Float, nullable=True)
    roscosmos_hours       = Column(Float, nullable=True)
    bryansk_hours         = Column(Float, nullable=True)
    mchs_hours            = Column(Float, nullable=True)
    internal_sales_hours  = Column(Float, nullable=True)
    # Ticket flow
    new_received           = Column(Float, nullable=True)
    renewed                = Column(Float, nullable=True)
    ratio_solved_received  = Column(Float, nullable=True)
    # AltOS / RUSG channel
    altos_rusg_email  = Column(Float, nullable=True)
    altos_rusg_tf     = Column(Float, nullable=True)
    altos_other_email = Column(Float, nullable=True)
    altos_other_tf    = Column(Float, nullable=True)
    # AltOffice / RUSG channel
    altoffice_rusg_email  = Column(Float, nullable=True)
    altoffice_rusg_tf     = Column(Float, nullable=True)
    altoffice_other_email = Column(Float, nullable=True)
    altoffice_other_tf    = Column(Float, nullable=True)
    # ProjServer
    projserver_taken   = Column(Float, nullable=True)
    projserver_solved  = Column(Float, nullable=True)
    projserver_avail   = Column(Float, nullable=True)
    # Weekly totals
    total_solved_week = Column(Float, nullable=True)
    # AltOS SLA
    altos_avg_time  = Column(Float, nullable=True)
    altos_total     = Column(Float, nullable=True)
    altos_1_2line   = Column(Float, nullable=True)
    altos_3line     = Column(Float, nullable=True)
    # AltOffice SLA
    altoffice_avg_time = Column(Float, nullable=True)
    altoffice_total    = Column(Float, nullable=True)
    altoffice_1_2line  = Column(Float, nullable=True)
    altoffice_3line    = Column(Float, nullable=True)
    # Availability buckets
    altos_avail_total  = Column(Float, nullable=True)
    altos_avail_1_3    = Column(Float, nullable=True)
    altos_avail_4_7    = Column(Float, nullable=True)
    altos_avail_8_10   = Column(Float, nullable=True)
    altoffice_avail_total = Column(Float, nullable=True)
    altoffice_avail_1_3   = Column(Float, nullable=True)
    altoffice_avail_4_7   = Column(Float, nullable=True)
    altoffice_avail_8_10  = Column(Float, nullable=True)
    # Free-form note
    extra = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.datetime.utcnow,
                         onupdate=datetime.datetime.utcnow)


class TpSettings(Base):
    """Key-value settings for the TP dashboard (traffic rules, block settings, etc.)."""
    __tablename__ = "tp_settings"
    key   = Column(String(80), primary_key=True)
    value = Column(Text, nullable=False, default="{}")
