"""Коннектор GitLab (ADR-0012, этап 1): проверка, справочник проектов, агрегаты коммитов и
пайплайнов, мерж-реквесты с ключами Jira — против поддельного сервера (FakeServer).

Реальный инстанс — https://gitlab.almi-partner.ru (self-managed, API v4): проверен read-only
пробами 2026-11-21; в тестах — те же формы ответов (пагинация X-Next-Page, with_stats).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.integrations.connectors.gitlab import GitlabConnector
from app.integrations.runner import RunContext
from app.models import GitlabCommitDay, GitlabMergeRequest, GitlabPipelineDay, GitlabProject
from tests.fake_http import FakeServer


def make(server, **config):
    return GitlabConnector({"base_url": server.url, "window_days": 30, **config},
                           {"token": "glpat-test"})


def routes(server, projects, commits=None, mrs=None, pipelines=None):
    def project_list(req):
        page = int(req.query.get("page", ["1"])[0])
        chunk = projects[(page - 1) * 1:(page) * 1]  # по одному на страницу — проверяем пагинацию
        headers = {"X-Next-Page": str(page + 1) if page < len(projects) else "",
                   "X-Total": str(len(projects))}
        return 200, chunk, headers

    server.route("GET", "/api/v4/user", lambda req: (200, {"username": "svc-dashboard", "email": "svc@x"}))
    server.route("GET", "/api/v4/version", lambda req: (200, {"version": "16.10.1"}))
    server.route("GET", "/api/v4/projects", project_list)
    for p in projects:
        pid = p["id"]
        if commits is not None:
            server.route("GET", f"/api/v4/projects/{pid}/repository/commits",
                         lambda req, c=commits.get(pid, []): (200, c, {"X-Next-Page": ""}))
        if mrs is not None:
            server.route("GET", f"/api/v4/projects/{pid}/merge_requests",
                         lambda req, m=mrs.get(pid, []): (200, m, {"X-Next-Page": ""}))
        if pipelines is not None:
            server.route("GET", f"/api/v4/projects/{pid}/pipelines",
                         lambda req, pl=pipelines.get(pid, []): (200, pl, {"X-Next-Page": ""}))


PROJECTS = [
    {"id": 21, "name": "Дашборды", "path_with_namespace": "dev/dashboards",
     "namespace": {"path": "dev"}, "web_url": "https://git/dev/dashboards", "default_branch": "main",
     "archived": False, "last_activity_at": "2026-11-20T10:00:00Z", "visibility": "private"},
    {"id": 22, "name": "Инфра", "path_with_namespace": "ops/infra",
     "namespace": {"path": "ops"}, "web_url": "https://git/ops/infra", "default_branch": "master",
     "archived": False, "last_activity_at": "2026-11-19T10:00:00Z", "visibility": "internal"},
]
COMMITS = {
    21: [
        {"id": "a1", "author_email": "Ivanov@almi-partner.ru", "committed_date": "2026-11-18T12:00:00Z",
         "stats": {"additions": 10, "deletions": 2}},
        {"id": "a2", "author_email": "ivanov@almi-partner.ru", "committed_date": "2026-11-18T15:00:00Z",
         "stats": {"additions": 5, "deletions": 0}},
        {"id": "a3", "author_email": "petrov@almi-partner.ru", "committed_date": "2026-11-19T09:00:00Z",
         "stats": {"additions": 1, "deletions": 9}},
    ],
    22: [],
}
MRS = {
    21: [
        {"iid": 7, "title": "COP-180: спарклайны", "state": "merged", "source_branch": "feature/COP-180",
         "target_branch": "main", "author": {"email": "Ivanov@almi-partner.ru"},
         "created_at": "2026-11-15T10:00:00Z", "merged_at": "2026-11-18T12:00:00Z", "closed_at": None,
         "reviewers": [{"username": "petrov"}, {"username": "sidorov"}]},
        {"iid": 8, "title": "правки без задачи", "state": "opened", "source_branch": "fix",
         "target_branch": "main", "author": {"email": "petrov@almi-partner.ru"},
         "created_at": "2026-11-19T10:00:00Z", "merged_at": None, "closed_at": None, "reviewers": []},
    ],
}
PIPELINES = {
    21: [
        {"id": 1, "status": "success", "updated_at": "2026-11-18T12:10:00Z"},
        {"id": 2, "status": "success", "updated_at": "2026-11-18T15:20:00Z"},
        {"id": 3, "status": "failed", "updated_at": "2026-11-19T09:05:00Z"},
    ],
}


def test_check_reports_version_user_and_total(db):
    server = FakeServer()
    routes(server, PROJECTS)
    with server:
        result = make(server).check()
    assert result.ok and "16.10.1" in result.message and "svc-dashboard" in result.message
    assert result.details["projects_total"] == 2  # по одному на страницу — пагинация прочитана


def test_projects_upsert_and_group_filter(db):
    server = FakeServer()
    routes(server, PROJECTS)
    with server:
        run = make(server).run("projects", RunContext(db=db))
        assert run.status == "ok" and run.counters == {"projects": 2, "created": 2, "updated": 0}
        # повтор — идемпотентно; фильтр по группе оставляет одну
        run = make(server).run("projects", RunContext(db=db))
        assert run.counters["created"] == 0 and run.counters["updated"] == 0
        run = make(server, group="dev").run("projects", RunContext(db=db))
        assert run.counters["projects"] == 1
    assert db.scalar(select(GitlabProject.path_with_namespace).where(GitlabProject.id == 21)) == "dev/dashboards"


def test_commits_daily_aggregate_normalizes_email(db):
    server = FakeServer()
    routes(server, PROJECTS, commits=COMMITS)
    with server:
        make(server).run("projects", RunContext(db=db))  # справочник — сначала
        run = make(server).run("commits", RunContext(db=db))
    assert run.status == "ok" and run.counters["commit_rows"] == 2  # 3 коммита → 2 строки (два ivanov одного дня слиты)
    row = db.scalar(select(GitlabCommitDay).where(GitlabCommitDay.author_email == "ivanov@almi-partner.ru",
                                                    GitlabCommitDay.day == date(2026, 11, 18)))
    assert row.commits == 2 and row.additions == 15 and row.deletions == 2  # два коммита одного дня слиты


def test_merge_requests_jira_keys_and_upsert(db):
    server = FakeServer()
    routes(server, PROJECTS, mrs=MRS)
    with server:
        make(server).run("projects", RunContext(db=db))
        run = make(server).run("merge_requests", RunContext(db=db))
        assert run.counters["created"] == 2
        run = make(server).run("merge_requests", RunContext(db=db))
        assert run.counters["created"] == 0 and run.counters["updated"] == 2
    mr = db.scalar(select(GitlabMergeRequest).where(GitlabMergeRequest.iid == 7))
    assert mr.jira_keys == ["COP-180"]  # ключ из названия и ветки — один и тот же
    assert mr.author_email == "ivanov@almi-partner.ru" and mr.reviewers == ["petrov", "sidorov"]
    bare = db.scalar(select(GitlabMergeRequest).where(GitlabMergeRequest.iid == 8))
    assert bare.jira_keys == [] and bare.gitlab_created_at is not None


def test_pipelines_daily_aggregate(db):
    server = FakeServer()
    routes(server, PROJECTS, pipelines=PIPELINES)
    with server:
        make(server).run("projects", RunContext(db=db))
        run = make(server).run("pipelines", RunContext(db=db))
    assert run.counters["pipeline_rows"] == 2  # 2 успеха одного дня слиты
    ok_day = db.scalar(select(GitlabPipelineDay).where(GitlabPipelineDay.status == "success",
                                                         GitlabPipelineDay.day == date(2026, 11, 18)))
    assert ok_day.count == 2
    failed = db.scalar(select(GitlabPipelineDay).where(GitlabPipelineDay.status == "failed"))
    assert failed.count == 1


def test_check_bad_token_raises_auth_error(db):
    """401 от GitLab — ошибка аутентификации с кодом auth (каркас превратит её в {ok: false})."""
    from app.integrations.http import IntegrationError

    server = FakeServer()
    server.route("GET", "/api/v4/user", lambda req: (401, {"message": "401 Unauthorized"}))
    server.route("GET", "/api/v4/version", lambda req: (200, {"version": "16.10.1"}))
    with server:
        try:
            make(server).check()
        except IntegrationError as error:
            assert error.code == "auth" and "401" in str(error)
        else:
            raise AssertionError("ожидали IntegrationError auth")
