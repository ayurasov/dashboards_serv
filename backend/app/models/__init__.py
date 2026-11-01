"""Модели базы данных. Импорт пакета регистрирует все таблицы в Base.metadata."""
from .core import (  # noqa: F401
    ACCESS_LEVELS,
    GLOBAL_ROLES,
    LIGHT_DIRECTIONS,
    WIDGET_TYPES,
    AuditEntry,
    ColorPalette,
    CustomDashboard,
    CustomDashboardWidget,
    DashboardLayout,
    DataImport,
    Department,
    Service,
    ServiceAccess,
    ServiceSetting,
    TrafficLightRule,
    User,
    UserSession,
    user_departments,
)
from .hr import (  # noqa: F401
    EVENT_TYPES,
    MONTH_NAMES,
    HrEmployeeEvent,
    HrMetricDefinition,
    HrMetricValue,
    HrMonth,
    HrMonthNote,
    HrTarget,
)
from .partnerships import (  # noqa: F401
    LIGHTS,
    PARTNERSHIP_STATUSES,
    PARTNERSHIP_TYPES,
    Partnership,
    PartnershipLightRule,
)
from .tp import TP_METRIC_COLUMNS, NaumenTicket, TpWeeklyReport  # noqa: F401
