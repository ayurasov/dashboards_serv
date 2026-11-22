"""Сырьё Jira (ADR-0012, этап 2): справочник проектов, задачи окном, трудозатраты — против
поддельного сервера (формы ответов Server 8.x: /project, POST /search с startAt, worklog в поле
задачи с догрузкой страницы через /issue/{key}/worklog).

Реальный инстанс — https://jira.almi-partner.ru:8443 (Server 8.3.5, REST API 2, basic-авторизация):
проверен read-only пробами 2026-11-21.
"""
from __future__ import annotations

from app.integrations.connectors.jira import JiraConnector
from app.integrations.runner import RunContext
from app.models import JiraIssue, JiraProject, JiraWorklog
from tests.fake_http import FakeServer

PROJECTS = [
    {"id": 101, "key": "COP", "name": "АЛМИ Connect", "lead": {"displayName": "Юрасов А.В."},
     "projectTypeKey": "software", "archived": False},
    {"id": 102, "key": "SUP", "name": "Поддержка", "lead": {"displayName": "Иванов И.И."},
     "projectTypeKey": "service_desk", "archived": False},
]

ISSUES = [
    {"id": 9001, "key": "COP-180", "fields": {
        "project": {"key": "COP"}, "summary": "Спарклайны", "issuetype": {"name": "Task"},
        "status": {"name": "Готово"}, "priority": {"name": "Высокий"},
        "assignee": {"emailAddress": "Ivanov@almi-partner.ru", "displayName": "Иванов И.И."},
        "reporter": {"emailAddress": "yurasov.av@almi-partner.ru"},
        "created": "2026-11-10T09:00:00.000+0300", "updated": "2026-11-18T15:00:00.000+0300",
        "resolutiondate": "2026-11-18T15:00:00.000+0300", "timespent": 14400, "labels": ["фронт"]}},
    {"id": 9002, "key": "SUP-5", "fields": {
        "project": {"key": "SUP"}, "summary": "Заявка", "issuetype": {"name": "Bug"},
        "status": {"name": "В работе"}, "priority": None,
        "assignee": None, "reporter": {"emailAddress": "petrov@almi-partner.ru"},
        "created": "2026-11-19T09:00:00.000+0300", "updated": "2026-11-19T10:00:00.000+0300",
        "resolutiondate": None, "timespent": None, "labels": []}},
]

WORKLOGS = {  # у COP-180 — 22 записи: 20 в поиске, остальное — страницей /worklog
    "COP-180": [{"id": 5000 + n, "author": {"emailAddress": "Ivanov@almi-partner.ru",
                                            "displayName": "Иванов И.И."},
                 "started": "2026-11-18T10:00:00.000+0300", "timeSpentSeconds": 3600,
                 "comment": ""} for n in range(22)],
}


def make_server() -> FakeServer:
    server = FakeServer()
    server.route("GET", "/rest/api/2/project", lambda req: (200, PROJECTS))

    def search(req):
        body = req.json()
        if "worklogDate" in body["jql"]:  # сырьё трудозатрат: задачи с полем worklog
            issues = [{"id": i["id"], "key": i["key"],
                       "fields": {"worklog": {"startAt": 0, "maxResults": 20, "total": len(WORKLOGS[i["key"]]),
                                              "worklogs": WORKLOGS[i["key"]][:20]}}}
                      for i in ISSUES if i["key"] in WORKLOGS]
            return 200, {"issues": issues, "startAt": 0, "maxResults": 100, "total": len(issues)}
        return 200, {"issues": ISSUES, "startAt": 0, "maxResults": 100, "total": len(ISSUES)}

    server.route("POST", "/rest/api/2/search", search)
    server.route("GET", "/rest/api/2/issue/COP-180/worklog",
                 lambda req: (200, {"startAt": 20, "maxResults": 50,
                                    "total": len(WORKLOGS["COP-180"]),
                                    "worklogs": WORKLOGS["COP-180"][20:]}))
    return server


def make(server) -> JiraConnector:
    return JiraConnector({"base_url": server.url, "instance": "server", "login": "svc",
                          "raw_issue_days": 90, "raw_worklog_days": 180},
                         {"token": "token"})


def test_raw_projects_upsert(db):
    server = make_server()
    with server:
        run = make(server).run("raw_projects", RunContext(db=db))
        assert run.status == "ok" and run.counters == {"projects": 2, "created": 2, "updated": 0}
        run = make(server).run("raw_projects", RunContext(db=db))
        assert run.counters["created"] == 0 and run.counters["updated"] == 0
    row = db.get(JiraProject, 101)
    assert row.key == "COP" and row.lead == "Юрасов А.В."


def test_raw_issues_fields_and_idempotency(db):
    server = make_server()
    with server:
        run = make(server).run("raw_issues", RunContext(db=db))
        assert run.counters == {"issues": 2, "created": 2, "updated": 0}
        run = make(server).run("raw_issues", RunContext(db=db))
        assert run.counters["created"] == 0 and run.counters["updated"] == 2
    done = db.get(JiraIssue, 9001)
    assert done.assignee_email == "ivanov@almi-partner.ru" and done.timespent_seconds == 14400
    assert done.resolved is not None and done.jira_created is not None
    empty = db.get(JiraIssue, 9002)
    assert empty.assignee_email == "" and empty.priority == "" and empty.resolved is None


def test_raw_worklogs_full_pages_and_upsert(db):
    server = make_server()
    with server:
        run = make(server).run("raw_worklogs", RunContext(db=db))
        # 22 записи: 20 из поиска + страница /worklog
        assert run.counters["worklogs"] == 22 and run.counters["issues"] == 1
        run = make(server).run("raw_worklogs", RunContext(db=db))
        assert run.counters["created"] == 0 and run.counters["updated"] == 22
    from sqlalchemy import select
    rows = list(db.scalars(select(JiraWorklog)))
    assert len(rows) == 22
    sample = rows[0]
    assert sample.author_email == "ivanov@almi-partner.ru" and sample.time_spent_seconds == 3600
