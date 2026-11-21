"""GitLab (self-managed, API v4) — сырьё проектного офиса (ADR-0012, этап 1).

Только чтение: действия забирают проекты, коммиты (дневным агрегатом), мерж-реквесты и пайплайны
в таблицы `gitlab_*` окном перезаливки — метрики активности и ревью считаются из сырья службой
«Проектный офис» (этап 3). Токен с правом `read_api` — в секретах подключения; адрес ограничивается
`GITLAB_ALLOWED_HOSTS`. Пагинация — по заголовку `X-Next-Page` (по 100 записей).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import select

from ...core.db import utcnow
from ...models import GitlabCommitDay, GitlabMergeRequest, GitlabPipelineDay, GitlabProject
from ..base import Action, CheckResult, Connector, Field, RunContext, RunResult, register

JIRA_KEY = re.compile(r"\b([A-Z][A-Z0-9_]{1,9}-\d+)\b")
PER_PAGE = 100


def _parse_dt(value) -> datetime | None:
    """ISO-дата GitLab → наивный UTC: так хранит база (и сравнение при перезаливке работает)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


@register
class GitlabConnector(Connector):
    kind = "gitlab"
    title = "GitLab"
    description = ("Сырьё проектного офиса из собственного GitLab: проекты, активность коммитов "
                   "(день × автор × проект), мерж-реквесты с ревью и ключами задач Jira, пайплайны CI. "
                   "Только чтение (токен read_api); сырьё перезаливается окном")
    url_field = "base_url"
    order = 35
    fields = (
        Field("base_url", "Адрес GitLab", "url", required=True, placeholder="https://gitlab.company.ru"),
        Field("token", "Токен API", "password", required=True, secret=True,
              hint="Токен с правом read_api (область «Личные настройки → Токены доступа»)"),
        Field("group", "Группа-фильтр", hint="Путь группы (например dev) — только её проекты; пусто — все доступные"),
        Field("window_days", "Окно перезаливки, дней", "int", default=30, min=1, max=365,
              hint="Насколько назад забирать коммиты, мерж-реквесты и пайплайны при каждом запуске"),
        Field("verify_tls", "Проверять сертификат", "bool", default=True,
              hint="Отключите только для самоподписанного сертификата с пониманием риска"),
    )
    counter_labels = {"projects": "проектов", "created": "новых", "updated": "изменено",
                      "commit_rows": "строк агрегата коммитов", "mrs": "мерж-реквестов",
                      "pipeline_rows": "строк агрегата пайплайнов", "projects_seen": "проектов в охвате"}
    detail_labels = {"projects_total": "Проектов доступно"}  # version и user — общие подписи каркаса
    actions = (
        Action("projects", "Обновить проекты", "Справочник проектов GitLab — весь список (остальные действия "
                                               "работают по нему; запускайте первым)"),
        Action("commits", "Забрать коммиты", "Дневной агрегат коммитов за окно: день × автор × проект"),
        Action("merge_requests", "Забрать мерж-реквесты", "Мерж-реквесты за окно: статусы, авторы, ревьюеры, "
                                                          "ключи задач Jira из названия и ветки"),
        Action("pipelines", "Забрать пайплайны", "Дневной агрегат пайплайнов CI за окно: день × проект × статус"),
    )

    # ---------------------------------------------------------------- клиент и страницы

    def client(self):
        return self.http(headers={"PRIVATE-TOKEN": self.secrets.get("token") or ""})

    def _all_pages(self, client, path: str, params: dict | None = None) -> list[dict]:
        """Страницы по заголовку X-Next-Page (GitLab отдаёт его при per_page)."""
        out: list[dict] = []
        params = {**(params or {}), "per_page": str(PER_PAGE)}
        page = 1
        while True:
            resp = client.request("GET", path, params={**params, "page": str(page)})
            chunk = client.parse(resp, list)
            out.extend(chunk)
            nxt = resp.header("X-Next-Page")  # ключи заголовков приведены к нижнему регистру
            if not chunk or not nxt:
                return out
            page = int(nxt)

    def _known_projects(self, db) -> list[GitlabProject]:
        return list(db.scalars(select(GitlabProject).where(GitlabProject.archived.is_(False))
                               .order_by(GitlabProject.path_with_namespace)))

    def _window_start(self, ctx: RunContext) -> datetime:
        days = int(self.config.get("window_days") or 30)
        return utcnow().replace(tzinfo=None) - timedelta(days=min(max(days, 1), 365))

    # ---------------------------------------------------------------- проверка

    def check(self) -> CheckResult:
        with self.client() as client:
            user = client.get_json("api/v4/user")
            version = client.get_json("api/v4/version")
            # Лёгкая проба охвата: одна запись и общее число из заголовка X-Total
            resp = client.request("GET", "api/v4/projects", params={"membership": "true", "per_page": "1"})
            client.parse(resp, list)
            total = resp.header("X-Total")
        return CheckResult(True, f"Подключено к GitLab {version.get('version', '?')} как {user.get('username')}",
                           {"version": version.get("version"), "user": user.get("username"),
                            "projects_total": int(total) if total.isdigit() else None},
                           [] if total.isdigit() else ["общее число проектов неизвестно — проверьте права токена"])

    # ---------------------------------------------------------------- действия

    def run(self, action: str, ctx: RunContext) -> RunResult:
        self.action(action)
        with self.client() as client:
            if action == "projects":
                return self._run_projects(client, ctx.db)
            since = self._window_start(ctx).isoformat()
            if action == "commits":
                return self._run_commits(client, ctx.db, since)
            if action == "merge_requests":
                return self._run_merge_requests(client, ctx.db, since)
            return self._run_pipelines(client, ctx.db, since)

    def _run_projects(self, client, db) -> RunResult:
        raw = self._all_pages(client, "api/v4/projects", {"membership": "true"})
        if group := (self.config.get("group") or "").strip():
            raw = [p for p in raw if p.get("path_with_namespace", "").startswith(f"{group}/")]
        created = updated = 0
        for p in raw:
            row = db.get(GitlabProject, p["id"])
            values = dict(path_with_namespace=p.get("path_with_namespace", ""), name=p.get("name", ""),
                          namespace=(p.get("namespace") or {}).get("path", ""), web_url=p.get("web_url", ""),
                          default_branch=p.get("default_branch") or "", archived=bool(p.get("archived")),
                          last_activity_at=_parse_dt(p.get("last_activity_at")),
                          visibility=p.get("visibility") or "")
            if row is None:
                db.add(GitlabProject(id=p["id"], **values))
                created += 1
            else:
                if any(getattr(row, k) != v for k, v in values.items()):
                    for k, v in values.items():
                        setattr(row, k, v)
                    updated += 1
        db.commit()
        return RunResult.ok(f"Проектов: {len(raw)} (новых {created}, изменено {updated})",
                            counters={"projects": len(raw), "created": created, "updated": updated})

    def _run_commits(self, client, db, since: str) -> RunResult:
        agg: dict[tuple, list[int]] = {}
        projects = self._known_projects(db)
        for project in projects:
            commits = self._all_pages(client, f"api/v4/projects/{project.id}/repository/commits",
                                      {"since": since, "with_stats": "true"})
            for c in commits:
                committed = _parse_dt(c.get("committed_date") or c.get("created_at"))
                author = (c.get("author_email") or c.get("committer_email") or "").strip().lower()
                if committed is None or not author:
                    continue
                stats = c.get("stats") or {}
                slot = agg.setdefault((committed.date(), author, project.id), [0, 0, 0])
                slot[0] += 1
                slot[1] += int(stats.get("additions") or 0)
                slot[2] += int(stats.get("deletions") or 0)
        created = updated = 0
        for (day, author, project_id), (count, additions, deletions) in agg.items():
            row = db.scalar(select(GitlabCommitDay).where(GitlabCommitDay.day == day,
                                                          GitlabCommitDay.author_email == author,
                                                          GitlabCommitDay.project_id == project_id))
            if row is None:
                db.add(GitlabCommitDay(day=day, author_email=author, project_id=project_id,
                                       commits=count, additions=additions, deletions=deletions))
                created += 1
            else:
                row.commits, row.additions, row.deletions = count, additions, deletions
                updated += 1
        db.commit()
        return RunResult.ok(f"Коммиты: {len(agg)} строк агрегата за окно (новых {created}, обновлено {updated})",
                            counters={"commit_rows": len(agg), "created": created, "updated": updated,
                                      "projects_seen": len(projects)})

    def _run_merge_requests(self, client, db, since: str) -> RunResult:
        created = updated = 0
        projects = self._known_projects(db)
        for project in projects:
            mrs = self._all_pages(client, f"api/v4/projects/{project.id}/merge_requests",
                                  {"updated_after": since})
            for m in mrs:
                row = db.scalar(select(GitlabMergeRequest).where(GitlabMergeRequest.project_id == project.id,
                                                                 GitlabMergeRequest.iid == m["iid"]))
                author = ((m.get("author") or {}).get("email") or "").strip().lower()
                keys = sorted(set(JIRA_KEY.findall(f"{m.get('title', '')} {m.get('source_branch', '')}")))
                values = dict(title=m.get("title", ""), state=m.get("state", "opened"), author_email=author,
                              source_branch=m.get("source_branch", ""), target_branch=m.get("target_branch", ""),
                              gitlab_created_at=_parse_dt(m.get("created_at")), merged_at=_parse_dt(m.get("merged_at")),
                              closed_at=_parse_dt(m.get("closed_at")),
                              reviewers=[r.get("username") for r in (m.get("reviewers") or []) if r.get("username")],
                              jira_keys=keys)
                if row is None:
                    db.add(GitlabMergeRequest(project_id=project.id, iid=m["iid"], **values))
                    created += 1
                else:
                    for k, v in values.items():
                        setattr(row, k, v)
                    updated += 1
        db.commit()
        return RunResult.ok(f"Мерж-реквесты: новых {created}, обновлено {updated}",
                            counters={"mrs": created + updated, "created": created, "updated": updated,
                                      "projects_seen": len(projects)})

    def _run_pipelines(self, client, db, since: str) -> RunResult:
        agg: dict[tuple, int] = {}
        projects = self._known_projects(db)
        for project in projects:
            pipelines = self._all_pages(client, f"api/v4/projects/{project.id}/pipelines",
                                        {"updated_after": since})
            for p in pipelines:
                finished = _parse_dt(p.get("updated_at"))
                if finished is None:
                    continue
                key = (finished.date(), project.id, p.get("status") or "")
                agg[key] = agg.get(key, 0) + 1
        created = updated = 0
        for (day, project_id, status), count in agg.items():
            row = db.scalar(select(GitlabPipelineDay).where(GitlabPipelineDay.day == day,
                                                            GitlabPipelineDay.project_id == project_id,
                                                            GitlabPipelineDay.status == status))
            if row is None:
                db.add(GitlabPipelineDay(day=day, project_id=project_id, status=status, count=count))
                created += 1
            else:
                row.count = count
                updated += 1
        db.commit()
        return RunResult.ok(f"Пайплайны: {len(agg)} строк агрегата (новых {created}, обновлено {updated})",
                            counters={"pipeline_rows": len(agg), "created": created, "updated": updated,
                                      "projects_seen": len(projects)})
