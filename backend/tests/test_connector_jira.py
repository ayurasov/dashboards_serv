"""Коннектор Jira (ADR-0011): поддельная Jira (Server — REST API 2, startAt и validateQuery; Cloud — REST API 3,
/search/jql и nextPageToken) на настоящем HTTP-сервере, правила JQL, значения по подразделениям и месяцам,
признаки качества данных, повторный запуск без изменений, ошибки входа (401, 403, CAPTCHA) и JQL."""
from __future__ import annotations

import base64
import json
import re
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.core.errors import ValidationFailed
from app.integrations.connectors import jira
from app.integrations.connectors.jira import JiraConnector
from app.models import AuditEntry, Department, Indicator, IndicatorValue
from app.services import reports
from tests.conftest import assert_counters_labelled
from tests.fake_http import FakeServer

TOKEN = "jira-pat-0123456789XYZ"
H = 3600
CUR = reports.current_period()
PREV = reports.add_months(CUR, -1)


def day(month: date, n: int) -> str:
    return (month + timedelta(days=n - 1)).isoformat()


def default_issues() -> list[dict]:
    prev_last = reports.month_end(PREV).isoformat()
    return [
        {"key": "SUP-1", "project": "SUP", "component": "AlterOS", "resolved": day(CUR, 1), "category": "done",
         "timespent": 2 * H, "timeoriginalestimate": 3 * H, "timeestimate": 0},
        {"key": "SUP-2", "project": "SUP", "component": "AlterOS", "resolved": day(CUR, 1), "category": "done",
         "timespent": H, "timeoriginalestimate": H, "timeestimate": H},                     # закрыта с остатком
        {"key": "SUP-3", "project": "SUP", "component": "AlterOS", "resolved": day(PREV, 3), "category": "done",
         "timespent": 5 * H, "timeoriginalestimate": 4 * H, "timeestimate": 0},             # перерасход
        {"key": "SUP-4", "project": "SUP", "component": "AlterOffice", "resolved": day(PREV, 10), "category": "done",
         "timespent": H, "timeoriginalestimate": 2 * H, "timeestimate": 0},
        {"key": "SUP-5", "project": "SUP", "component": "AlterOffice", "resolved": None,
         "category": "indeterminate"},                                                       # без оценки
        {"key": "SUP-6", "project": "SUP", "component": "AlterOS", "resolved": f"{prev_last}T23:10", "category": "done",
         "timespent": H, "timeoriginalestimate": H, "timeestimate": 0},                     # последний день месяца
        {"key": "IT-1", "project": "IT", "resolved": day(CUR, 1), "category": "done", "timespent": 3 * H,
         "timeoriginalestimate": 2 * H, "customfield_10050": 2.5},                          # перерасход
        {"key": "IT-2", "project": "IT", "resolved": day(CUR, 1), "category": "done", "timespent": 5400,
         "customfield_10050": 1},
        {"key": "IT-3", "project": "IT", "resolved": day(PREV, 20), "category": "done", "timespent": 4 * H},
    ]


class JqlError(Exception):
    pass


JQL_FIELDS = {"project", "component", "statuscategory", "resolved", "key"}
COND = re.compile(r"^\s*(\w+)\s*(!=|>=|<=|=|<|>)\s*(.+?)\s*$")


def jql_match(issue: dict, jql: str) -> bool:
    """Учебный JQL: условия через AND, операторы = != >= <= < >; даты — по первым 10 символам."""
    for part in re.split(r"\s+AND\s+", jql.strip(), flags=re.IGNORECASE):
        m = COND.match(part)
        if not m:
            raise JqlError(f"Error in the JQL Query: Expecting operator but got '{part}'.")
        name, op, raw = m.group(1).lower(), m.group(2), m.group(3).strip()
        if name not in JQL_FIELDS:
            raise JqlError(f"Field '{m.group(1)}' does not exist or you do not have permission to view it.")
        value = raw[1:-1].replace('\\"', '"') if raw.startswith('"') and raw.endswith('"') else raw
        if name == "statuscategory":
            actual = {"done": "done", "indeterminate": "in progress", "new": "to do"}[issue.get("category", "new")]
            value = value.lower()
        elif name == "resolved":
            actual = (issue.get("resolved") or "")[:10]
            if not actual:
                return False
        else:
            actual = issue.get(name)
        ok = {"=": actual == value, "!=": actual != value, ">=": actual >= value, "<=": actual <= value,
              "<": actual < value, ">": actual > value}[op]
        if not ok:
            return False
    return True


