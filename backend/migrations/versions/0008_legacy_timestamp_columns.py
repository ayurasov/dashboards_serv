"""Add columns present in current ORM models but missing from legacy tables.

Revision ID: 0008_legacy_timestamp_columns
Revises:     0007_user_created_at
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_legacy_timestamp_columns"
down_revision = "0007_user_created_at"
branch_labels = None
depends_on = None


def _add_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def upgrade() -> None:
    _add_if_missing(
        "month_records",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("month_records")}
    if "updated_at" in columns:
        op.drop_column("month_records", "updated_at")
