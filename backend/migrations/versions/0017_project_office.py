"""Сырьё проектного офиса (версия 0.6.0, этап 1, ADR-0012): GitLab.

- gitlab_projects — справочник проектов (обновляется целиком действием `projects`);
- gitlab_commits_daily — дневной агрегат коммитов «день × автор × проект» (компактное сырьё:
  счёт и вклад в активность считаются из него; уникальность тройки — перезаливка окна идемпотентна);
- gitlab_merge_requests — мерж-реквесты построчно: метрики ревью и связка с задачами Jira
  (ключи из названия и ветки); уникальность (проект, iid);
- gitlab_pipelines_daily — дневной агрегат пайплайнов «день × проект × статус» (количество,
  суммарная длительность) — успешность и время до зелёного.

Откат удаляет таблицы. Заполняет коннектор GitLab; служба «Проектный офис» (этап 3) читает сырьё.

Revision ID: 0017_project_office
Revises: 0016_integrations
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_project_office"
down_revision = "0016_integrations"
branch_labels = None
depends_on = None

BIG_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "gitlab_projects",
        sa.Column("id", BIG_ID, primary_key=True),
        sa.Column("path_with_namespace", sa.String(500), nullable=False, unique=True),
        sa.Column("name", sa.String(300), nullable=False, server_default=""),
        sa.Column("namespace", sa.String(300), nullable=False, server_default=""),
        sa.Column("web_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("default_branch", sa.String(200), nullable=False, server_default=""),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_activity_at", sa.DateTime(), nullable=True),
        sa.Column("visibility", sa.String(30), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_gitlab_projects_archived", "gitlab_projects", ["archived"])
    op.create_index("ix_gitlab_projects_namespace", "gitlab_projects", ["namespace"])

    op.create_table(
        "gitlab_commits_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("author_email", sa.String(320), nullable=False),
        sa.Column("project_id", BIG_ID, sa.ForeignKey("gitlab_projects.id"), nullable=False),
        sa.Column("commits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("additions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deletions", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("day", "author_email", "project_id", name="uq_gitlab_commit_day"),
    )
    op.create_index("ix_gitlab_commits_daily_day", "gitlab_commits_daily", ["day"])
    op.create_index("ix_gitlab_commits_daily_author_email", "gitlab_commits_daily", ["author_email"])
    op.create_index("ix_gitlab_commits_daily_project_id", "gitlab_commits_daily", ["project_id"])

    op.create_table(
        "gitlab_merge_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", BIG_ID, sa.ForeignKey("gitlab_projects.id"), nullable=False),
        sa.Column("iid", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("state", sa.String(30), nullable=False, server_default="opened"),
        sa.Column("author_email", sa.String(320), nullable=False, server_default=""),
        sa.Column("source_branch", sa.String(300), nullable=False, server_default=""),
        sa.Column("target_branch", sa.String(300), nullable=False, server_default=""),
        sa.Column("gitlab_created_at", sa.DateTime(), nullable=True),
        sa.Column("merged_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("first_approved_at", sa.DateTime(), nullable=True),
        sa.Column("additions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deletions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changed_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reviewers", sa.JSON(), nullable=True),
        sa.Column("jira_keys", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "iid", name="uq_gitlab_mr"),
    )
    op.create_index("ix_gitlab_merge_requests_project_id", "gitlab_merge_requests", ["project_id"])
    op.create_index("ix_gitlab_merge_requests_state", "gitlab_merge_requests", ["state"])
    op.create_index("ix_gitlab_merge_requests_author_email", "gitlab_merge_requests", ["author_email"])

    op.create_table(
        "gitlab_pipelines_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("project_id", BIG_ID, sa.ForeignKey("gitlab_projects.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=""),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_total", sa.Float(), nullable=False, server_default="0"),
        sa.UniqueConstraint("day", "project_id", "status", name="uq_gitlab_pipeline_day"),
    )
    op.create_index("ix_gitlab_pipeline_day_day", "gitlab_pipelines_daily", ["day"])
    op.create_index("ix_gitlab_pipelines_daily_project_id", "gitlab_pipelines_daily", ["project_id"])


def downgrade() -> None:
    op.drop_table("gitlab_pipelines_daily")
    op.drop_table("gitlab_merge_requests")
    op.drop_table("gitlab_commits_daily")
    op.drop_table("gitlab_projects")
