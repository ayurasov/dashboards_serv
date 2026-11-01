"""Сквозные отчёты (версия 0.3.0, ADR-0010).

- indicators — каталог показателей: класс данных, направление, свёртка по структуре, правило
  светофора (пороги или отклонение от цели), цель по умолчанию, источник (вычисляется из данных
  службы или вводится), служба-владелец, типы уровней, где значение ожидается;
- indicator_values — введённые значения за месяц по подразделениям (уникальность: показатель,
  подразделение, период); вычисляемые показатели не хранятся;
- unit_status_notes — заметки руководителя о статусе подразделения за период («под контролем»);
- report_revision — ревизия отчётов (одна строка), увеличивается в транзакции любого изменения.

Настройка «служба → подразделение структуры» хранится в app_settings (report_service_units)
и создаётся при первом изменении. Откат удаляет таблицы отчётов и эту настройку.

Revision ID: 0015_reports
Revises: 0014_org_access
"""
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0015_reports"
down_revision = "0014_org_access"
branch_labels = None
depends_on = None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def upgrade() -> None:
    op.create_table(
        "indicators",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("data_class", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("rollup", sa.String(10), nullable=False),
        sa.Column("rule_type", sa.String(20), nullable=False),
        sa.Column("green_threshold", sa.Float(), nullable=True),
        sa.Column("yellow_threshold", sa.Float(), nullable=True),
        sa.Column("green_deviation", sa.Float(), nullable=True),
        sa.Column("yellow_deviation", sa.Float(), nullable=True),
        sa.Column("default_target", sa.Float(), nullable=True),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_key", sa.String(40), nullable=True),
        sa.Column("owner_service", sa.String(40), nullable=True),
        sa.Column("expected_kinds", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_indicators"),
        sa.UniqueConstraint("key", name="uq_indicators_key"),
        sa.UniqueConstraint("name", name="uq_indicators_name"),
        sa.ForeignKeyConstraint(["owner_service"], ["services.key"], name="fk_indicators_owner_service_services",
                                ondelete="SET NULL", onupdate="CASCADE"),
        sa.CheckConstraint("data_class IN ('operational', 'personal', 'financial')", name="ck_indicators_data_class"),
        sa.CheckConstraint("direction IN ('higher_is_better', 'lower_is_better', 'neutral')",
                           name="ck_indicators_direction"),
        sa.CheckConstraint("rollup IN ('sum', 'avg', 'none')", name="ck_indicators_rollup"),
        sa.CheckConstraint("rule_type IN ('threshold', 'target')", name="ck_indicators_rule_type"),
        sa.CheckConstraint("source_type IN ('computed', 'manual')", name="ck_indicators_source_type"),
    )
    op.create_index("ix_indicators_owner_service", "indicators", ["owner_service"])

    op.create_table(
        "indicator_values",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("indicator_id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("target", sa.Float(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_indicator_values"),
        sa.UniqueConstraint("indicator_id", "department_id", "period",
                            name="uq_indicator_values_indicator_id_department_id_period"),
        sa.ForeignKeyConstraint(["indicator_id"], ["indicators.id"], name="fk_indicator_values_indicator_id_indicators",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"],
                                name="fk_indicator_values_department_id_departments", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_indicator_values_updated_by_id_users",
                                ondelete="SET NULL"),
        sa.CheckConstraint("source IN ('manual', 'import')", name="ck_indicator_values_source"),
    )
    op.create_index("ix_indicator_values_department_id", "indicator_values", ["department_id"])
    op.create_index("ix_indicator_values_period", "indicator_values", ["period"])

    op.create_table(
        "unit_status_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_unit_status_notes"),
        sa.UniqueConstraint("department_id", "period", name="uq_unit_status_notes_department_id_period"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"],
                                name="fk_unit_status_notes_department_id_departments", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name="fk_unit_status_notes_author_id_users",
                                ondelete="SET NULL"),
        sa.CheckConstraint("status IN ('watch')", name="ck_unit_status_notes_status"),
    )
    op.create_index("ix_unit_status_notes_period", "unit_status_notes", ["period"])

    op.create_table(
        "report_revision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_report_revision"),
    )
    op.execute(sa.text("INSERT INTO report_revision (id, revision, updated_at) VALUES (1, 0, :now)")
               .bindparams(now=_now()))


def downgrade() -> None:
    op.execute("DELETE FROM app_settings WHERE key = 'report_service_units'")
    op.drop_table("report_revision")
    op.drop_index("ix_unit_status_notes_period", table_name="unit_status_notes")
    op.drop_table("unit_status_notes")
    op.drop_index("ix_indicator_values_period", table_name="indicator_values")
    op.drop_index("ix_indicator_values_department_id", table_name="indicator_values")
    op.drop_table("indicator_values")
    op.drop_index("ix_indicators_owner_service", table_name="indicators")
    op.drop_table("indicators")
