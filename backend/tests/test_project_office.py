"""Служба «Проектный офис» (ADR-0012, этап 3): календарь, сопоставление авторов, агрегации
часов/проектов/задач, план часов и доступ. Сырьё засеивается прямо в тесте (таблицы этапов 1–2)."""
from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import select

from app.models import (
    ExternalIdentity,
    GitlabCommitDay,
    GitlabMergeRequest,
    GitlabProject,
    JiraIssue,
    JiraWorklog,
    ProjectHourPlan,
    User,
)
from app.services import production_calendar, project_office


@pytest.fixture()
def raw(db):
    """Сырьё: два автора (один сопоставится по e-mail), два проекта, задачи, MR, коммиты."""
    users = {u.username: u for u in db.scalars(select(User))}
    ivanov = users["hr_head"]  # у демо-пользователей есть e-mail
    ivanov.email = "ivanov@almi-partner.ru"
    db.add(JiraWorklog(jira_id=1, issue_key="COP-180", author_email="Ivanov@almi-partner.ru",
                       author_name="Иванов", started=datetime(2026, 11, 10, 10), time_spent_seconds=7200))
    db.add(JiraWorklog(jira_id=2, issue_key="SRM-100", author_email="bot@ci",
                       author_name="CI", started=datetime(2026, 11, 12, 10), time_spent_seconds=3600))
    db.add(JiraWorklog(jira_id=3, issue_key="SRM-101", author_email="ivanov@almi-partner.ru",
                       author_name="Иванов", started=datetime(2026, 11, 20, 10), time_spent_seconds=1800))
    db.add(JiraIssue(id=1, key="COP-180", project_key="COP", summary="Задача",
                     jira_created=datetime(2026, 10, 1), jira_updated=datetime(2026, 11, 12),
                     resolved=datetime(2026, 11, 12, 15)))
    db.add(JiraIssue(id=2, key="SRM-100", project_key="SRM", summary="Ещё",
                     jira_created=datetime(2026, 11, 1), jira_updated=datetime(2026, 11, 12)))
    db.add(GitlabProject(id=21, path_with_namespace="dev/dash", name="dash"))
    db.flush()  # проект раньше коммитов и MR: у тестовой сессии autoflush=False
    db.add(GitlabCommitDay(day=date(2026, 11, 15), author_email="ivanov@almi-partner.ru",
                           project_id=21, commits=3, additions=10, deletions=2))
    db.add(GitlabMergeRequest(project_id=21, iid=7, title="COP-180: спарклайны", state="merged",
                              author_email="ivanov@almi-partner.ru", jira_keys=["COP-180"],
                              gitlab_created_at=datetime(2026, 11, 10), merged_at=datetime(2026, 11, 12)))
    db.commit()
    return {"ivanov": ivanov}


MONTH = date(2026, 11, 1)


# ---------------------------------------------------------------- календарь

def test_production_calendar_rf_norms():
    assert production_calendar.day_hours(date(2025, 1, 1)) == 0
    assert production_calendar.day_hours(date(2025, 4, 26)) == 8  # перенесённый рабочий
    assert production_calendar.day_hours(date(2025, 4, 30)) == 7  # предпраздничный
    hours, precise = production_calendar.capacity(None, date(2025, 1, 1), date(2025, 1, 31))
    assert hours == 136 and precise  # норма января 2025: 17 дней × 8 ч
    hours, precise = production_calendar.capacity(None, date(2028, 1, 1), date(2028, 1, 31))
    assert not precise  # за пределами справочника — предупреждение


def test_calendar_override_makes_day_off(db):
    db.add(__import__("app.models", fromlist=["CalendarOverride"]).CalendarOverride(
        day=date(2026, 11, 16), hours=0, note="корпоративный выходной"))
    db.commit()
    hours, _ = production_calendar.month_capacity(db, MONTH)
    hours_before, _ = production_calendar.capacity(None, date(2026, 11, 1), date(2026, 11, 30))
    assert hours == hours_before - 8


# ---------------------------------------------------------------- агрегации