class FakeJira:
    """Jira Server (REST API 2) или Cloud (REST API 3): вход, myself, serverInfo, поиск постранично."""

    def __init__(self, mode: str = "server", login: str = "", token: str = TOKEN, page: int = 2):
        self.mode, self.login, self.token, self.page = mode, login, token, page
        self.issues = default_issues()
        self.captcha = False
        self.forbidden = False
        self.deployment = "Cloud" if mode == "cloud" else "Server"
        self.server = FakeServer()
        self.searches: list[dict] = []
        for v in ("2", "3"):
            self.server.route("GET", f"/rest/api/{v}/myself", self.guard(v, self.myself))
            self.server.route("GET", f"/rest/api/{v}/serverInfo", self.guard(v, self.server_info))
        self.server.route("POST", "/rest/api/2/search", self.guard("2", self.search))
        self.server.route("POST", "/rest/api/3/search/jql", self.guard("3", self.search))

    def __enter__(self) -> FakeJira:
        self.server.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.server.stop()

    @property
    def url(self) -> str:
        return self.server.url

    @property
    def requests(self):
        return self.server.requests

    def guard(self, version: str, handler):
        def wrapped(request):
            if self.captcha:
                return 403, {"errorMessages": ["Forbidden"]}, {
                    "X-Authentication-Denied-Reason": "CAPTCHA_CHALLENGE; login-url=/login.jsp"}
            header = request.headers.get("authorization", "")
            if self.mode == "server":
                ok = header == f"Bearer {self.token}"
            else:
                ok = header == "Basic " + base64.b64encode(f"{self.login}:{self.token}".encode()).decode()
            if not ok:
                return 401, {"errorMessages": ["You are not authenticated"]}
            if self.forbidden:
                return 403, {"errorMessages": ["Browse projects permission required"]}
            if version != ("3" if self.mode == "cloud" else "2"):
                return 404, {"errorMessages": ["wrong api version"]}
            return handler(request)
        return wrapped

    def myself(self, _request):
        return 200, {"name": self.login or "svc-dash", "displayName": "Тестовый Пользователь",
                     "emailAddress": "svc@company.ru"}

    def server_info(self, _request):
        return 200, {"version": "1001.0.0" if self.deployment == "Cloud" else "9.12.2",
                     "deploymentType": self.deployment}

    def issue_json(self, issue: dict, fields: list[str]) -> dict:
        out = {}
        for name in fields:
            if name == "status":
                category = issue.get("category", "new")
                out[name] = {"name": category, "statusCategory": {"key": category}}
            else:
                out[name] = issue.get(name)
        return {"id": str(10000 + self.issues.index(issue)), "key": issue["key"], "fields": out}

    def search(self, request):
        body = request.json()
        self.searches.append(body)
        try:
            found = [i for i in self.issues if jql_match(i, body["jql"])]
        except JqlError as exc:
            return 400, {"errorMessages": [str(exc)], "errors": {}}
        start = int(body.get("nextPageToken") or 0) if self.mode == "cloud" else int(body.get("startAt") or 0)
        size = min(int(body.get("maxResults") or 50), self.page)
        page = [self.issue_json(i, body.get("fields") or []) for i in found[start:start + size]]
        if self.mode == "cloud":
            more = start + size < len(found)
            return 200, {"issues": page, **({"nextPageToken": str(start + size)} if more else {}), "isLast": not more}
        return 200, {"issues": page, "startAt": start, "maxResults": size, "total": len(found)}


