"""Поддельные «По Делу», Jira и Confluence для снимков экрана раздела «Интеграции» (tools/docs/screenshots.mjs).

    sudo python3 tools/docs/fake_systems.py [адрес] [порт]   # по умолчанию 127.0.0.2:80

Один HTTP-сервер отвечает за три системы — по заголовку Host:
    podelu.almi-partner.local      «По Делу»: CSRF и вход служебной учётной записи (dashboards-sync / demo-password),
                                   выгрузки структуры и сотрудников, список «Данные для дашбордов» с вложениями задач
    jira.almi-partner.local        Jira Server 9.12: myself, serverInfo, поиск по JQL (токен demo-jira-token)
    confluence.almi-partner.local  Confluence, отклоняющая токен (401) — снимок неудачной проверки
Имена нужно направить на адрес сервера (строка в /etc/hosts: «127.0.0.2 podelu.almi-partner.local …»), а серверу
«Дашбордов» — не пускать их через прокси (NO_PROXY). Отдельный адрес петли оставляет порт 80 на 127.0.0.1 для самих
«Дашбордов» (dashboards.almi-partner.local) — адреса на снимках без номеров портов. Данные — в духе демо-стенда «АЛМИ Партнер»; секреты — демонстрационные.
"""
from __future__ import annotations

import json
import re
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

LOGIN, PASSWORD = "dashboards-sync", "demo-password"
JIRA_TOKEN = "demo-jira-token"
COOKIE = "todo_planner_session"

# ---------------------------------------------------------------- «По Делу»

DEPARTMENTS = [  # как в демо-структуре «Дашбордов»; «Группа внедрения» — новое подразделение «По Делу»
    ("d-almi", "АЛМИ Партнер", None, "company"),
    ("d-agd", "Аппарат генерального директора", "d-almi", "division"),
    ("d-aho", "АХО", "d-agd", "department"),
    ("d-hr", "Служба персонала", "d-agd", "service"),
    ("d-comm", "Коммерческая дирекция", "d-almi", "division"),
    ("d-mkt", "Служба маркетинга", "d-comm", "service"),
    ("d-sales", "Коммерческая служба", "d-comm", "service"),
    ("d-tech", "Техническая дирекция", "d-almi", "division"),
    ("d-it", "ИТ-служба", "d-tech", "service"),
    ("d-sup", "Техническая служба", "d-tech", "service"),
    ("d-os", "Группа поддержки AlterOS", "d-sup", "group"),
    ("d-office", "Группа поддержки AlterOffice", "d-sup", "group"),
    ("d-impl", "Группа внедрения", "d-sup", "group"),
    ("d-proj", "Проектная служба", "d-almi", "service"),
]
PEOPLE = [  # id, email, ФИО, должность, путь подразделения
    ("p-orlova", "n.orlova@almi-partner.ru", "Орлова Наталья Викторовна", "Специалист по подбору",
     ["АЛМИ Партнер", "Аппарат генерального директора", "Служба персонала"]),
    ("p-kuznetsova", "o.kuznetsova@almi-partner.ru", "Кузнецова Ольга Павловна", "Ведущий инженер",
     ["АЛМИ Партнер", "Техническая дирекция", "Техническая служба", "Группа внедрения"]),
    ("p-belov", "a.belov@almi-partner.ru", "Белов Артём Николаевич", "Инженер технической поддержки",
     ["АЛМИ Партнер", "Техническая дирекция", "Техническая служба", "Группа поддержки AlterOffice"]),
    ("p-zaitseva", "e.zaitseva@almi-partner.ru", "Зайцева Елена Андреевна", "Руководитель проектов",
     ["АЛМИ Партнер", "Проектная служба"]),
]
ACCOUNT = {"id": "p-svc", "login": LOGIN, "name": "Синхронизация дашбордов", "email": "dashboards-sync@almi-partner.ru",
           "globalRole": "user", "isActive": True, "capabilities": ["org.manage", "users.manage"]}
HR_FILE = ("﻿Метрика;2026-10\nВсего сотрудников;196\nТекучесть кадров;1,4\nТекучесть по инициативе компании;0,5\n"
           "Среднее время закрытия позиции;29\nПринятые офферы;86\nПрохождение испытательного срока (общее);92\n")
PROJECT_FILE = ("﻿Подразделение;Показатель;Период;Значение;Цель;Комментарий\n"
                "PROJ;ops.plan;2026-10;96;100;Перенос этапа внедрения на ноябрь\nPROJ;ops.csat;2026-10;4,7;;\n")
