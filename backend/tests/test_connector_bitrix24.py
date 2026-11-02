"""Коннектор Bitrix24 (ADR-0011): поддельный портал на настоящем HTTP-сервере — входящий вебхук REST,
crm.deal.list постранично по 50 (start / next), QUERY_LIMIT_EXCEEDED, user.get и department.get; выручка,
число выигранных сделок и воронка по подразделениям ответственных и месяцам, итоги веток, нули для
исчезнувших сделок, повторный запуск без изменений, вебхук не попадает в сообщения."""
from __future__ import annotations

import re
from datetime import timedelta
from urllib.parse import unquote

import pytest
from sqlalchemy import select

from app.core.errors import ValidationFailed
from app.integrations.connectors import bitrix24
from app.integrations.connectors.bitrix24 import Bitrix24Connector
from app.models import Department, Indicator, IndicatorValue, User
from app.services import reports
from tests.conftest import assert_counters_labelled
from tests.fake_http import FakeServer

CODE = "abc123secret0042"
CUR = reports.current_period()
PREV = reports.add_months(CUR, -1)
OLD = reports.add_months(CUR, -2)


def closed(month, day: int) -> str:
    return f"{(month + timedelta(days=day - 1)).isoformat()}T03:00:00+03:00"


def deal(n: int, user: int, stage: str, month, amount: float, category: int = 0, currency: str = "RUB") -> dict:
    return {"ID": str(n), "TITLE": f"Сделка {n}", "OPPORTUNITY": f"{amount:.2f}", "CURRENCY_ID": currency,
            "STAGE_ID": stage, "CATEGORY_ID": str(category), "ASSIGNED_BY_ID": str(user),
            "CLOSEDATE": closed(month, 3 + n % 20) if month else closed(CUR, 28),
            "CLOSED": "N" if month is None else "Y"}


def default_deals() -> list[dict]:
    deals = [deal(1, 1, "WON", CUR, 1_000_000), deal(2, 2, "WON", CUR, 500_000), deal(3, 3, "WON", PREV, 250_000),
             deal(4, 3, "C1:WON", CUR, 2_000_000, category=1), deal(5, 2, "LOSE", CUR, 900_000),
             deal(6, 4, "WON", CUR, 50_000), deal(7, 2, "NEW", None, 300_000),
             deal(8, 3, "C1:NEW", None, 700_000, category=1), deal(9, 1, "WON", OLD, 10_000_000)]
    deals += [deal(100 + n, 3, "WON", PREV, 1_000) for n in range(120)]
    return deals


USERS = {
    "1": {"ID": "1", "NAME": "Анна", "LAST_NAME": "Смирнова", "EMAIL": "tech.dir@almi.ru", "UF_DEPARTMENT": [1]},
    "2": {"ID": "2", "NAME": "Борис", "LAST_NAME": "Петров", "EMAIL": "TP.Lead@almi.ru", "UF_DEPARTMENT": [5]},
    "3": {"ID": "3", "NAME": "Вера", "LAST_NAME": "Иванова", "EMAIL": "engineer@almi.ru", "UF_DEPARTMENT": [12]},
    "4": {"ID": "4", "NAME": "Глеб", "LAST_NAME": "Глебов", "EMAIL": "nobody@almi.ru", "UF_DEPARTMENT": [99]},
}
DEPARTMENTS = [{"ID": "1", "NAME": "Техническая дирекция"}, {"ID": "5", "NAME": "Техническая служба"},
               {"ID": "12", "NAME": "Поддержка ОС"}, {"ID": "99", "NAME": "Склад"}]


def semantic(stage: str) -> str:
    return "S" if stage.endswith("WON") else ("F" if stage.endswith("LOSE") else "P")


def deal_matches(item: dict, flt: dict) -> bool:
    for key, value in flt.items():
        if key == ">=CLOSEDATE" and not item["CLOSEDATE"][:19] >= value:
            return False
        if key == "<CLOSEDATE" and not item["CLOSEDATE"][:19] < value:
            return False
        if key == "STAGE_ID" and item["STAGE_ID"] not in value:
            return False
        if key == "STAGE_SEMANTIC_ID" and semantic(item["STAGE_ID"]) != value:
            return False
        if key == "CATEGORY_ID" and int(item["CATEGORY_ID"]) not in value:
            return False
        if key == "CLOSED" and item["CLOSED"] != value:
            return False
    return True