@pytest.fixture()
def server_jira(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.delenv("JIRA_ALLOWED_HOSTS", raising=False)
    with FakeJira() as fake:
        yield fake


@pytest.fixture()
def cloud_jira(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    with FakeJira(mode="cloud", login="svc@company.ru") as fake:
        yield fake


RESOLVED = 'project = SUP AND component = "{unit_code}" AND resolved >= "{month_start}" ' \
           'AND resolved < "{next_month_start}"'
RULES = [
    {"indicator": "jira.resolved", "name": "Решено задач в Jira", "measure": "count", "jql": RESOLVED,
     "units": {"SUP-OS": "AlterOS", "SUP-OFFICE": "AlterOffice"}, "direction": "higher_is_better",
     "green": 2, "yellow": 1},
    {"indicator": "jira.spent", "name": "Затрачено в Jira", "measure": "sum", "field": "timespent",
     "unit_jql": {"IT": 'project = IT AND resolved >= "{month_start}" AND resolved < "{next_month_start}"'}},
    {"indicator": "jira.open", "name": "Открытые задачи Jira", "measure": "count", "direction": "lower_is_better",
     "unit_jql": {"TECH": "project = SUP AND statusCategory != Done"}},
]


def create(admin, fake, rules=None, **config) -> dict:
    body = {"kind": "jira", "name": "Jira", "config": {"base_url": fake.url, "instance": fake.mode, "login": fake.login,
                                                        "rules": rules if rules is not None else RULES, **config},
            "secrets": {"token": fake.token}}
    response = admin.post("/api/integrations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def run(admin, item, action="refresh") -> dict:
    response = admin.post(f"/api/integrations/{item['id']}/run", json={"action": action})
    assert response.status_code == 200, response.text
    return assert_counters_labelled(response.json(), "jira")


def values(db, key: str) -> dict[tuple[str, str], tuple[float, str]]:
    db.expire_all()
    rows = db.execute(select(Department.code, IndicatorValue.period, IndicatorValue.value, IndicatorValue.comment)
                      .join(Indicator, Indicator.id == IndicatorValue.indicator_id)
                      .join(Department, Department.id == IndicatorValue.department_id)
                      .where(Indicator.key == key)).all()
    return {(code, reports.period_key(period)): (value, comment) for code, period, value, comment in rows}


def import_audits(db) -> int:
    return db.scalar(select(func.count()).select_from(AuditEntry).where(AuditEntry.entity_type == "indicator_value",
                                                                       AuditEntry.action == "import"))


# ---------------------------------------------------------------- описание и настройки

def test_kind_is_described_in_russian(admin):
    kinds = {k["kind"]: k for k in admin.get("/api/integrations/kinds").json()}
    meta = kinds["jira"]
    assert meta["title"] == "Jira" and meta["allowed_hosts_env"] == "JIRA_ALLOWED_HOSTS"
    fields = {f["key"]: f for f in meta["fields"]}
    assert set(fields) == {"base_url", "instance", "login", "token", "verify_tls", "rules", "months", "owner_service"}
    assert [o["value"] for o in fields["instance"]["options"]] == ["cloud", "server", "server_basic"]
    assert fields["token"]["secret"] and fields["login"]["show_if"] == {"instance": ["cloud", "server_basic"]}
    assert fields["rules"]["type"] == "json" and "{unit_code}" in fields["rules"]["hint"]
    assert fields["months"]["default"] == 2 and fields["verify_tls"]["default"] is True
    actions = {a["key"]: a for a in meta["actions"]}
    assert actions["refresh"]["label"] == "Обновить показатели" and actions["refresh"]["schedulable"]
    assert not actions["preview"]["schedulable"]


def test_rules_are_validated_and_normalized():
    base = {"base_url": "https://jira.company.ru", "instance": "server"}
    out = JiraConnector.validate_config({**base, "rules": RULES})
    assert isinstance(out["rules"], list) and parse_count(out["rules"]) == 3, "правила хранятся разобранным JSON"
    assert parse_count(json.dumps(RULES)) == 3, "JSON-текст тоже принимается"
    bad = [
        ("{", "ошибка JSON в строке 1, позиция 2"),
        ([{"indicator": "Bad Key", "jql": "x", "units": ["A"]}], "ключ показателя"),
        ([{"indicator": "a.b", "measure": "avg", "jql": "x", "units": ["A"]}], "measure"),
        ([{"indicator": "a.b", "measure": "sum", "jql": "x", "units": ["A"]}], "field"),
        ([{"indicator": "a.b", "jql": "project = X", "units": ["A", "B"]}], "{unit_code}"),
        ([{"indicator": "a.b", "jql": "x {month_begin}", "units": ["A"]}], "{month_begin}"),
        ([{"indicator": "a.b", "jql": "x", "units": ["A"], "unit_jql": {"A": "y"}}], "либо jql"),
        ([{"indicator": "a.b", "jql": "x"}], "units"),
        ([{"indicator": "a.b", "jql": "x", "units": ["A"], "colour": "red"}], "colour"),
        ([{"indicator": "a.b", "jql": "x", "units": ["A"]}, {"indicator": "a.b", "unit_jql": {"a": "y"}}],
         "уже считает правило 1"),
        ([{"indicator": "a.b", "jql": "x", "units": ["A"], "data_class": "financial"}], "operational"),
        ([], "Обязательное поле"),
    ]
    for rules, text in bad:
        with pytest.raises(ValidationFailed) as exc:
            JiraConnector.validate_config({**base, "rules": rules})
        assert text in exc.value.detail and "config.rules" in exc.value.fields, rules


def parse_count(text) -> int:
    return len(jira.parse_rules(text))


def test_create_rejects_invalid_rules_via_api(admin, server_jira):
    response = admin.post("/api/integrations", json={
        "kind": "jira", "config": {"base_url": server_jira.url, "instance": "server",
                                   "rules": [{"indicator": "x.y", "jql": "x"}]}, "secrets": {"token": TOKEN}})
    assert response.status_code == 422 and "config.rules" in response.json()["fields"]


# ---------------------------------------------------------------- проверка подключения

def test_check_server_with_personal_token(admin, server_jira):
    item = create(admin, server_jira)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"], check
    assert check["message"].startswith("Подключено как Тестовый Пользователь · Jira 9.12.2 (Server) · REST API 2")
    assert "«jira.resolved» нет в каталоге" in check["message"] and check["details"]["rules"] == 3
    assert server_jira.requests[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert {r.path for r in server_jira.requests} == {"/rest/api/2/myself", "/rest/api/2/serverInfo"}


def test_check_cloud_with_email_and_token(admin, cloud_jira):
    item = create(admin, cloud_jira)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"] and "REST API 3" in check["message"] and "(Cloud)" in check["message"]
    raw = cloud_jira.requests[0].headers["authorization"].split()[1]
    assert base64.b64decode(raw).decode() == f"svc@company.ru:{TOKEN}"
    assert cloud_jira.requests[0].path == "/rest/api/3/myself"


def test_check_explains_login_failures(admin, server_jira):
    item = create(admin, server_jira)
    url = f"/api/integrations/{item['id']}/check"
    wrong = admin.post(url, json={"secrets": {"token": "wrong"}}).json()
    assert not wrong["ok"] and "отклонила логин или токен (401)" in wrong["message"]
    assert "персональный токен" in wrong["message"] and wrong["details"]["code"] == "auth"
    server_jira.captcha = True
    captcha = admin.post(url).json()
    assert not captcha["ok"] and "CAPTCHA" in captcha["message"] and captcha["details"]["code"] == "captcha"
    server_jira.captcha, server_jira.forbidden = False, True
    forbidden = admin.post(url).json()
    assert not forbidden["ok"] and "Недостаточно прав в Jira (403): Browse projects" in forbidden["message"]
    assert TOKEN not in str(wrong) + str(captcha) + str(forbidden)


def test_check_wrong_instance_type(admin, cloud_jira, server_jira):
    bearer = create(admin, cloud_jira, instance="server")
    check = admin.post(f"/api/integrations/{bearer['id']}/check").json()
    assert not check["ok"] and check["details"]["code"] == "auth", "Cloud не принимает персональный токен"
    server_jira.login = "svc"
    cloud = admin.post("/api/integrations", json={"kind": "jira", "name": "Jira Cloud?", "config": {
        "base_url": server_jira.url, "instance": "cloud", "login": "svc", "rules": RULES},
        "secrets": {"token": TOKEN}}).json()
    server_jira.mode = "basic"   # принимает Basic, но REST API 3 у Server нет
    check = admin.post(f"/api/integrations/{cloud['id']}/check").json()
    assert not check["ok"] and "нет REST API 3" in check["message"] and "тип подключения" in check["message"]
    server_jira.mode, server_jira.deployment = "server", "Cloud"
    check = admin.post("/api/integrations/check", json={"kind": "jira", "config": {
        "base_url": server_jira.url, "instance": "server", "rules": RULES}, "secrets": {"token": TOKEN}}).json()
    assert check["ok"] and "выберите тип подключения «Cloud»" in check["message"]


def test_allowed_hosts(admin, server_jira, monkeypatch):
    monkeypatch.setenv("JIRA_ALLOWED_HOSTS", "jira.company.ru")
    response = admin.post("/api/integrations", json={"kind": "jira", "config": {
        "base_url": server_jira.url, "instance": "server", "rules": RULES}, "secrets": {"token": TOKEN}})
    assert response.status_code == 422 and "JIRA_ALLOWED_HOSTS" in response.json()["detail"]


# ---------------------------------------------------------------- обновление показателей

def test_refresh_server_writes_values_per_unit_and_month(admin, server_jira, db):
    server_jira.page = 1   # Jira отдаёт меньше, чем просили: дочитывается по startAt
    item = create(admin, server_jira)
    data = run(admin, item)
    assert data["status"] == "ok", data
    cur, prev = reports.period_key(CUR), reports.period_key(PREV)
    resolved = values(db, "jira.resolved")
    assert {k: v[0] for k, v in resolved.items()} == {("SUP-OS", cur): 2, ("SUP-OS", prev): 2,
                                                       ("SUP-OFFICE", cur): 0, ("SUP-OFFICE", prev): 1}
    comment = resolved[("SUP-OS", prev)][1]
    assert comment == (f'из Jira (JQL project = SUP AND component = "AlterOS" AND resolved >= "{PREV.isoformat()}" '
                       f'AND resolved < "{CUR.isoformat()}")')
    assert {k: v[0] for k, v in values(db, "jira.spent").items()} == {("IT", cur): 4.5, ("IT", prev): 4.0}
    assert {k: v[0] for k, v in values(db, "jira.open").items()} == {("TECH", cur): 1}, "снимок — текущий месяц"
    summary = data["summary"]
    assert summary["values"] == 7 and summary["created"] == 7 and summary["indicators_created"] == 3
    assert (summary["done_with_remaining"], summary["no_estimate"], summary["overspent"]) == (1, 1, 2)
    assert summary["details"]["problems"] == {"done_with_remaining": ["SUP-2"], "no_estimate": ["SUP-5"],
                                              "overspent": ["IT-1", "SUP-3"]}
    assert summary["issues"] == 9 and "качество данных: закрыта, но остаток не обнулён — 1" in data["message"]
    created = db.scalar(select(Indicator).where(Indicator.key == "jira.resolved"))
    assert (created.name, created.unit, created.data_class, created.owner_service, created.source_type) == \
        ("Решено задач в Jira", "шт.", "operational", "it", "manual")
    assert (created.green_threshold, created.yellow_threshold) == (2, 1)
    assert db.scalar(select(Indicator.unit).where(Indicator.key == "jira.spent")) == "ч"
    # Server: REST API 2, startAt и validateQuery: false
    bodies = [b for b in server_jira.searches if "AlterOS" in b["jql"] and PREV.isoformat() in b["jql"]]
    assert [b["startAt"] for b in bodies] == [0, 1] and all(b["validateQuery"] is False for b in bodies)
    assert bodies[0]["maxResults"] == jira.SERVER_BATCH and "status" in bodies[0]["fields"]
    assert TOKEN not in str(data)


def test_rerun_is_idempotent_and_change_updates(admin, server_jira, db):
    item = create(admin, server_jira)
    first = run(admin, item)
    audits = import_audits(db)
    second = run(admin, item)
    assert second["status"] == "ok" and second["summary"]["created"] == second["summary"]["updated"] == 0
    assert second["summary"]["unchanged"] == first["summary"]["values"] == 7
    assert import_audits(db) == audits, "без изменений — без записи и без строки журнала"
    assert second["summary"]["indicators_created"] == 0
    assert db.scalar(select(func.count()).select_from(Indicator).where(Indicator.key.like("jira.%"))) == 3
    server_jira.issues.append({"key": "SUP-7", "project": "SUP", "component": "AlterOffice",
                               "resolved": day(CUR, 1), "category": "done", "timespent": H,
                               "timeoriginalestimate": H})
    third = run(admin, item)
    assert third["summary"]["updated"] == 1 and third["summary"]["unchanged"] == 6
    assert values(db, "jira.resolved")[("SUP-OFFICE", reports.period_key(CUR))][0] == 1
    assert import_audits(db) == audits + 1


def test_refresh_cloud_uses_next_page_token(admin, cloud_jira, db):
    item = create(admin, cloud_jira, months=1)
    data = run(admin, item)
    assert data["status"] == "ok", data
    cur = reports.period_key(CUR)
    assert values(db, "jira.resolved")[("SUP-OS", cur)][0] == 2
    assert values(db, "jira.spent")[("IT", cur)][0] == 4.5
    assert all(r.path == "/rest/api/3/search/jql" for r in cloud_jira.requests if r.method == "POST")
    assert all("startAt" not in b and "validateQuery" not in b for b in cloud_jira.searches)
    assert all(b["maxResults"] == jira.SEARCH_BATCH for b in cloud_jira.searches)


def test_cloud_paginates_by_token(admin, cloud_jira, db):
    cloud_jira.issues += [{"key": f"SUP-{n}", "project": "SUP", "component": "AlterOS", "resolved": day(CUR, 2),
                           "category": "done", "timeoriginalestimate": H} for n in range(10, 15)]
    item = create(admin, cloud_jira, months=1, rules=[RULES[0]])
    run(admin, item)
    paged = [b for b in cloud_jira.searches if "AlterOS" in b["jql"]]
    assert [b.get("nextPageToken") for b in paged] == [None, "2", "4", "6"]
    assert values(db, "jira.resolved")[("SUP-OS", reports.period_key(CUR))][0] == 7


def test_bad_jql_and_unknown_unit_give_partial_result(admin, server_jira, db):
    rules = [RULES[0],
             {"indicator": "jira.bad", "name": "Плохой JQL", "unit_jql": {"IT": "projekt = IT"}},
             {"indicator": "jira.nounit", "name": "Без подразделения", "unit_jql": {"NOPE": "project = IT"}}]
    item = create(admin, server_jira, rules=rules)
    data = run(admin, item)
    assert data["status"] == "partial", data
    assert "Jira отклонила JQL: Field 'projekt' does not exist" in data["error"]
    assert "подразделение «NOPE» не найдено в структуре" in data["error"]
    assert len(values(db, "jira.resolved")) == 4 and values(db, "jira.bad") == {}
    assert data["summary"]["errors"] == 2, "JQL без месяца (снимок) отклонён один раз, подразделение не найдено"


def test_computed_or_missing_indicator_is_reported(admin, server_jira, db):
    rules = [{"indicator": "hr.turnover", "unit_jql": {"IT": "project = IT"}},
             {"indicator": "jira.noname", "unit_jql": {"IT": "project = IT"}}]
    item = create(admin, server_jira, rules=rules)
    data = run(admin, item)
    assert data["status"] == "error"
    assert "«Текучесть кадров» вычисляется из данных службы" in data["error"]
    assert "«jira.noname» не найден в каталоге" in data["error"]
    assert db.scalar(select(Indicator).where(Indicator.key == "jira.noname")) is None


def test_existing_indicator_is_used_without_creating(admin, server_jira, db):
    rules = [{"indicator": "ops.plan", "unit_jql": {"IT": 'project = IT AND resolved >= "{month_start}" '
                                                          'AND resolved < "{next_month_start}"'}}]
    item = create(admin, server_jira, rules=rules, months=1)
    data = run(admin, item)
    assert data["status"] == "ok" and data["summary"]["indicators_created"] == 0
    assert values(db, "ops.plan")[("IT", reports.period_key(CUR))][0] == 2


def test_preview_writes_nothing(admin, server_jira, db):
    item = create(admin, server_jira)
    data = run(admin, item, "preview")
    assert data["status"] == "ok" and data["message"].startswith("План без записи")
    # Показателей ещё нет: план считает их значения отдельно — сколько запишется, когда запуск их создаст
    pending = data["summary"]["details"]["values"]
    counts = {k: sum(1 for v in pending if v["indicator"] == k) for k in ("jira.resolved", "jira.spent", "jira.open")}
    assert all(counts.values()) and data["summary"]["values_pending"] == sum(counts.values()) == 7
    assert all(v["pending"] and v["action"] == "create" for v in pending)
    for key, count in counts.items():
        assert f"показатель «{key}» будет создан при запуске: значений {count}" in data["message"]
    assert db.scalar(select(func.count()).select_from(Indicator).where(Indicator.key.like("jira.%"))) == 0
    written = run(admin, item)
    assert written["summary"]["created"] == 7 and "values_pending" not in written["summary"]
    preview = run(admin, item, "preview")
    assert preview["summary"]["unchanged"] == 7 and preview["summary"]["values"] == 7
    assert "будет создан" not in preview["message"]


def test_search_limit_is_not_written(admin, server_jira, db, monkeypatch):
    monkeypatch.setattr(jira, "SEARCH_LIMIT", 1)
    server_jira.page = 1
    item = create(admin, server_jira, rules=[RULES[0]], months=1)
    data = run(admin, item)
    assert data["status"] == "partial" and "задач — значение не записано: уточните запрос" in data["error"]
    assert ("SUP-OS", reports.period_key(CUR)) not in values(db, "jira.resolved")


def test_unit_code_is_escaped_in_jql(admin, server_jira, db):
    server_jira.issues.append({"key": "SUP-9", "project": "SUP", "component": 'Офис "Север"', "resolved": day(CUR, 1),
                               "category": "done", "timeoriginalestimate": H})
    rules = [{"indicator": "jira.north", "name": "Север", "jql": 'project = SUP AND component = "{unit_code}"',
              "units": {"MKT": 'Офис "Север"'}}]
    item = create(admin, server_jira, rules=rules, months=1)
    assert run(admin, item)["status"] == "ok"
    assert server_jira.searches[-1]["jql"] == 'project = SUP AND component = "Офис \\"Север\\""'
    assert values(db, "jira.north")[("MKT", reports.period_key(CUR))][0] == 1


def test_auth_failure_during_run_is_an_error(admin, server_jira, db):
    item = create(admin, server_jira)
    server_jira.token = "rotated"
    data = run(admin, item)
    assert data["status"] == "error" and "(401)" in data["error"]
    state = admin.get(f"/api/integrations/{item['id']}").json()
    assert "(401)" in state["last_error"] and state["last_error_at"]
    assert db.scalar(select(func.count()).select_from(Indicator).where(Indicator.key.like("jira.%"))) == 0, \
        "неудачный запуск не создаёт показатели"


def test_values_reach_company_report(admin, server_jira, db):
    item = create(admin, server_jira, months=1)
    run(admin, item)
    data = admin.get("/api/reports/scorecard", params={"period": reports.period_key(CUR)}).json()
    unit = next(u for u in data["units"] if u["code"] == "SUP-OS")
    assert unit["cells"]["jira.resolved"]["value"] == 2 and unit["cells"]["jira.resolved"]["status"] == "green"
    tech = next(u for u in data["units"] if u["code"] == "TECH")
    assert tech["cells"]["jira.resolved"]["value"] == 2 and tech["cells"]["jira.resolved"]["source"] == "rollup"


def test_same_unit_by_code_and_path_is_counted_once(admin, server_jira, db):
    rules = [{"indicator": "jira.it", "name": "ИТ в Jira", "jql": 'project = {unit_code}',
              "units": {"IT": "IT", "АЛМИ Партнер / Техническая дирекция / ИТ-служба": "IT"}}]
    item = create(admin, server_jira, rules=rules)
    data = run(admin, item)
    assert data["status"] == "partial" and "«ИТ-служба» уже считает правило 1" in data["error"]
    assert values(db, "jira.it")[("IT", reports.period_key(CUR))][0] == 3