TASKS = [
    {"id": "t-101", "listId": "L1", "title": "Метрики службы персонала за октябрь", "status": "done", "tags": ["hr"],
     "attachmentCount": 1, "updatedAt": "2026-11-01T09:12:00Z", "createdBy": "p-orlova",
     "files": [{"id": "a-1", "fileName": "Метрики персонала 2026-10.csv", "mimeType": "text/csv",
                "uploadedBy": "p-orlova", "content": HR_FILE}]},
    {"id": "t-102", "listId": "L1", "title": "Показатели Проектной службы за октябрь", "status": "in_progress",
     "tags": ["отчёт"], "attachmentCount": 2, "updatedAt": "2026-11-01T11:40:00Z", "createdBy": "p-zaitseva",
     "files": [{"id": "a-2", "fileName": "Показатели 2026-10.csv", "mimeType": "text/csv", "uploadedBy": "p-zaitseva",
                "content": PROJECT_FILE},
               {"id": "a-3", "fileName": "Снимок плана.png", "mimeType": "image/png", "uploadedBy": "p-zaitseva",
                "content": "png"}]},
]
SESSIONS: dict[str, dict] = {}


def org_export() -> dict:
    return {"format": "podelu.org-structure", "version": 1, "exportedAt": "2026-11-02T03:00:00Z", "app": "1.18.0",
            "settings": {}, "departments": [{"key": k, "name": n, "parent": p, "kind": kind, "sortOrder": i,
                                             "externalId": None, "heads": []}
                                            for i, (k, n, p, kind) in enumerate(DEPARTMENTS)]}


def users_export() -> dict:
    return {"format": "podelu.employees", "version": 1, "employees": [
        {"email": e, "login": e.split("@")[0], "name": n, "position": pos, "department": path, "manager": "",
         "reportsToNone": False, "heads": [], "role": "user", "capabilities": [], "isActive": True, "externalId": ""}
        for _id, e, n, pos, path in PEOPLE]}


def podelu(handler, method: str, path: str, query: dict) -> tuple:
    cookie = handler.headers.get("Cookie") or ""
    sid = next((v for k, _, v in (c.strip().partition("=") for c in cookie.split(";")) if k == COOKIE), None)
    session = SESSIONS.get(sid or "")
    if path == "/api/auth/csrf-token":
        if session is None:
            sid, session = secrets.token_hex(8), {"csrf": secrets.token_hex(8), "user": None}
            SESSIONS[sid] = session
        return 200, {"csrfToken": session["csrf"]}, {"Set-Cookie": f"{COOKIE}={sid}; Path=/; HttpOnly"}
    if method != "GET" and (session is None or handler.headers.get("X-CSRF-Token") != session["csrf"]):
        return 400, {"error": "csrf_error", "message": "The CSRF token is missing."}
    if path == "/api/auth/login":
        body = handler.json()
        if body.get("login") != LOGIN or body.get("password") != PASSWORD:
            return 401, {"error": "invalid_credentials", "message": "Неверный логин или пароль"}
        session["user"] = LOGIN
        return 200, {"user": ACCOUNT}
    if path == "/api/auth/logout":
        session["user"] = None
        return 200, {"message": "logged_out"}
    if session is None or not session["user"]:
        return 401, {"error": "auth_required", "message": "Нужно войти"}
    if path == "/api/org/export":
        return 200, org_export()
    if path == "/api/users/export":
        return 200, users_export()
    if path == "/api/users/admin/all":
        return 200, [{"id": i, "email": e, "name": n, "isSystem": False} for i, e, n, _p, _d in PEOPLE]
    if path == "/api/lists":
        return 200, [{"id": "L1", "title": "Данные для дашбордов", "settings": {"allowComments": True}},
                     {"id": "L2", "title": "Задачи офиса", "settings": {}}]
    if path == "/api/v2/tasks":
        items = [{k: v for k, v in t.items() if k != "files"} for t in TASKS if t["listId"] in query.get("listId", [])]
        return 200, {"items": items, "nextCursor": None, "hasMore": False}
    match = re.match(r"^/api/users/([\w-]+)$", path)
    if match:
        person = next((p for p in PEOPLE if p[0] == match.group(1)), None)
        return (200, {"id": person[0], "name": person[2], "email": person[1]}) if person else (404, {"error": "no"})
    match = re.match(r"^/api/tasks/([\w-]+)/(attachments|results|comments)(?:/([\w-]+)/content)?$", path)
    task = next((t for t in TASKS if match and t["id"] == match.group(1)), None)
    if task is None:
        return 404, {"error": "not_found", "message": "Нет такого"}
    kind, attachment = match.group(2), match.group(3)
    if kind == "results":
        return 200, []
    if kind == "comments":
        return 201, {"id": secrets.token_hex(4), "text": handler.json().get("text")}
    if attachment:
        found = next(f for f in task["files"] if f["id"] == attachment)
        return 200, found["content"].encode("utf-8"), {"Content-Type": found["mimeType"]}
    return 200, [{"id": f["id"], "taskId": task["id"], "fileName": f["fileName"], "mimeType": f["mimeType"],
                  "size": len(f["content"].encode("utf-8")), "uploadedBy": f["uploadedBy"],
                  "uploadedAt": task["updatedAt"]} for f in task["files"]]