class Routes(dict):
    def __init__(self, handler):
        super().__init__()
        self.handler = handler

    def get(self, key, default=None):
        method, path = key
        match = re.fullmatch(r"/rest/(\d+)/([A-Za-z0-9_]+)/([\w.]+)\.json", unquote(path))
        if method == "POST" and match:
            return lambda request: self.handler(request, *match.groups())
        return default


class FakeBitrix:
    def __init__(self):
        self.deals = default_deals()
        self.users = dict(USERS)
        self.scopes = ["crm", "user", "department"]
        self.limit_left = 0
        self.echo_code = False
        self.calls: list[tuple[str, dict]] = []
        self.server = FakeServer(routes=Routes(self.dispatch))

    def __enter__(self) -> FakeBitrix:
        self.server.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.server.stop()

    @property
    def url(self) -> str:
        return self.server.url

    @property
    def webhook(self) -> str:
        return f"{self.url}/rest/1/{CODE}/"

    def dispatch(self, request, user, code, method):
        params = request.json() or {}
        self.calls.append((method, params))
        if user != "1" or code != CODE:
            return 401, {"error": "INVALID_CREDENTIALS", "error_description": "Invalid request credentials"}
        if self.echo_code and method == "crm.deal.list":
            return 500, {"error": "INTERNAL_SERVER_ERROR",
                         "error_description": f"Вебхук /rest/{user}/{code}/ временно заблокирован ({code})"}
        if method == "crm.deal.list" and self.limit_left:
            self.limit_left -= 1
            return 503, {"error": "QUERY_LIMIT_EXCEEDED", "error_description": "Too many requests"}
        if method == "profile":
            return 200, {"result": {"ID": "1", "NAME": "Анна", "LAST_NAME": "Смирнова", "ADMIN": True}}
        if method == "scope":
            return 200, {"result": self.scopes}
        if method == "crm.deal.list":
            if "crm" not in self.scopes:
                return 401, {"error": "insufficient_scope", "error_description": "The request requires higher "
                                                                                 "privileges than provided"}
            found = sorted((d for d in self.deals if deal_matches(d, params.get("filter") or {})),
                           key=lambda d: int(d["ID"]))
            select_fields = params.get("select") or list(found[0]) if found else []
            return self.page([{k: d.get(k) for k in select_fields} for d in found], params)
        if method == "user.get":
            ids = {str(i) for i in (params.get("filter") or {}).get("ID", [])}
            return self.page([u for k, u in sorted(self.users.items()) if k in ids], params)
        if method == "department.get":
            return self.page(DEPARTMENTS, params)
        return 404, {"error": "ERROR_METHOD_NOT_FOUND", "error_description": "Method not found!"}

    @staticmethod
    def page(items: list, params: dict):
        start = int(params.get("start") or 0)
        chunk = items[start:start + 50]
        more = start + 50 < len(items)
        return 200, {"result": chunk, "total": len(items), **({"next": start + 50} if more else {}),
                     "time": {"start": 0, "finish": 0.01}}


