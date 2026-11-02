"""Коннектор «Пульс проекта» против поддельного «Пульса» (настоящий HTTP-сервер в потоке): ключ интеграции
(«Пульс» 0.6.0: Bearer без cookie, права projects.read и projects.stats, направления с числом проектов, inwork,
blocked и directionInfo, не больше 200 проектов, отзыв, 429, старый «Пульс» без ключей), вход служебной учётной
записью (CSRF, выход всегда), готовность и версия, направления для сопоставления, расчёт показателей проектов
по подразделениям, светофор проекта, создание показателей каталога, запись значений движком загрузки, ошибки,
ключ не попадает наружу."""
from __future__ import annotations

import json
import logging
import secrets as pysecrets
from datetime import date

import pytest
from sqlalchemy import select, update

from app.models import Department, Indicator, IndicatorValue
from tests.conftest import assert_counters_labelled
from tests.fake_http import FakeServer, Request

PASSWORD = "Пароль-пульса-7"
KEY = "puls_" + "Kp4Zr" * 9
V1 = "/api/integration/v1"
COOKIE = "puls_session"
TODAY = date(2026, 11, 2)
MAPPING = "Внедрение = PROJ\n2 = АЛМИ Партнер / Техническая дирекция / ИТ-служба"


def _project(pid, title, direction, *, total, done, overdue=0, blocked=0, progress=0, end=None, stats=True):
    out = {"id": pid, "title": title, "subtitle": "", "directionId": direction, "position": pid, "access": "view",
           "plans": [{"id": pid * 10, "title": "План"}]}
    if stats:
        out["stats"] = {"total": total, "done": done, "inwork": max(0, total - done - blocked), "blocked": blocked,
                        "overdue": overdue, "progress": progress, "start": "2026-01-01", "end": end,
                        "planId": pid * 10, "planTitle": "План"}
    return out


