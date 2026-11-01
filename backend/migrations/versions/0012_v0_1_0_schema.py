"""Схема 0.1.0: перестройка всех таблиц с переносом данных.

Базы версий до 0.1.0 расходились с моделями: часть таблиц создавали миграции, часть —
create_all() при старте, часть столбцов добавлялась вручную. Поэтому миграция не меняет
таблицы по месту, а для каждой создаёт каноническую версию и переносит данные, читая
только те столбцы, которые в старой таблице действительно есть.

Что меняется:
- таблицы служб получили префиксы: hr_months, hr_employee_events, hr_metric_definitions,
  hr_metric_values, hr_month_notes, hr_targets, tp_weekly_reports; dashboard_modules →
  services, user_service_access → service_access, user_dashboard_preferences →
  dashboard_layouts, dashboard_widgets → custom_dashboard_widgets, audit_logs → audit_log;
- роли: admin и user; прежние роли превращаются в доступ к службе персонала
  (hr_head → «Управление», department_viewer → «Просмотр» только своих подразделений);
- уровни доступа: read → viewer, edit и edit_metrics → editor, admin → manager;
- правила светофора техподдержки из tp_settings перенесены в общую traffic_light_rules;
- год и неделя отчёта ТП — целые числа, пара (год, неделя) уникальна; номер заявки
  Naumen уникален (дубли схлопываются, остаётся последняя загруженная);
- внешние ключи, уникальные ограничения, CHECK и индексы — с едиными именами;
- новые таблицы: user_sessions, service_settings, data_imports.

Откат не поддерживается: перед обновлением сделайте резервную копию базы
(docs/runbooks/backup-restore.md).

Revision ID: 0012_v0_1_0_schema
Revises: 0011_naumen_tickets
"""
from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime

import sqlalchemy as sa
from alembic import op

revision = "0012_v0_1_0_schema"
down_revision = "0011_naumen_tickets"
branch_labels = None
depends_on = None

# Справочник служб на момент 0.1.0 (дальше его обновляет приложение при старте).
SERVICES = [
    ("hr", "Служба персонала", "Персонал", "users", "/hr", True, 0),
    ("tech", "Техническая поддержка", "Техподдержка", "headset", "/tp", True, 1),
    ("project_product", "Проектный и продуктовый офис", "Партнёрства", "handshake", "/product", True, 2),
    ("apparat_gd", "Аппарат генерального директора", "Аппарат ГД", "building", "/apparat", False, 3),
    ("it", "ИТ-служба", "ИТ", "monitor", "/it", False, 4),
    ("commercial", "Коммерческая служба", "Коммерция", "briefcase", "/commercial", False, 5),
    ("marketing", "Служба маркетинга", "Маркетинг", "megaphone", "/marketing", False, 6),
    ("finance", "Финансовая служба", "Финансы", "wallet", "/finance", False, 7),
    ("legal", "Юридическая служба", "Юристы", "scale", "/legal", False, 8),
]
SERVICE_KEYS = {s[0] for s in SERVICES}
LEGACY_SERVICE_KEYS = {"product_partnerships": "project_product"}
LEVEL_MAP = {"read": "viewer", "edit": "editor", "edit_metrics": "editor", "admin": "manager",
             "viewer": "viewer", "editor": "editor", "manager": "manager"}
LEVEL_RANK = {"viewer": 1, "editor": 2, "manager": 3}
PRESET_NAMES = {"Сдержанная", "Мягкая", "Классическая", "Холодная", "Контрастная"}

TP_METRIC_COLUMNS = (
    "total_in_work", "avail_total",
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
    "projserver_avail",
)

# Таблицы, имя которых совпадает с канонической: старую версию сначала «паркуем».
SAME_NAME_TABLES = (
    "users", "departments", "user_departments", "color_palettes", "custom_dashboards",
    "traffic_light_rules", "partnerships", "partnership_light_rules", "naumen_tickets", "audit_log",
)
# Старые таблицы с другими именами — удаляются после переноса.
LEGACY_TABLES = (
    "month_records", "employee_events", "metric_definitions", "metric_values", "notes", "benchmarks",
    "tp_report_rows", "tp_settings", "dashboard_modules", "user_service_access",
    "user_dashboard_preferences", "dashboard_prefs", "dashboard_widgets", "audit_logs",
)


# ---------------------------------------------------------------- helpers

def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "")).replace(tzinfo=None)
    except ValueError:
        return None


