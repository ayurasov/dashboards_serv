"""Служба «Проектный офис» (версия 0.6.0, этап 3, ADR-0012).

- external_identities — сопоставление внешних авторов (Jira/GitLab) с сотрудниками структуры:
  автоматом по e-mail, эта таблица — для исключений (другая почта, CI-бот, несколько учёток);
- calendar_overrides — корпоративные отличия производственного календаря РФ (0 — выходной);
- project_hour_plans — план часов «проект × месяц»: задаёт руководитель проекта.

Сама служба добавляется в справочник кодом (registry.SERVICES, sync_reference_data).
Откат удаляет таблицы; данные сырья (этапы 1–2) не трогает.

Revision ID: 0019_project_office_service
Revises: 0018_jira_raw
"""
import sqlalchemy as sa
from alembic import op

revision = "0019_project_office_service"
down_revision = "0018_jira_raw"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service", sa.String(30), nullable=False),
        sa.Column("external_email", sa.String(320), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
    )
    op.create_index("ix_external_identities_service", "external_identities", ["service"])
    op.create_index("ix_external_identities_external_email", "external_identities", ["external_email"])
    op.create_index("ix_external_identities_user_id", "external_identities", ["user_id"])

    op.create_table(
        "calendar_overrides",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
    )

    op.create_table(
        "project_hour_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_key", sa.String(60), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_key", "month", name="uq_project_hour_plan"),
    )
    op.create_index("ix_project_hour_plans_project_key", "project_hour_plans", ["project_key"])


def downgrade() -> None:
    op.drop_table("project_hour_plans")
    op.drop_table("calendar_overrides")
    op.drop_table("external_identities")