class FakePuls:
    def __init__(self, server: FakeServer):
        self.server = server
        self.account = {"id": 5, "login": "svc", "password": PASSWORD, "name": "Наблюдатель дашбордов",
                        "role": "viewer", "isActive": True}
        self.sessions: dict[str, dict] = {}
        self.logins = self.logouts = 0
        self.ready_status = 200
        self.break_csrf = False
        self.directions = [{"id": 1, "name": "Внедрение", "color": "blue"}, {"id": 2, "name": "Разработка"},
                           {"id": 3, "name": "Маркетинг"}]
        self.projects = [
            _project(1, "Внедрение А", 1, total=10, done=5, blocked=1, progress=60, end="2026-12-31"),
            _project(2, "Внедрение Б", 1, total=8, done=2, overdue=2, progress=40, end="2026-12-01"),
            _project(3, "Разработка ядра", 2, total=4, done=4, progress=100, end="2026-10-01"),
            _project(4, "Маркетинг осень", 3, total=5, done=1, progress=30, end="2026-10-15"),
            _project(5, "Без плана", None, total=0, done=0, stats=False),
            _project(6, "Разработка API", 2, total=6, done=3, progress=50, end="2026-11-10"),
        ]
        for method, path, handler in (
            ("GET", "/api/auth/csrf", self.csrf), ("POST", "/api/auth/login", self.login),
            ("POST", "/api/auth/logout", self.logout), ("GET", "/api/health/ready", self.ready),
            ("GET", "/api/directions", self.guarded(lambda r: (200, self.directions))),
            ("GET", "/api/projects", self.guarded(lambda r: (200, self.projects))),
            ("GET", f"{V1}/ping", self.keyed(self.v1_ping)),
            ("GET", f"{V1}/projects", self.keyed(self.v1_projects, "projects.read")),
            ("GET", f"{V1}/directions", self.keyed(self.v1_directions, "projects.read")),
        ):
            server.route(method, path, handler)
        # Ключи интеграций 0.6.0: у каждой системы свой ключ и права; отозванный ключ — как неверный (401);
        # budget — сколько запросов по ключу ещё до 429
        self.keys = {KEY: {"name": "Дашборды компании", "scopes": ["projects.read", "projects.stats"],
                           "revoked": False}}
        self.budget: int | None = None

    def sid(self, request: Request) -> str | None:
        for part in (request.headers.get("cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE and value in self.sessions:
                return value
        return None

    def csrf(self, request):
        sid = self.sid(request) or pysecrets.token_hex(8)
        self.sessions.setdefault(sid, {"csrf": pysecrets.token_hex(8), "user": None})
        return 200, {"csrfToken": self.sessions[sid]["csrf"]}, {"Set-Cookie": f"{COOKIE}={sid}; Path=/; HttpOnly"}

    def _csrf_error(self, request):
        sid = self.sid(request)
        if sid is None or self.break_csrf or request.headers.get("x-csrf-token") != self.sessions[sid]["csrf"]:
            return 400, {"error": "csrf_error", "message": "Сессия устарела — обновите страницу"}
        return None

    def login(self, request):
        error = self._csrf_error(request)
        if error:
            return error
        body = request.json()
        if body.get("login") != self.account["login"] or body.get("password") != self.account["password"]:
            return 401, {"error": "invalid_credentials", "message": "Неверный логин или пароль"}
        sid = self.sid(request)
        session = self.sessions.pop(sid)
        new = pysecrets.token_hex(8)
        self.sessions[new] = {**session, "user": self.account["login"]}
        self.logins += 1
        user = {k: v for k, v in self.account.items() if k != "password"}
        return 200, {"user": user}, {"Set-Cookie": f"{COOKIE}={new}; Path=/; HttpOnly"}

    def logout(self, request):
        error = self._csrf_error(request)
        if error:
            return error
        self.sessions.pop(self.sid(request))
        self.logouts += 1
        return 200, {"ok": True}

    def ready(self, request):
        if self.ready_status != 200:
            return self.ready_status, {"status": "unavailable"}, {"Retry-After": "0"}
        return 200, {"status": "ok", "schema": "0021_access", "version": "0.5.1"}

    def guarded(self, handler):
        def wrapper(request):
            sid = self.sid(request)
            if sid is None or self.sessions[sid]["user"] is None:
                return 401, {"error": "auth_required", "message": "Требуется вход в систему"}
            return handler(request)
        return wrapper

    def keyed(self, handler, scope=None):
        """Как integration_key_required «Пульса»: действующий ключ, право, предел частоты на ключ."""
        def wrapper(request):
            assert "cookie" not in request.headers, "режим ключа — без cookie"
            if self.budget is not None:
                if self.budget <= 0:
                    return 429, {"error": "too_many_requests", "message": "Слишком много попыток — подождите минуту"}, \
                        {"Retry-After": "0"}
                self.budget -= 1
            header = request.headers.get("authorization") or ""
            key = self.keys.get(header[7:]) if header.startswith("Bearer ") else None
            if key is None or key["revoked"]:
                return 401, {"error": "unauthorized",
                             "message": "Нужен действующий ключ «Пульса» (Authorization: Bearer puls_…) — его "
                                        "выпускает администратор «Пульса»: Администрирование → Интеграции → Ключи "
                                        "доступа"}
            if scope and scope not in key["scopes"]:
                return 403, {"error": "insufficient_scope", "message": f"У ключа «{key['name']}» нет права {scope}"}
            return handler(request, key)
        return wrapper

    def v1_ping(self, request, key):
        return 200, {"ok": True, "app": "puls", "name": "Пульс Проекта", "version": "0.6.0",
                     "key": {"name": key["name"], "scopes": list(key["scopes"])}}

    def v1_projects(self, request, key):
        names = {d["id"]: d["name"] for d in self.directions}
        stats = "projects.stats" in key["scopes"]
        limit = max(1, min(200, int((request.query.get("limit") or ["50"])[0])))
        out = []
        for p in self.projects[:limit]:
            s = p.get("stats") or {}
            data = {"id": p["id"], "title": p["title"], "subtitle": "", "direction": names.get(p["directionId"]),
                    "path": f"/projects/{p['id']}", "progress": s.get("progress", 0), "start": s.get("start"),
                    "end": s.get("end"), "overdue": s.get("overdue", 0), "total": s.get("total", 0),
                    "done": s.get("done", 0), "planId": s.get("planId"), "planTitle": s.get("planTitle"),
                    "nextMilestone": None}
            if stats:
                data.update(inwork=s.get("inwork", 0), blocked=s.get("blocked", 0), updatedAt="2026-11-01T10:00:00Z",
                            directionInfo={"id": p["directionId"], "name": names[p["directionId"]]}
                            if p["directionId"] in names else None, planWindow=None)
            out.append(data)
        return 200, {"projects": out, "userFound": None}

    def v1_directions(self, request, key):
        counts: dict = {}
        for p in self.projects:
            counts[p["directionId"]] = counts.get(p["directionId"], 0) + 1
        return 200, {"directions": [{"id": d["id"], "name": d["name"], "color": d.get("color", "gray"), "position": i,
                                     "projects": counts.get(d["id"], 0)} for i, d in enumerate(self.directions)],
                     "withoutDirection": counts.get(None, 0), "userFound": None}


@pytest.fixture()
def fake(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.delenv("PULS_ALLOWED_HOSTS", raising=False)
    from app.integrations.connectors import puls

    monkeypatch.setattr(puls, "today_local", lambda: TODAY)
    server = FakeServer()
    fake = FakePuls(server)
    with server:
        yield fake


def _create(admin, fake, *, secrets=None, **config) -> dict:
    body = {"kind": "puls", "name": "Пульс",
            "config": {"base_url": fake.server.url, "login": "svc", "directions": MAPPING, **config},
            "secrets": secrets or {"password": PASSWORD}}
    response = admin.post("/api/integrations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _run(admin, item) -> dict:
    response = admin.post(f"/api/integrations/{item['id']}/run", json={"action": "indicators"})
    assert response.status_code == 200, response.text
    return assert_counters_labelled(response.json(), "puls")


def _values(db) -> dict[tuple[str, str], IndicatorValue]:
    db.expire_all()
    departments = {d.id: d.code or d.name for d in db.scalars(select(Department))}
    keys = {i.id: i.key for i in db.scalars(select(Indicator))}
    return {(departments[v.department_id], keys[v.indicator_id]): v for v in db.scalars(select(IndicatorValue))
            if keys[v.indicator_id].startswith("puls.")}


# ---------------------------------------------------------------- настройки и проверка

def test_kind_and_mapping_validation(admin, fake):
    meta = {k["kind"]: k for k in admin.get("/api/integrations/kinds").json()}["puls"]
    fields = {f["key"]: f for f in meta["fields"]}
    mode = fields["mode"]
    assert mode["default"] == "key" and [(o["value"], o["label"]) for o in mode["options"]] == [
        ("key", "Ключ интеграции (Пульс 0.6.0 и новее)"), ("session", "Служебная учётная запись (для версий до 0.6.0)")]
    assert not any("поддержит несколько ключей" in (f["hint"] or "") for f in meta["fields"])
    assert fields["api_key"]["secret"] and fields["api_key"]["show_if"] == {"mode": ["key"]}
    for text in ("«Интеграции → Ключи доступа»", "«Дашборды компании»", "projects.read", "projects.stats"):
        assert text in fields["api_key"]["hint"], text
    assert fields["login"]["show_if"] == {"mode": ["session"]} and "до 0.6.0" in fields["login"]["hint"]
    assert meta["actions"][0]["label"] == "Обновить показатели проектов"
    bad = admin.post("/api/integrations", json={"kind": "puls", "config": {"base_url": fake.server.url, "login": "svc",
                                                                           "directions": "Внедрение PROJ"},
                                                "secrets": {"password": PASSWORD}})
    assert bad.status_code == 422 and "строка 1" in bad.json()["detail"] and "config.directions" in bad.json()["fields"]
    dup = admin.post("/api/integrations", json={"kind": "puls", "config": {
        "base_url": fake.server.url, "login": "svc", "directions": "Внедрение = PROJ\n# комментарий\nвнедрение → IT"},
        "secrets": {"password": PASSWORD}})
    assert dup.status_code == 422 and "уже указано в строке 1" in dup.json()["detail"]
    key_only = admin.post("/api/integrations", json={"kind": "puls", "config": {"base_url": fake.server.url,
                                                                                "mode": "key"}})
    assert key_only.status_code == 422 and "secrets.api_key" in key_only.json()["fields"]


def test_check_session_reads_version_and_directions(admin, fake):
    item = _create(admin, fake)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"], check
    assert check["message"] == ("Подключено к «Пульс проекта» 0.5.1 (служебная учётная запись Наблюдатель дашбордов): "
                                "проектов 6, направлений 3, сопоставлено 2; без подразделения (в корень структуры): "
                                "Маркетинг")
    details = check["details"]
    assert details["schema"] == "0021_access" and details["user"]["role"] == "viewer"
    assert details["directions"] == [
        {"id": 1, "name": "Внедрение", "projects": 2, "department": "АЛМИ Партнер / Проектная служба"},
        {"id": 2, "name": "Разработка", "projects": 2,
         "department": "АЛМИ Партнер / Техническая дирекция / ИТ-служба"},
        {"id": 3, "name": "Маркетинг", "projects": 1, "department": None}]
    assert fake.logins == 1 and fake.logouts == 1
    assert PASSWORD not in json.dumps(check, ensure_ascii=False)


def test_check_reports_mapping_problems(admin, fake):
    item = _create(admin, fake, directions="Внедрение = NOPE\nПродажи = PROJ")
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"] and "Проверьте" not in check["message"]
    assert check["warnings"] == ["сопоставление, строка 1 («Внедрение»): подразделение «NOPE» не найдено",
                                 "направления «Продажи» нет в «Пульсе»"]
    assert "problems" not in check["details"]


def test_check_failures(admin, fake):
    item = _create(admin, fake)
    admin.patch(f"/api/integrations/{item['id']}", json={"secrets": {"password": "не тот"}})
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["message"] == ("«Пульс проекта» отклонила вход: неверный логин или пароль "
                                                    "служебной учётной записи")
    assert fake.logouts == 1
    admin.patch(f"/api/integrations/{item['id']}", json={"secrets": {"password": PASSWORD}})
    fake.break_csrf = True
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and "CSRF" in check["message"] and "Сессия устарела" in check["message"]
    fake.break_csrf = False
    fake.ready_status = 503
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and "вернула ошибку 503" in check["message"]
    assert fake.logouts == 2, "выход — и когда «Пульс» не готов"


# ---------------------------------------------------------------- показатели

def test_run_creates_indicators_and_writes_values(admin, fake, db):
    item = _create(admin, fake)
    run = _run(admin, item)
    assert run["status"] == "ok", run
    summary = run["summary"]
    assert summary["indicators_created"] == 5 and summary["projects"] == 6 and summary["mapped"] == 4
    assert summary["projects_red"] == 2 and summary["projects_yellow"] == 2 and summary["projects_green"] == 1
    assert summary["projects_gray"] == 1 and summary["units"] == 4
    assert run["message"].startswith("Показатели проектов за ноябрь 2026: проектов 6 (в работе 4, красных 2, жёлтых 2)")
    catalog = {i.key: i for i in db.scalars(select(Indicator).where(Indicator.key.like("puls.%")))}
    assert set(catalog) == {"puls.projects", "puls.overdue", "puls.on_time_share", "puls.progress", "puls.blocked"}
    share = catalog["puls.on_time_share"]
    assert (share.direction, share.rule_type, share.green_threshold, share.yellow_threshold) == \
        ("higher_is_better", "threshold", 90, 70)
    assert all(i.data_class == "operational" and i.source_type == "manual" and i.owner_service == "project_product"
               for i in catalog.values())
    values = _values(db)
    expected = {
        ("PROJ", "puls.projects"): 2, ("PROJ", "puls.overdue"): 1, ("PROJ", "puls.blocked"): 1,
        ("PROJ", "puls.progress"): 50, ("PROJ", "puls.on_time_share"): 50,
        ("IT", "puls.projects"): 1, ("IT", "puls.overdue"): 0, ("IT", "puls.progress"): 50,
        ("IT", "puls.on_time_share"): 100, ("TECHDIR", "puls.projects"): 1,
        ("ALMI", "puls.projects"): 4, ("ALMI", "puls.overdue"): 2, ("ALMI", "puls.blocked"): 1,
        ("ALMI", "puls.progress"): 45, ("ALMI", "puls.on_time_share"): 50,
    }
    for cell, value in expected.items():
        assert values[cell].value == value, cell
    sample = values[("PROJ", "puls.overdue")]
    assert sample.comment == "из «Пульса проекта»" and sample.period == date(2026, 11, 1) and sample.source == "import"
    assert ("MKT", "puls.projects") not in values, "несопоставленные проекты — в корне структуры"
    flagged = {f["project"]: f for f in summary["details"]["flagged"]}
    assert flagged["Внедрение Б"]["light"] == "red" and flagged["Внедрение Б"]["reason"] == "просроченных задач: 2"
    assert flagged["Маркетинг осень"]["reason"] == "срок окончания 15.10.2026 прошёл, прогресс 30 %"
    assert flagged["Маркетинг осень"]["department"] == "АЛМИ Партнер"
    assert flagged["Внедрение А"]["light"] == "yellow" and flagged["Разработка API"]["reason"].startswith(
        "до окончания 8 дн.")
    assert fake.logouts == 1
    # Повторный запуск: показатели не создаются заново, значения без изменений
    again = _run(admin, item)
    assert again["summary"]["indicators_created"] == 0 and again["summary"]["values_create"] == 0
    assert again["summary"]["values_unchanged"] == len(values)
    fake.projects[1]["stats"]["overdue"] = 0
    third = _run(admin, item)
    assert third["summary"]["values_update"] > 0
    assert _values(db)[("PROJ", "puls.on_time_share")].value == 100


def test_run_report_shows_traffic_light(admin, fake, db):
    item = _create(admin, fake)
    _run(admin, item)
    report = admin.get("/api/reports/scorecard", params={"period": "2026-11"})
    assert report.status_code == 200, report.text
    proj = next(u for u in report.json()["units"] if u["code"] == "PROJ")
    cells = proj["cells"]
    assert cells["puls.on_time_share"]["status"] == "red", "доля в срок 50 % — меньше 70 %"
    assert cells["puls.overdue"]["status"] == "yellow" and cells["puls.projects"]["status"] == "gray"
    assert cells["puls.overdue"]["comment"] == "из «Пульса проекта»"
    assert proj["explanation"]["text"].startswith("Красный: Проекты в срок в «Проектная служба» — 50%")


def test_run_skips_disabled_indicator_and_bad_mapping(admin, fake, db):
    item = _create(admin, fake)
    _run(admin, item)
    db.execute(update(Indicator).where(Indicator.key == "puls.progress").values(is_active=False))
    db.commit()
    admin.patch(f"/api/integrations/{item['id']}", json={"config": {"directions": MAPPING + "\nМаркетинг = NOPE"}})
    run = _run(admin, item)
    assert run["status"] == "partial"
    notes = run["summary"]["details"]["notes"]
    assert "показатель puls.progress выключен — не обновляется" in notes
    assert "строка 3 («Маркетинг»): подразделение «NOPE» не найдено" in notes


def test_run_failures_log_out(admin, fake, db):
    item = _create(admin, fake)
    fake.server.route("GET", "/api/projects", lambda r: (500, {"error": "internal", "message": "Сбой"}))
    run = _run(admin, item)
    assert run["status"] == "error" and "«Пульс проекта» вернула ошибку 500 (/api/projects)" in run["error"]
    assert fake.logouts == 1
    assert db.scalar(select(Indicator).where(Indicator.key == "puls.projects")) is None


def test_unit_without_projects_in_work_gets_progress_and_share_cleared(admin, fake, db):
    item = _create(admin, fake)
    _run(admin, item)
    values = _values(db)
    assert values[("PROJ", "puls.progress")].value == 50 and values[("PROJ", "puls.on_time_share")].value == 50
    # Оба проекта внедрения завершены: в работе у «Проектной службы» ничего нет
    for project in fake.projects[:2]:
        project["stats"].update(done=project["stats"]["total"], overdue=0, blocked=0, progress=100)
    run = _run(admin, item)
    assert run["status"] == "ok", run
    assert run["summary"]["values_cleared"] == 2 and "очищено 2 (нет проектов в работе)" in run["message"]
    values = _values(db)
    assert ("PROJ", "puls.progress") not in values and ("PROJ", "puls.on_time_share") not in values, \
        "среднего прогресса и доли в срок без проектов в работе нет — старое значение не остаётся"
    assert values[("PROJ", "puls.projects")].value == 0 and values[("PROJ", "puls.overdue")].value == 0, \
        "количества — ноль, а не пусто"
    assert values[("ALMI", "puls.progress")].value == 40, "у корня проекты в работе остались"
    from app.models import AuditEntry

    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "indicator_value",
                                               AuditEntry.action == "import").order_by(AuditEntry.id.desc()))
    assert "очищено 2" in entry.summary and entry.username == "Подключение «Пульс»"
    again = _run(admin, item)
    assert again["summary"]["values_cleared"] == 0 and again["summary"]["values_create"] == 0
    assert "очищено" not in again["message"]


def test_indicator_name_taken_gets_puls_suffix(admin, fake, db):
    taken = admin.post("/api/reports/indicators", json={"key": "ops.projects", "name": "Проекты в работе",
                                                        "owner_service": "project_product"})
    assert taken.status_code == 201, taken.text
    run = _run(admin, _create(admin, fake))
    assert run["status"] == "ok" and run["summary"]["indicators_created"] == 5
    assert db.scalar(select(Indicator.name).where(Indicator.key == "puls.projects")) == "Проекты в работе («Пульс»)"


# ================================================================ ключ интеграции («Пульс» 0.6.0)

def _create_key(admin, fake, **config) -> dict:
    body = {"kind": "puls", "name": "Пульс", "config": {"base_url": fake.server.url, "directions": MAPPING, **config},
            "secrets": {"api_key": KEY}}
    response = admin.post("/api/integrations", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["config"]["mode"] == "key", "новое подключение — по ключу"
    return response.json()


def test_new_connection_defaults_to_key_and_stored_session_keeps_working(admin, fake, db):
    bare = admin.post("/api/integrations", json={"kind": "puls", "config": {"base_url": fake.server.url}})
    assert bare.status_code == 422 and "secrets.api_key" in bare.json()["fields"]
    legacy = _create(admin, fake)
    assert legacy["config"]["mode"] == "session", "логин без режима — служебная учётная запись, как раньше"
    from app.core import db as core_db
    from app.models import Integration

    stored = {k: v for k, v in legacy["config"].items() if k != "mode"}
    with core_db.SessionLocal() as session:
        session.execute(update(Integration).where(Integration.id == legacy["id"]).values(config=stored))
        session.commit()
    assert admin.get(f"/api/integrations/{legacy['id']}").json()["config"]["mode"] == "session"
    assert admin.post(f"/api/integrations/{legacy['id']}/check").json()["ok"]
    assert _run(admin, {"id": legacy["id"]})["summary"]["details"]["mode"] == "session"


def test_key_check_reports_key_rights_and_directions_by_id(admin, fake):
    item = _create_key(admin, fake)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"], check
    assert check["message"] == ("Подключено к «Пульс проекта» 0.6.0 (ключ интеграции «Дашборды компании», права: "
                                "projects.read, projects.stats): проектов 6, направлений 3, сопоставлено 2; без "
                                "подразделения (в корень структуры): Маркетинг")
    details = check["details"]
    assert details["key"] == {"name": "Дашборды компании", "scopes": ["projects.read", "projects.stats"]}
    assert details["stats"] is True and details["projects"] == 6 and details["without_direction"] == 1
    assert check["warnings"] == [] and "total" not in details and "limited" not in details
    assert details["directions"] == [
        {"id": 1, "name": "Внедрение", "projects": 2, "department": "АЛМИ Партнер / Проектная служба"},
        {"id": 2, "name": "Разработка", "projects": 2,
         "department": "АЛМИ Партнер / Техническая дирекция / ИТ-служба"},
        {"id": 3, "name": "Маркетинг", "projects": 1, "department": None}], "направление 2 сопоставлено по id"
    paths = [r.path for r in fake.server.requests]
    assert paths == [f"{V1}/ping", f"{V1}/directions"], "проверке хватает числа проектов из направлений"
    assert all(r.headers["authorization"] == f"Bearer {KEY}" for r in fake.server.requests)
    assert fake.logins == 0 and KEY not in json.dumps(check, ensure_ascii=False)


def test_key_check_without_stats_warns_and_flags_id_lines(admin, fake):
    fake.keys[KEY]["scopes"] = ["projects.read"]
    item = _create_key(admin, fake)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"]
    assert check["message"] == ("Подключено к «Пульс проекта» 0.6.0 (ключ интеграции «Дашборды компании», права: "
                                "projects.read): проектов 6, направлений 3, сопоставлено 2; без подразделения (в "
                                "корень структуры): Маркетинг"), "замечания — отдельным списком"
    assert check["warnings"] == [
        "у ключа нет права «Показатели проектов» (projects.stats): «Пульс» не отдаёт задачи «в работе» и "
        "«заблокировано» и id направлений — puls.blocked не обновляется, направления сопоставляются только по "
        "названию",
        "сопоставление, строка 2 («2»): без права projects.stats направление сопоставляется только по названию — "
        "укажите «Разработка»"]
    assert check["details"]["stats"] is False and "warnings" not in check["details"]


def test_key_check_failures(admin, fake):
    item = _create_key(admin, fake)
    fake.keys[KEY]["revoked"] = True
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["details"]["code"] == "auth"
    assert check["message"].startswith("«Пульс проекта» не приняла ключ интеграции (401): Нужен действующий ключ "
                                       "«Пульса»"), "отозванный ключ «Пульс» не отличает от неверного"
    fake.keys[KEY].update(revoked=False, scopes=[])
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["message"] == ("У ключа «Дашборды компании» нет права «Проекты и планы» "
                                                    "(projects.read) — добавьте его ключу: «Пульс» → «Интеграции → "
                                                    "Ключи доступа»")
    fake.keys[KEY]["scopes"] = ["projects.read", "projects.stats"]
    admin.patch(f"/api/integrations/{item['id']}", json={"secrets": {"api_key": "not-a-key"}})
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["message"] == "Ключ интеграции «Пульса» начинается с puls_ — проверьте ключ"
    admin.patch(f"/api/integrations/{item['id']}", json={"secrets": {"api_key": KEY}})
    fake.budget = 0
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["details"]["code"] == "rate_limited"
    assert check["message"] == ("Ключ интеграции превысил лимит частоты запросов «Пульс проекта» (429) — повторите "
                                "позже")
    fake.budget = 1
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["message"].startswith("Ключ «Дашборды компании» превысил лимит частоты"), "после ping — по названию"
    fake.budget = None
    # «Пульс» 0.5.x: ключ один (для «По Делу»), прав в ответе ping нет
    fake.server.route("GET", f"{V1}/ping", fake.keyed(lambda r, key: (200, {"ok": True, "app": "puls",
                                                                            "name": "Пульс Проекта",
                                                                            "version": "0.5.1"})))
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["details"]["code"] == "no_api" and "0.5.1" in check["message"]
    assert "выберите режим «Служебная учётная запись (для версий до 0.6.0)»" in check["message"]
    # Ещё старше — API ключей нет вовсе (404: и без кода, и «Не найдено» Flask)
    for answer in ((404, b"<html>Not Found</html>"), (404, {"error": "not_found", "message": "Не найдено"})):
        fake.server.route("GET", f"{V1}/ping", lambda r, a=answer: a)
        check = admin.post(f"/api/integrations/{item['id']}/check").json()
        assert not check["ok"] and check["details"]["code"] == "no_api"
        assert "«Пульс» старше 0.6.0 или адрес указан неверно" in check["message"]


def test_run_key_mode_with_stats_matches_session_values(admin, fake, db):
    item = _create_key(admin, fake)
    run = _run(admin, item)
    assert run["status"] == "ok", run
    summary = run["summary"]
    assert summary["projects"] == 6 and summary["mapped"] == 4 and summary["projects_yellow"] == 2
    assert "limits" not in summary["details"] and summary["details"]["stats"] is True
    assert "puls.blocked не обновляется" not in run["message"]
    values = _values(db)
    expected = {("PROJ", "puls.projects"): 2, ("PROJ", "puls.overdue"): 1, ("PROJ", "puls.blocked"): 1,
                ("PROJ", "puls.progress"): 50, ("IT", "puls.projects"): 1, ("IT", "puls.on_time_share"): 100,
                ("ALMI", "puls.projects"): 4, ("ALMI", "puls.blocked"): 1, ("ALMI", "puls.progress"): 45}
    for cell, value in expected.items():
        assert values[cell].value == value, cell
    flagged = {f["project"]: f for f in summary["details"]["flagged"]}
    assert flagged["Внедрение А"]["reason"] == "заблокированных задач: 1", "blocked — из projects.stats"
    query = next(r.query for r in fake.server.requests if r.path == f"{V1}/projects")
    assert query == {"limit": ["200"]}
    assert fake.logins == 0


def test_run_key_mode_maps_by_direction_id_only_with_stats(admin, fake, db):
    fake.directions[1]["name"] = "Разработка ПО"     # id тот же — сопоставление «2 = …» по id не ломается
    item = _create_key(admin, fake)
    run = _run(admin, item)
    assert run["status"] == "ok" and _values(db)[("IT", "puls.projects")].value == 1
    fake.keys[KEY]["scopes"] = ["projects.read"]
    run = _run(admin, item)
    assert run["status"] == "partial", "строка по id без projects.stats не работает — это нужно поправить"
    assert run["summary"]["mapped"] == 2 and run["summary"]["details"]["notes"] == [
        "строка 2 («2»): без права projects.stats направление сопоставляется только по названию — укажите "
        "«Разработка ПО»"]
    assert "Без права" not in run["message"] and "У ключа нет права «Показатели проектов»" in run["message"]


def test_run_key_mode_without_stats_skips_blocked(admin, fake, db):
    fake.keys[KEY]["scopes"] = ["projects.read"]
    item = _create_key(admin, fake, directions="Внедрение = PROJ")
    run = _run(admin, item)
    assert run["status"] == "ok", "ограничение ключа — сведения, а не ошибка"
    assert run["summary"]["details"]["limits"][0].startswith("у ключа нет права «Показатели проектов»")
    assert "puls.blocked не обновляется" in run["message"]
    values = _values(db)
    assert ("PROJ", "puls.blocked") not in values and values[("PROJ", "puls.projects")].value == 2
    assert values[("ALMI", "puls.projects")].value == 4
    flagged = {f["project"]: f for f in run["summary"]["details"]["flagged"]}
    assert "Внедрение А" not in flagged, "без числа заблокированных задач светофор — только по срокам"
    assert flagged["Внедрение Б"]["light"] == "red"


def test_key_mode_warns_about_200_projects(admin, fake, db):
    fake.projects += [_project(100 + n, f"Проект {n}", 3, total=2, done=1, progress=50, end="2027-06-30")
                      for n in range(244)]
    item = _create_key(admin, fake)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"] and "проектов в «Пульсе» 250, а API отдаёт не больше 200 — показатели будут посчитаны по " \
        "первым 200" in check["warnings"]
    run = _run(admin, item)
    assert run["status"] == "ok" and run["summary"]["projects"] == 200
    assert run["message"].endswith(". Возможно, проектов больше 200 — показатели посчитаны по первым 200")
    assert run["summary"]["details"]["limits"] == ["возможно, проектов больше 200 — показатели посчитаны по первым 200"]


def test_puls_key_never_logged_stored_or_returned(admin, fake, db, caplog):
    from app.models import AuditEntry, Integration, IntegrationRun

    caplog.set_level(logging.DEBUG)
    item = _create_key(admin, fake)
    responses = [admin.post(f"/api/integrations/{item['id']}/check").text]
    runs = [_run(admin, item)]
    fake.keys[KEY]["revoked"] = True
    runs.append(_run(admin, item))
    responses.append(admin.post(f"/api/integrations/{item['id']}/check").text)
    assert runs[1]["status"] == "error"
    responses += [json.dumps(runs, ensure_ascii=False), admin.get(f"/api/integrations/{item['id']}").text,
                  admin.get(f"/api/integrations/{item['id']}/runs").text]
    db.expire_all()
    row = db.get(Integration, item["id"])
    stored = [row.last_error, json.dumps(row.state, ensure_ascii=False), json.dumps(row.config, ensure_ascii=False)]
    for run in db.scalars(select(IntegrationRun).where(IntegrationRun.integration_id == item["id"])):
        stored += [run.message, run.error, json.dumps(run.summary, ensure_ascii=False)]
    stored += [f"{e.summary} {json.dumps(e.after, ensure_ascii=False)}"
               for e in db.scalars(select(AuditEntry).where(AuditEntry.entity_type == "integration"))]
    for where, content in (("журнал сервера", caplog.text), *(("ответ API", t) for t in responses),
                           *(("база", t) for t in stored)):
        assert KEY not in content and KEY[5:] not in content, f"{where}: {content[:300]}"
