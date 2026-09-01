"""Align metric_definitions with the SQLAlchemy model.

Revision ID: 0006_metric_definition_id
Revises:     0005_add_tp_tables
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_metric_definition_id"
down_revision = "0005_add_tp_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("metric_definitions")}

    # Fresh databases may already have the corrected schema if the initial
    # migration was edited before first installation.
    if "id" in columns:
        return

    # SQLite cannot add a new primary-key column to the existing table. Rebuild
    # the table while preserving all seeded metric definitions and values.
    op.rename_table("metric_definitions", "metric_definitions_old")
    op.create_table(
        "metric_definitions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(80), unique=True, nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(30), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("value_type", sa.String(20), nullable=True),
        sa.Column("aggregation", sa.String(20), nullable=True),
        sa.Column("direction", sa.String(30), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True, server_default="0"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO metric_definitions
                (key, label, unit, category, value_type, aggregation,
                 direction, description, sort_order)
            SELECT key, label, unit, category, value_type, aggregation,
                   direction, description, sort_order
            FROM metric_definitions_old
            """
        )
    )
    op.drop_table("metric_definitions_old")
    op.create_index(
        "ix_metric_definitions_key", "metric_definitions", ["key"], unique=False
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("metric_definitions")}
    if "id" not in columns:
        return

    op.drop_index("ix_metric_definitions_key", table_name="metric_definitions")
    op.rename_table("metric_definitions", "metric_definitions_new")
    op.create_table(
        "metric_definitions",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(30), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("value_type", sa.String(20), nullable=True),
        sa.Column("aggregation", sa.String(20), nullable=True),
        sa.Column("direction", sa.String(30), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True, server_default="0"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO metric_definitions
                (key, label, unit, category, value_type, aggregation,
                 direction, description, sort_order)
            SELECT key, label, unit, category, value_type, aggregation,
                   direction, description, sort_order
            FROM metric_definitions_new
            """
        )
    )
    op.drop_table("metric_definitions_new")
