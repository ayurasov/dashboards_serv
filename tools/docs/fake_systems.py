"""Поддельные «По Делу», «Пульс проекта», Jira и Confluence для снимков экрана раздела «Интеграции»
(tools/docs/screenshots.mjs).

    sudo python3 tools/docs/fake_systems.py [адрес] [порт]   # по умолчанию 127.0.0.2:80

Один HTTP-сервер отвечает за несколько систем — по заголовку Host:
    podelu.almi-partner.local      «По Делу» 1.4.5: API ключей интеграций /api/integrations/v1 (ключи — PODELU_KEYS:
                                   podelu_demo-dashboards-key-2026 — все области, списки «Данные для дашбордов»
                                   и «Отчёты руководителей»; podelu_demo-files-only-key-2026 — только файлы задач
                                   (проверка с «Не хватает: …»); podelu_demo-revoked-key-2026 — отозван) и, для режима
                                   служебной учётной записи, CSRF и вход (dashboards-sync / demo-password), выгрузки
                                   структуры и сотрудников, список «Данные для дашбордов» с вложениями задач
    podelu-old.almi-partner.local  «По Делу» до 1.4.5: только служебная учётная запись, API ключей нет (404) —
                                   снимок проверки по ключу со старой версией
    puls.almi-partner.local        «Пульс проекта» 0.6.0: API ключей /api/integration/v1 — ping, направления, проекты
                                   (ключи — PULS_KEYS: puls_demo-dashboards-key-2026 — права projects.read
                                   и projects.stats; puls_demo-readonly-key-2026 — только projects.read: проверка
                                   с предупреждением о показателях). Служебной учётной записи у этой «Пульса» нет
    jira.almi-partner.local        Jira Server 9.12: myself, serverInfo, поиск по JQL (токен demo-jira-token)
    confluence.almi-partner.local  Confluence, отклоняющая токен (401) — снимок неудачной проверки
Имена нужно направить на адрес сервера (строка в /etc/hosts: «127.0.0.2 podelu.almi-partner.local
podelu-old.almi-partner.local puls.almi-partner.local jira.almi-partner.local confluence.almi-partner.local»), а
серверу «Дашбордов» — не пускать их через прокси (NO_PROXY). Отдельный адрес петли оставляет порт 80 на 127.0.0.1 для
самих «Дашбордов» (dashboards.almi-partner.local) — адреса на снимках без номеров портов. Данные — в духе демо-стенда
«АЛМИ Партнер»; секреты — демонстрационные.

Подключения в режиме ключа (API «Дашбордов»):
    {"kind": "podelu", "config": {"base_url": "http://podelu.almi-partner.local", "mode": "key"},
     "secrets": {"key": "podelu_demo-dashboards-key-2026"}}
    {"kind": "puls", "config": {"base_url": "http://puls.almi-partner.local", "mode": "key",
                                "directions": "Внедрение = PROJ\nСопровождение = АЛМИ Партнер / Техническая дирекция / "
                                              "Техническая служба\n7 = TECHDIR"},
     "secrets": {"api_key": "puls_demo-dashboards-key-2026"}}
"""
from __future__ import annotations

import base64
import hashlib
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
    # Только для ключа: список «Отчёты руководителей» открыт ключу «Дашборды», служебной учётной записи — нет
    {"id": "t-103", "listId": "L3", "title": "Показатели Технической службы за октябрь", "status": "done",
     "tags": ["отчёт"], "attachmentCount": 1, "updatedAt": "2026-11-01T15:05:00Z", "createdBy": "p-kuznetsova",
     "files": [{"id": "a-4", "fileName": "Техническая служба 2026-10.csv", "mimeType": "text/csv",
                "uploadedBy": "p-kuznetsova",
                "content": "\ufeffПодразделение;Показатель;Период;Значение;Цель;Комментарий\nSUP;ops.plan;2026-10;91;"
                           "100;\n"}]},
]
LISTS = [{"id": "L1", "title": "Данные для дашбордов", "settings": {"allowComments": True}},
         {"id": "L2", "title": "Задачи офиса", "settings": {}},
         {"id": "L3", "title": "Отчёты руководителей", "settings": {"allowComments": True}}]
SESSIONS: dict[str, dict] = {}

# API ключей интеграций «По Делу» 1.4.5 (/api/integrations/v1, ADR-0058 «По Делу»)
V1 = "/api/integrations/v1"
SCOPES = {"org.read": "Структура компании", "users.read": "Сотрудники", "tasks.attachments.read": "Задачи и вложения",
          "tasks.comment": "Комментарии к задачам"}