def test_hours_by_person_matches_by_email(db, raw):
    people = project_office.hours_by_person(db, MONTH)
    by_email = {p["email"]: p for p in people}
    ivanov = by_email["ivanov@almi-partner.ru"]
    assert ivanov["hours"] == 2.5 and ivanov["user_id"] == raw["ivanov"].id and ivanov["name"]
    assert by_email["bot@ci"]["user_id"] is None


def test_identity_override_beats_email(db, raw):
    """Справочник сильнее автосопоставления: часы бота уходят сотруднику."""
    db.add(ExternalIdentity(service="jira", external_email="bot@ci", user_id=raw["ivanov"].id))
    db.commit()
    people = {p["email"]: p for p in project_office.hours_by_person(db, MONTH)}
    assert "bot@ci" not in people
    assert people["ivanov@almi-partner.ru"]["user_id"] == raw["ivanov"].id
    assert people["ivanov@almi-partner.ru"]["hours"] == 3.5  # 2.5 Иванова + 1.0 бота


def test_hours_by_project_with_plan(db, raw):
    db.add(ProjectHourPlan(project_key="COP", month=MONTH, hours=10))
    db.commit()
    projects = {p["project_key"]: p for p in project_office.hours_by_project(db, MONTH)}
    assert projects["COP"]["hours"] == 2.0 and projects["COP"]["plan_hours"] == 10
    assert projects["SRM"]["hours"] == 1.5 and projects["SRM"]["plan_hours"] is None


def test_issue_stats_lead_time_and_wip(db, raw):
    stats = project_office.issue_stats(db, MONTH)
    assert stats["resolved"] == 1 and stats["open"] == 1
    assert stats["lead_p50"] == pytest.approx(42.6)  # 1 окт 00:00 → 12 ноя 15:00


def test_dev_activity_and_unmatched(db, raw):
    activity = project_office.dev_activity(db)
    assert activity["commits"] == 3 and activity["merge_requests"] == 1
    assert activity["linked_to_jira"] == 1
    unmatched = {a["email"]: a for a in project_office.unmatched_authors(db)}
    assert "bot@ci" in unmatched and "ivanov@almi-partner.ru" not in unmatched


# ---------------------------------------------------------------- API

def test_api_dashboard_plans_and_access(admin, db, raw):
    data = admin.get("/api/project-office/dashboard", params={"month": "2026-11"}).json()
    assert data["hours_total"] == 3.5, data["people"]
    assert data["people_total"] == 2, data["people"]
    assert data["plan_total"] == 0 and data["capacity_hours"] > 100
    assert data["issues"]["resolved"] == 1

    # план часов: менеджер службы задаёт, viewer не может
    created = admin.put("/api/project-office/plans/COP", json={"month": "2026-11", "hours": 10})
    assert created.status_code == 200 and created.json()["hours"] == 10
    data = admin.get("/api/project-office/dashboard", params={"month": "2026-11"}).json()
    assert data["plan_total"] == 10

    # сопоставления: несопоставленный автор виден, сопоставление создаётся и убирает его из списка
    unmatched = admin.get("/api/project-office/identities/unmatched").json()
    assert any(a["email"] == "bot@ci" for a in unmatched)
    identity = admin.post("/api/project-office/identities",
                          json={"external_email": "bot@ci", "user_id": raw["ivanov"].id, "service": "jira"})
    assert identity.status_code == 201
    data = admin.get("/api/project-office/dashboard", params={"month": "2026-11"}).json()
    assert data["people_total"] == 1 and data["hours_total"] == 3.5  # бот слит в Иванова

    # повтор — конфликт; удаление — ок
    assert admin.post("/api/project-office/identities",
                      json={"external_email": "bot@ci", "user_id": raw["ivanov"].id,
                            "service": "jira"}).status_code == 409
    assert admin.delete(f"/api/project-office/identities/{identity.json()['id']}").status_code == 200


def test_api_denies_without_service_access(login, db, raw):
    viewer = login("viewer")  # демо-пользователь без службы «Проектный офис»
    assert viewer.get("/api/project-office/dashboard").status_code == 403
