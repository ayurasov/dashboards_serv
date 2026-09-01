"""Add legacy columns required by current ORM models.

Revision ID: 0009_employee_event_created_at
Revises:     0008_legacy_timestamp_columns
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_employee_event_created_at"
down_revision = "0008_legacy_timestamp_columns"
branch_labels = None
depends_on = None


def _add_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def upgrade() -> None:
    _add_if_missing("employee_events", sa.Column("created_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("employee_events")}
    if "created_at" in columns:
        op.drop_column("employee_events", "created_at")