@pytest.fixture()
def fake(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.delenv("BITRIX24_ALLOWED_HOSTS", raising=False)
    sleeps: list[float] = []
    monkeypatch.setattr(bitrix24, "sleep", sleeps.append)
    with FakeBitrix() as server:
        server.sleeps = sleeps
        yield server


@pytest.fixture()
def people(db):
    """Email наших сотрудников: директор техдирекции, руководитель ТП (Техническая служба), инженер AlterOS."""
    for username, email in (("tech_dir", "tech.dir@almi.ru"), ("tp_lead", "tp.lead@almi.ru"),
                            ("engineer", "Engineer@Almi.ru")):
        db.scalar(select(User).where(User.username == username)).email = email
    db.commit()


def create(admin, fake, name="Bitrix24", **config) -> dict:
    body = {"kind": "bitrix24", "name": name, "config": {"portal_url": fake.url, **config},
            "secrets": {"webhook": fake.webhook}}
    response = admin.post("/api/integrations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def run(admin, item, action="sales") -> dict:
    response = admin.post(f"/api/integrations/{item['id']}/run", json={"action": action})
    assert response.status_code == 200, response.text
    return assert_counters_labelled(response.json(), "bitrix24")


def values(db, key: str) -> dict[tuple[str, str], float]:
    return {k: v[0] for k, v in values_with_comment(db, key).items()}


def values_with_comment(db, key: str) -> dict[tuple[str, str], tuple[float, str]]:
    db.expire_all()
    rows = db.execute(select(Department.code, IndicatorValue.period, IndicatorValue.value, IndicatorValue.comment)
                      .join(Indicator, Indicator.id == IndicatorValue.indicator_id)
                      .join(Department, Department.id == IndicatorValue.department_id)
                      .where(Indicator.key == key)).all()
    return {(code, reports.period_key(period)): (value, comment) for code, period, value, comment in rows}


C, P = reports.period_key(CUR), reports.period_key(PREV)


# ---------------------------------------------------------------- описание и настройки

def test_kind_is_described_in_russian(admin):
    meta = {k["kind"]: k for k in admin.get("/api/integrations/kinds").json()}["bitrix24"]
    fields = {f["key"]: f for f in meta["fields"]}
    assert meta["url_field"] == "portal_url" and meta["allowed_hosts_env"] == "BITRIX24_ALLOWED_HOSTS"
    assert fields["webhook"]["secret"] and fields["webhook"]["type"] == "password"
    assert fields["department_map"]["show_if"] == {"mapping": ["department"]}
    assert fields["revenue_indicator"]["default"] == "crm.revenue" and fields["amount_unit"]["default"] == "million"
    assert {a["key"]: a["label"] for a in meta["actions"]} == {"sales": "Обновить показатели продаж",
                                                               "preview": "Проверить без записи"}


def test_validate_config():
    base = {"portal_url": "https://company.bitrix24.ru"}
    out = Bitrix24Connector.validate_config({**base, "categories": "0, 3", "won_stages": "WON, C3:WON"})
    assert out["categories"] == ["0", "3"] and out["won_stages"] == ["WON", "C3:WON"] and out["mapping"] == "email"
    for bad, field in (({"categories": "основная"}, "categories"), ({"won_stages": "WON STAGE"}, "won_stages"),
                       ({"user_map": "ivanov@company.ru"}, "user_map"), ({"revenue_indicator": "Выручка"},
                                                                         "revenue_indicator"),
                       ({"revenue_indicator": "", "deals_indicator": "", "pipeline_indicator": ""},
                        "revenue_indicator"), ({"deals_indicator": "crm.revenue"}, "deals_indicator")):
        with pytest.raises(ValidationFailed) as exc:
            Bitrix24Connector.validate_config({**base, **bad})
        assert f"config.{field}" in exc.value.fields, bad


# ---------------------------------------------------------------- проверка

def test_check_reports_portal_user_and_scopes(admin, fake):
    item = create(admin, fake)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"], check
    assert check["message"].startswith("Подключено к порталу 127.0.0.1 как Анна Смирнова (ID 1), администратор "
                                       "портала · права вебхука: crm, user, department")
    assert "«crm.revenue» нет в каталоге" in check["message"]
    assert [c[0] for c in fake.calls] == ["profile", "scope"]
    fake.scopes = ["user"]
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"] and "нет прав «CRM»" in check["message"]


def test_check_failures_never_show_webhook_code(admin, fake):
    item = create(admin, fake)
    bad = admin.post(f"/api/integrations/{item['id']}/check",
                     json={"secrets": {"webhook": f"{fake.url}/rest/1/wrongcode/"}}).json()
    assert not bad["ok"] and "Bitrix24 отклонил вебхук" in bad["message"] and "wrongcode" not in bad["message"]
    other = admin.post(f"/api/integrations/{item['id']}/check",
                       json={"secrets": {"webhook": f"https://other.bitrix24.ru/rest/1/{CODE}/"}}).json()
    assert not other["ok"] and "Вебхук выдан другим порталом (other.bitrix24.ru)" in other["message"]
    garbage = admin.post(f"/api/integrations/{item['id']}/check", json={"secrets": {"webhook": "abc"}}).json()
    assert not garbage["ok"] and "https://портал/rest/1/код/" in garbage["message"]
    down = admin.post("/api/integrations/check", json={"kind": "bitrix24", "config": {
        "portal_url": "http://127.0.0.1:9"}, "secrets": {"webhook": f"http://127.0.0.1:9/rest/1/{CODE}/"}}).json()
    assert not down["ok"] and "Не удалось подключиться" in down["message"]
    for result in (bad, other, garbage, down):
        assert CODE not in str(result), "код вебхука не попадает в сообщения"
    assert CODE not in admin.get(f"/api/integrations/{item['id']}").text


def test_webhook_code_never_leaks_from_runs_logs_or_rows(admin, fake, db, people, caplog):
    import json
    import logging

    from app.models import Integration, IntegrationRun

    caplog.set_level(logging.DEBUG)
    fake.echo_code = True
    item = create(admin, fake)
    data = run(admin, item)
    assert data["status"] == "error" and "временно заблокирован" in data["error"] and "/rest/1/…/" in data["error"]
    fake.echo_code = False
    fake.users.pop("2", None)
    admin.post(f"/api/integrations/{item['id']}/check")
    texts = [json.dumps(data, ensure_ascii=False), caplog.text, admin.get(f"/api/integrations/{item['id']}").text,
             admin.get(f"/api/integrations/{item['id']}/runs").text]
    db.expire_all()
    row = db.get(Integration, item["id"])
    texts += [row.last_error or ""] + [f"{r.message} {r.error} {json.dumps(r.summary, ensure_ascii=False)}"
                                       for r in db.scalars(select(IntegrationRun))]
    assert not any(CODE in t for t in texts), "код вебхука — ни в журнале сервера, ни в запусках, ни в API"


def test_short_webhook_form(admin, fake):
    response = admin.post("/api/integrations/check", json={"kind": "bitrix24", "config": {"portal_url": fake.url},
                                                           "secrets": {"webhook": f"1/{CODE}"}}).json()
    assert response["ok"], response


# ---------------------------------------------------------------- обновление показателей

def test_sales_by_email_with_branch_totals(admin, fake, db, people):
    item = create(admin, fake)
    data = run(admin, item)
    assert data["status"] == "ok", data
    assert values(db, "crm.revenue") == {("TECHDIR", C): 3.5, ("TECH", C): 2.5, ("SUP-OS", C): 2.0,
                                         ("SUP-OS", P): 0.37}
    assert values(db, "crm.deals_won") == {("TECHDIR", C): 3, ("TECH", C): 2, ("SUP-OS", C): 1, ("SUP-OS", P): 121}
    assert values(db, "crm.pipeline") == {("TECH", C): 1.0, ("SUP-OS", C): 0.7}, "воронка — только текущий месяц"
    comments = values_with_comment(db, "crm.revenue")
    assert comments[("SUP-OS", P)][1] == "из Bitrix24: выигранных сделок — 121"
    assert comments[("TECHDIR", C)][1].endswith("(вместе с вложенными подразделениями)")
    summary = data["summary"]
    assert (summary["deals_won"], summary["deals_open"], summary["deals_unmapped"]) == (125, 2, 1)
    assert summary["details"]["unmapped"] == {"Глеб Глебов": 1} and "Глеб Глебов — 1" in data["message"]
    revenue = db.scalar(select(Indicator).where(Indicator.key == "crm.revenue"))
    assert (revenue.name, revenue.unit, revenue.data_class, revenue.owner_service) == \
        ("Выручка по сделкам (Bitrix24)", "млн ₽", "financial", "commercial")
    assert db.scalar(select(Indicator.data_class).where(Indicator.key == "crm.deals_won")) == "operational"
    # Запрос сделок: фильтр по CLOSEDATE и семантике «успешно», select, порядок, страницы по 50 с паузой
    lists = [p for m, p in fake.calls if m == "crm.deal.list"]
    won = [p for p in lists if "STAGE_SEMANTIC_ID" in p["filter"]]
    assert [p["start"] for p in won] == [0, 50, 100]
    assert won[0]["filter"] == {">=CLOSEDATE": f"{PREV.isoformat()}T00:00:00",
                                "<CLOSEDATE": f"{reports.add_months(CUR, 1).isoformat()}T00:00:00",
                                "STAGE_SEMANTIC_ID": "S"}
    assert "OPPORTUNITY" in won[0]["select"] and won[0]["order"] == {"ID": "ASC"}
    assert [p["filter"] for p in lists if "CLOSED" in p["filter"]] == [{"CLOSED": "N"}]
    assert bitrix24.PAGE_PAUSE in fake.sleeps
    assert CODE not in str(data)


def test_rerun_unchanged_and_vanished_deal_gets_zero(admin, fake, db, people):
    item = create(admin, fake)
    first = run(admin, item)
    second = run(admin, item)
    assert second["summary"]["created"] == second["summary"]["updated"] == 0
    assert second["summary"]["unchanged"] == first["summary"]["values"] == 10
    fake.deals = [d for d in fake.deals if d["ID"] != "4"]   # сделку AlterOS отменили
    third = run(admin, item)
    revenue = values_with_comment(db, "crm.revenue")
    assert revenue[("SUP-OS", C)] == (0, "из Bitrix24 — за месяц данных нет")
    assert values(db, "crm.revenue")[("TECH", C)] == 0.5 and values(db, "crm.revenue")[("TECHDIR", C)] == 1.5
    assert values(db, "crm.deals_won")[("SUP-OS", C)] == 0
    assert third["summary"]["updated"] == 6 and third["status"] == "ok"
    sample = {(v["unit"], v["indicator"]): v["action"] for v in third["summary"]["details"]["values"]}
    assert "clear" not in sample.values(), "суммы исчезнувших сделок — ноль (update), а не очистка значения"
    fourth = run(admin, item)
    assert fourth["summary"]["created"] == fourth["summary"]["updated"] == 0


def test_categories_and_won_stages(admin, fake, db, people):
    item = create(admin, fake, categories="0", won_stages="WON", pipeline_indicator="", months=1)
    data = run(admin, item)
    assert data["status"] == "ok", data
    assert values(db, "crm.revenue") == {("TECHDIR", C): 1.5, ("TECH", C): 0.5}
    lists = [p for m, p in fake.calls if m == "crm.deal.list"]
    assert lists[0]["filter"]["CATEGORY_ID"] == [0] and lists[0]["filter"]["STAGE_ID"] == ["WON"]
    assert "STAGE_SEMANTIC_ID" not in lists[0]["filter"] and len(lists) == 1, "воронка не запрашивается"
    assert db.scalar(select(Indicator).where(Indicator.key == "crm.pipeline")) is None


def test_department_mapping_and_user_override(admin, fake, db):
    item = create(admin, fake, mapping="department", department_map="12 = SUP-OS", user_map="nobody@almi.ru = MKT",
                  amount_unit="thousand", revenue_indicator="sales.revenue", deals_indicator="", pipeline_indicator="",
                  months=1)
    data = run(admin, item)
    assert data["status"] == "ok", data
    assert values(db, "sales.revenue") == {("TECHDIR", C): 3500, ("TECH", C): 2500, ("SUP-OS", C): 2000,
                                           ("MKT", C): 50}
    assert db.scalar(select(Indicator.unit).where(Indicator.key == "sales.revenue")) == "тыс. ₽"
    assert "department.get" in [m for m, _ in fake.calls] and data["summary"]["deals_unmapped"] == 0


def test_query_limit_is_retried_with_pause(admin, fake, db, people):
    fake.limit_left = 4   # три ответа съедают повторы HTTP-клиента, ещё один — повтор коннектора
    item = create(admin, fake, months=1, pipeline_indicator="")
    data = run(admin, item)
    assert data["status"] == "ok", data
    assert bitrix24.LIMIT_PAUSE in fake.sleeps and values(db, "crm.revenue")[("SUP-OS", C)] == 2.0
    fake.limit_left = 100
    failed = run(admin, item)
    assert failed["status"] == "error" and "QUERY_LIMIT_EXCEEDED" in failed["error"]


def test_insufficient_scope_is_explained(admin, fake, people):
    fake.scopes = ["user"]
    data = run(admin, create(admin, fake))
    assert data["status"] == "error" and "Bitrix24 отклонил вебхук" not in data["error"]
    assert "insufficient_scope" in data["error"] and "права «CRM»" in data["error"]


def test_preview_and_currencies(admin, fake, db, people):
    fake.deals.append(deal(500, 1, "WON", CUR, 1_000, currency="USD"))
    item = create(admin, fake, months=1)
    data = run(admin, item, "preview")
    assert data["status"] == "ok" and data["message"].startswith("План без записи")
    # Показателей crm.* ещё нет: их значения посчитаны и названы в сообщении (тот же _metrics, что у Jira)
    pending = data["summary"]["details"]["values"]
    keys = sorted({v["indicator"] for v in pending})
    assert keys and all(v["pending"] for v in pending) and data["summary"]["values_pending"] == len(pending)
    for key in keys:
        count = sum(1 for v in pending if v["indicator"] == key)
        assert f"показатель «{key}» будет создан при запуске: значений {count}" in data["message"]
    assert "сложены без пересчёта" in data["message"] and data["summary"]["details"]["currencies"] == \
        {"RUB": 6, "USD": 1}
    assert db.scalar(select(Indicator).where(Indicator.key.like("crm.%"))) is None
    assert db.scalar(select(IndicatorValue).join(Indicator).where(Indicator.key.like("crm.%"))) is None
    written = run(admin, item)
    assert written["summary"]["created"] == len(pending), "запуск записывает столько, сколько обещал план"


def test_existing_computed_indicator_is_refused(admin, fake, db, people):
    item = create(admin, fake, revenue_indicator="tech.solved", deals_indicator="", pipeline_indicator="crm.pipe")
    data = run(admin, item)
    assert data["status"] == "partial" and "вычисляется из данных службы" in data["error"]
    assert values(db, "crm.pipe") == {("TECH", C): 1.0, ("SUP-OS", C): 0.7}