def _d(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _b(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "t", "yes")
    return bool(value)


def _s(value, limit: int | None = None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value)
    return text[:limit] if limit else text


def _f(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _json(value, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _rows(bind, table: str) -> list[dict]:
    if table not in _tables(bind):
        return []
    return [dict(r) for r in bind.execute(sa.text(f'SELECT * FROM "{table}"')).mappings()]


def _park(bind, table: str) -> str | None:
    """Переименовывает старую таблицу и убирает с дороги её индексы и последовательности."""
    if table not in _tables(bind):
        return None
    parked = f"_legacy_{table}"
    op.rename_table(table, parked)
    if bind.dialect.name == "postgresql":
        # Имена индексов и последовательностей в PostgreSQL общие для схемы: освобождаем их.
        index_names = bind.execute(sa.text(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() AND tablename = :t"),
            {"t": parked}).scalars().all()
        for n, index_name in enumerate(index_names):
            bind.execute(sa.text(f'ALTER INDEX "{index_name}" RENAME TO "_lgx_{table[:40]}_{n}"'))
        for column in sa.inspect(bind).get_columns(parked):
            seq = bind.execute(sa.text("SELECT pg_get_serial_sequence(:t, :c)"),
                               {"t": f'"{parked}"', "c": column["name"]}).scalar()
            if seq:
                bind.execute(sa.text(f'ALTER SEQUENCE {seq} RENAME TO "_lgs_{table[:40]}_{column["name"][:15]}"'))
    else:
        for (index_name,) in bind.execute(sa.text(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = :t AND sql IS NOT NULL"),
                {"t": parked}).all():
            bind.execute(sa.text(f'DROP INDEX "{index_name}"'))
    return parked


def _drop(bind, table: str) -> None:
    if table in _tables(bind):
        suffix = " CASCADE" if bind.dialect.name == "postgresql" else ""
        bind.execute(sa.text(f'DROP TABLE "{table}"{suffix}'))


def _insert(table: sa.Table, rows: list[dict]) -> None:
    if rows:
        op.bulk_insert(table, rows)


def _reset_sequence(bind, table: str, column: str = "id") -> None:
    if bind.dialect.name != "postgresql":
        return
    bind.execute(sa.text(
        f"SELECT setval(pg_get_serial_sequence('\"{table}\"', '{column}'), "
        f"COALESCE((SELECT MAX({column}) FROM \"{table}\"), 1), "
        f"(SELECT MAX({column}) FROM \"{table}\") IS NOT NULL)"))


def _ts():
    return [sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False)]


def _fk(table: str, column: str, ref: str, ref_col: str = "id", **kw) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([column], [f"{ref}.{ref_col}"], name=f"fk_{table}_{column}_{ref}", **kw)


# ---------------------------------------------------------------- schema

def _create_schema() -> dict[str, sa.Table]:
    t: dict[str, sa.Table] = {}

    t["services"] = op.create_table(
        "services",
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("short_title", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(40), nullable=False),
        sa.Column("route_prefix", sa.String(80), nullable=False),
        sa.Column("has_dashboard", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_services"),
    )
    t["departments"] = op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_departments"),
        sa.UniqueConstraint("name", name="uq_departments_name"),
        sa.UniqueConstraint("code", name="uq_departments_code"),
    )
    t["users"] = op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("position", sa.String(200), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("avatar", sa.Text(), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        *_ts(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("role IN ('admin', 'user')", name="ck_users_role"),
    )
    t["user_departments"] = op.create_table(
        "user_departments",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "department_id", name="pk_user_departments"),
        _fk("user_departments", "user_id", "users", ondelete="CASCADE"),
        _fk("user_departments", "department_id", "departments", ondelete="CASCADE"),
    )
    t["user_sessions"] = op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(300), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_user_sessions"),
        _fk("user_sessions", "user_id", "users", ondelete="CASCADE"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])

    t["service_access"] = op.create_table(
        "service_access",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("service_key", sa.String(40), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("department_scope", sa.Boolean(), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("granted_by_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_service_access"),
        sa.UniqueConstraint("user_id", "service_key", name="uq_service_access_user_id_service_key"),
        sa.CheckConstraint("level IN ('viewer', 'editor', 'manager')", name="ck_service_access_level"),
        _fk("service_access", "user_id", "users", ondelete="CASCADE"),
        _fk("service_access", "service_key", "services", "key", ondelete="CASCADE", onupdate="CASCADE"),
        _fk("service_access", "granted_by_id", "users", ondelete="SET NULL"),
    )
    op.create_index("ix_service_access_user_id", "service_access", ["user_id"])
    op.create_index("ix_service_access_service_key", "service_access", ["service_key"])

    t["audit_log"] = op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("service_key", sa.String(40), nullable=True),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=True),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(300), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
        _fk("audit_log", "user_id", "users", ondelete="SET NULL"),
    )
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_service_key", "audit_log", ["service_key"])
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])

    t["color_palettes"] = op.create_table(
        "color_palettes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("colors", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_preset", sa.Boolean(), nullable=False),
        *_ts(),
        sa.PrimaryKeyConstraint("id", name="pk_color_palettes"),
        sa.UniqueConstraint("name", name="uq_color_palettes_name"),
    )
    t["service_settings"] = op.create_table(
        "service_settings",
        sa.Column("service_key", sa.String(40), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("service_key", "key", name="pk_service_settings"),
        _fk("service_settings", "service_key", "services", "key", ondelete="CASCADE", onupdate="CASCADE"),
        _fk("service_settings", "updated_by_id", "users", ondelete="SET NULL"),
    )
    t["traffic_light_rules"] = op.create_table(
        "traffic_light_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_key", sa.String(40), nullable=False),
        sa.Column("metric_key", sa.String(80), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("green_threshold", sa.Float(), nullable=True),
        sa.Column("yellow_threshold", sa.Float(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_traffic_light_rules"),
        sa.UniqueConstraint("service_key", "metric_key", name="uq_traffic_light_rules_service_key_metric_key"),
        sa.CheckConstraint("direction IN ('lower_is_better', 'higher_is_better')",
                           name="ck_traffic_light_rules_direction"),
        _fk("traffic_light_rules", "service_key", "services", "key", ondelete="CASCADE", onupdate="CASCADE"),
    )
    op.create_index("ix_traffic_light_rules_service_key", "traffic_light_rules", ["service_key"])

    t["data_imports"] = op.create_table(
        "data_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_key", sa.String(40), nullable=False),
        sa.Column("dataset", sa.String(60), nullable=False),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("rows_total", sa.Integer(), nullable=False),
        sa.Column("rows_created", sa.Integer(), nullable=False),
        sa.Column("rows_updated", sa.Integer(), nullable=False),
        sa.Column("rows_skipped", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_data_imports"),
        _fk("data_imports", "service_key", "services", "key", ondelete="CASCADE", onupdate="CASCADE"),
        _fk("data_imports", "user_id", "users", ondelete="SET NULL"),
    )
    op.create_index("ix_data_imports_service_key", "data_imports", ["service_key"])
    op.create_index("ix_data_imports_created_at", "data_imports", ["created_at"])

    t["dashboard_layouts"] = op.create_table(
        "dashboard_layouts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("service_key", sa.String(40), nullable=False),
        sa.Column("layout", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dashboard_layouts"),
        sa.UniqueConstraint("user_id", "service_key", name="uq_dashboard_layouts_user_id_service_key"),
        _fk("dashboard_layouts", "user_id", "users", ondelete="CASCADE"),
        _fk("dashboard_layouts", "service_key", "services", "key", ondelete="CASCADE", onupdate="CASCADE"),
    )
    op.create_index("ix_dashboard_layouts_user_id", "dashboard_layouts", ["user_id"])

    t["custom_dashboards"] = op.create_table(
        "custom_dashboards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        *_ts(),
        sa.PrimaryKeyConstraint("id", name="pk_custom_dashboards"),
        _fk("custom_dashboards", "owner_id", "users", ondelete="SET NULL"),
    )
    op.create_index("ix_custom_dashboards_owner_id", "custom_dashboards", ["owner_id"])
    t["custom_dashboard_widgets"] = op.create_table(
        "custom_dashboard_widgets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dashboard_id", sa.Integer(), nullable=False),
        sa.Column("widget_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_custom_dashboard_widgets"),
        _fk("custom_dashboard_widgets", "dashboard_id", "custom_dashboards", ondelete="CASCADE"),
    )
    op.create_index("ix_custom_dashboard_widgets_dashboard_id", "custom_dashboard_widgets", ["dashboard_id"])

    # --- служба персонала
    t["hr_months"] = op.create_table(
        "hr_months",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        *_ts(),
        sa.PrimaryKeyConstraint("id", name="pk_hr_months"),
        sa.UniqueConstraint("year", "month", name="uq_hr_months_year_month"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_hr_months_month_range"),
    )
    t["hr_employee_events"] = op.create_table(
        "hr_employee_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(10), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("full_name", sa.String(300), nullable=False),
        sa.Column("position", sa.String(300), nullable=False),
        sa.Column("department", sa.String(200), nullable=False),
        sa.Column("employment_type", sa.String(100), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        *_ts(),
        sa.PrimaryKeyConstraint("id", name="pk_hr_employee_events"),
        sa.CheckConstraint("event_type IN ('hired', 'fired')", name="ck_hr_employee_events_event_type"),
        _fk("hr_employee_events", "month_id", "hr_months", ondelete="CASCADE"),
    )
    op.create_index("ix_hr_employee_events_month_id", "hr_employee_events", ["month_id"])
    op.create_index("ix_hr_employee_events_department", "hr_employee_events", ["department"])

    t["hr_metric_definitions"] = op.create_table(
        "hr_metric_definitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("aggregation", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_hr_metric_definitions"),
        sa.UniqueConstraint("key", name="uq_hr_metric_definitions_key"),
    )
    t["hr_metric_values"] = op.create_table(
        "hr_metric_values",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month_id", sa.Integer(), nullable=False),
        sa.Column("metric_key", sa.String(80), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_hr_metric_values"),
        sa.UniqueConstraint("month_id", "metric_key", name="uq_hr_metric_values_month_id_metric_key"),
        _fk("hr_metric_values", "month_id", "hr_months", ondelete="CASCADE"),
        _fk("hr_metric_values", "metric_key", "hr_metric_definitions", "key", ondelete="CASCADE",
            onupdate="CASCADE"),
    )
    op.create_index("ix_hr_metric_values_month_id", "hr_metric_values", ["month_id"])
    op.create_index("ix_hr_metric_values_metric_key", "hr_metric_values", ["metric_key"])

    t["hr_month_notes"] = op.create_table(
        "hr_month_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_hr_month_notes"),
        _fk("hr_month_notes", "month_id", "hr_months", ondelete="CASCADE"),
        _fk("hr_month_notes", "author_id", "users", ondelete="SET NULL"),
    )
    op.create_index("ix_hr_month_notes_month_id", "hr_month_notes", ["month_id"])

    t["hr_targets"] = op.create_table(
        "hr_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_key", sa.String(80), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("reference_value", sa.Float(), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source", sa.String(300), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_hr_targets"),
        sa.UniqueConstraint("metric_key", "year", name="uq_hr_targets_metric_key_year"),
        _fk("hr_targets", "metric_key", "hr_metric_definitions", "key", ondelete="CASCADE", onupdate="CASCADE"),
    )
    op.create_index("ix_hr_targets_metric_key", "hr_targets", ["metric_key"])

    # --- техподдержка
    t["tp_weekly_reports"] = op.create_table(
        "tp_weekly_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        *[sa.Column(name, sa.Float(), nullable=True) for name in TP_METRIC_COLUMNS],
        *_ts(),
        sa.PrimaryKeyConstraint("id", name="pk_tp_weekly_reports"),
        sa.UniqueConstraint("year", "week", name="uq_tp_weekly_reports_year_week"),
        sa.CheckConstraint("week BETWEEN 1 AND 53", name="ck_tp_weekly_reports_week_range"),
    )
    t["naumen_tickets"] = op.create_table(
        "naumen_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("registered_at", sa.DateTime(), nullable=True),
        sa.Column("solved_at", sa.DateTime(), nullable=True),
        sa.Column("deadline_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(100), nullable=False),
        sa.Column("org", sa.String(300), nullable=False),
        sa.Column("responsible", sa.String(300), nullable=False),
        sa.Column("team", sa.String(200), nullable=False),
        sa.Column("first_line", sa.String(300), nullable=False),
        sa.Column("channel", sa.String(100), nullable=False),
        sa.Column("is_overdue", sa.Boolean(), nullable=False),
        sa.Column("is_reopened", sa.Boolean(), nullable=False),
        sa.Column("processing_hours", sa.Float(), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_naumen_tickets"),
        sa.UniqueConstraint("number", name="uq_naumen_tickets_number"),
    )
    op.create_index("ix_naumen_tickets_registered_at", "naumen_tickets", ["registered_at"])
    op.create_index("ix_naumen_tickets_solved_at", "naumen_tickets", ["solved_at"])
    op.create_index("ix_naumen_tickets_org", "naumen_tickets", ["org"])

    # --- партнёрства
    t["partnerships"] = op.create_table(
        "partnerships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("partner", sa.String(300), nullable=False),
        sa.Column("product", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(300), nullable=False),
        sa.Column("almi_product", sa.String(200), nullable=False),
        sa.Column("almi_version", sa.String(200), nullable=False),
        sa.Column("status", sa.String(60), nullable=False),
        sa.Column("cert_date", sa.Date(), nullable=True),
        sa.Column("nda", sa.Boolean(), nullable=False),
        sa.Column("agreement", sa.Boolean(), nullable=False),
        sa.Column("bitrix", sa.String(500), nullable=False),
        sa.Column("website", sa.String(500), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("last_modified", sa.Date(), nullable=True),
        *_ts(),
        sa.PrimaryKeyConstraint("id", name="pk_partnerships"),
    )
    op.create_index("ix_partnerships_partner", "partnerships", ["partner"])
    op.create_index("ix_partnerships_almi_product", "partnerships", ["almi_product"])
    op.create_index("ix_partnerships_status", "partnerships", ["status"])
    t["partnership_light_rules"] = op.create_table(
        "partnership_light_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("group_key", sa.String(40), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("light", sa.String(20), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_partnership_light_rules"),
        sa.UniqueConstraint("key", name="uq_partnership_light_rules_key"),
        sa.CheckConstraint("light IN ('green', 'yellow', 'red', 'gray')", name="ck_partnership_light_rules_light"),
    )
    return t


# ---------------------------------------------------------------- data transfer

def _transfer(bind, t: dict[str, sa.Table], parked: dict[str, str | None]) -> None:
    now = _now()

    def old(name: str) -> list[dict]:
        source = parked.get(name, name) if name in SAME_NAME_TABLES else name
        return _rows(bind, source) if source else []

    _insert(t["services"], [
        {"key": key, "title": title, "short_title": short, "description": "", "icon": icon,
         "route_prefix": prefix, "has_dashboard": has_dash, "sort_order": order}
        for key, title, short, icon, prefix, has_dash, order in SERVICES
    ])

    # Подразделения и пользователи
    seen_names, seen_codes, departments = set(), set(), []
    for r in old("departments"):
        name, code = _s(r.get("name"), 200).strip(), _s(r.get("code"), 50).strip()
        if not name or not code or name in seen_names or code in seen_codes:
            continue
        seen_names.add(name)
        seen_codes.add(code)
        departments.append({"id": r["id"], "name": name, "code": code,
                            "created_at": _dt(r.get("created_at")) or now})
    _insert(t["departments"], departments)
    dept_ids = {d["id"] for d in departments}

    users, legacy_roles, emails = [], {}, set()
    for r in old("users"):
        username = _s(r.get("username"), 100).strip()
        password_hash = r.get("hashed_password") or r.get("password_hash")
        if not username or not password_hash:
            continue
        legacy_role = _s(r.get("role")).strip().lower()
        legacy_roles[r["id"]] = legacy_role
        email = (_s(r.get("email"), 200).strip() or None)
        if email and email.lower() in emails:
            email = None
        if email:
            emails.add(email.lower())
        created = _dt(r.get("created_at")) or now
        users.append({
            "id": r["id"], "username": username,
            "full_name": _s(r.get("full_name"), 200).strip() or username,
            "email": email, "position": r.get("position") or None, "phone": r.get("phone") or None,
            "avatar": r.get("avatar") or None,
            "role": "admin" if legacy_role == "admin" else "user",
            "password_hash": password_hash,
            "is_active": _b(r.get("is_active"), True),
            "must_change_password": _b(r.get("must_change_password")),
            "password_changed_at": None, "last_login_at": None,
            "created_at": created, "updated_at": created,
        })
    _insert(t["users"], users)
    user_ids = {u["id"] for u in users}

    _insert(t["user_departments"], [
        {"user_id": r["user_id"], "department_id": r["department_id"]}
        for r in {(r["user_id"], r["department_id"]): r for r in old("user_departments")}.values()
        if r["user_id"] in user_ids and r["department_id"] in dept_ids
    ])

    # Доступ к службам: явные строки + права, которые раньше давала глобальная роль
    access: dict[tuple[int, str], dict] = {}
    for r in _rows(bind, "user_service_access"):
        key = LEGACY_SERVICE_KEYS.get(r.get("service_key"), r.get("service_key"))
        level = LEVEL_MAP.get(_s(r.get("access_level")).strip())
        if r.get("user_id") not in user_ids or key not in SERVICE_KEYS or not level:
            continue
        current = access.get((r["user_id"], key))
        if current and LEVEL_RANK[current["level"]] >= LEVEL_RANK[level]:
            continue
        access[(r["user_id"], key)] = {"user_id": r["user_id"], "service_key": key, "level": level,
                                       "department_scope": False,
                                       "granted_at": _dt(r.get("granted_at")) or now, "granted_by_id": None}
    for user_id, legacy_role in legacy_roles.items():
        if user_id not in user_ids:
            continue
        if legacy_role == "hr_head":
            access[(user_id, "hr")] = {"user_id": user_id, "service_key": "hr", "level": "manager",
                                       "department_scope": False, "granted_at": now, "granted_by_id": None}
        elif legacy_role in ("dept_viewer", "department_viewer"):
            row = access.setdefault((user_id, "hr"), {"user_id": user_id, "service_key": "hr", "level": "viewer",
                                                      "granted_at": now, "granted_by_id": None})
            row["department_scope"] = True
    _insert(t["service_access"], list(access.values()))

    # Журнал: новая таблица audit_logs и самая первая audit_log
    audit = []
    for r in _rows(bind, "audit_logs"):
        audit.append({
            "occurred_at": _dt(r.get("timestamp")) or now,
            "user_id": r.get("user_id") if r.get("user_id") in user_ids else None,
            "username": _s(r.get("username"), 100) or "system", "service_key": None,
            "entity_type": _s(r.get("entity_type"), 60) or "unknown", "entity_id": r.get("entity_id"),
            "action": _s(r.get("action"), 30) or "update", "summary": "",
            "before": _json(r.get("before_json")), "after": _json(r.get("after_json")),
            "ip_address": _s(r.get("ip_address"), 64), "user_agent": "",
        })
    usernames = {u["id"]: u["username"] for u in users}
    for r in old("audit_log"):
        audit.append({
            "occurred_at": _dt(r.get("created_at")) or now,
            "user_id": r.get("user_id") if r.get("user_id") in user_ids else None,
            "username": usernames.get(r.get("user_id"), "system"), "service_key": None,
            "entity_type": _s(r.get("entity_type"), 60) or "unknown", "entity_id": r.get("entity_id"),
            "action": _s(r.get("action"), 30) or "update", "summary": _s(r.get("detail"), 500),
            "before": None, "after": None, "ip_address": _s(r.get("ip_address"), 64), "user_agent": "",
        })
    audit.sort(key=lambda a: a["occurred_at"])
    _insert(t["audit_log"], audit)

    # Палитры: имя уникально, цвета — JSON
    palettes, names, active_seen = [], set(), False
    for r in sorted(old("color_palettes"), key=lambda r: (not _b(r.get("is_active")), r["id"])):
        name = _s(r.get("name"), 200).strip() or f"Палитра {r['id']}"
        if name in names:
            continue
        names.add(name)
        is_active = _b(r.get("is_active")) and (r.get("scope") or "global") == "global" and not active_seen
        active_seen = active_seen or is_active
        created = _dt(r.get("created_at")) or now
        palettes.append({"id": r["id"], "name": name, "colors": _json(r.get("colors_json"), {}) or {},
                         "is_active": is_active, "is_preset": name in PRESET_NAMES,
                         "created_at": created, "updated_at": created})
    _insert(t["color_palettes"], palettes)

    # Раскладки дашбордов
    layouts = {}
    for r in _rows(bind, "dashboard_prefs") + _rows(bind, "user_dashboard_preferences"):
        key = LEGACY_SERVICE_KEYS.get(r.get("service_key"), r.get("service_key"))
        layout = _json(r.get("preferences_json") if "preferences_json" in r else r.get("prefs_json"), {})
        if r.get("user_id") in user_ids and key in SERVICE_KEYS and isinstance(layout, dict):
            layouts[(r["user_id"], key)] = {"user_id": r["user_id"], "service_key": key, "layout": layout,
                                            "updated_at": _dt(r.get("updated_at")) or now}
    _insert(t["dashboard_layouts"], list(layouts.values()))

    dashboards = []
    for r in old("custom_dashboards"):
        created = _dt(r.get("created_at")) or now
        dashboards.append({"id": r["id"], "name": _s(r.get("name"), 200) or "Дашборд",
                           "owner_id": r.get("owner_id") if r.get("owner_id") in user_ids else None,
                           "is_shared": _b(r.get("is_shared")), "created_at": created, "updated_at": created})
    _insert(t["custom_dashboards"], dashboards)
    dash_ids = {d["id"] for d in dashboards}
    _insert(t["custom_dashboard_widgets"], [
        {"id": r["id"], "dashboard_id": r["dashboard_id"], "widget_type": _s(r.get("widget_type"), 40) or "note",
         "title": _s(r.get("title"), 200), "config": _json(r.get("config"), {}) or {},
         "sort_order": int(r.get("sort_order") or 0)}
        for r in _rows(bind, "dashboard_widgets") if r.get("dashboard_id") in dash_ids
    ])

    # --- служба персонала
    months = []
    for r in _rows(bind, "month_records"):
        year, month = r.get("year"), r.get("month")
        if year is None or month is None or not 1 <= int(month) <= 12:
            continue
        created = _dt(r.get("created_at")) or now
        months.append({"id": r["id"], "year": int(year), "month": int(month), "comment": _s(r.get("notes")),
                       "created_at": created, "updated_at": _dt(r.get("updated_at")) or created})
    months = list({(m["year"], m["month"]): m for m in months}.values())
    _insert(t["hr_months"], months)
    month_ids = {m["id"] for m in months}

    _insert(t["hr_employee_events"], [
        {"id": r["id"], "month_id": r["month_record_id"],
         "event_type": "fired" if _s(r.get("event_type")).strip() == "fired" else "hired",
         "event_date": _d(r.get("event_date")) or date.today(),
         "full_name": _s(r.get("full_name"), 300) or "—", "position": _s(r.get("position"), 300),
         "department": _s(r.get("department"), 200), "employment_type": _s(r.get("employment_type"), 100),
         "reason": "", "created_at": _dt(r.get("created_at")) or now, "updated_at": _dt(r.get("created_at")) or now}
        for r in _rows(bind, "employee_events") if r.get("month_record_id") in month_ids
    ])

    definitions, def_keys = [], set()
    for i, r in enumerate(_rows(bind, "metric_definitions")):
        key = _s(r.get("key"), 80).strip()
        if not key or key in def_keys:
            continue
        def_keys.add(key)
        direction = _s(r.get("direction")) or "neutral"
        definitions.append({
            "key": key, "label": _s(r.get("label"), 200) or key, "unit": _s(r.get("unit"), 30),
            "category": _s(r.get("category"), 40) or "general", "aggregation": _s(r.get("aggregation"), 20) or "avg",
            "direction": direction if direction in ("lower_is_better", "higher_is_better") else "neutral",
            "description": _s(r.get("description")), "sort_order": int(r.get("sort_order") or i),
            "is_active": True,
        })
    values = []
    for r in _rows(bind, "metric_values"):
        key = _s(r.get("metric_key"), 80).strip()
        if r.get("month_record_id") not in month_ids or not key:
            continue
        if key not in def_keys:
            # Значение метрики без описания сохраняем: создаём выключенную метрику.
            def_keys.add(key)
            definitions.append({"key": key, "label": key, "unit": "", "category": "general",
                                "aggregation": "avg", "direction": "neutral", "description": "",
                                "sort_order": 9000 + len(definitions), "is_active": False})
        note = _s(r.get("source_note"))
        if not note and r.get("text_value"):
            note = _s(r.get("text_value"))
        values.append({"month_id": r["month_record_id"], "metric_key": key, "value": _f(r.get("numeric_value")),
                       "source_note": note, "updated_at": now})
    _insert(t["hr_metric_definitions"], definitions)
    _insert(t["hr_metric_values"], list({(v["month_id"], v["metric_key"]): v for v in values}.values()))

    _insert(t["hr_month_notes"], [
        {"id": r["id"], "month_id": r["month_record_id"],
         "author_id": r.get("author_id") if r.get("author_id") in user_ids else None,
         "content": _s(r.get("content")), "created_at": _dt(r.get("created_at")) or now}
        for r in _rows(bind, "notes") if r.get("month_record_id") in month_ids and r.get("content")
    ])

    targets = {}
    for r in _rows(bind, "benchmarks"):
        key = _s(r.get("metric_key"), 80).strip()
        if key not in def_keys or r.get("year") is None:
            continue
        target, value = _f(r.get("target_value")), _f(r.get("value"))
        targets[(key, int(r["year"]))] = {
            "metric_key": key, "year": int(r["year"]), "label": _s(r.get("label"), 200),
            "reference_value": None if target is not None and value == target else value,
            "target_value": target, "description": _s(r.get("description")),
            "source": _s(r.get("source"), 300), "updated_at": now}
    _insert(t["hr_targets"], list(targets.values()))

    # Светофор: правила службы персонала и правила ТП из tp_settings
    rules = {}
    for r in old("traffic_light_rules"):
        key = _s(r.get("metric_key"), 80).strip()
        if not key:
            continue
        direction = _s(r.get("direction"))
        rules[("hr", key)] = {
            "service_key": "hr", "metric_key": key,
            "direction": direction if direction in ("lower_is_better", "higher_is_better") else "higher_is_better",
            "green_threshold": _f(r.get("green_threshold")), "yellow_threshold": _f(r.get("yellow_threshold")),
            "enabled": _b(r.get("enabled"), True), "updated_at": now}
    settings_rows = []
    for r in _rows(bind, "tp_settings"):
        value = _json(r.get("value"), {})
        if r.get("key") == "traffic_rules" and isinstance(value, dict):
            for key, rule in value.items():
                if not isinstance(rule, dict):
                    continue
                rules[("tech", key)] = {
                    "service_key": "tech", "metric_key": _s(key, 80),
                    "direction": "lower_is_better" if rule.get("direction") == "less" else "higher_is_better",
                    "green_threshold": _f(rule.get("green")), "yellow_threshold": _f(rule.get("yellow")),
                    "enabled": _b(rule.get("enabled"), True), "updated_at": now}
        elif r.get("key") in ("block_settings", "color_palette") and value:
            settings_rows.append({"service_key": "tech", "key": r["key"], "value": value,
                                  "updated_at": now, "updated_by_id": None})
    _insert(t["traffic_light_rules"], list(rules.values()))
    _insert(t["service_settings"], settings_rows)

    # --- техподдержка
    weeks = {}
    for r in sorted(_rows(bind, "tp_report_rows"), key=lambda r: r["id"]):
        year, week = _f(r.get("year")), _f(r.get("week"))
        if year is None or week is None or not 1 <= int(week) <= 53:
            continue
        created = _dt(r.get("created_at")) or now
        row = {"year": int(year), "week": int(week), "note": _s(r.get("extra")),
               "created_at": created, "updated_at": _dt(r.get("updated_at")) or created}
        row.update({name: _f(r.get(name)) for name in TP_METRIC_COLUMNS})
        weeks[(row["year"], row["week"])] = row
    _insert(t["tp_weekly_reports"], sorted(weeks.values(), key=lambda w: (w["year"], w["week"])))

    tickets, numbers = [], {}
    for r in sorted(old("naumen_tickets"), key=lambda r: r["id"]):
        number = r.get("number")
        row = {"id": r["id"], "number": int(number) if number is not None else None,
               "name": _s(r.get("name"), 50), "registered_at": _dt(r.get("registered_at")),
               "solved_at": _dt(r.get("solved_at")), "deadline_at": _dt(r.get("deadline_at")),
               "status": _s(r.get("status"), 100), "org": _s(r.get("org"), 300),
               "responsible": _s(r.get("responsible"), 300), "team": _s(r.get("team"), 200),
               "first_line": _s(r.get("first_line"), 300), "channel": _s(r.get("channel"), 100),
               "is_overdue": _b(r.get("overdue")), "is_reopened": _b(r.get("reopened")),
               "processing_hours": _f(r.get("processing_hours")),
               "imported_at": _dt(r.get("created_at")) or now}
        if row["number"] is None:
            tickets.append(row)
        else:
            numbers[row["number"]] = row
    _insert(t["naumen_tickets"], sorted(tickets + list(numbers.values()), key=lambda r: r["id"]))

    # --- партнёрства
    partnerships = []
    for r in old("partnerships"):
        created = _dt(r.get("created_at")) or now
        partnerships.append({
            "id": r["id"], "partner": _s(r.get("partner"), 300) or "—", "product": _s(r.get("product")),
            "direction": _s(r.get("direction"), 300), "almi_product": _s(r.get("almi_product"), 200),
            "almi_version": _s(r.get("almi_version"), 200), "status": _s(r.get("status"), 60) or "В работе",
            "cert_date": _d(r.get("cert_date")), "nda": _b(r.get("nda")), "agreement": _b(r.get("agreement")),
            "bitrix": _s(r.get("bitrix"), 500), "website": _s(r.get("website"), 500),
            "comment": _s(r.get("comment")), "type": _s(r.get("type"), 30) or "ПО",
            "last_modified": _d(r.get("last_modified")), "created_at": created, "updated_at": created})
    _insert(t["partnerships"], partnerships)
    light_rules = {}
    for r in old("partnership_light_rules"):
        light = _s(r.get("light"))
        light_rules[_s(r.get("key"), 80)] = {
            "id": r["id"], "key": _s(r.get("key"), 80), "group_key": _s(r.get("group_key"), 40),
            "label": _s(r.get("label"), 200), "light": light if light in ("green", "yellow", "red", "gray") else "gray",
            "threshold": _f(r.get("threshold")), "sort_order": int(r.get("sort_order") or 0)}
    _insert(t["partnership_light_rules"], list(light_rules.values()))

    for table in ("departments", "users", "service_access", "audit_log", "color_palettes", "data_imports",
                  "dashboard_layouts", "custom_dashboards", "custom_dashboard_widgets", "traffic_light_rules",
                  "hr_months", "hr_employee_events", "hr_metric_definitions", "hr_metric_values",
                  "hr_month_notes", "hr_targets", "tp_weekly_reports", "naumen_tickets", "partnerships",
                  "partnership_light_rules"):
        _reset_sequence(bind, table)


def upgrade() -> None:
    bind = op.get_bind()
    parked = {name: _park(bind, name) for name in SAME_NAME_TABLES}
    tables = _create_schema()
    _transfer(bind, tables, parked)
    for name in LEGACY_TABLES:
        _drop(bind, name)
    for name in parked.values():
        if name:
            _drop(bind, name)


def downgrade() -> None:
    raise RuntimeError(
        "Откат схемы 0.1.0 не поддерживается: восстановите резервную копию базы, "
        "сделанную перед обновлением (docs/runbooks/backup-restore.md)."
    )
