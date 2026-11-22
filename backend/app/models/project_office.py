"""Сырьё проектного офиса (ADR-0012): проекты, агрегат коммитов и мерж-реквесты GitLab.

Заполняет коннектор GitLab (app/integrations/connectors/gitlab.py) окном перезаливки;
коммиты хранятся дневным агрегатом «день × автор × проект» — сырьё компактно, счёт
и вклад в активность считаются из него. Мерж-реквесты — построчно: их на порядок меньше,
а метрики ревью требуют деталей. Сопоставление авторов с сотрудниками — по e-mail
(таблица переопределений появится со службой «Проектный офис», этап 3).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from .core import TimestampMixin

BIG_ID = BigInteger().with_variant(Integer(), "sqlite")


class GitlabProject(TimestampMixin, Base):
    """Проект GitLab (справочник; обновляется действием `projects` целиком)."""

    __tablename__ = "gitlab_projects"

    id: Mapped[int] = mapped_column(BIG_ID, primary_key=True)  # идентификатор проекта GitLab
    path_with_namespace: Mapped[str] = mapped_column(String(500), unique=True)
    name: Mapped[str] = mapped_column(String(300), default="")
    namespace: Mapped[str] = mapped_column(String(300), default="", index=True)  # группа/пользователь
    web_url: Mapped[str] = mapped_column(String(500), default="")
    default_branch: Mapped[str] = mapped_column(String(200), default="")
    archived: Mapped[bool] = mapped_column(default=False, index=True)
    last_activity_at: Mapped[datetime | None] = mapped_column()
    visibility: Mapped[str] = mapped_column(String(30), default="")


class GitlabCommitDay(Base):
    """Дневной агрегат коммитов: день × автор (e-mail, в нижнем регистре) × проект."""

    __tablename__ = "gitlab_commits_daily"
    __table_args__ = (UniqueConstraint("day", "author_email", "project_id", name="uq_gitlab_commit_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    author_email: Mapped[str] = mapped_column(String(320), index=True)
    project_id: Mapped[int] = mapped_column(BIG_ID, ForeignKey("gitlab_projects.id"), index=True)
    commits: Mapped[int] = mapped_column(Integer, default=0)
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)


class GitlabMergeRequest(TimestampMixin, Base):
    """Мерж-реквест: метрики ревью и связка с задачами Jira (ключи из названия и ветки)."""

    __tablename__ = "gitlab_merge_requests"
    __table_args__ = (UniqueConstraint("project_id", "iid", name="uq_gitlab_mr"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(BIG_ID, ForeignKey("gitlab_projects.id"), index=True)
    iid: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(30), default="opened", index=True)  # opened · merged · closed
    author_email: Mapped[str] = mapped_column(String(320), default="", index=True)
    source_branch: Mapped[str] = mapped_column(String(300), default="")
    target_branch: Mapped[str] = mapped_column(String(300), default="")
    gitlab_created_at: Mapped[datetime | None] = mapped_column()
    merged_at: Mapped[datetime | None] = mapped_column()
    closed_at: Mapped[datetime | None] = mapped_column()
    first_approved_at: Mapped[datetime | None] = mapped_column()
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    changed_files: Mapped[int] = mapped_column(Integer, default=0)
    reviewers: Mapped[list | None] = mapped_column(JSON)  # e-mail/имена ревьюеров
    jira_keys: Mapped[list | None] = mapped_column(JSON)  # ключи задач из названия и ветки


class GitlabPipelineDay(Base):
    """Дневной агрегат пайплайнов: день × проект × итоговый статус."""

    __tablename__ = "gitlab_pipelines_daily"
    __table_args__ = (UniqueConstraint("day", "project_id", "status", name="uq_gitlab_pipeline_day"),
                      Index("ix_gitlab_pipeline_day_day", "day"))

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date)
    project_id: Mapped[int] = mapped_column(BIG_ID, ForeignKey("gitlab_projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="")  # success · failed · canceled …
    count: Mapped[int] = mapped_column(Integer, default=0)
    duration_total: Mapped[float] = mapped_column(Float, default=0.0)  # сумма секунд, среднее = /count


# ---------------------------------------------------------------- Jira: сырьё (ADR-0012, этап 2)


class JiraProject(TimestampMixin, Base):
    """Проект Jira (справочник; обновляется действием `raw_projects` целиком)."""

    __tablename__ = "jira_projects"

    id: Mapped[int] = mapped_column(primary_key=True)  # идентификатор проекта Jira
    key: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(300), default="")
    lead: Mapped[str] = mapped_column(String(300), default="")  # displayName ведущего
    project_type: Mapped[str] = mapped_column(String(30), default="")
    archived: Mapped[bool] = mapped_column(default=False)


class JiraIssue(TimestampMixin, Base):
    """Задача Jira: окно перезаливки по updated (по умолчанию 90 дней, ADR-0012)."""

    __tablename__ = "jira_issues"

    id: Mapped[int] = mapped_column(primary_key=True)  # идентификатор задачи Jira
    key: Mapped[str] = mapped_column(String(60), unique=True)
    project_key: Mapped[str] = mapped_column(String(30), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    issue_type: Mapped[str] = mapped_column(String(60), default="")
    status: Mapped[str] = mapped_column(String(100), default="", index=True)
    priority: Mapped[str] = mapped_column(String(60), default="")
    assignee_email: Mapped[str] = mapped_column(String(320), default="", index=True)
    assignee_name: Mapped[str] = mapped_column(String(300), default="")
    reporter_email: Mapped[str] = mapped_column(String(320), default="")
    labels: Mapped[list | None] = mapped_column(JSON)
    jira_created: Mapped[datetime | None] = mapped_column()
    jira_updated: Mapped[datetime | None] = mapped_column()
    resolved: Mapped[datetime | None] = mapped_column()
    timespent_seconds: Mapped[int] = mapped_column(Integer, default=0)


class JiraWorklog(TimestampMixin, Base):
    """Запись трудозатрат: автор, задача, дата, часы (окно по started, по умолчанию 180 дней)."""

    __tablename__ = "jira_worklogs"
    __table_args__ = (UniqueConstraint("jira_id", name="uq_jira_worklog_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    jira_id: Mapped[str] = mapped_column(BigInteger)  # идентификатор worklog в Jira
    issue_key: Mapped[str] = mapped_column(String(60), index=True)
    author_email: Mapped[str] = mapped_column(String(320), default="", index=True)
    author_name: Mapped[str] = mapped_column(String(300), default="")
    started: Mapped[datetime | None] = mapped_column(index=True)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0)
    comment: Mapped[str] = mapped_column(Text, default="")