PODELU_KEYS = {
    "podelu_demo-dashboards-key-2026": {"name": "Дашборды", "app": "dashboards", "scopes": list(SCOPES),
                                        "listIds": ["L1", "L3"]},
    "podelu_demo-files-only-key-2026": {"name": "Дашборды — файлы задач", "app": "dashboards",
                                        "scopes": ["tasks.attachments.read"], "listIds": ["L1"]},
    "podelu_demo-revoked-key-2026": {"name": "Дашборды (прежний)", "app": "dashboards", "scopes": list(SCOPES),
                                     "listIds": ["L1"], "revoked": True},
}


def org_export() -> dict:
    return {"format": "podelu.org-structure", "version": 1, "exportedAt": "2026-11-02T03:00:00Z", "app": "1.18.0",
            "settings": {}, "departments": [{"key": k, "name": n, "parent": p, "kind": kind, "sortOrder": i,
                                             "externalId": None, "heads": []}
                                            for i, (k, n, p, kind) in enumerate(DEPARTMENTS)]}


def users_export(with_ids: bool = False) -> dict:
    return {"format": "podelu.employees", "version": 1, "employees": [
        {**({"userId": i} if with_ids else {}), "email": e, "login": e.split("@")[0], "name": n, "position": pos,
         "department": path, "manager": "", "reportsToNone": False, "heads": [], "role": "user", "capabilities": [],
         "isActive": True, "externalId": ""}
        for i, e, n, pos, path in PEOPLE]}


def activity(task: dict) -> str:
    return task.get("activityAt") or task["updatedAt"]


