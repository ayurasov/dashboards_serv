"""Коннектор «По Делу» против поддельной «По Делу» (настоящий HTTP-сервер в потоке): вход служебной учётной записью
(CSRF, Referer, Origin, cookie, выход всегда), проверка прав и списка, синхронизация структуры и сотрудников через
движки «Дашбордов» (сопоставление по id «По Делу» и email, «Без доступа», роли не переносятся, правила «Входящих»),
данные из вложений задач (курсор, повторы, файлы результатов, комментарий-отметка), ошибки и секреты."""
from __future__ import annotations

import hashlib
import json
import logging
import secrets as pysecrets
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, update

from app.models import Department, InboxItem, InboxRule, Integration, User
from app.services import inbox
from tests.fake_http import FakeServer, Request
from tests.test_inbox import csv_bytes, tp_file

PASSWORD = "Пароль-служебной-42"
COOKIE = "todo_planner_session"


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
                "attachmentCount": 0, "updatedAt": updated or _now(), "createdBy": created_by}
        self.tasks[task_id] = task
        self.files[task_id] = []
        self.results[task_id] = []
        self.server.route("GET", f"/api/tasks/{task_id}/attachments",
                          self.guarded(lambda r: (200, [self.public(a) for a in self.files[task_id]])))
        self.server.route("GET", f"/api/tasks/{task_id}/results", self.guarded(
            lambda r: (200, [{**res, "attachments": [self.public(a) for a in res["attachments"]]}
                             for res in self.results[task_id]])))
        self.server.route("POST", f"/api/tasks/{task_id}/comments", lambda r: self.comment(r, task_id))
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

        def content_route(r):
            if self.content_status != 200:
                return self.content_status, {"error": "internal", "message": "Сбой хранилища"}
            return 200, content, {"ETag": f'"{hashlib.sha256(content).hexdigest()}"'}
        self.server.route("GET", f"/api/tasks/{task_id}/attachments/{att_id}/content", self.guarded(content_route))

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
    return response.json()


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
