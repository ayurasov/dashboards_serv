"""Служба «Проектный офис» (ADR-0012, этап 3): агрегации сырья Jira/GitLab.

Считает из таблиц этапов 1–2: часы по людям и проектам (worklogs, план — из project_hour_plans
с ёмкостью производственного календаря), lead time задач, активность разработки (коммиты, MR,
пайплайны), несопоставленных авторов. Сопоставление авторов с сотрудниками: справочник
external_identities, автоматически — по users.email (без регистра).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import (
    ExternalIdentity,
    GitlabCommitDay,
    GitlabMergeRequest,
    GitlabPipelineDay,
    GitlabProject,
    JiraIssue,
    JiraWorklog,
    ProjectHourPlan,
    User,
)
from . import production_calendar

SERVICE = "project_office"


def month_bounds(month: date) -> tuple[datetime, datetime]:
    first = month.replace(day=1)
    if month.month == 12:
        nxt = first.replace(year=first.year + 1, month=1)
    else:
        nxt = first.replace(month=first.month + 1)
    return datetime(first.year, first.month, first.day), datetime(nxt.year, nxt.month, nxt.day)


def resolve_map(db: Session, service: str, emails: list[str]) -> dict[str, int | None]:
    """e-mail автора → id сотрудника: справочник external_identities, затем users.email."""
    emails = [e.lower() for e in emails]
    known = {e: uid for e, uid in db.execute(
        select(ExternalIdentity.external_email, ExternalIdentity.user_id)
        .where(ExternalIdentity.service.in_((service, "*")))).all()}
    by_user = {u.email.lower(): u.id for u in db.scalars(select(User).where(User.email.is_not(None)))
               if u.email}
    return {e: known.get(e) or by_user.get(e) for e in emails}


def hours_by_person(db: Session, month: date) -> list[dict]:
    """Часы трудозатрат за месяц по людям: сопоставленные сотрудники + несопоставленные авторы."""
    start, end = month_bounds(month)
    rows = db.execute(
        select(JiraWorklog.author_email, func.sum(JiraWorklog.time_spent_seconds))
        .where(JiraWorklog.started >= start, JiraWorklog.started < end)
        .group_by(JiraWorklog.author_email)).all()
    emails = [r[0].lower() for r in rows if r[0]]  # авторы Jira могут быть в любом регистре
    matched = resolve_map(db, "jira", emails)
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(
        [m for m in matched.values() if m])))}
    people: dict[int | str, dict] = {}
    for raw_email, seconds in rows:
        if not raw_email:
            continue
        email = raw_email.lower()
        uid = matched.get(email)
        key = uid or email
        slot = people.setdefault(key, {"name": "", "email": email, "user_id": uid, "hours": 0.0})
        slot["hours"] += round((seconds or 0) / 3600.0, 1)
    for slot in people.values():
        if slot["user_id"] and slot["user_id"] in users:
            slot["name"] = users[slot["user_id"]].full_name
    return sorted(people.values(), key=lambda p: -p["hours"])


def hours_by_project(db: Session, month: date) -> list[dict]:
    """Часы за месяц по проектам Jira (ключ из issue_key) с планом и месяцом-фактом прошлого."""
    start, end = month_bounds(month)
    prev_start = start - (end - start)
    def by_project(since: datetime, until: datetime) -> dict[str, float]:
        # Ключ проекта — часть до дефиса; split_part нет в SQLite, агрегируем в Python
        out: dict[str, float] = {}
        for issue_key, seconds in db.execute(select(JiraWorklog.issue_key,
                                                    func.sum(JiraWorklog.time_spent_seconds))
                                             .where(JiraWorklog.started >= since,
                                                    JiraWorklog.started < until)
                                             .group_by(JiraWorklog.issue_key)).all():
            out[issue_key.split("-", 1)[0]] = out.get(issue_key.split("-", 1)[0], 0) + (seconds or 0)
        return out

    actual, previous = by_project(start, end), by_project(prev_start, start)
    plans = {p.project_key: p.hours for p in db.scalars(
        select(ProjectHourPlan).where(ProjectHourPlan.month == start.date()))}
    keys = sorted(set(actual) | set(plans), key=lambda k: -(actual.get(k) or 0))
    return [{"project_key": k, "hours": round((actual.get(k) or 0) / 3600.0, 1),
             "plan_hours": plans.get(k), "prev_hours": round((previous.get(k) or 0) / 3600.0, 1)}
            for k in keys]


def issue_stats(db: Session, month: date) -> dict:
    """Задачи месяца: lead time решённых, WIP (открытых на конец месяца), просроченные."""
    start, end = month_bounds(month)
    resolved_rows = db.execute(
        select(JiraIssue.jira_created, JiraIssue.resolved).where(
            JiraIssue.resolved >= start, JiraIssue.resolved < end)).all()
    lead_days = sorted((r - c).total_seconds() / 86400.0 for c, r in resolved_rows if c and r and r >= c)

    def percentile(sorted_values: list[float], fraction: float) -> float | None:
        if not sorted_values:
            return None
        position = min(len(sorted_values) - 1, max(0, round(fraction * (len(sorted_values) - 1))))
        return round(sorted_values[position], 1)

    open_issues = db.scalar(select(func.count()).select_from(JiraIssue).where(
        JiraIssue.resolved.is_(None), JiraIssue.jira_created < end)) or 0
    return {"resolved": len(resolved_rows), "open": open_issues,
            "lead_p50": percentile(lead_days, 0.5), "lead_p90": percentile(lead_days, 0.9)}


def dev_activity(db: Session, weeks: int = 4) -> dict:
    """Активность разработки за N недель: коммиты, MR (время ревью, revert-доля), пайплайны."""
    since = utcnow() - timedelta(weeks=weeks)
    since_day = since.date()
    commits = db.scalar(select(func.coalesce(func.sum(GitlabCommitDay.commits), 0))
                        .where(GitlabCommitDay.day >= since_day)) or 0
    commit_authors = db.scalar(select(func.count(func.distinct(GitlabCommitDay.author_email)))
                               .where(GitlabCommitDay.day >= since_day)) or 0
    mrs = list(db.scalars(select(GitlabMergeRequest).where(
        GitlabMergeRequest.created_at >= since.replace(tzinfo=None))))
    merged = [m for m in mrs if m.merged_at and m.created_at]
    review_hours = sorted((m.merged_at - m.created_at).total_seconds() / 3600.0 for m in merged)
    total_pipelines = db.scalar(select(func.coalesce(func.sum(GitlabPipelineDay.count), 0))
                                .where(GitlabPipelineDay.day >= since_day)) or 0
    ok_pipelines = db.scalar(select(func.coalesce(func.sum(GitlabPipelineDay.count), 0))
                             .where(GitlabPipelineDay.day >= since_day,
                                    GitlabPipelineDay.status == "success")) or 0
    linked = sum(1 for m in mrs if m.jira_keys)
    return {"weeks": weeks, "commits": int(commits), "commit_authors": int(commit_authors),
            "merge_requests": len(mrs), "linked_to_jira": linked,
            "review_p50": round(review_hours[len(review_hours) // 2], 1) if review_hours else None,
            "pipelines": int(total_pipelines),
            "pipelines_ok_pct": round(100.0 * ok_pipelines / total_pipelines, 1) if total_pipelines else None}


def unmatched_authors(db: Session) -> list[dict]:
    """Авторы сырья без сопоставления: часы за 180 дней, источник, последний вклад."""
    since = utcnow() - timedelta(days=180)
    jira = dict(db.execute(select(JiraWorklog.author_email, func.sum(JiraWorklog.time_spent_seconds))
                           .where(JiraWorklog.started >= since.replace(tzinfo=None))
                           .group_by(JiraWorklog.author_email)).all())
    git = dict(db.execute(select(GitlabCommitDay.author_email, func.sum(GitlabCommitDay.commits))
                          .where(GitlabCommitDay.day >= since.date())
                          .group_by(GitlabCommitDay.author_email)).all())
    emails = set(jira) | set(git)
    if not emails:
        return []
    matched = resolve_map(db, "*", list(emails))
    manual = {e for e, uid in db.execute(select(ExternalIdentity.external_email,
                                                ExternalIdentity.user_id)).all()}
    out = []
    for email in sorted(emails):
        if matched.get(email) or email in manual:
            continue
        out.append({"email": email,
                    "jira_hours": round((jira.get(email) or 0) / 3600.0, 1),
                    "gitlab_commits": int(git.get(email) or 0)})
    return sorted(out, key=lambda a: -(a["jira_hours"] + a["gitlab_commits"]))


def dashboard(db: Session, month: date) -> dict:
    capacity_hours, calendar_precise = production_calendar.month_capacity(db, month)
    people = hours_by_person(db, month)
    matched_hours = sum(p["hours"] for p in people if p["user_id"])
    projects = hours_by_project(db, month)
    plan_total = sum(p["plan_hours"] or 0 for p in projects)
    return {
        "month": month.isoformat(),
        "capacity_hours": capacity_hours,
        "calendar_precise": calendar_precise,
        "people": people,
        "people_matched": sum(1 for p in people if p["user_id"]),
        "people_total": len(people),
        "hours_total": round(sum(p["hours"] for p in people), 1),
        "hours_matched": round(matched_hours, 1),
        "projects": projects,
        "plan_total": round(plan_total, 1),
        "issues": issue_stats(db, month),
        "activity": dev_activity(db),
    }


# ---------------------------------------------------------------- реестры (этап 3b)


def issue_registry(db: Session, *, project: str = "", status: str = "", assignee: str = "",
                   search: str = "", open_only: bool = False, page: int = 1, page_size: int = 50) -> dict:
    """Реестр задач Jira (окно сырья 90 дней по updated): фильтры и пагинация."""
    stmt = select(JiraIssue)
    if project:
        stmt = stmt.where(JiraIssue.project_key == project.upper())
    if status:
        stmt = stmt.where(JiraIssue.status == status)
    if assignee:
        stmt = stmt.where(JiraIssue.assignee_email == assignee.lower())
    if open_only:
        stmt = stmt.where(JiraIssue.resolved.is_(None))
    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(JiraIssue.key.ilike(like) | func.lower(JiraIssue.summary).ilike(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(stmt.order_by(JiraIssue.jira_updated.desc().nullslast(), JiraIssue.key)
                           .offset((page - 1) * page_size).limit(page_size)))
    # Количество MR по ключам задач — json_each не переносим между СУБД, считаем в Python
    mr_index: dict[str, int] = {}
    for keys in db.scalars(select(GitlabMergeRequest.jira_keys).where(GitlabMergeRequest.jira_keys.is_not(None))):
        for key in keys or []:
            mr_index[key] = mr_index.get(key, 0) + 1
    items = [{
        "key": r.key, "project_key": r.project_key, "summary": r.summary, "status": r.status,
        "issue_type": r.issue_type, "assignee_name": r.assignee_name, "assignee_email": r.assignee_email,
        "created": r.jira_created.isoformat() if r.jira_created else None,
        "updated": r.jira_updated.isoformat() if r.jira_updated else None,
        "resolved": r.resolved.isoformat() if r.resolved else None,
        "timespent_hours": round(r.timespent_seconds / 3600.0, 1),
        "merge_requests": mr_index.get(r.key, 0),
    } for r in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def issue_merge_requests(db: Session, issue_key: str) -> list[dict]:
    """Мерж-реквесты, связанные с задачей Jira (ключ в названии или ветке), — связка «задача → код»."""
    rows = db.scalars(select(GitlabMergeRequest).where(GitlabMergeRequest.jira_keys.is_not(None)))
    out = []
    for mr in rows:
        if issue_key.upper() not in (mr.jira_keys or []):
            continue
        out.append({
            "id": mr.id, "project_id": mr.project_id, "iid": mr.iid, "title": mr.title,
            "state": mr.state, "author_email": mr.author_email,
            "created": mr.gitlab_created_at.isoformat() if mr.gitlab_created_at else None,
            "merged": mr.merged_at.isoformat() if mr.merged_at else None,
            "additions": mr.additions, "deletions": mr.deletions,
        })
    return sorted(out, key=lambda m: m.get("merged") or m.get("created") or "", reverse=True)


def merge_request_registry(db: Session, *, project_id: int | None = None, state: str = "",
                           author: str = "", jira_key: str = "", search: str = "",
                           page: int = 1, page_size: int = 50) -> dict:
    """Реестр мерж-реквестов GitLab (окно сырья — год по ADR-0012): фильтры и пагинация."""
    stmt = select(GitlabMergeRequest)
    if project_id:
        stmt = stmt.where(GitlabMergeRequest.project_id == project_id)
    if state:
        stmt = stmt.where(GitlabMergeRequest.state == state)
    if author:
        stmt = stmt.where(GitlabMergeRequest.author_email == author.lower())
    if jira_key:
        stmt = stmt.where(GitlabMergeRequest.jira_keys.ilike(f'%"{jira_key.upper()}"%'))
    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(func.lower(GitlabMergeRequest.title).ilike(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(stmt.order_by(GitlabMergeRequest.gitlab_created_at.desc().nullslast())
                           .offset((page - 1) * page_size).limit(page_size)))
    projects = {p.id: p.path_with_namespace for p in db.scalars(select(GitlabProject))}
    items = [{
        "id": mr.id, "project_id": mr.project_id, "project_path": projects.get(mr.project_id, str(mr.project_id)),
        "iid": mr.iid, "title": mr.title, "state": mr.state, "author_email": mr.author_email,
        "source_branch": mr.source_branch,
        "created": mr.gitlab_created_at.isoformat() if mr.gitlab_created_at else None,
        "merged": mr.merged_at.isoformat() if mr.merged_at else None,
        "review_hours": round((mr.merged_at - mr.gitlab_created_at).total_seconds() / 3600.0, 1)
        if mr.merged_at and mr.gitlab_created_at else None,
        "jira_keys": mr.jira_keys or [],
    } for mr in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