# ---------------------------------------------------------------- Jira

def issues(prefix: str, count: int, *, spent: int = 0, start: int = 1) -> list[dict]:
    out = []
    for n in range(count):
        done = n % 9 != 0
        out.append({"key": f"{prefix}-{start + n}", "fields": {
            "status": {"statusCategory": {"key": "done" if done else "indeterminate"}},
            "timeoriginalestimate": 0 if n % 11 == 3 else 14400,
            "timeestimate": 1800 if (done and n % 13 == 5) else (0 if done else 7200),
            "timespent": spent or (18000 if n % 17 == 2 else 10800)}})
    return out


def jira_found(jql: str) -> list[dict]:
    month = re.search(r'"(\d{4}-\d{2})-01"', jql)
    late = month and month.group(1) == "2026-11"
    if "AlterOS" in jql:
        return issues("SUP", 14 if late else 43, start=100)
    if "AlterOffice" in jql:
        return issues("SUP", 11 if late else 38, start=200)
    if "project = IT" in jql:
        return issues("IT", 9 if late else 26, spent=12600, start=300)
    if "statusCategory != Done" in jql:
        return issues("SUP", 52, start=400)
    return []


def jira(handler, method: str, path: str, _query: dict) -> tuple:
    if handler.headers.get("Authorization") != f"Bearer {JIRA_TOKEN}":
        return 401, {"errorMessages": ["Учётные данные не приняты"]}
    if path == "/rest/api/2/myself":
        return 200, {"name": "svc-dashboards", "displayName": "Служебная учётная запись дашбордов",
                     "emailAddress": "svc-dashboards@almi-partner.ru"}
    if path == "/rest/api/2/serverInfo":
        return 200, {"version": "9.12.15", "deploymentType": "Server", "serverTitle": "Jira АЛМИ Партнер"}
    if path == "/rest/api/2/search" and method == "POST":
        body = handler.json()
        found = jira_found(body.get("jql") or "")
        start, size = int(body.get("startAt") or 0), int(body.get("maxResults") or 50)
        return 200, {"startAt": start, "maxResults": size, "total": len(found), "issues": found[start:start + size]}
    return 404, {"errorMessages": ["Not found"]}


# ---------------------------------------------------------------- Confluence

def confluence(_handler, _method: str, _path: str, _query: dict) -> tuple:
    return 401, {"statusCode": 401, "message": "Personal access token is invalid or expired"}


SYSTEMS = {"podelu": podelu, "jira": jira, "confluence": confluence}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # короткий журнал запросов
        sys.stderr.write(f"{self.headers.get('Host')} {fmt % args}\n")

    def json(self) -> dict:
        try:
            return json.loads(self.body or b"{}")
        except ValueError:
            return {}

    def handle_any(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.body = self.rfile.read(length) if length else b""
        parts = urlsplit(self.path)
        host = (self.headers.get("Host") or "").split(":")[0].split(".")[0]
        system = SYSTEMS.get(host)
        result = system(self, self.command, parts.path, parse_qs(parts.query)) if system else (404, {"error": host})
        status, body, headers = (*result, {})[:3]
        if isinstance(body, (dict, list)):
            payload, ctype = json.dumps(body, ensure_ascii=False).encode(), "application/json"
        else:
            payload, ctype = body, headers.pop("Content-Type", "application/octet-stream")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_DELETE = handle_any


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.2"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    print(f"Поддельные системы на {host}:{port} — podelu, jira, confluence .almi-partner.local")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