def podelu_v1(handler, method: str, path: str, query: dict) -> tuple:
    """API ключей «По Делу» 1.4.5: Bearer podelu_…, области ключа, только списки ключа, курсор по activityAt."""
    header = handler.headers.get("Authorization") or ""
    token = header[7:].strip() if header[:7].lower() == "bearer " else ""
    if not token.startswith("podelu_"):
        return 401, {"error": "unauthorized", "message": "Нужен ключ «По Делу»: заголовок Authorization: Bearer podelu_…"}
    key = PODELU_KEYS.get(token)
    if key is None:
        return 401, {"error": "unauthorized",
                     "message": "Неверный ключ «По Делу» — проверьте ключ или выпустите новый в «По Делу»"}
    if key.get("revoked"):
        return 403, {"error": "key_revoked", "message": "Ключ отозван администратором «По Делу»"}
    sub = path[len(V1):]
    task_scoped = {"tasks.attachments.read", "tasks.comment"} & set(key["scopes"])
    lists = [i for i in key["listIds"] if any(x["id"] == i for x in LISTS)] if task_scoped else []

    def denied(scope: str) -> tuple | None:
        if scope in key["scopes"]:
            return None
        return 403, {"error": "insufficient_scope", "message": f"У ключа нет доступа «{SCOPES[scope]}» (область {scope})"}

    if sub == "/ping":
        body = {"ok": True, "app": "podelu", "name": "По Делу", "version": "1.4.5",
                "key": {"name": key["name"], "app": key["app"]}, "scopes": [s for s in SCOPES if s in key["scopes"]]}
        if task_scoped:
            body["listIds"] = list(key["listIds"])
        return 200, body
    if sub == "/org/export":
        return denied("org.read") or (200, {**org_export(), "app": "1.4.5"})
    if sub == "/users/export":
        return denied("users.read") or (200, users_export(with_ids=True))
    if sub == "/tasks":
        if denied("tasks.attachments.read"):
            return denied("tasks.attachments.read")
        arg = {k: v[0] for k, v in query.items()}
        if arg.get("listId") and arg["listId"] not in lists:
            return 404, {"error": "not_found", "message": "Список не найден или не открыт этому ключу"}
        targets = [arg["listId"]] if arg.get("listId") else lists
        tags = [t for t in (arg.get("tags") or "").split(",") if t]
        items = [t for t in TASKS if t["listId"] in targets and all(tag in t["tags"] for tag in tags)
                 and (arg.get("hasAttachments") != "1" or any(f["fileName"] for f in t["files"]))
                 and activity(t) >= (arg.get("updatedSince") or "")]
        if arg.get("cursor"):
            raw = arg["cursor"] + "=" * (-len(arg["cursor"]) % 4)
            stamp, last = base64.urlsafe_b64decode(raw).decode().split("|", 1)
            items = [t for t in items if (activity(t), t["id"]) > (stamp, last)]
        items.sort(key=lambda t: (activity(t), t["id"]))
        limit = min(500, int(arg.get("limit") or 100))
        titles = {x["id"]: x["title"] for x in LISTS}
        page = [{"id": t["id"], "listId": t["listId"], "listTitle": titles.get(t["listId"]), "parentTaskId": None,
                 "title": t["title"], "status": t["status"], "priority": "normal", "tags": t["tags"],
                 "assigneeId": t["createdBy"], "createdBy": t["createdBy"], "dueDate": None, "startDate": None,
                 "createdAt": t["updatedAt"], "updatedAt": t["updatedAt"], "activityAt": activity(t),
                 "completedAt": None, "attachmentsCount": len(t["files"])} for t in items[:limit]]
        more = len(items) > limit
        cursor = base64.urlsafe_b64encode(f"{page[-1]['activityAt']}|{page[-1]['id']}".encode()).decode().rstrip("=") \
            if more else None
        return 200, {"items": page, "nextCursor": cursor}
    match = re.match(r"^/tasks/([\w-]+)/(attachments|comments)(?:/([\w-]+)/content)?$", sub)
    task = next((t for t in TASKS if match and t["id"] == match.group(1)), None)
    if match is None:
        return 404, {"error": "not_found", "message": "Не найдено"}
    if match.group(2) == "comments":
        if method != "POST" or denied("tasks.comment"):
            return denied("tasks.comment") or (405, {"error": "method_not_allowed", "message": "Только POST"})
        if task is None or task["listId"] not in lists:
            return 404, {"error": "not_found", "message": "Задача не найдена"}
        if next(x for x in LISTS if x["id"] == task["listId"])["settings"].get("allowComments") is False:
            return 403, {"error": "comments_disabled", "message": "Комментарии в этом списке отключены его владельцем"}
        task["activityAt"] = "2026-11-02T08:00:00Z"
        return 201, {"id": secrets.token_hex(4), "taskId": task["id"], "text": handler.json().get("text"),
                     "createdAt": task["activityAt"], "integrationName": key["name"]}
    if denied("tasks.attachments.read"):
        return denied("tasks.attachments.read")
    if task is None or task["listId"] not in lists:
        return 404, {"error": "not_found", "message": "Задача не найдена"}
    if match.group(3):
        found = next((f for f in task["files"] if f["id"] == match.group(3)), None)
        if found is None:
            return 404, {"error": "not_found", "message": "Файл не найден"}
        content = found["content"].encode("utf-8")
        return 200, content, {"Content-Type": found["mimeType"], "ETag": f'"{hashlib.sha256(content).hexdigest()}"'}
    return 200, {"taskId": task["id"], "items": [
        {"id": f["id"], "fileName": f["fileName"], "mimeType": f["mimeType"], "size": len(f["content"].encode("utf-8")),
         "sha256": hashlib.sha256(f["content"].encode("utf-8")).hexdigest(), "uploadedAt": task["updatedAt"],
         "uploadedBy": f["uploadedBy"], "contentPath": f"{V1}/tasks/{task['id']}/attachments/{f['id']}/content"}
        for f in task["files"]]}


def podelu(handler, method: str, path: str, query: dict) -> tuple:
    if path.startswith(V1 + "/"):
        return podelu_v1(handler, method, path, query)
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
        return 200, LISTS[:2]
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


# ---------------------------------------------------------------- «По Делу» до 1.4.5 (без API ключей)

def podelu_old(handler, method: str, path: str, query: dict) -> tuple:
    if path.startswith(V1 + "/"):
        return 404, {"error": "not_found", "message": "The requested URL was not found on the server."}
    return podelu(handler, method, path, query)


# ---------------------------------------------------------------- «Пульс проекта» 0.6.0 (API ключей)

PULS_KEYS = {
    "puls_demo-dashboards-key-2026": {"name": "Дашборды компании", "scopes": ["projects.read", "projects.stats"]},
    "puls_demo-readonly-key-2026": {"name": "Дашборды компании (без показателей)", "scopes": ["projects.read"]},
}
DIRECTIONS = [(3, "Внедрение", "blue"), (5, "Сопровождение", "green"), (7, "Разработка", "violet"),
              (9, "Маркетинг", "orange")]
