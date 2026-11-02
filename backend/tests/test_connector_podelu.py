"""Коннектор «По Делу» против поддельной «По Делу» (настоящий HTTP-сервер в потоке).

Ключ интеграции («По Делу» 1.4.5, /api/integrations/v1): Bearer без cookie, области ключа, отзыв, списки ключа,
курсор activityAt и листание nextCursor, hasAttachments/updatedSince, sha256 файлов, комментарии системы
и comments_disabled, предел частоты 429, старая «По Делу» без API ключей (404), ключ не попадает наружу.
Служебная учётная запись («По Делу» до 1.4.5): вход (CSRF, Referer, Origin, cookie, выход всегда), проверка прав
и списка, синхронизация структуры и сотрудников через движки «Дашбордов» (сопоставление по id «По Делу» и email,
«Без доступа», роли не переносятся, правила «Входящих»), данные из вложений задач (курсор, повторы, файлы
результатов, комментарий-отметка), ошибки и секреты."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets as pysecrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.models import Department, InboxItem, InboxRule, Integration, User
from app.services import inbox
from tests.conftest import assert_counters_labelled
from tests.fake_http import FakeServer, Request
from tests.test_inbox import csv_bytes, tp_file

PASSWORD = "Пароль-служебной-42"
COOKIE = "todo_planner_session"
KEY = "podelu_" + "Kd7xQ2" * 7
V1 = "/api/integrations/v1"
ALL_SCOPES = ["org.read", "users.read", "tasks.attachments.read", "tasks.comment"]
SCOPE_TITLES = {"org.read": "Структура компании", "users.read": "Сотрудники",
                "tasks.attachments.read": "Задачи и вложения", "tasks.comment": "Комментарии к задачам"}


def _now(offset: int = 0) -> str:
    return datetime(2026, 10, 20 + offset, 9, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z")


class FakePodelu:
    """Поддельная «По Делу»: сессии Flask (cookie + CSRF-токен в сессии), выгрузки, списки, задачи, вложения."""

    def __init__(self, server: FakeServer):
        self.server = server
        self.account = {"id": "u-svc", "login": "svc", "password": PASSWORD, "name": "Синхронизация дашбордов",
                        "email": "svc@company.ru", "globalRole": "user", "isActive": True,
                        "capabilities": ["org.manage", "users.manage"]}
        self.sessions: dict[str, dict] = {}
        self.logins = self.logouts = 0
        self.break_csrf = False
        self.secure_cookie = False
        self.comment_status = 201
        self.content_status = 200
        self.comments: list[tuple[str, str]] = []
        self.departments = [
            {"key": "d-root", "name": "АЛМИ Партнер", "parent": None, "kind": "company", "sortOrder": 0,
             "externalId": None, "heads": []},
            {"key": "d-proj", "name": "Проектная служба", "parent": "d-root", "kind": "service", "sortOrder": 7,
             "externalId": None, "heads": [{"email": "pm@company.ru", "primary": True}]},
            {"key": "d-impl", "name": "Офис внедрения", "parent": "d-proj", "kind": "department", "sortOrder": 1,
             "externalId": "1C-77", "heads": []},
            {"key": "d-team", "name": "Команда X", "parent": "d-root", "kind": "team", "sortOrder": 9,
             "externalId": None, "heads": []},
        ]
        self.employees = [
            {"email": "pm@company.ru", "login": "petrov", "name": "Петров Пётр", "position": "Руководитель офиса",
             "department": ["АЛМИ Партнер", "Проектная служба"], "manager": "", "reportsToNone": False,
             "heads": [{"department": ["АЛМИ Партнер", "Проектная служба"], "primary": True}],
             "functionalManagers": [], "role": "admin", "capabilities": ["users.manage"], "timezone": "Europe/Moscow",
             "isActive": True, "visibilityScope": "", "authSource": "local", "externalId": ""},
            {"email": "ivanova@company.ru", "login": "ivanova", "name": "Иванова Анна", "position": "Аналитик",
             "department": ["АЛМИ Партнер", "Проектная служба", "Офис внедрения"], "manager": "pm@company.ru",
             "reportsToNone": False, "heads": [], "role": "user", "capabilities": [], "isActive": True,
             "externalId": ""},
            {"email": "product@company.ru", "login": "product", "name": "Продуктов Павел", "position": "Продакт",
             "department": ["АЛМИ Партнер", "Проектная служба"], "manager": "", "heads": [], "role": "user",
             "capabilities": [], "isActive": True, "externalId": ""},
            {"email": "svc@company.ru", "login": "svc", "name": "Синхронизация дашбордов", "position": "",
             "department": [], "manager": "", "heads": [], "role": "user", "isActive": True, "externalId": ""},
        ]
        self.people = [{"id": "p-pm", "email": "pm@company.ru", "name": "Петров Пётр", "isSystem": False},
                       {"id": "p-iv", "email": "ivanova@company.ru", "name": "Иванова Анна", "isSystem": False},
                       {"id": "p-prod", "email": "product@company.ru", "name": "Продуктов Павел", "isSystem": False},
                       {"id": "u-svc", "email": "svc@company.ru", "name": "Синхронизация дашбордов",
                        "isSystem": False}]
        self.lists = [{"id": "L1", "title": "Данные для дашбордов", "settings": {}},
                      {"id": "L2", "title": "Прочее", "settings": {}}]
        self.tasks: dict[str, dict] = {}
        self.files: dict[str, list[dict]] = {}
        self.results: dict[str, list[dict]] = {}
        # API ключей интеграций (1.4.5): ключи систем, версия, предел частоты (budget — сколько запросов v1 ещё
        # до 429), часы активности задач (файл и комментарий сдвигают activityAt, а не updatedAt)
        self.version = "1.4.5"
        self.keys = {KEY: {"name": "Дашборды", "app": "dashboards", "scopes": list(ALL_SCOPES), "listIds": ["L1"],
                           "revoked": False}}
        self.budget: int | None = None
        self.clock = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
        for method, path, handler in (
            ("GET", f"{V1}/ping", self.v1(self.v1_ping)),
            ("GET", f"{V1}/org/export", self.v1(self.v1_org, "org.read")),
            ("GET", f"{V1}/users/export", self.v1(self.v1_users, "users.read")),
            ("GET", f"{V1}/tasks", self.v1(self.v1_tasks, "tasks.attachments.read")),
        ):
            server.route(method, path, handler)
        for method, path, handler in (
            ("GET", "/api/auth/csrf-token", self.csrf_token), ("POST", "/api/auth/login", self.login),
            ("POST", "/api/auth/logout", self.logout), ("GET", "/api/org/export", self.org_export),
            ("GET", "/api/users/export", self.users_export), ("GET", "/api/users/admin/all", self.admin_all),
            ("GET", "/api/lists", self.list_lists), ("GET", "/api/v2/tasks", self.v2_tasks),
        ):
            server.route(method, path, handler)
        for person in self.people:
            server.route("GET", f"/api/users/{person['id']}", self.guarded(lambda r, p=person: (200, p)))

    # --- сессия
    def sid(self, request: Request) -> str | None:
        for part in (request.headers.get("cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE and value in self.sessions:
                return value
        return None

    def cookie(self, sid: str) -> dict:
        return {"Set-Cookie": f"{COOKIE}={sid}; Path=/; HttpOnly" + ("; Secure" if self.secure_cookie else "")}

    def csrf_ok(self, request: Request) -> tuple[str | None, tuple | None]:
        sid = self.sid(request)
        token = request.headers.get("x-csrf-token")
        if sid is None or self.break_csrf or token != self.sessions[sid]["csrf"]:
            return sid, (400, {"error": "csrf_error", "message": "The CSRF token is missing."})
        return sid, None

    def csrf_token(self, request: Request):
        sid = self.sid(request)
        if sid is None:
            sid = pysecrets.token_hex(8)
            self.sessions[sid] = {"csrf": pysecrets.token_hex(8), "user": None}
        return 200, {"csrfToken": self.sessions[sid]["csrf"]}, self.cookie(sid)

    def login(self, request: Request):
        sid, error = self.csrf_ok(request)
        if error:
            return error
        assert request.headers.get("referer") == self.server.url + "/"
        assert request.headers.get("origin") == self.server.url
        body = request.json()
        if body.get("login") != self.account["login"] or body.get("password") != self.account["password"]:
            return 401, {"error": "invalid_credentials", "message": "Неверный login или пароль"}
        if not self.account["isActive"]:
            return 403, {"error": "account_disabled", "message": "Аккаунт деактивирован"}
        session = self.sessions.pop(sid)
        new = pysecrets.token_hex(8)        # новый id сессии при входе (как regenerate_session)
        self.sessions[new] = {**session, "user": self.account["login"]}
        self.logins += 1
        user = {k: v for k, v in self.account.items() if k != "password"}
        return 200, {"user": user}, self.cookie(new)

    def logout(self, request: Request):
        sid, error = self.csrf_ok(request)
        if error:
            return error
        self.sessions[sid]["user"] = None
        self.logouts += 1
        return 200, {"message": "logged_out"}

    def guarded(self, handler, *rights):
        def wrapper(request: Request):
            sid = self.sid(request)
            if sid is None or self.sessions[sid]["user"] is None:
                return 401, {"error": "auth_required", "message": "Требуется авторизация"}
            caps = self.account["capabilities"]
            if rights and self.account["globalRole"] != "admin" and not set(rights) & set(caps):
                return 403, {"error": "permission_denied", "message": "Недостаточно прав"}
            return handler(request)
        return wrapper

    # --- выгрузки
    def org_export(self, request):
        return self.guarded(lambda r: (200, {"format": "podelu.org-structure", "version": 1, "exportedAt": _now(),
                                             "app": "1.9.2", "settings": {"org_max_depth": 12},
                                             "departments": self.departments}), "org.manage")(request)

    def users_export(self, request):
        def handler(r):
            assert r.query.get("format") == ["json"]
            active = r.query.get("inactive") == ["0"]
            items = [e for e in self.employees if e["isActive"] or not active]
            return 200, {"format": "podelu.employees", "version": 1, "app": "1.9.2", "employees": items}
        return self.guarded(handler, "users.manage")(request)

    def admin_all(self, request):
        return self.guarded(lambda r: (200, self.people), "users.manage", "org.manage")(request)

    def list_lists(self, request):
        return self.guarded(lambda r: (200, self.lists))(request)

    # --- задачи
    def add_task(self, task_id: str, title: str, *, list_id: str = "L1", updated: str | None = None,
                 tags: tuple = (), created_by: str = "p-iv") -> dict:
        task = {"id": task_id, "listId": list_id, "title": title, "status": "open", "tags": list(tags),
                "attachmentCount": 0, "updatedAt": updated or _now(), "createdBy": created_by,
                "activityAt": updated or _now()}
        self.tasks[task_id] = task
        self.files[task_id] = []
        self.results[task_id] = []
        self.server.route("GET", f"/api/tasks/{task_id}/attachments",
                          self.guarded(lambda r: (200, [self.public(a) for a in self.files[task_id]])))
        self.server.route("GET", f"/api/tasks/{task_id}/results", self.guarded(
            lambda r: (200, [{**res, "attachments": [self.public(a) for a in res["attachments"]]}
                             for res in self.results[task_id]])))
        self.server.route("POST", f"/api/tasks/{task_id}/comments", lambda r: self.comment(r, task_id))
        self.server.route("GET", f"{V1}/tasks/{task_id}/attachments",
                          self.v1(lambda r, key: self.v1_attachments(key, task_id), "tasks.attachments.read"))
        self.server.route("POST", f"{V1}/tasks/{task_id}/comments",
                          self.v1(lambda r, key: self.v1_comment(r, key, task_id), "tasks.comment"))
        return task

    @staticmethod
    def public(att: dict) -> dict:
        return {k: v for k, v in att.items() if k != "_content"}

    def add_file(self, task_id: str, att_id: str, name: str, content: bytes, *, result: bool = False,
                 uploaded_by: str = "p-iv") -> None:
        att = {"id": att_id, "taskId": task_id, "noteId": None, "fileName": name,
               "mimeType": "application/octet-stream", "url": f"/api/tasks/{task_id}/attachments/{att_id}/content",
               "size": len(content), "uploadedBy": uploaded_by, "uploadedAt": _now(), "kind": "document",
               "_content": content}
        if result:
            if not self.results[task_id]:
                self.results[task_id].append({"id": f"r-{task_id}", "taskId": task_id, "text": "Готово",
                                              "attachments": []})
            self.results[task_id][0]["attachments"].append(att)
        else:
            self.files[task_id].append(att)
        self.tasks[task_id]["attachmentCount"] += 1   # загрузка вложения не меняет updatedAt — как в «По Делу»
        self.tasks[task_id]["activityAt"] = self.tick()  # …но с 1.4.5 сдвигает время последней активности

        def content_route(r, key=None):
            if self.content_status != 200:
                return self.content_status, {"error": "internal", "message": "Сбой хранилища"}
            if key is not None and (result or not self.open_to(key, task_id)):
                return 404, {"error": "not_found", "message": "Файл не найден"}
            return 200, content, {"ETag": f'"{hashlib.sha256(content).hexdigest()}"'}
        self.server.route("GET", f"/api/tasks/{task_id}/attachments/{att_id}/content", self.guarded(content_route))
        self.server.route("GET", f"{V1}/tasks/{task_id}/attachments/{att_id}/content",
                          self.v1(content_route, "tasks.attachments.read"))

    def v2_tasks(self, request):
        def handler(r):
            list_id = (r.query.get("listId") or [None])[0]
            tags = set(((r.query.get("tags") or [""])[0]).split(",")) - {""}
            size = int((r.query.get("pageSize") or ["50"])[0])
            start = int((r.query.get("cursor") or ["0"])[0])
            items = [t for t in self.tasks.values() if t["listId"] == list_id and (not tags or tags & set(t["tags"]))]
            items.sort(key=lambda t: t["updatedAt"], reverse=True)
            page = items[start:start + size]
            more = start + size < len(items)
            return 200, {"items": page, "nextCursor": str(start + size) if more else None, "hasMore": more,
                         "totalCount": len(items), "filteredCount": len(items)}
        return self.guarded(handler)(request)

    def comment(self, request, task_id):
        sid, error = self.csrf_ok(request)
        if error:
            return error
        if sid is None or self.sessions[sid]["user"] is None:
            return 401, {"error": "auth_required", "message": "Требуется авторизация"}
        if self.comment_status != 201:
            return self.comment_status, {"error": "permission_denied", "message": "Комментарии отключены владельцем "
                                                                                    "списка"}
        text = request.json().get("text")
        self.comments.append((task_id, text))
        self.tasks[task_id]["updatedAt"] = _now(5)  # комментарий меняет updatedAt (touch_activity)
        return 201, {"id": f"c{len(self.comments)}", "taskId": task_id, "text": text}

    # --- API ключей интеграций /api/integrations/v1 (1.4.5)
    def tick(self) -> str:
        self.clock += timedelta(minutes=1)
        return self.clock.isoformat().replace("+00:00", "Z")

    def v1(self, handler, scope: str | None = None):
        """Вход по ключу: Bearer без cookie, отзыв, область ключа, общий предел частоты (как в v1_routes.py)."""
        def wrapper(request: Request):
            assert "cookie" not in request.headers, "ключ интеграции — без cookie сессии"
            assert "x-csrf-token" not in request.headers, "и без CSRF-токена"
            if self.budget is not None:
                if self.budget <= 0:
                    return 429, {"error": "too_many_requests",
                                 "message": "Слишком много запросов по этому ключу — повторите позже"}, \
                        {"Retry-After": "0"}
                self.budget -= 1
            header = request.headers.get("authorization") or ""
            token = header[7:].strip() if header[:7].lower() == "bearer " else ""
            if not token.startswith("podelu_"):
                return 401, {"error": "unauthorized",
                             "message": "Нужен ключ «По Делу»: заголовок Authorization: Bearer podelu_…"}
            key = self.keys.get(token)
            if key is None:
                return 401, {"error": "unauthorized",
                             "message": "Неверный ключ «По Делу» — проверьте ключ или выпустите новый в «По Делу»"}
            if key["revoked"]:
                return 403, {"error": "key_revoked", "message": "Ключ отозван администратором «По Делу»"}
            if scope and scope not in key["scopes"]:
                return 403, {"error": "insufficient_scope",
                             "message": f"У ключа нет доступа «{SCOPE_TITLES[scope]}» (область {scope})"}
            return handler(request, key)
        return wrapper

    def key_lists(self, key: dict) -> list[str]:
        if not {"tasks.attachments.read", "tasks.comment"} & set(key["scopes"]):
            return []
        return [i for i in key["listIds"] if any(x["id"] == i for x in self.lists)]

    def open_to(self, key: dict, task_id: str) -> bool:
        return self.tasks[task_id]["listId"] in self.key_lists(key)

    def user_id(self, email: str) -> str | None:
        return next((p["id"] for p in self.people if p["email"] == email), None)

    def v1_ping(self, request, key):
        body = {"ok": True, "app": "podelu", "name": "По Делу", "version": self.version,
                "key": {"name": key["name"], "app": key["app"]},
                "scopes": [s for s in ALL_SCOPES if s in key["scopes"]]}
        if {"tasks.attachments.read", "tasks.comment"} & set(key["scopes"]):
            body["listIds"] = list(key["listIds"])
        return 200, body

    def v1_org(self, request, key):
        departments = [{**d, "heads": [{**h, "userId": self.user_id(h["email"])} for h in d["heads"]]}
                       for d in self.departments]
        return 200, {"format": "podelu.org-structure", "version": 1, "exportedAt": _now(), "app": self.version,
                     "settings": {"org_max_depth": 12}, "departments": departments}

    def v1_users(self, request, key):
        if (request.query.get("format") or ["json"])[0] != "json":
            return 400, {"error": "validation_error", "message": "format — только json"}
        active = (request.query.get("inactive") or ["1"])[0] == "0"
        items = [{"userId": self.user_id(e["email"]), **e} for e in self.employees if e["isActive"] or not active]
        return 200, {"format": "podelu.employees", "version": 1, "app": self.version, "employees": items}

    @staticmethod
    def cursor(task: dict) -> str:
        return base64.urlsafe_b64encode(f"{task['activityAt']}|{task['id']}".encode()).decode().rstrip("=")

    def v1_tasks(self, request, key):
        arg = {k: v[0] for k, v in request.query.items()}
        lists = self.key_lists(key)
        if arg.get("listId") and arg["listId"] not in lists:
            return 404, {"error": "not_found", "message": "Список не найден или не открыт этому ключу"}
        targets = [arg["listId"]] if arg.get("listId") else lists
        items = [t for t in self.tasks.values() if t["listId"] in targets]
        tags = [t for t in (arg.get("tags") or "").split(",") if t]
        items = [t for t in items if all(tag in t["tags"] for tag in tags)]
        if arg.get("hasAttachments") == "1":
            items = [t for t in items if self.files[t["id"]]]
        if arg.get("updatedSince"):
            items = [t for t in items if t["activityAt"] >= arg["updatedSince"]]
        if arg.get("cursor"):
            raw = arg["cursor"] + "=" * (-len(arg["cursor"]) % 4)
            stamp, task_id = base64.urlsafe_b64decode(raw).decode().split("|", 1)
            items = [t for t in items if (t["activityAt"], t["id"]) > (stamp, task_id)]
        items.sort(key=lambda t: (t["activityAt"], t["id"]))
        limit = min(500, int(arg.get("limit") or 100))
        page = items[:limit]
        titles = {x["id"]: x["title"] for x in self.lists}
        out = [{"id": t["id"], "listId": t["listId"], "listTitle": titles.get(t["listId"]), "parentTaskId": None,
                "title": t["title"], "status": t["status"], "priority": "normal", "tags": t["tags"],
                "assigneeId": None, "createdBy": t["createdBy"], "dueDate": None, "startDate": None,
                "createdAt": t["updatedAt"], "updatedAt": t["updatedAt"], "activityAt": t["activityAt"],
                "completedAt": None, "attachmentsCount": len(self.files[t["id"]])} for t in page]
        return 200, {"items": out, "nextCursor": self.cursor(page[-1]) if len(items) > limit else None}

    def v1_attachments(self, key, task_id):
        if not self.open_to(key, task_id):
            return 404, {"error": "not_found", "message": "Задача не найдена"}
        items = [{"id": a["id"], "fileName": a["fileName"], "mimeType": a["mimeType"], "size": a["size"],
                  "sha256": hashlib.sha256(a["_content"]).hexdigest(), "uploadedAt": a["uploadedAt"],
                  "uploadedBy": a["uploadedBy"] or None,
                  "contentPath": f"{V1}/tasks/{task_id}/attachments/{a['id']}/content"}
                 for a in self.files[task_id]]      # файлы результатов поручений API ключей не отдаёт
        return 200, {"taskId": task_id, "items": items}

    def v1_comment(self, request, key, task_id):
        if not self.open_to(key, task_id):
            return 404, {"error": "not_found", "message": "Задача не найдена"}
        settings = next(x for x in self.lists if x["id"] == self.tasks[task_id]["listId"])["settings"]
        if settings.get("allowComments") is False:
            return 403, {"error": "comments_disabled", "message": "Комментарии в этом списке отключены его владельцем"}
        if self.comment_status != 201:
            return self.comment_status, {"error": "internal_server_error", "message": "Внутренняя ошибка сервера"}
        text = request.json().get("text")
        self.comments.append((task_id, text))
        self.tasks[task_id]["activityAt"] = self.tick()   # комментарий — событие задачи (touch_activity)
        return 201, {"id": f"c{len(self.comments)}", "taskId": task_id, "text": text,
                     "createdAt": self.tasks[task_id]["activityAt"], "integrationName": key["name"]}


@pytest.fixture()
def fake(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.delenv("PODELU_ALLOWED_HOSTS", raising=False)
    server = FakeServer()
    podelu = FakePodelu(server)
    with server:
        yield podelu


def _create(admin, fake, **config) -> dict:
    body = {"kind": "podelu", "name": "По Делу",
            "config": {"base_url": fake.server.url, "login": "svc", "data_list": "Данные для дашбордов", **config},
            "secrets": {"password": PASSWORD}}
    response = admin.post("/api/integrations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _run(admin, item, action) -> dict:
    response = admin.post(f"/api/integrations/{item['id']}/run", json={"action": action})
    assert response.status_code == 200, response.text
    return assert_counters_labelled(response.json(), "podelu", unlabelled=("structure_item",))


def _rules(db, *datasets):
    for dataset in datasets:
        db.merge(InboxRule(source="integration", dataset=dataset, auto_apply=True))
    db.commit()


def _user(db, email):
    db.expire_all()
    return db.scalar(select(User).where(func.lower(User.email) == email))


# ---------------------------------------------------------------- описание и настройки

def test_kind_fields_and_secret_binding_fields(admin):
    kinds = {k["kind"]: k for k in admin.get("/api/integrations/kinds").json()}
    meta = kinds["podelu"]
    fields = {f["key"]: f for f in meta["fields"]}
    assert meta["title"] == "По Делу" and meta["allowed_hosts_env"] == "PODELU_ALLOWED_HOSTS"
    assert fields["password"]["secret"] and not fields["login"]["secret"]
    assert fields["deactivate_missing"]["default"] is False and fields["create_missing_units"]["default"] is True
    assert "secret_url" not in fields, "привязка пароля — механизм каркаса (secret_url), а не скрытое поле"
    assert meta["url_field"] == "base_url" and meta["secret_url_fields"] == ["base_url", "server_url"], \
        "форма предупреждает: смена любого из адресов требует ввести пароль заново"
    assert [a["key"] for a in meta["actions"]] == ["sync", "pull"]
    assert [a["label"] for a in meta["actions"]] == ["Синхронизировать структуру", "Забрать данные из задач"]
    from app.services import inbox_datasets

    labels = [inbox_datasets.get(k).label for k in ("structure", "employees")]
    assert f"наборы «{labels[0]}» и «{labels[1]}»" in meta["actions"][0]["description"], "подписи наборов — как есть"


def test_password_is_bound_to_both_addresses(admin, fake):
    item = _create(admin, fake, server_url=fake.server.url)
    assert item["config"]["server_url"] is None, "тот же адрес — не нужен"
    moved = admin.patch(f"/api/integrations/{item['id']}", json={"config": {"server_url": "http://10.0.0.5:5000"}})
    assert moved.status_code == 422 and moved.json()["code"] == "secret_rebind_required", \
        "пароль не уходит на новый адрес для запросов сервера без повторного ввода"
    rebound = admin.patch(f"/api/integrations/{item['id']}", json={"config": {"server_url": "http://10.0.0.5:5000"},
                                                                    "secrets": {"password": PASSWORD}}).json()
    assert rebound["secret_bound_url"] == f"{fake.server.url} → http://10.0.0.5:5000"
    assert "secret_url" not in rebound["config"] and rebound["secret_problem"] is None
    base = admin.patch(f"/api/integrations/{item['id']}", json={"config": {"base_url": "https://podelu.company.ru"}})
    assert base.status_code == 422 and base.json()["code"] == "secret_rebind_required", "и при смене основного адреса"
    # Настройка ранней сборки 0.4.0 (скрытое поле привязки) не мешает сохранить подключение
    db_config = {**rebound["config"], "secret_url": "устаревшее"}
    from app.core import db as core_db

    with core_db.SessionLocal() as session:
        session.execute(update(Integration).where(Integration.id == item["id"]).values(config=db_config))
        session.commit()
    renamed = admin.patch(f"/api/integrations/{item['id']}", json={"config": {"data_list": "L1"}})
    assert renamed.status_code == 200, renamed.text
    assert "secret_url" not in renamed.json()["config"] and renamed.json()["secret_problem"] is None


# ---------------------------------------------------------------- проверка

def test_check_logs_in_reads_version_rights_lists_and_logs_out(admin, fake):
    item = _create(admin, fake)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"], check
    assert check["message"].startswith("Подключено к «По Делу» 1.9.2 как Синхронизация дашбордов")
    assert "подразделений: 4" in check["message"] and "список «Данные для дашбордов»" in check["message"]
    details = check["details"]
    assert details["lists"] == [{"id": "L1", "title": "Данные для дашбордов"}, {"id": "L2", "title": "Прочее"}]
    assert details["data_list"] == {"id": "L1", "title": "Данные для дашбордов", "comments": True}
    assert details["capabilities"] == ["org.manage", "users.manage"] and details["missing"] == []
    assert fake.logins == 1 and fake.logouts == 1
    login = next(r for r in fake.server.requests if r.path == "/api/auth/login")
    assert login.headers["x-csrf-token"] and login.headers["referer"] == fake.server.url + "/"
    logout = next(r for r in fake.server.requests if r.path == "/api/auth/logout")
    assert logout.headers["x-csrf-token"] == login.headers["x-csrf-token"]
    assert PASSWORD not in json.dumps(check, ensure_ascii=False)


def test_check_reports_exactly_what_is_missing(admin, fake):
    fake.account["capabilities"] = ["org.manage"]
    item = _create(admin, fake, data_list="Закрытый список")
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"]
    assert "не хватает: полномочие «Ведёт учётные записи» (users.manage); доступ к списку «Закрытый список»" \
        in check["message"]
    assert check["details"]["missing"][0] == "полномочие «Ведёт учётные записи» (users.manage)"
    assert fake.logouts == 1
    fake.account["capabilities"] = []
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert "«Ведёт структуру компании» (org.manage)" in check["message"]


def test_check_admin_account_and_disabled_comments_are_warnings(admin, fake):
    fake.account.update(globalRole="admin", capabilities=[])
    fake.lists[0]["settings"] = {"allowComments": False}
    item = _create(admin, fake)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"] and "выключены комментарии" in check["message"] and "администратор «По Делу»" in check["message"]


def test_check_wrong_password_still_logs_out(admin, fake):
    item = _create(admin, fake)
    admin.patch(f"/api/integrations/{item['id']}", json={"secrets": {"password": "не тот"}})
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["details"]["code"] == "auth"
    assert check["message"] == "«По Делу» отклонила вход: неверный логин или пароль служебной учётной записи"
    assert fake.logins == 0 and fake.logouts == 1, "сессия с CSRF-токеном закрывается и после ошибки входа"


def test_check_csrf_rejection_and_secure_cookie_over_http(admin, fake):
    item = _create(admin, fake)
    fake.break_csrf = True
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["details"]["code"] == "csrf" and "CSRF" in check["message"]
    fake.break_csrf = False
    fake.secure_cookie = True
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and "только для HTTPS" in check["message"]


def test_check_network_error_and_disabled_account(admin, fake):
    down = admin.post("/api/integrations/check", json={"kind": "podelu", "config": {"base_url": "http://127.0.0.1:9",
                                                                                     "login": "svc"},
                                                       "secrets": {"password": PASSWORD}}).json()
    assert not down["ok"] and "Не удалось подключиться к http://127.0.0.1:9" in down["message"]
    fake.account["isActive"] = False
    item = _create(admin, fake)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["message"] == "Служебная учётная запись отключена в «По Делу»"


def test_requests_go_to_server_url(admin, fake):
    item = _create(admin, fake, base_url="https://podelu.example.ru", server_url=fake.server.url)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"], check["message"]


# ---------------------------------------------------------------- структура и сотрудники

def test_sync_applies_structure_and_employees(admin, fake, db):
    db.execute(update(User).where(User.username == "product").values(email="product@company.ru"))
    db.commit()
    _rules(db, "structure", "employees")
    item = _create(admin, fake)
    run = _run(admin, item, "sync")
    assert run["status"] == "ok", run
    summary = run["summary"]
    assert summary["structure_create"] == 2 and summary["users_create"] == 2 and summary["users_update"] == 1
    assert run["message"].startswith("Структура: создать 2, изменить 1, руководителей 0 — применено (элемент входящих")
    assert "Сотрудники: создано 2, изменено 1" in run["message"]
    assert any("«team» не заданы" in n for n in summary["details"]["notes"])
    structure = db.get(InboxItem, summary["structure_item"])
    assert structure.dataset == "structure" and structure.status == "applied" and structure.source_ref.startswith(
        "podelu:org-structure:")
    impl = db.scalar(select(Department).where(Department.name == "Офис внедрения"))
    team = db.scalar(select(Department).where(Department.name == "Команда X"))
    assert impl.external_id == "d-impl" and db.get(Department, impl.parent_id).name == "Проектная служба"
    assert team.kind == "department"
    pm = _user(db, "pm@company.ru")
    assert pm.org_source == "podelu" and pm.external_id == "p-pm" and pm.password_hash is None
    assert pm.role == "user" and not pm.is_admin, "роль администратора из «По Делу» не переносится"
    assert pm.department.name == "Проектная служба" and pm.username == "petrov"
    from app.services.users import user_status

    assert user_status(pm) == "no_access", "новые — «Без доступа»"
    ivanova = _user(db, "ivanova@company.ru")
    assert ivanova.department_id == impl.id and ivanova.external_id == "p-iv"
    product = db.scalar(select(User).where(User.username == "product"))
    assert product.org_source == "podelu" and product.external_id == "p-prod" and product.full_name == "Продуктов Павел"
    assert _user(db, "svc@company.ru") is None, "служебная учётная запись не синхронизируется как сотрудник"
    from app.services import org

    snap = org.build_snapshot(db)
    assert pm.id in snap.heads[pm.department_id], "руководитель подразделения — из «По Делу»"
    assert fake.logins == 1 and fake.logouts == 1
    again = _run(admin, item, "sync")
    assert again["status"] == "ok" and again["message"].startswith("Структура: без изменений")
    assert again["summary"]["users_create"] == 0 and again["summary"]["users_update"] == 0
    assert db.scalar(select(func.count()).select_from(InboxItem).where(InboxItem.dataset == "structure")) == 1


def test_sync_waits_for_rules(admin, fake, db, login):
    item = _create(admin, fake)
    run = _run(admin, item, "sync")
    assert run["status"] == "ok"
    assert "ожидает подтверждения на экране «Входящие»" in run["message"]
    assert "Сотрудники: план — создать 3" in run["message"] and "сначала примените структуру" in run["message"]
    assert _user(db, "pm@company.ru") is None
    again = _run(admin, item, "sync")
    assert "уже ожидает решения" in again["message"], "повторный запуск не плодит одинаковые элементы"
    assert db.scalar(select(func.count()).select_from(InboxItem).where(InboxItem.dataset == "structure")) == 1
    pending = run["summary"]["structure_item"]
    assert admin.post(f"/api/inbox/{pending}/apply").status_code == 200
    third = _run(admin, item, "sync")
    assert "для источника «Подключение» и набора «Сотрудники» не включено «применять сразу»" in third["message"]
    _rules(db, "employees")
    fourth = _run(admin, item, "sync")
    assert "Сотрудники: создано 3" in fourth["message"]
    assert _user(db, "pm@company.ru").org_source == "podelu"


def test_sync_matches_by_podelu_id_when_email_changes(admin, fake, db):
    _rules(db, "structure", "employees")
    item = _create(admin, fake)
    _run(admin, item, "sync")
    users_before = db.scalar(select(func.count()).select_from(User))
    fake.employees[0].update(email="petrov@company.ru", position="Директор проектов")
    fake.people[0]["email"] = "petrov@company.ru"
    run = _run(admin, item, "sync")
    assert run["status"] == "ok" and run["summary"]["users_create"] == 0 and run["summary"]["users_update"] == 1
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(User)) == users_before
    pm = db.scalar(select(User).where(User.external_id == "p-pm"))
    assert pm.position == "Директор проектов"


def test_sync_without_creating_units(admin, fake, db):
    _rules(db, "structure", "employees")
    item = _create(admin, fake, create_missing_units=False)
    run = _run(admin, item, "sync")
    assert run["status"] == "partial", "сотрудник нового подразделения пропущен"
    assert db.scalar(select(Department).where(Department.name == "Офис внедрения")) is None
    assert _user(db, "ivanova@company.ru") is None and _user(db, "pm@company.ru") is not None
    skipped = run["summary"]["details"]["employees"]["skipped"]
    assert skipped == ["Иванова Анна: подразделения «АЛМИ Партнер / Проектная служба / Офис внедрения» нет в "
                       "структуре — сотрудник не создаётся"]


def test_sync_deactivates_missing_podelu_employees_only(admin, fake, db):
    _rules(db, "structure", "employees")
    # Служебная учётная запись когда-то попала в «Дашборды» из «По Делу»; сотрудник из AD; сотрудник вручную
    db.add_all([
        User(username="svc", full_name="Синхронизация дашбордов", email="svc@company.ru", role="user", is_active=True,
             org_source="podelu", external_id="u-svc", auth_source="local", must_change_password=False),
        User(username="ad.user", full_name="Сотрудник из AD", email="ad.user@company.ru", role="user", is_active=True,
             org_source="ad", external_id="guid-1", auth_source="ldap", must_change_password=False),
    ])
    db.commit()
    item = _create(admin, fake, deactivate_missing=True)
    first = _run(admin, item, "sync")
    assert first["status"] == "ok" and first["summary"]["users_deactivate"] == 0
    assert "отключено" not in first["message"]
    fake.employees[1]["isActive"] = False      # Иванову отключили в «По Делу»: в выгрузке активных её нет
    run = _run(admin, item, "sync")
    assert run["status"] == "ok", run
    assert run["summary"]["users_deactivate"] == 1 and "отключено 1" in run["message"]
    assert not any("отключает только" in n for n in run["summary"]["details"].get("notes", [])), \
        "обходной заметки больше нет — движок отключает сам"
    assert _user(db, "ivanova@company.ru").is_active is False
    assert _user(db, "svc@company.ru").is_active, "служебная учётная запись подключения не отключается"
    assert _user(db, "ad.user@company.ru").is_active, "сотрудник из AD не отключается синхронизацией «По Делу»"
    assert db.scalar(select(User).where(User.username == "viewer")).is_active, "заведённые вручную — тоже"
    assert _user(db, "pm@company.ru").is_active and _user(db, "product@company.ru").is_active
    from app.models import AuditEntry

    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "user",
                                               AuditEntry.summary.like("Отключён сотрудник Иванова Анна%")))
    assert entry is not None and "нет среди активных в «По Делу»" in entry.summary


def test_sync_without_deactivate_missing_keeps_everyone(admin, fake, db):
    _rules(db, "structure", "employees")
    item = _create(admin, fake)
    _run(admin, item, "sync")
    fake.employees[1]["isActive"] = False
    run = _run(admin, item, "sync")
    assert run["summary"]["users_deactivate"] == 0 and _user(db, "ivanova@company.ru").is_active


def test_sync_missing_right_fails_and_logs_out(admin, fake, db):
    fake.account["capabilities"] = ["org.manage"]
    item = _create(admin, fake)
    run = _run(admin, item, "sync")
    assert run["status"] == "error" and "нет полномочий: «Ведёт учётные записи» (users.manage)" in run["error"]
    assert fake.logouts == 1
    fake.account["capabilities"] = ["org.manage", "users.manage"]
    fake.server.route("GET", "/api/users/export", lambda r: (403, {"error": "permission_denied", "message": "Нет"}))
    run = _run(admin, item, "sync")
    assert run["status"] == "error" and "нет права выгружать сотрудников" in run["error"]
    assert fake.logouts == 2, "выход — и после ошибки посреди работы"


def test_podelu_files_dropped_into_inbox_are_recognized(db, fake):
    # Форматы «По Делу» регистрирует модуль коннектора; распознавание само загружает коннекторы
    # (свежий процесс без обращения к подключениям — test_inbox.test_podelu_format_recognized_in_fresh_process)
    bundle = {"format": "podelu.org-structure", "version": 1, "exportedAt": _now(), "app": "1.9.2", "settings": {},
              "departments": [{"key": "a", "name": "АЛМИ Партнер", "parent": None, "kind": "company", "sortOrder": 0,
                               "heads": []}]}
    item = inbox.add(db, json.dumps(bundle).encode(), "podelu-structure.json", source="upload")
    assert item.dataset == "structure" and item.status == "pending" and item.plan_ok
    employees = {"format": "podelu.employees", "version": 1, "employees": [fake.employees[0]]}
    item = inbox.add(db, json.dumps(employees).encode(), "podelu-employees.json", source="upload")
    assert item.dataset == "employees" and item.plan_ok
    record = item.plan["records"][0]
    assert record["action"] == "create" and record["name"] == "Петров Пётр"


# ---------------------------------------------------------------- данные из задач

def _data_tasks(fake):
    fake.add_task("T1", "Недельный отчёт ТП", created_by="p-pm")
    fake.add_file("T1", "a1", "tp-week.xlsx", tp_file())
    fake.add_file("T1", "a2", "photo.png", b"\x89PNG....")
    fake.add_file("T1", "a3", "показатели.csv", csv_bytes([["Подразделение", "Показатель", "Период", "Значение"],
                                                           ["COMM", "fin.revenue", "2031-01", "61,5"]]), result=True)
    fake.add_task("T2", "Без файлов")
    fake.add_task("T3", "Чужой список", list_id="L2")
    fake.add_file("T3", "b1", "other.xlsx", tp_file())


def test_pull_takes_task_and_result_files_and_marks_task(admin, fake, db):
    _data_tasks(fake)
    _rules(db, "tp-weekly")
    item = _create(admin, fake)
    run = _run(admin, item, "pull")
    assert run["status"] == "ok", run
    summary = run["summary"]
    assert summary["candidates"] == 1 and summary["added"] == 2 and summary["skipped_type"] == 1
    assert summary["comments"] == 1 and summary["status_applied"] == 1 and summary["status_pending"] == 1
    assert run["message"].startswith("Список «Данные для дашбордов»: задач с новыми вложениями 1, файлов во "
                                     "«Входящие» 2")
    items = {i.filename: i for i in db.scalars(select(InboxItem).where(InboxItem.integration_id == item["id"]))}
    assert set(items) == {"tp-week.xlsx", "показатели.csv"}
    tp = items["tp-week.xlsx"]
    assert tp.status == "applied" and tp.source == "integration"
    assert tp.source_ref == f"podelu:T1:a1:{hashlib.sha256(tp_file()).hexdigest()}"
    assert items["показатели.csv"].dataset == "indicators" and items["показатели.csv"].status == "pending"
    assert fake.comments == [("T1", "Файл «tp-week.xlsx» принят в «Дашборды»: применён\n"
                                    "Файл «показатели.csv» принят в «Дашборды»: ожидает подтверждения")], \
        "без PUBLIC_URL — без ссылки"
    assert tp.note == "Задача «Недельный отчёт ТП» · Иванова Анна", "откуда файл — пояснением элемента"
    assert items["показатели.csv"].note == "Задача «Недельный отчёт ТП» · Иванова Анна"
    files = summary["details"]["files"]
    assert files[0] == {"item": tp.id, "file": "tp-week.xlsx", "status": "применён"}, \
        "задача и автор — в пояснении элемента, а не в подробностях запуска"
    detail = admin.get(f"/api/inbox/{tp.id}").json()
    assert detail["note"] == tp.note
    assert not any("/api/tasks/T3/" in r.path for r in fake.server.requests), "задачи другого списка не трогаются"
    tasks_query = next(r for r in fake.server.requests if r.path == "/api/v2/tasks").query
    assert tasks_query["listId"] == ["L1"] and tasks_query["sort"] == ["updatedAt"]
    db.expire_all()
    state = db.get(Integration, item["id"]).state
    assert state["list"] == "L1" and state["since"] and state["tasks"]["T1"]["n"] == 3
    assert fake.logouts == 1


def test_pull_comment_links_to_inbox_with_public_url(admin, fake, db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "public_url", "https://dash.company.ru")
    fake.add_task("T9", "Очень длинное название задачи " * 30, created_by="p-pm")
    fake.add_file("T9", "z1", "показатели.csv", csv_bytes([["Подразделение", "Показатель", "Период", "Значение"],
                                                           ["COMM", "fin.revenue", "2031-03", "5"]]), uploaded_by="")
    item = _create(admin, fake)
    run = _run(admin, item, "pull")
    assert run["status"] == "ok", run
    assert fake.comments == [("T9", "Файл «показатели.csv» принят в «Дашборды»: ожидает подтверждения\n"
                                    "Входящие данные: https://dash.company.ru/inbox")]
    taken = db.scalar(select(InboxItem).where(InboxItem.integration_id == item["id"]))
    assert len(taken.note) <= 500 and taken.note.startswith("Задача «Очень длинное название задачи")
    assert taken.note.endswith("…» · Петров Пётр"), "без загрузившего — автор задачи; длинное название сокращено"


def test_pull_cursor_dedup_and_new_attachment(admin, fake, db):
    _data_tasks(fake)
    item = _create(admin, fake, mark_processed=False)
    first = _run(admin, item, "pull")
    assert first["summary"]["added"] == 2 and fake.comments == []
    fake.server.requests.clear()
    second = _run(admin, item, "pull")
    assert second["summary"]["candidates"] == 0 and second["summary"]["added"] == 0
    assert not any(r.path.endswith("/content") for r in fake.server.requests), "без изменений — ничего не скачивается"
    # Новое вложение старой задачи: updatedAt в «По Делу» не меняется, меняется число вложений
    fake.add_file("T1", "a4", "naumen.csv", csv_bytes([["Подразделение", "Показатель", "Период", "Значение"],
                                                       ["COMM", "fin.revenue", "2031-02", "70"]]))
    fake.server.requests.clear()
    third = _run(admin, item, "pull")
    assert third["summary"]["added"] == 1 and third["summary"]["seen"] == 2
    downloaded = [r.path for r in fake.server.requests if r.path.endswith("/content")]
    assert downloaded == ["/api/tasks/T1/attachments/a4/content"], "уже забранные файлы не скачиваются"
    # Состояние потеряно: файлы скачиваются, но во «Входящие» повторно не кладутся (ctx.inbox.seen)
    db.execute(update(Integration).where(Integration.id == item["id"]).values(state={}))
    db.commit()
    fourth = _run(admin, item, "pull")
    assert fourth["summary"]["added"] == 0 and fourth["summary"]["seen"] == 3
    assert db.scalar(select(func.count()).select_from(InboxItem).where(InboxItem.integration_id == item["id"])) == 3


def test_pull_with_tags_and_paging(admin, fake, db, monkeypatch):
    from app.integrations.connectors import podelu

    monkeypatch.setattr(podelu, "PAGE_SIZE", 2)
    for n in range(5):
        fake.add_task(f"P{n}", f"Задача {n}", tags=("данные",) if n % 2 == 0 else (), updated=_now(n))
        fake.add_file(f"P{n}", f"f{n}", f"week-{n}.csv", csv_bytes([["Подразделение", "Показатель", "Период",
                                                                      "Значение"], ["COMM", "fin.revenue",
                                                                                    f"2031-0{n + 1}", str(n)]]))
    item = _create(admin, fake, data_tags=["данные"], mark_processed=False)
    run = _run(admin, item, "pull")
    assert run["summary"]["tasks"] == 3 and run["summary"]["added"] == 3
    pages = [r.query for r in fake.server.requests if r.path == "/api/v2/tasks"]
    assert len(pages) == 2 and pages[0]["tags"] == ["данные"] and pages[1]["cursor"] == ["2"]


def test_pull_comment_failure_is_partial(admin, fake, db):
    _data_tasks(fake)
    fake.comment_status = 403
    item = _create(admin, fake)
    run = _run(admin, item, "pull")
    assert run["status"] == "partial" and run["summary"]["added"] == 2 and run["summary"]["comment_errors"] == 1
    assert "Комментарии отключены владельцем списка" in run["error"]


def test_pull_errors_and_logout(admin, fake, db):
    item = _create(admin, fake, data_list="")
    run = _run(admin, item, "pull")
    assert run["status"] == "error" and run["error"].startswith("Не выбран список задач с данными")
    assert fake.logins == 0
    item_id = item["id"]
    admin.patch(f"/api/integrations/{item_id}", json={"config": {"data_list": "Нет такого"}})
    run = _run(admin, {"id": item_id}, "pull")
    assert run["status"] == "error" and "Список «Нет такого» в «По Делу» не найден" in run["error"]
    assert fake.logouts == 1
    _data_tasks(fake)
    fake.content_status = 500
    admin.patch(f"/api/integrations/{item_id}", json={"config": {"data_list": "L1"}})
    run = _run(admin, {"id": item_id}, "pull")
    assert run["status"] == "error" and "«По Делу» вернула ошибку 500" in run["error"]
    assert fake.logouts == 2, "выход выполнен и после ошибки скачивания"


def test_password_never_logged_or_returned(admin, fake, db, caplog):
    _data_tasks(fake)
    caplog.set_level(logging.DEBUG)
    item = _create(admin, fake)
    admin.post(f"/api/integrations/{item['id']}/check")
    runs = [_run(admin, item, "sync"), _run(admin, item, "pull")]
    fake.account["password"] = "другой"
    runs.append(_run(admin, item, "pull"))
    assert runs[-1]["status"] == "error"
    texts = [caplog.text, json.dumps(runs, ensure_ascii=False), admin.get(f"/api/integrations/{item['id']}").text]
    assert not any(PASSWORD in t for t in texts)


# ================================================================ ключ интеграции («По Делу» 1.4.5)

def _create_key(admin, fake, *, key=KEY, **config) -> dict:
    """Подключение по ключу. Служебной учётной записи у «Дашбордов» в этом режиме нет — нет её и в выгрузке."""
    fake.employees = [e for e in fake.employees if e["login"] != "svc"]
    body = {"kind": "podelu", "name": "По Делу", "config": {"base_url": fake.server.url, **config},
            "secrets": {"key": key}}
    response = admin.post("/api/integrations", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["config"]["mode"] == "key", "новое подключение — по ключу"
    return response.json()


def _key_requests(fake):
    return [r for r in fake.server.requests if r.path.startswith(V1)]


def _key_files(fake):
    fake.add_task("T1", "Недельный отчёт ТП", created_by="p-pm")
    fake.add_file("T1", "a1", "tp-week.xlsx", tp_file())
    fake.add_file("T1", "a2", "photo.png", b"\x89PNG....")
    fake.add_file("T1", "a3", "показатели.csv", csv_bytes([["Подразделение", "Показатель", "Период", "Значение"],
                                                           ["COMM", "fin.revenue", "2031-01", "61,5"]]))
    fake.add_file("T1", "a4", "итог.csv", b"x;y\n1;2\n", result=True)
    fake.add_task("T2", "Без файлов")
    fake.add_task("T3", "Чужой список", list_id="L2")
    fake.add_file("T3", "b1", "other.xlsx", tp_file())


def test_key_mode_is_default_with_hints_and_old_settings_still_work(admin, fake, db):
    meta = {k["kind"]: k for k in admin.get("/api/integrations/kinds").json()}["podelu"]
    fields = {f["key"]: f for f in meta["fields"]}
    mode = fields["mode"]
    assert mode["default"] == "key" and [(o["value"], o["label"]) for o in mode["options"]] == [
        ("key", "Ключ интеграции (По Делу 1.4.5 и новее)"),
        ("session", "Служебная учётная запись (для версий до 1.4.5)")]
    key = fields["key"]
    assert key["secret"] and key["required"] and key["show_if"] == {"mode": ["key"]}
    for text in ("Настройки → Интеграции → Ключи интеграций", "«Дашборды»", "dashboards", "org.read", "users.read",
                 "tasks.attachments.read", "tasks.comment", "списки задач"):
        assert text in key["hint"], text
    assert fields["login"]["show_if"] == fields["password"]["show_if"] == {"mode": ["session"]}
    assert "пусто — все списки ключа" in fields["data_list"]["hint"]
    assert meta["secret_url_fields"] == ["base_url", "server_url"], "ключ привязан к тем же адресам, что и пароль"
    assert meta["counter_labels"]["comments_disabled"] == "не отмечено: комментарии выключены"
    # Новое подключение без режима — по ключу: нужен ключ, а не пароль
    bare = admin.post("/api/integrations", json={"kind": "podelu", "config": {"base_url": fake.server.url}})
    assert bare.status_code == 422 and "secrets.key" in bare.json()["fields"]
    # Запрос прежнего вида (логин без режима) — служебная учётная запись, как раньше
    legacy = _create(admin, fake)
    assert legacy["config"]["mode"] == "session"
    # Подключение, сохранённое до режима ключа (mode нет), видно, проверяется и сохраняется служебной учётной записью
    from app.core import db as core_db

    stored = {k: v for k, v in legacy["config"].items() if k != "mode"}
    with core_db.SessionLocal() as session:
        session.execute(update(Integration).where(Integration.id == legacy["id"]).values(config=stored))
        session.commit()
    shown = admin.get(f"/api/integrations/{legacy['id']}").json()
    assert shown["config"]["mode"] == "session" and shown["secret_problem"] is None
    assert admin.post(f"/api/integrations/{legacy['id']}/check").json()["ok"]
    saved = admin.patch(f"/api/integrations/{legacy['id']}", json={"config": {"data_tags": ["данные"]}})
    assert saved.status_code == 200 and saved.json()["config"]["mode"] == "session"
    db.expire_all()
    assert db.get(Integration, legacy["id"]).config["mode"] == "session"


def test_key_check_reports_version_key_scopes_and_lists(admin, fake):
    fake.keys[KEY]["listIds"] = ["L1", "L2", "L-gone"]
    fake.add_task("T1", "Отчёт", list_id="L1")
    item = _create_key(admin, fake)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"], check
    assert check["message"] == ("Подключено к «По Делу» 1.4.5 по ключу «Дашборды», подразделений: 4, списки ключа: "
                                "«Данные для дашбордов», L2, L-gone")
    details = check["details"]
    assert details["mode"] == "key" and details["version"] == "1.4.5"
    assert details["key"] == {"name": "Дашборды", "app": "dashboards"} and details["scopes"] == ALL_SCOPES
    assert details["lists"] == [{"id": "L1", "title": "Данные для дашбордов"}, {"id": "L2", "title": None},
                                {"id": "L-gone", "title": None}], "названия — по задачам; список без задач — id"
    assert details["missing"] == []
    probes = [r.query for r in fake.server.requests if r.path == f"{V1}/tasks"]
    assert probes[0] == {"limit": ["200"]} and {"listId": ["L2"], "limit": ["1"]} in probes
    requests = _key_requests(fake)
    assert requests and all(r.headers["authorization"] == f"Bearer {KEY}" for r in requests)
    assert not any(r.path.startswith("/api/auth/") or r.path == "/api/lists" for r in fake.server.requests), \
        "по ключу — без входа служебной учётной записью"
    assert KEY not in json.dumps(check, ensure_ascii=False)
    # Выбранный список — по названию или id из списков ключа
    admin.patch(f"/api/integrations/{item['id']}", json={"config": {"data_list": "данные для дашбордов"}})
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"] and check["message"].endswith("список «Данные для дашбордов»")
    assert check["details"]["data_list"] == {"id": "L1", "title": "Данные для дашбордов"}


def test_key_check_lists_what_is_missing(admin, fake):
    fake.keys[KEY]["scopes"] = ["tasks.attachments.read"]
    item = _create_key(admin, fake)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"], "ключ только для файлов задач — «Забрать данные из задач» работает"
    assert ("Не хватает: область «Структура компании» (org.read) — для «Синхронизировать структуру»; область "
            "«Сотрудники» (users.read) — для сотрудников в «Синхронизировать структуру»; область «Комментарии к "
            "задачам» (tasks.comment) — для «Отмечать задачу комментарием» — добавьте ключу: «По Делу» → «Настройки "
            "→ Интеграции → Ключи интеграций»") in check["message"]
    assert not any(r.path == f"{V1}/org/export" for r in fake.server.requests)
    admin.patch(f"/api/integrations/{item['id']}", json={"config": {"mark_processed": False}})
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert "tasks.comment" not in check["message"], "отметка выключена — область комментариев не нужна"
    # Ни одно действие не работает — проверка не пройдена
    fake.keys[KEY].update(scopes=["users.read"], listIds=[])
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"]
    assert check["message"].startswith("Ключ «Дашборды» принят в «По Делу» 1.4.5, но не хватает: область «Структура "
                                       "компании» (org.read)")
    assert "область «Задачи и вложения» (tasks.attachments.read) со списками задач — для «Забрать данные из задач»" \
        in check["message"]
    # Выбранного списка нет среди списков ключа
    fake.keys[KEY].update(scopes=list(ALL_SCOPES), listIds=["L1"])
    admin.patch(f"/api/integrations/{item['id']}", json={"config": {"data_list": "Прочее"}})
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and "доступ ключа к списку «Прочее»" in check["message"]


def test_key_revoked_wrong_and_malformed_keys(admin, fake, db):
    item = _create_key(admin, fake)
    fake.keys[KEY]["revoked"] = True
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["details"]["code"] == "key_revoked"
    assert check["message"] == ("Ключ интеграции отозван администратором «По Делу» — выпустите ключ заново: «По Делу» "
                                "→ «Настройки → Интеграции → Ключи интеграций» и введите его в подключении")
    run = _run(admin, item, "pull")
    assert run["status"] == "error" and "отозван администратором «По Делу»" in run["error"]
    assert db.scalar(select(func.count()).select_from(InboxItem)) == 0
    admin.patch(f"/api/integrations/{item['id']}", json={"secrets": {"key": "podelu_" + "x" * 43}})
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["details"]["code"] == "auth"
    assert check["message"] == ("«По Делу» не приняла ключ интеграции (401): Неверный ключ «По Делу» — проверьте ключ "
                                "или выпустите новый в «По Делу»")
    admin.patch(f"/api/integrations/{item['id']}", json={"secrets": {"key": "dash_not-a-podelu-key"}})
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["message"] == "Ключ интеграции «По Делу» начинается с podelu_ — проверьте ключ"


@pytest.mark.parametrize("answer", [(404, {"message": "not found"}),
                                    (404, {"error": "not_found", "message": "The requested URL was not found on the "
                                                                           "server."})])
def test_key_mode_against_podelu_without_key_api(admin, fake, answer):
    fake.server.route("GET", f"{V1}/ping", lambda r: answer)
    item = _create_key(admin, fake)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["details"]["code"] == "no_api"
    assert "«По Делу» старше 1.4.5 или адрес указан неверно" in check["message"]
    assert "выберите режим «Служебная учётная запись (для версий до 1.4.5)»" in check["message"]
    run = _run(admin, item, "sync")
    assert run["status"] == "error" and "нет API ключей интеграций" in run["error"]


def test_key_sync_uses_user_ids_without_admin_list_or_service_account(admin, fake, db):
    _rules(db, "structure", "employees")
    # Руководитель уже пришёл из «По Делу» с прежним email: по userId он находится и до синхронизации сотрудников;
    # прежняя служебная учётная запись больше не исключается — её нет в выгрузке, и она отключается как отсутствующая
    db.add_all([
        User(username="petrov", full_name="Петров Пётр", email="pm.old@company.ru", role="user", is_active=True,
             org_source="podelu", external_id="p-pm", auth_source="local", must_change_password=False),
        User(username="svc", full_name="Синхронизация дашбордов", email="svc@company.ru", role="user", is_active=True,
             org_source="podelu", external_id="u-svc", auth_source="local", must_change_password=False),
    ])
    db.commit()
    item = _create_key(admin, fake, deactivate_missing=True)
    run = _run(admin, item, "sync")
    assert run["status"] == "ok", run
    assert run["message"].startswith("Структура: создать 2, изменить 1, руководителей 1 — применено"), \
        "руководитель назначен по userId, хотя email в «По Делу» другой"
    assert "Сотрудники: создано 2, изменено 1" in run["message"] and "отключено 1" in run["message"]
    assert run["summary"]["details"]["mode"] == "key"
    pm = db.scalar(select(User).where(User.external_id == "p-pm"))
    db.refresh(pm)
    assert pm.department.name == "Проектная служба" and pm.position == "Руководитель офиса"
    assert pm.email == "pm.old@company.ru", "email у сопоставленного по id сотрудника движок не перезаписывает"
    from app.services import org

    assert pm.id in org.build_snapshot(db).heads[pm.department_id]
    ivanova = _user(db, "ivanova@company.ru")
    assert ivanova.external_id == "p-iv" and ivanova.org_source == "podelu" and ivanova.password_hash is None
    assert _user(db, "svc@company.ru").is_active is False, "в режиме ключа служебной учётной записи нет — keep пуст"
    paths = [r.path for r in fake.server.requests]
    assert f"{V1}/org/export" in paths and f"{V1}/users/export" in paths
    assert "/api/users/admin/all" not in paths and not any(p.startswith("/api/auth/") for p in paths)
    users_query = next(r.query for r in fake.server.requests if r.path == f"{V1}/users/export")
    assert users_query == {"format": ["json"], "inactive": ["0"]}
    again = _run(admin, item, "sync")
    assert again["message"].startswith("Структура: без изменений") and again["summary"]["users_update"] == 0


def test_key_sync_needs_org_and_users_scopes(admin, fake):
    fake.keys[KEY]["scopes"] = ["org.read", "tasks.attachments.read"]
    item = _create_key(admin, fake)
    run = _run(admin, item, "sync")
    assert run["status"] == "error"
    assert run["error"] == ("У ключа «Дашборды» нет областей: «Сотрудники» (users.read) — добавьте их ключу: «По Делу» "
                            "→ «Настройки → Интеграции → Ключи интеграций»")
    assert not any(r.path == f"{V1}/org/export" for r in fake.server.requests)
    # Область отняли между проверкой и выгрузкой — ответ «По Делу» 403 insufficient_scope понятен
    fake.keys[KEY]["scopes"] = list(ALL_SCOPES)
    fake.server.route("GET", f"{V1}/users/export", fake.v1(fake.v1_users, "users.manage"))
    SCOPE_TITLES["users.manage"] = "Сотрудники"
    try:
        run = _run(admin, item, "sync")
    finally:
        SCOPE_TITLES.pop("users.manage")
    assert run["status"] == "error" and run["error"] == (
        "У ключа нет доступа «Сотрудники» (область users.manage) — добавьте её ключу: «По Делу» → «Настройки → "
        "Интеграции → Ключи интеграций»")


def test_key_pull_takes_task_files_with_uploader_and_comment(admin, fake, db):
    _key_files(fake)
    _rules(db, "tp-weekly")
    item = _create_key(admin, fake)
    activity = fake.tasks["T1"]["activityAt"]
    run = _run(admin, item, "pull")
    assert run["status"] == "ok", run
    summary = run["summary"]
    assert summary["tasks"] == 1 and summary["candidates"] == 1 and summary["added"] == 2
    assert summary["skipped_type"] == 1 and summary["comments"] == 1
    assert run["message"].startswith("Списки ключа «Дашборды» (1): задач с новыми вложениями 1, файлов во «Входящие» 2")
    items = {i.filename: i for i in db.scalars(select(InboxItem).where(InboxItem.integration_id == item["id"]))}
    assert set(items) == {"tp-week.xlsx", "показатели.csv"}, "файлы результатов поручений API ключей не отдаёт"
    assert items["tp-week.xlsx"].status == "applied"
    assert items["tp-week.xlsx"].source_ref == f"podelu:T1:a1:{hashlib.sha256(tp_file()).hexdigest()}"
    assert items["tp-week.xlsx"].note == "Задача «Недельный отчёт ТП» · Иванова Анна", "имя — из выгрузки сотрудников"
    assert fake.comments == [("T1", "Файл «tp-week.xlsx» принят в «Дашборды»: применён\n"
                                    "Файл «показатели.csv» принят в «Дашборды»: ожидает подтверждения")]
    tasks_query = next(r.query for r in fake.server.requests if r.path == f"{V1}/tasks")
    assert tasks_query == {"hasAttachments": ["1"], "limit": ["200"]}, "все списки ключа, первый запуск — с начала"
    assert sum(1 for r in fake.server.requests if r.path == f"{V1}/users/export") == 1, "имена — один раз за запуск"
    assert not any("/T3/" in r.path or "/T2/" in r.path for r in fake.server.requests), \
        "задачи без файлов и вне списков ключа не трогаются"
    comment = next(r for r in fake.server.requests if r.method == "POST")
    assert comment.path == f"{V1}/tasks/T1/comments" and comment.headers["authorization"] == f"Bearer {KEY}"
    db.expire_all()
    state = db.get(Integration, item["id"]).state
    assert state == {"mode": "key", "scope": {"lists": ["L1"], "tags": []}, "since": activity}
    assert fake.tasks["T1"]["activityAt"] > activity, "комментарий сдвинул активность — задача придёт ещё раз"
    assert "tasks" not in state, "число вложений по задачам больше не отслеживается"


def test_key_pull_without_users_scope_names_nobody(admin, fake, db):
    fake.keys[KEY]["scopes"] = ["tasks.attachments.read", "tasks.comment"]
    _key_files(fake)
    item = _create_key(admin, fake)
    run = _run(admin, item, "pull")
    assert run["status"] == "ok"
    taken = db.scalar(select(InboxItem).where(InboxItem.filename == "показатели.csv"))
    assert taken.note == "Задача «Недельный отчёт ТП»"
    assert not any(r.path.endswith("/users/export") for r in fake.server.requests)


def test_key_pull_cursor_dedup_by_sha256_and_new_file(admin, fake, db):
    _key_files(fake)
    item = _create_key(admin, fake)
    first = _run(admin, item, "pull")
    assert first["summary"]["added"] == 2 and len(fake.comments) == 1
    since = db.get(Integration, item["id"]).state["since"]
    fake.server.requests.clear()
    second = _run(admin, item, "pull")
    assert second["status"] == "ok" and second["summary"]["added"] == 0 and second["summary"]["seen"] == 2
    query = next(r.query for r in fake.server.requests if r.path == f"{V1}/tasks")
    assert query["updatedSince"] == [since], "курсор — время активности прошлого запуска"
    assert not any(r.path.endswith("/content") for r in fake.server.requests), \
        "уже забранные — по sha256, без скачивания"
    assert len(fake.comments) == 1, "задача без новых файлов не отмечается снова"
    fake.add_file("T1", "a5", "naumen.csv", csv_bytes([["Подразделение", "Показатель", "Период", "Значение"],
                                                       ["COMM", "fin.revenue", "2031-02", "70"]]))
    fake.server.requests.clear()
    third = _run(admin, item, "pull")
    assert third["summary"]["added"] == 1 and third["summary"]["seen"] == 2
    assert [r.path for r in fake.server.requests if r.path.endswith("/content")] == \
        [f"{V1}/tasks/T1/attachments/a5/content"]
    # Состояние потеряно: всё просматривается заново, но ничего не скачивается и не кладётся повторно
    db.execute(update(Integration).where(Integration.id == item["id"]).values(state={}))
    db.commit()
    fake.server.requests.clear()
    fourth = _run(admin, item, "pull")
    assert fourth["summary"]["added"] == 0 and fourth["summary"]["seen"] == 3
    assert not any(r.path.endswith("/content") for r in fake.server.requests)
    assert db.scalar(select(func.count()).select_from(InboxItem).where(InboxItem.integration_id == item["id"])) == 3


def test_key_pull_pages_by_cursor_and_continues_after_rate_limit(admin, fake, db, monkeypatch):
    from app.integrations.connectors import podelu

    monkeypatch.setattr(podelu, "PAGE_SIZE", 2)
    for n in range(5):
        fake.add_task(f"P{n}", f"Задача {n}", created_by="p-pm")
        fake.add_file(f"P{n}", f"f{n}", f"week-{n}.csv", csv_bytes([["Подразделение", "Показатель", "Период",
                                                                      "Значение"], ["COMM", "fin.revenue",
                                                                                    f"2031-0{n + 1}", str(n)]]))
    item = _create_key(admin, fake, mark_processed=False)
    # Предел частоты: ping, страница задач (P0, P1), P0 (файлы, имена, содержимое), P1 — и 429 на второй странице
    fake.budget = 7
    run = _run(admin, item, "pull")
    assert run["status"] == "partial", run
    assert run["summary"]["added"] == 2 and run["summary"]["tasks"] == 2
    assert "Ключ «Дашборды» превысил лимит частоты запросов «По Делу» (429) — повторите позже" in run["message"]
    assert "следующий запуск продолжит с места остановки" in run["message"]
    db.expire_all()
    assert db.get(Integration, item["id"]).state["since"] == fake.tasks["P1"]["activityAt"], \
        "курсор — последняя обработанная задача"
    fake.budget = None
    fake.server.requests.clear()
    again = _run(admin, item, "pull")
    assert again["status"] == "ok" and again["summary"]["added"] == 3 and again["summary"]["seen"] == 1
    pages = [r.query for r in fake.server.requests if r.path == f"{V1}/tasks"]
    assert pages[0]["updatedSince"] == [fake.tasks["P1"]["activityAt"]] and "cursor" not in pages[0]
    assert len(pages) == 2 and pages[1]["cursor"] and pages[1]["updatedSince"] == pages[0]["updatedSince"]
    listed = [r.path for r in fake.server.requests if r.path.endswith("/attachments")]
    assert f"{V1}/tasks/P0/attachments" not in listed, "до курсора задачи не просматриваются"
    assert not any(r.path.endswith("/P1/attachments/f1/content") for r in fake.server.requests)
    assert db.get(Integration, item["id"]).state["since"] == fake.tasks["P4"]["activityAt"]


def test_key_pull_list_and_tags(admin, fake, db):
    fake.keys[KEY]["listIds"] = ["L1", "L2"]
    fake.add_task("A", "Отчёт по меткам", tags=("данные", "финансы"))
    fake.add_file("A", "x1", "a.csv", b"a;b\n1;2\n")
    fake.add_task("B", "Другой отчёт", tags=("hr",))
    fake.add_file("B", "x2", "b.csv", b"c;d\n3;4\n")
    fake.add_task("C", "Прочее", list_id="L2", tags=("данные",))
    fake.add_file("C", "x3", "c.csv", b"e;f\n5;6\n")
    item = _create_key(admin, fake, mark_processed=False, data_list="Данные для дашбордов", data_tags=["данные"])
    run = _run(admin, item, "pull")
    assert run["status"] == "ok" and run["summary"]["added"] == 1
    assert run["message"].startswith("Список «Данные для дашбордов»:")
    query = [r.query for r in fake.server.requests if r.path == f"{V1}/tasks"][-1]
    assert query["listId"] == ["L1"] and query["tags"] == ["данные"], "одна метка — отбор у «По Делу»"
    # Несколько меток — «одна из» (у «По Делу» метки через запятую — все сразу): отбор у нас
    admin.patch(f"/api/integrations/{item['id']}", json={"config": {"data_list": "L2", "data_tags": ["hr", "данные"]}})
    fake.server.requests.clear()
    run = _run(admin, item, "pull")
    assert run["summary"]["added"] == 1 and run["message"].startswith("Список «Прочее»:")
    queries = [r.query for r in fake.server.requests if r.path == f"{V1}/tasks"]
    assert queries == [{"hasAttachments": ["1"], "limit": ["200"], "listId": ["L2"]}], \
        "id из списков ключа — без поиска названия; смена списка — курсор с начала"
    admin.patch(f"/api/integrations/{item['id']}", json={"config": {"data_list": ""}})
    run = _run(admin, item, "pull")
    assert run["summary"]["added"] == 1 and run["summary"]["seen"] == 2, "все списки ключа: B (метка hr) — новый"
    admin.patch(f"/api/integrations/{item['id']}", json={"config": {"data_list": "Нет такого"}})
    run = _run(admin, item, "pull")
    assert run["status"] == "error" and run["error"].startswith("Список «Нет такого» не открыт ключу «Дашборды»")
    assert "оставьте «Список задач с данными» пустым" in run["error"]


def test_key_pull_comments_disabled_is_a_warning(admin, fake, db):
    fake.lists[0]["settings"] = {"allowComments": False}
    _key_files(fake)
    fake.add_task("T4", "Ещё отчёт")
    fake.add_file("T4", "c1", "ещё.csv", b"a;b\n1;2\n")
    item = _create_key(admin, fake)
    run = _run(admin, item, "pull")
    assert run["status"] == "ok", "комментарии выключены владельцем списка — предупреждение, а не сбой"
    assert run["summary"]["added"] == 3 and run["summary"]["comments_disabled"] == 1
    assert "не отмечено задач: 1 (комментарии выключены)" in run["message"]
    assert run["summary"]["details"]["notes"] == [
        "в списке «Данные для дашбордов» владелец отключил комментарии — задачи не отмечаются"]
    assert sum(1 for r in fake.server.requests if r.method == "POST") == 1, "в этом списке больше не пробуем"
    assert fake.comments == []


def test_key_pull_comment_scope_and_errors(admin, fake, db):
    fake.keys[KEY]["scopes"] = ["users.read", "tasks.attachments.read"]
    _key_files(fake)
    item = _create_key(admin, fake)
    run = _run(admin, item, "pull")
    assert run["status"] == "ok" and run["summary"]["comments"] == 0
    assert run["summary"]["details"]["notes"] == [
        "у ключа нет области «Комментарии к задачам» (tasks.comment) — задачи не отмечаются"]
    assert not any(r.method == "POST" for r in fake.server.requests)
    fake.keys[KEY]["scopes"] = list(ALL_SCOPES)
    fake.add_file("T1", "a9", "новый.csv", b"a;b\n9;9\n")
    fake.comment_status = 500
    run = _run(admin, item, "pull")
    assert run["status"] == "partial" and run["summary"]["comment_errors"] == 1
    assert "«По Делу» вернула ошибку 500" in run["error"]


def test_key_rate_limit_and_comment_post_is_not_retried(admin, fake, db):
    item = _create_key(admin, fake)
    fake.budget = 0
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["details"]["code"] == "rate_limited"
    assert check["message"] == "Ключ интеграции превысил лимит частоты запросов «По Делу» (429) — повторите позже"
    assert sum(1 for r in fake.server.requests if r.path == f"{V1}/ping") == 3, "GET повторяется по Retry-After"
    fake.budget = 1
    run = _run(admin, item, "sync")
    assert run["status"] == "error" and run["error"] == ("Ключ «Дашборды» превысил лимит частоты запросов «По Делу» "
                                                         "(429) — повторите позже")
    fake.add_task("T1", "Отчёт")
    fake.add_file("T1", "a1", "a.csv", b"a;b\n1;2\n")
    fake.budget = 5          # ping, страница, файлы, имена, содержимое — и 429 на комментарии
    fake.server.requests.clear()
    run = _run(admin, item, "pull")
    assert run["status"] == "partial" and run["summary"]["added"] == 1
    assert sum(1 for r in fake.server.requests if r.method == "POST") == 1, "POST при 429 не повторяется"


def test_key_never_logged_stored_or_returned(admin, fake, db, caplog):
    _key_files(fake)
    caplog.set_level(logging.DEBUG)
    item = _create_key(admin, fake)
    responses = [admin.post(f"/api/integrations/{item['id']}/check").text,
                 admin.post("/api/integrations/check", json={"kind": "podelu", "config": {"base_url": fake.server.url},
                                                             "secrets": {"key": KEY}}).text]
    runs = [_run(admin, item, "sync"), _run(admin, item, "pull")]
    fake.budget = 0
    runs.append(_run(admin, item, "pull"))
    fake.budget = None
    fake.keys[KEY]["revoked"] = True
    runs.append(_run(admin, item, "sync"))
    responses.append(admin.post(f"/api/integrations/{item['id']}/check").text)
    assert runs[2]["status"] == runs[3]["status"] == "error"
    responses += [json.dumps(runs, ensure_ascii=False), admin.get(f"/api/integrations/{item['id']}").text,
                  admin.get("/api/integrations").text, admin.get(f"/api/integrations/{item['id']}/runs").text]
    from app.models import AuditEntry, IntegrationRun

    db.expire_all()
    row = db.get(Integration, item["id"])
    stored = [row.last_error, json.dumps(row.state, ensure_ascii=False), json.dumps(row.config, ensure_ascii=False),
              row.secret_bound_url or ""]
    for run in db.scalars(select(IntegrationRun).where(IntegrationRun.integration_id == item["id"])):
        stored += [run.message, run.error, json.dumps(run.summary, ensure_ascii=False)]
    stored += [f"{e.summary} {json.dumps(e.after, ensure_ascii=False)}"
               for e in db.scalars(select(AuditEntry).where(AuditEntry.entity_type == "integration"))]
    stored += [f"{i.note} {i.source_ref} {i.message}" for i in db.scalars(select(InboxItem))]
    for where, content in (("журнал сервера", caplog.text), *(("ответ API", t) for t in responses),
                           *(("база", t) for t in stored)):
        assert KEY not in content and KEY[7:] not in content, f"{where}: {content[:300]}"
