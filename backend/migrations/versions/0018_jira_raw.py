"""Сырьё Jira (версия 0.6.0, этап 2, ADR-0012).

- jira_projects — справочник проектов (обновляется целиком действием `raw_projects`);
- jira_issues — задачи окном по updated (по умолчанию 90 дней; уникальность — ключ задачи);
- jira_worklogs — трудозатраты окном по started (по умолчанию 180 дней; уникальность —
  идентификатор worklog), оттуда считаются рабочие часы по людям и проектам.

Откат удаляет таблицы. Заполняет коннектор Jira (действия «Сырьё: …»); агрегаты по JQL
(значения показателей) работают как раньше — поверх того же подключения.

Revision ID: 0018_jira_raw
Revises: 0017_project_office
"""
import sqlalchemy as sa
from alembic import op

revision = "0018_jira_raw"
down_revision = "0017_project_office"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jira_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(300), nullable=False, server_default=""),
        sa.Column("lead", sa.String(300), nullable=False, server_default=""),
        sa.Column("project_type", sa.String(30), nullable=False, server_default=""),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "jira_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(60), nullable=False, unique=True),
        sa.Column("project_key", sa.String(30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("issue_type", sa.String(60), nullable=False, server_default=""),
        sa.Column("status", sa.String(100), nullable=False, server_default=""),
        sa.Column("priority", sa.String(60), nullable=False, server_default=""),
        sa.Column("assignee_email", sa.String(320), nullable=False, server_default=""),
        sa.Column("assignee_name", sa.String(300), nullable=False, server_default=""),
        sa.Column("reporter_email", sa.String(320), nullable=False, server_default=""),
        sa.Column("labels", sa.JSON(), nullable=True),
        sa.Column("jira_created", sa.DateTime(), nullable=True),
        sa.Column("jira_updated", sa.DateTime(), nullable=True),
        sa.Column("resolved", sa.DateTime(), nullable=True),
        sa.Column("timespent_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_jira_issues_project_key", "jira_issues", ["project_key"])
    op.create_index("ix_jira_issues_status", "jira_issues", ["status"])
    op.create_index("ix_jira_issues_assignee_email", "jira_issues", ["assignee_email"])

    op.create_table(
        "jira_worklogs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jira_id", sa.BigInteger(), nullable=False),
        sa.Column("issue_key", sa.String(60), nullable=False),
        sa.Column("author_email", sa.String(320), nullable=False, server_default=""),
        sa.Column("author_name", sa.String(300), nullable=False, server_default=""),
        sa.Column("started", sa.DateTime(), nullable=True),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("jira_id", name="uq_jira_worklog_id"),
    )
    op.create_index("ix_jira_worklogs_issue_key", "jira_worklogs", ["issue_key"])
    op.create_index("ix_jira_worklogs_author_email", "jira_worklogs", ["author_email"])
    op.create_index("ix_jira_worklogs_started", "jira_worklogs", ["started"])


def downgrade() -> None:
    op.drop_table("jira_worklogs")
    op.drop_table("jira_issues")
    op.drop_table("jira_projects")