# id, название, направление, задач всего, выполнено, в работе, заблокировано, просрочено, прогресс, окончание, веха
PROJECTS = [
    (11, "Внедрение AlterOS в Минтрансе", 3, 24, 15, 6, 1, 0, 68, "2026-12-20", ("Опытная эксплуатация", "2026-11-16")),
    (12, "Внедрение AlterOffice в банке «Восток»", 3, 18, 7, 8, 0, 2, 41, "2026-11-30", None),
    (13, "Пилот AlterOS для РЖД", 3, 10, 10, 0, 0, 0, 100, "2026-10-15", None),
    (21, "Сопровождение госзаказчиков", 5, 30, 21, 8, 1, 0, 74, "2027-03-31", ("Отчёт за квартал", "2026-12-28")),
    (22, "Миграция почты клиентов", 5, 12, 4, 6, 2, 1, 35, "2026-11-14", None),
    (31, "AlterOS 2.8", 7, 40, 28, 10, 2, 0, 71, "2026-12-25", ("Бета-версия", "2026-11-20")),
    (32, "Портал поддержки", 7, 16, 6, 9, 0, 0, 38, "2026-11-20", None),
    (41, "Осенняя выставка", 9, 8, 3, 4, 0, 1, 45, "2026-10-31", None),
    (51, "Новый сайт компании", None, 0, 0, 0, 0, 0, 0, None, None),
]


def puls_project(row: tuple, stats: bool) -> dict:
    pid, title, direction, total, done, inwork, blocked, overdue, progress, end, milestone = row
    names = {i: n for i, n, _c in DIRECTIONS}
    data = {"id": pid, "title": title, "subtitle": "", "direction": names.get(direction), "path": f"/projects/{pid}",
            "progress": progress, "start": "2026-03-01" if total else None, "end": end, "overdue": overdue,
            "total": total, "done": done, "planId": pid * 10, "planTitle": "Основной план",
            "nextMilestone": {"name": milestone[0], "date": milestone[1]} if milestone else None}
    if stats:
        data.update(inwork=inwork, blocked=blocked, updatedAt="2026-11-01T17:20:00Z",
                    directionInfo={"id": direction, "name": names[direction]} if direction in names else None,
                    planWindow={"start": "2026-03-01", "end": "2027-03-31"})
    return data


def puls(handler, method: str, path: str, query: dict) -> tuple:
    """«Пульс» 0.6.0: только API ключей интеграций (GET, Bearer puls_…, права projects.read / projects.stats)."""
    if not path.startswith("/api/integration/v1/") or method != "GET":
        return 404, {"error": "not_found", "message": "Не найдено"}
    header = handler.headers.get("Authorization") or ""
    key = PULS_KEYS.get(header[7:].strip()) if header.startswith("Bearer ") else None
    if key is None:
        return 401, {"error": "unauthorized",
                     "message": "Нужен действующий ключ «Пульса» (Authorization: Bearer puls_…) — его выпускает "
                                "администратор «Пульса»: Администрирование → Интеграции → Ключи доступа"}
    sub = path[len("/api/integration/v1"):]
    if sub == "/ping":
        return 200, {"ok": True, "app": "puls", "name": "Пульс Проекта", "version": "0.6.0",
                     "key": {"name": key["name"], "scopes": list(key["scopes"])}}
    if "projects.read" not in key["scopes"]:
        return 403, {"error": "insufficient_scope", "message": f"У ключа «{key['name']}» нет права projects.read"}
    if sub == "/directions":
        counts: dict = {}
        for row in PROJECTS:
            counts[row[2]] = counts.get(row[2], 0) + 1
        return 200, {"directions": [{"id": i, "name": n, "color": c, "position": p, "projects": counts.get(i, 0)}
                                    for p, (i, n, c) in enumerate(DIRECTIONS)],
                     "withoutDirection": counts.get(None, 0), "userFound": None}
    if sub == "/projects":
        try:
            limit = max(1, min(200, int((query.get("limit") or ["50"])[0])))
        except ValueError:
            limit = 50
        stats = "projects.stats" in key["scopes"]
        return 200, {"projects": [puls_project(row, stats) for row in PROJECTS[:limit]], "userFound": None}
    return 404, {"error": "not_found", "message": "Не найдено"}


SYSTEMS = {"podelu": podelu, "podelu-old": podelu_old, "puls": puls, "jira": jira, "confluence": confluence}


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
    print(f"Поддельные системы на {host}:{port} — podelu, podelu-old, puls, jira, confluence .almi-partner.local")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
