"""Align remaining legacy database tables with current ORM models.

Revision ID: 0010_align_remaining_orm_tables
Revises:     0009_employee_event_created_at
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_align_remaining_orm_tables"
down_revision = "0009_employee_event_created_at"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _add_column(table: str, column: sa.Column) -> None:
    if table in _tables() and column.name not in _columns(table):
        op.add_column(table, column)


def _create_index_if_missing(name: str, table: str, columns: list[str], unique: bool = False) -> None:
    if name not in {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    # Models currently use audit_logs; 0001 created the legacy audit_log table.
    # Keep the legacy table intact and create the current table for new writes.
    if "audit_logs" not in _tables():
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("username", sa.String(100), nullable=True, server_default="system"),
            sa.Column("entity_type", sa.String(60), nullable=False),
            sa.Column("entity_id", sa.String(100), nullable=True),
            sa.Column("action", sa.String(30), nullable=False),
            sa.Column("before_json", sa.JSON(), nullable=True),
            sa.Column("after_json", sa.JSON(), nullable=True),
            sa.Column("ip_address", sa.String(50), nullable=True, server_default=""),
            sa.Column("timestamp", sa.DateTime(), nullable=True),
        )

    # Current models use user_dashboard_preferences; dashboard_prefs is legacy.
    if "user_dashboard_preferences" not in _tables():
        op.create_table(
            "user_dashboard_preferences",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("service_key", sa.String(80), nullable=False),
            sa.Column("preferences_json", sa.JSON(), nullable=True),
            sa.UniqueConstraint("user_id", "service_key", name="uq_user_service_prefs"),
        )
        _create_index_if_missing(
            "ix_user_dashboard_preferences_user_id",
            "user_dashboard_preferences",
            ["user_id"],
        )
        _create_index_if_missing(
            "ix_user_dashboard_preferences_service_key",
            "user_dashboard_preferences",
            ["service_key"],
        )

    if "custom_dashboards" not in _tables():
        op.create_table(
            "custom_dashboards",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("is_shared", sa.Boolean(), nullable=True, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    if "dashboard_widgets" not in _tables():
        op.create_table(
            "dashboard_widgets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("dashboard_id", sa.Integer(), sa.ForeignKey("custom_dashboards.id", ondelete="CASCADE"), nullable=False),
            sa.Column("widget_type", sa.String(40), nullable=False),
            sa.Column("title", sa.String(200), nullable=True, server_default=""),
            sa.Column("config", sa.JSON(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=True, server_default="0"),
        )

    if "notes" not in _tables():
        op.create_table(
            "notes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("month_record_id", sa.Integer(), sa.ForeignKey("month_records.id", ondelete="CASCADE"), nullable=False),
            sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    if "partnership_light_rules" not in _tables():
        op.create_table(
            "partnership_light_rules",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("key", sa.String(80), unique=True, nullable=False),
            sa.Column("group_key", sa.String(40), nullable=False),
            sa.Column("label", sa.String(200), nullable=False),
            sa.Column("light", sa.String(20), nullable=False, server_default="gray"),
            sa.Column("threshold", sa.Float(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=True, server_default="0"),
        )
        _create_index_if_missing(
            "ix_partnership_light_rules_key",
            "partnership_light_rules",
            ["key"],
        )

    # These fields are in current models but may be absent in databases created
    # before the corresponding models were introduced.
    _add_column("users", sa.Column("created_at", sa.DateTime(), nullable=True))
    _add_column("month_records", sa.Column("updated_at", sa.DateTime(), nullable=True))
    _add_column("employee_events", sa.Column("created_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    for table in (
        "partnership_light_rules",
        "notes",
        "dashboard_widgets",
        "custom_dashboards",
        "user_dashboard_preferences",
        "audit_logs",
    ):
        if table in _tables():
            op.drop_table(table)
