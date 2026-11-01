"""Справочные данные, которыми владеет код: службы, метрики, правила по умолчанию, палитры.

При каждом старте app.services.reference_data приводит к ним таблицы-справочники.
Настройки, которые меняет администратор (пороги светофора, цели, активная палитра),
создаются один раз и дальше не перезаписываются.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceDef:
    key: str
    title: str
    short_title: str
    description: str
    icon: str
    route_prefix: str
    has_dashboard: bool


SERVICES: tuple[ServiceDef, ...] = (
    ServiceDef("hr", "Служба персонала", "Персонал",
               "Найм, адаптация, текучесть кадров, приёмы и увольнения по месяцам",
               "users", "/hr", True),
    ServiceDef("tech", "Техническая поддержка", "Техподдержка",
               "Недельный отчёт: нагрузка, трудозатраты по клиентам, решение заявок; аналитика Naumen SD",
               "headset", "/tp", True),
    ServiceDef("project_product", "Проектный и продуктовый офис", "Партнёрства",
               "Технологические партнёрства и сертификация совместимости продуктов",
               "handshake", "/product", True),
    ServiceDef("apparat_gd", "Аппарат генерального директора", "Аппарат ГД", "", "building", "/apparat", False),
    ServiceDef("it", "ИТ-служба", "ИТ", "", "monitor", "/it", False),
    ServiceDef("commercial", "Коммерческая служба", "Коммерция", "", "briefcase", "/commercial", False),
    ServiceDef("marketing", "Служба маркетинга", "Маркетинг", "", "megaphone", "/marketing", False),
    ServiceDef("finance", "Финансовая служба", "Финансы", "", "wallet", "/finance", False),
    ServiceDef("legal", "Юридическая служба", "Юристы", "", "scale", "/legal", False),
)
SERVICE_KEYS: tuple[str, ...] = tuple(s.key for s in SERVICES)
SERVICE_BY_KEY = {s.key: s for s in SERVICES}

ACCESS_LEVEL_LABELS = {
    "viewer": "Просмотр",
    "editor": "Ввод данных",
    "manager": "Управление",
}
ACCESS_LEVEL_RANK = {"viewer": 1, "editor": 2, "manager": 3}
# Службы, у которых есть данные и дашборды (остальные — справочник на будущее)
DATA_SERVICE_KEYS: tuple[str, ...] = tuple(s.key for s in SERVICES if s.has_dashboard)

# ---------------------------------------------------------------- модель доступа 2.0 (ADR-0009)

DATA_CLASSES: dict[str, str] = {
    "operational": "Операционные",   # объёмы, сроки, статусы — доступны всем, у кого есть доступ к данным
    "personal": "Персональные",      # ФИО, должности, причины увольнения в реестрах
    "financial": "Финансовые",       # денежные показатели: выручка, затраты, ФОТ, бюджеты
}
DATA_CLASS_HINTS: dict[str, str] = {
    "operational": "Объёмы, сроки, статусы, количество — доступны всегда",
    "personal": "ФИО, должности, причины увольнения в реестрах",
    "financial": "Денежные показатели: выручка, затраты, ФОТ, бюджеты",
}
ORG_SCOPE_LABELS: dict[str, str] = {
    "company": "Вся компания",
    "branch": "Своя ветка структуры",
    "unit": "Своё подразделение",
}
MAX_DRILL_DEPTH = 9
# Измерения, которые пользователь может переопределить поверх профиля (users.access_overrides)
ACCESS_DIMENSIONS: tuple[str, ...] = ("org_scope", "data_classes", "drill_depth", "can_view_records", "can_export")


@dataclass(frozen=True)
class ProfileDef:
    key: str
    name: str
    description: str
    org_scope: str
    data_classes: tuple[str, ...]
    drill_depth: int | None
    can_view_records: bool
    can_export: bool
    service_levels: tuple[tuple[str, str], ...]
    sort_order: int


_VIEW_ALL = tuple((key, "viewer") for key in DATA_SERVICE_KEYS)

# Встроенные профили — уровни сотрудников. Создаются один раз; администратор может их изменить.
ACCESS_PROFILES: tuple[ProfileDef, ...] = (
    ProfileDef("executive", "Высшее руководство",
               "Верхнеуровневая картина всей компании, все классы данных, без исходных записей. "
               "Глубину детализации расширяйте лично.",
               "company", ("operational", "personal", "financial"), 1, False, True, _VIEW_ALL, 10),
    ProfileDef("director", "Руководитель направления",
               "Своё направление до уровня отделов, все классы данных и исходные записи.",
               "branch", ("operational", "personal", "financial"), 2, True, True, _VIEW_ALL, 20),
    ProfileDef("head", "Руководитель подразделения",
               "Своя ветка структуры целиком, без финансовых показателей.",
               "branch", ("operational", "personal"), None, True, True, (), 30),
    ProfileDef("specialist", "Специалист",
               "Своё подразделение, операционные данные; доступ к службам выдаётся лично.",
               "unit", ("operational",), None, True, True, (), 40),
    ProfileDef("employee", "Сотрудник",
               "Только просмотр статуса своего подразделения, без денежных показателей, детализации и выгрузок.",
               "unit", ("operational",), 0, False, False, (), 50),
)
ACCESS_PROFILE_BY_KEY = {p.key: p for p in ACCESS_PROFILES}

# Без профиля («индивидуальная настройка») — как в 0.1.0: ограничивают только уровни служб
INDIVIDUAL_DEFAULTS: dict = {
    "org_scope": "company", "data_classes": list(DATA_CLASSES), "drill_depth": None,
    "can_view_records": True, "can_export": True,
}

# Полномочия администрирования без роли администратора (как в todo-planner)
CAPABILITIES: dict[str, str] = {
    "org.manage": "Структура компании: подразделения, руководители, загрузка и выгрузка",
    "users.manage": "Пользователи и доступ (кроме администраторов)",
}

# ---------------------------------------------------------------- структура компании (ADR-0007)

ORG_UNIT_KINDS: tuple[dict, ...] = (
    {"value": "company", "label": "Компания", "color": "#7c3aed"},
    {"value": "division", "label": "Дирекция", "color": "#0369a1"},
    {"value": "direction", "label": "Направление", "color": "#0f766e"},
    {"value": "service", "label": "Служба", "color": "#b45309"},
    {"value": "department", "label": "Отдел", "color": "#4f7cff"},
    {"value": "sector", "label": "Сектор", "color": "#be185d"},
    {"value": "group", "label": "Группа", "color": "#15803d"},
    {"value": "position", "label": "Позиция", "color": "#64748b"},
)
ORG_SETTINGS_DEFAULTS: dict = {
    "org_unit_kinds": list(ORG_UNIT_KINDS),
    "org_max_depth": 15,
    "org_default_view": "chart",
}
ORG_VIEWS = ("chart", "people", "tree", "table")

DEPARTMENTS: tuple[tuple[str, str], ...] = (
    ("Аппарат генерального директора", "ADMIN"),
    ("ИТ-служба", "IT"),
    ("Техническая служба", "TECH"),
    ("Служба маркетинга", "MKT"),
    ("Коммерческая служба", "COMM"),
    ("Проектная служба", "PROJ"),
    ("АХО", "AHO"),
)


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    unit: str
    category: str
    aggregation: str  # sum | avg | latest | max
    direction: str  # lower_is_better | higher_is_better | neutral
    description: str
    sort_order: int


HR_METRIC_CATEGORIES = {
    "headcount": "Численность",
    "hiring": "Подбор",
    "adaptation": "Адаптация",
    "turnover": "Текучесть",
}

# Порядок воронки найма: вакансии → резюме → интервью → офферы → найм → скорость,
# затем адаптация и удержание. sort_order задаёт порядок во всех таблицах и формах.
HR_METRICS: tuple[MetricDef, ...] = (
    MetricDef("total_employees", "Всего сотрудников", "чел.", "headcount", "latest", "neutral",
              "Списочная численность на конец месяца", 0),
    MetricDef("projects_count", "Проекты найма", "шт.", "hiring", "sum", "neutral",
              "Количество проектов (вакансий) в работе", 10),
    MetricDef("resumes_screened", "Отобрано резюме", "чел.", "hiring", "sum", "neutral",
              "Количество отобранных резюме", 20),
    MetricDef("interviews_hr", "Интервью с HR", "чел.", "hiring", "sum", "neutral",
              "Количество проведённых интервью с HR", 30),
    MetricDef("interviews_hm", "Интервью с заказчиком", "чел.", "hiring", "sum", "neutral",
              "Количество интервью с нанимающими руководителями", 40),
    MetricDef("offers_accepted_pct", "Принятые офферы", "%", "hiring", "latest", "higher_is_better",
              "Доля принятых офферов от выставленных", 50),
    MetricDef("hired_count", "Нанято (по списку)", "чел.", "hiring", "sum", "neutral",
              "Количество принятых сотрудников по списку", 60),
    MetricDef("avg_time_to_fill", "Среднее время закрытия позиции", "дн.", "hiring", "avg", "lower_is_better",
              "Среднее время от открытия вакансии до выхода кандидата", 70),
    MetricDef("on_adaptation_count", "Сотрудников на адаптации", "чел.", "adaptation", "latest", "neutral",
              "Численность сотрудников на испытательном сроке", 80),
    MetricDef("adaptation_meetings", "Встречи по адаптации", "шт.", "adaptation", "sum", "neutral",
              "Количество встреч по адаптации", 90),
    MetricDef("probation_completed", "Завершили испытательный срок", "чел.", "adaptation", "sum", "neutral",
              "Количество завершённых испытательных сроков", 100),
    MetricDef("probation_pass_rate", "Прохождение испытательного срока (общее)", "%", "adaptation", "latest",
              "higher_is_better", "Доля сотрудников, прошедших испытательный срок", 110),
    MetricDef("probation_pass_rate_adaptation", "Прохождение испытательного срока (адаптация)", "%",
              "adaptation", "latest", "higher_is_better",
              "Доля прошедших испытательный срок среди сотрудников на адаптации", 120),
    MetricDef("adaptation_dismissals", "Увольнения на адаптации", "чел.", "adaptation", "sum", "lower_is_better",
              "Увольнения в период испытательного срока", 130),
    MetricDef("turnover", "Текучесть кадров", "%", "turnover", "latest", "lower_is_better",
              "Текучесть накопительно с начала года", 140),
    MetricDef("turnover_company", "Текучесть по инициативе компании", "%", "turnover", "latest", "lower_is_better",
              "Доля увольнений по инициативе компании", 150),
)
HR_METRIC_BY_KEY = {m.key: m for m in HR_METRICS}

# (metric_key, green, yellow, direction, enabled)
HR_DEFAULT_RULES: tuple[tuple[str, float, float, str, bool], ...] = (
    ("turnover", 5.0, 8.0, "lower_is_better", True),
    ("turnover_company", 3.5, 5.5, "lower_is_better", True),
    ("avg_time_to_fill", 40.0, 60.0, "lower_is_better", True),
    ("offers_accepted_pct", 85.0, 65.0, "higher_is_better", True),
    ("probation_pass_rate", 90.0, 75.0, "higher_is_better", True),
    ("probation_pass_rate_adaptation", 85.0, 70.0, "higher_is_better", True),
    ("adaptation_dismissals", 1.0, 3.0, "lower_is_better", True),
)

# Цели службы персонала: (metric_key, year, label, reference, target, description, source)
HR_DEFAULT_TARGETS: tuple[tuple, ...] = (
    ("turnover", 2025, "2025 год", 5.17, None,
     "Фактическая текучесть кадров за 2025 год", "Годовой отчёт службы персонала за 2025 год"),
    ("turnover", 2026, "Цель 2026", None, 5.0,
     "Целевой уровень текучести кадров", "План службы персонала на 2026 год"),
    ("avg_time_to_fill", 2026, "Цель 2026", None, 30.0,
     "Среднее время закрытия вакансии", "План службы персонала на 2026 год"),
    ("offers_accepted_pct", 2026, "Цель 2026", None, 90.0,
     "Доля принятых офферов", "План службы персонала на 2026 год"),
    ("probation_pass_rate", 2026, "Цель 2026", None, 95.0,
     "Прохождение испытательного срока", "План службы персонала на 2026 год"),
    ("probation_pass_rate_adaptation", 2026, "Цель 2026", None, 90.0,
     "Доля неудач адаптации не более 10%", "План службы персонала на 2026 год"),
)

# Светофор техподдержки по умолчанию: (metric_key, green, yellow, direction, enabled)
TP_DEFAULT_RULES: tuple[tuple[str, float, float, str, bool], ...] = (
    ("total_in_work", 180, 220, "lower_is_better", True),
    ("avail_total", 350, 420, "lower_is_better", True),
    ("new_received", 25, 35, "lower_is_better", False),
    ("total_solved_week", 25, 18, "higher_is_better", True),
    ("ratio_solved_received", 1, 0.8, "higher_is_better", True),
    ("altos_avg_time", 24, 48, "lower_is_better", True),
    ("altoffice_avg_time", 36, 72, "lower_is_better", True),
    ("altos_avail_total", 90, 70, "higher_is_better", False),
    ("altoffice_avail_total", 110, 90, "higher_is_better", False),
)

PARTNERSHIP_LIGHT_GROUPS = {
    "status": "Статус",
    "nda": "NDA",
    "agreement": "Соглашение",
    "cert_age": "Срок сертификата",
}

# (key, group, label, light, threshold)
PARTNERSHIP_DEFAULT_RULES: tuple[tuple[str, str, str, str, float | None], ...] = (
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
)

DEFAULT_PALETTE_NAME = "Сдержанная"

# Палитры-образцы. Значения согласованы с frontend/src/stores/palette.js (FALLBACK).
PALETTE_PRESETS: tuple[dict, ...] = (
    {
        "name": "Сдержанная",
        "colors": {
            "traffic_light": {"green": "#3f9f6b", "yellow": "#d29a2f", "red": "#d1495b", "neutral": "#a3acb9"},
            "charts": ["#3f6fb5", "#2c9aa6", "#7a5ba6", "#5b5fc7", "#b07aa1", "#8c6d46", "#64748b"],
            "brand": {"primary": "#c8302c", "muted": "#6b7280"},
        },
    },
    {
        "name": "Мягкая",
        "colors": {
            "traffic_light": {"green": "#5a9e68", "yellow": "#c9974a", "red": "#c97171", "neutral": "#b8bec7"},
            "charts": ["#5a9e68", "#6f8fbf", "#c9974a", "#8bbe9f", "#c97171", "#a9b2c3"],
            "brand": {"primary": "#c0392b", "muted": "#6b6a65"},
        },
    },
    {
        "name": "Классическая",
        "colors": {
            "traffic_light": {"green": "#4caf50", "yellow": "#ffc107", "red": "#f44336", "neutral": "#9e9e9e"},
            "charts": ["#4caf50", "#1f77b4", "#ffc107", "#8e44ad", "#f44336", "#7f8c8d"],
            "brand": {"primary": "#f44336", "muted": "#6b6a65"},
        },
    },
    {
        "name": "Холодная",
        "colors": {
            "traffic_light": {"green": "#26a69a", "yellow": "#42a5f5", "red": "#ff7043", "neutral": "#8fa3b0"},
            "charts": ["#26a69a", "#42a5f5", "#6fb1e0", "#8e7cc3", "#ff7043", "#8fa3b0"],
            "brand": {"primary": "#26a69a", "muted": "#5a6b78"},
        },
    },
    {
        "name": "Контрастная",
        "colors": {
            "traffic_light": {"green": "#2e7d32", "yellow": "#ef6c00", "red": "#c62828", "neutral": "#6e7378"},
            "charts": ["#2e7d32", "#0b5fa5", "#ef6c00", "#7b2fa0", "#c62828", "#5a6570"],
            "brand": {"primary": "#c62828", "muted": "#5a6570"},
        },
    },
)
