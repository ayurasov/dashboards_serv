"""Каркас подключений (ADR-0011): поддельный коннектор, API подключений и секретов, проверка, запуск,
журнал, расписание, атомарное занятие запуска (в том числе два процесса на PostgreSQL), планировщик, CLI."""
from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.orm import sessionmaker

from app.core.db import utcnow
from app.core.errors import ValidationFailed
from app.integrations import base, runner
from app.integrations.base import Action, CheckResult, Connector, Field, Option, RunContext, RunResult
from app.integrations.http import IntegrationError
from app.models import AppSetting, AuditEntry, InboxItem, InboxRule, Integration, IntegrationRun, User
from tests.conftest import drop_pg_database
from tests.fake_http import FakeServer
from tests.test_inbox import tp_file

TOKEN = "demo-token-42-xYz"


class DemoConnector(Connector):
    """Поддельный коннектор только для тестов: проверка по токену, файлы во входящие, структура движком."""

    kind = "demo"
    title = "Демо-система"
    description = "Только для тестов"
    fields = (
        Field("base_url", "Адрес", "url", required=True),
        Field("login", "Логин", required=True, show_if={"mode": ("a",)}),
        Field("token", "Токен", "password", required=True, secret=True),
        Field("verify_tls", "Проверять сертификат", "bool", default=True),
        Field("mode", "Режим", "select", options=(Option("a", "A"), Option("b", "B")), default="a"),
        Field("lists", "Списки", "list"),
        Field("batch", "Пачка", "int", default=50, min=1, max=500),
    )
    actions = (Action("pull", "Забрать данные"), Action("structure", "Синхронизировать структуру"),
               Action("manual", "Только вручную", schedulable=False))

    def client(self):
        return self.http(headers={"Authorization": f"Bearer {self.secrets['token']}"})

    def check(self) -> CheckResult:
        with self.client() as c:
            me = c.get_json("api/me")
        return CheckResult(True, f"Подключено как {me['login']}", {"version": me["version"]})

    def run(self, action: str, ctx: RunContext) -> RunResult:
        if action == "pull":
            with self.client() as c:
                content = c.get_bytes("export/tp.xlsx")
            item = ctx.inbox.add(content, "tp.xlsx", source_ref="demo:export/tp.xlsx")
            ctx.state["pulls"] = ctx.state.get("pulls", 0) + 1
            return RunResult.ok("Забрано файлов: 1", counters={"files": 1, "status_" + item.status: 1})
        if action == "structure":
            from app.services import org_transfer

            bundle = org_transfer.export_structure(ctx.db)
            plan = ctx.plans.structure(bundle)
            return RunResult.ok("План структуры", counters={"unchanged": plan["summary"]["unchanged"]})
        raise IntegrationError("Нет связи с демо-системой", code="connect", short="Нет связи")


@pytest.fixture()
def demo():
    base.register(DemoConnector)
    yield DemoConnector
    base.unregister("demo")


@pytest.fixture()
def fake(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    server = FakeServer()

    def me(request):
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return 401, {"message": "bad token"}
        return 200, {"login": "svc", "version": "2.1"}

    server.route("GET", "/api/me", me)
    server.route("GET", "/export/tp.xlsx", lambda r: (200, tp_file()))
    with server:
        yield server


def _create(admin, fake, **extra):
    body = {"kind": "demo", "name": "Демо", "config": {"base_url": fake.url, "login": "svc"},
            "secrets": {"token": TOKEN}, **extra}
    response = admin.post("/api/integrations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _enable(admin, integration_id):
    assert admin.post(f"/api/integrations/{integration_id}/check").json()["ok"]
    response = admin.patch(f"/api/integrations/{integration_id}", json={"enabled": True})
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- описание и реестр

def test_registry_and_kinds(admin, demo):
    kinds = {k["kind"]: k for k in admin.get("/api/integrations/kinds").json()}
    assert {"folder", "demo"} <= set(kinds)
    folder = kinds["folder"]
    assert folder["singleton"] and folder["url_field"] is None and folder["actions"][0]["key"] == "scan"
    fields = {f["key"]: f for f in kinds["demo"]["fields"]}
    assert fields["token"]["secret"] and fields["token"]["type"] == "password"
    assert fields["mode"]["options"] == [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]
    assert fields["login"]["show_if"] == {"mode": ["a"]}
    assert kinds["demo"]["allowed_hosts_env"] == "DEMO_ALLOWED_HOSTS"
    assert kinds["demo"]["secret_url_fields"] == ["base_url"], "по умолчанию секрет привязан к url_field"
    assert folder["secret_url_fields"] == [] and folder["allowed_hosts_env"] is None
    assert DemoConnector.secret_url({"base_url": "https://demo.ru"}) == "https://demo.ru"
    assert runner.url_of(DemoConnector, {"base_url": "https://demo.ru"}) == "https://demo.ru"
    with pytest.raises(Exception, match="Неизвестный вид"):
        base.get("nope")


def test_validate_config(demo):
    out = DemoConnector.validate_config({"base_url": "https://demo.ru/", "login": "x", "lists": "a, b\nc",
                                         "batch": "10", "verify_tls": "false"})
    assert out == {"base_url": "https://demo.ru", "login": "x", "verify_tls": False, "mode": "a",
                   "lists": ["a", "b", "c"], "batch": 10}
    # Логин обязателен только для режима «a» (show_if)
    assert DemoConnector.validate_config({"base_url": "https://demo.ru", "mode": "b"})["login"] is None
    for bad, field in (({"base_url": "ftp://x"}, "config.base_url"), ({"base_url": "https://d.ru"}, "config.login"),
                       ({"base_url": "https://d.ru", "login": "x", "mode": "z"}, "config.mode"),
                       ({"base_url": "https://d.ru", "login": "x", "batch": 0}, "config.batch"),
                       ({"base_url": "https://d.ru", "login": "x", "extra": 1}, "config.extra")):
        with pytest.raises(ValidationFailed) as exc:
            DemoConnector.validate_config(bad)
        assert field in exc.value.fields


# ---------------------------------------------------------------- подключение и секреты

def test_create_never_returns_secret_and_encrypts_it(admin, demo, fake, db):
    response = admin.post("/api/integrations", json={"kind": "demo", "name": "Демо",
                                                      "config": {"base_url": fake.url, "login": "svc"},
                                                      "secrets": {"token": TOKEN}})
    assert response.status_code == 201 and TOKEN not in response.text
    data = response.json()
    assert data["has_secret"] and data["secret_fields"] == ["token"] and data["secret_bound_url"] == fake.url
    assert data["enabled"] is False and data["health"] == "disabled" and data["connector"]["kind"] == "demo"
    row = db.get(Integration, data["id"])
    assert TOKEN not in row.secret_encrypted and "Секрет" not in str(row.config)
    assert TOKEN not in admin.get("/api/integrations").text
    assert not any(TOKEN in str(e.after) + str(e.before) for e in db.scalars(select(AuditEntry)))


def test_create_validation(admin, demo, fake):
    base_body = {"kind": "demo", "config": {"base_url": fake.url, "login": "svc"}}
    missing = admin.post("/api/integrations", json=base_body)
    assert missing.status_code == 422 and "secrets.token" in missing.json()["fields"]
    enabled = admin.post("/api/integrations", json={**base_body, "secrets": {"token": "t"}, "enabled": True})
    assert enabled.status_code == 409 and enabled.json()["code"] == "check_required"
    assert admin.post("/api/integrations", json={**base_body, "kind": "nope"}).status_code == 422
    _create(admin, fake)
    dup = admin.post("/api/integrations", json={**base_body, "name": "демо", "secrets": {"token": "t"}})
    assert dup.status_code == 409
    assert admin.post("/api/integrations", json={"kind": "folder"}).status_code == 201
    assert admin.post("/api/integrations", json={"kind": "folder", "name": "Ещё"}).json()["code"] == "singleton"


def test_enable_requires_successful_check(admin, demo, fake, db):
    item = _create(admin, fake)
    early = admin.patch(f"/api/integrations/{item['id']}", json={"enabled": True})
    assert early.status_code == 409 and early.json()["code"] == "check_required"
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"] and check["message"] == "Подключено как svc" and check["details"] == {"version": "2.1"}
    assert fake.requests[-1].headers["authorization"] == f"Bearer {TOKEN}"
    data = _enable(admin, item["id"])
    assert data["enabled"] and data["verified_at"] and data["health"] == "ok"
    # Изменение настроек снимает отметку проверки
    changed = admin.patch(f"/api/integrations/{item['id']}", json={"config": {"login": "other"}}).json()
    assert changed["verified_at"] is None and changed["config"]["login"] == "other"


def test_secret_is_bound_to_url(admin, demo, fake, db):
    item = _create(admin, fake)
    moved = admin.patch(f"/api/integrations/{item['id']}", json={"config": {"base_url": "https://demo.example.ru"}})
    assert moved.status_code == 422 and moved.json()["code"] == "secret_rebind_required"
    assert "введите токен или пароль заново" in moved.json()["detail"]
    # Пустой секрет при том же адресе — сохранённый остаётся
    same = admin.patch(f"/api/integrations/{item['id']}", json={"secrets": {"token": ""}, "name": "Демо 2"}).json()
    assert same["has_secret"] and same["name"] == "Демо 2"
    assert admin.post(f"/api/integrations/{item['id']}/check").json()["ok"]
    rebound = admin.patch(f"/api/integrations/{item['id']}", json={
        "config": {"base_url": "https://demo.example.ru"}, "secrets": {"token": "new"}}).json()
    assert rebound["secret_bound_url"] == "https://demo.example.ru" and rebound["secret_problem"] is None
    # Подмена адреса в базе: секрет на чужой адрес не уходит
    db.execute(update(Integration).where(Integration.id == item["id"]).values(config={
        "base_url": fake.url, "login": "svc", "verify_tls": True, "mode": "a", "lists": [], "batch": 50}))
    db.commit()
    data = admin.get(f"/api/integrations/{item['id']}").json()
    assert data["secret_problem"] and "введите" in data["secret_problem"]
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["details"]["code"] == "secret_rebind_required"
    assert all(r.headers.get("authorization") != "Bearer new" for r in fake.requests)


def test_clear_secrets_and_unreadable_secret(admin, demo, fake, db, monkeypatch):
    item = _create(admin, fake)
    cleared = admin.patch(f"/api/integrations/{item['id']}", json={"clear_secrets": ["token"]})
    assert cleared.status_code == 422, "обязательный секрет не стирается"
    from app.core.config import settings

    monkeypatch.setattr(settings, "secret_key", "сменённый-" + "1" * 40)
    data = admin.get(f"/api/integrations/{item['id']}").json()
    assert data["has_secret"] and "SECRET_KEY" in data["secret_problem"] and data["secret_fields"] == []
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["details"]["code"] == "secret_unreadable"
    fixed = admin.patch(f"/api/integrations/{item['id']}", json={"secrets": {"token": TOKEN}}).json()
    assert fixed["secret_problem"] is None


def test_failed_check_records_health(admin, demo, fake, login):
    item = _create(admin, fake, secrets={"token": "wrong"})
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and "401" in check["message"] and check["details"]["code"] == "auth"
    data = admin.get(f"/api/integrations/{item['id']}").json()
    assert data["last_error"] and data["last_error_at"] and data["verified_at"] is None
    draft = admin.post(f"/api/integrations/{item['id']}/check", json={"secrets": {"token": TOKEN}}).json()
    assert draft["ok"] and draft["draft"], "несохранённый токен проверяется без сохранения"
    assert admin.get(f"/api/integrations/{item['id']}").json()["verified_at"] is None
    new = admin.post("/api/integrations/check", json={"kind": "demo", "config": {"base_url": fake.url, "login": "s"},
                                                      "secrets": {"token": TOKEN}}).json()
    assert new["ok"] and new["draft"]
    down = admin.post("/api/integrations/check", json={"kind": "demo", "config": {"base_url": "http://127.0.0.1:9",
                                                                                   "login": "s"},
                                                       "secrets": {"token": "x"}}).json()
    assert not down["ok"] and "127.0.0.1:9" in down["message"], "администратору — подробно"


def test_permissions_and_capability(admin, demo, fake, login, db):
    item = _create(admin, fake)
    lead = login("tp_lead")
    assert lead.get("/api/integrations").status_code == 403
    assert lead.post(f"/api/integrations/{item['id']}/run", json={"action": "pull"}).status_code == 403
    tp = db.scalar(select(User).where(User.username == "tp_lead"))
    admin.patch(f"/api/users/{tp.id}", json={"capabilities": ["integrations.manage"]})
    assert lead.get("/api/integrations").status_code == 200
    assert lead.get("/api/integrations/keys").status_code == 200


# ---------------------------------------------------------------- запуск и журнал

def test_run_puts_file_into_inbox_and_journal(admin, demo, fake, db):
    item = _create(admin, fake)
    _enable(admin, item["id"])
    db.merge(InboxRule(source="integration", dataset="tp-weekly", auto_apply=True))
    db.commit()
    run = admin.post(f"/api/integrations/{item['id']}/run", json={"action": "pull"})
    assert run.status_code == 200, run.text
    data = run.json()
    assert data["status"] == "ok" and data["trigger"] == "manual" and data["username"] == "admin"
    assert data["summary"]["files"] == 1 and data["summary"]["status_applied"] == 1 and data["summary"]["items"]
    row = db.scalar(select(InboxItem).where(InboxItem.id == data["summary"]["items"][0]))
    assert row.source == "integration" and row.integration_id == item["id"] and row.status == "applied"
    assert row.received_by == "Подключение «Демо»" and row.applied_by == "Подключение «Демо»"
    integration = admin.get(f"/api/integrations/{item['id']}").json()
    assert integration["last_run"]["id"] == data["id"] and integration["running"] is False
    db.expire_all()
    assert db.get(Integration, item["id"]).state == {"pulls": 1}
    runs = admin.get(f"/api/integrations/{item['id']}/runs").json()
    assert [r["id"] for r in runs] == [data["id"]]
    listing = admin.get("/api/inbox", params={"integration_id": item["id"]}).json()
    assert listing["total"] == 1 and listing["items"][0]["integration"] == {"id": item["id"], "name": "Демо"}
    assert db.scalar(select(func.count()).select_from(AuditEntry).where(
        AuditEntry.entity_type == "integration", AuditEntry.action == "run")) == 1


def test_run_engines_via_ctx_plans(admin, demo, fake):
    item = _create(admin, fake)
    data = admin.post(f"/api/integrations/{item['id']}/run", json={"action": "structure"}).json()
    assert data["status"] == "ok" and data["summary"]["unchanged"] > 0


def test_run_errors(admin, demo, fake, db):
    item = _create(admin, fake)
    assert admin.post(f"/api/integrations/{item['id']}/run", json={"action": "nope"}).status_code == 422
    failed = admin.post(f"/api/integrations/{item['id']}/run", json={"action": "manual"}).json()
    assert failed["status"] == "error" and failed["error"] == "Нет связи с демо-системой"
    data = admin.get(f"/api/integrations/{item['id']}").json()
    assert data["last_error"] == "Нет связи с демо-системой" and data["running"] is False
    db.execute(update(Integration).where(Integration.id == item["id"]).values(running_since=utcnow()))
    db.commit()
    busy = admin.post(f"/api/integrations/{item['id']}/run", json={"action": "pull"})
    assert busy.status_code == 409 and busy.json()["code"] == "run_in_progress"
    assert admin.delete(f"/api/integrations/{item['id']}").status_code == 409
    # Зависший запуск (старше 2 ч) не мешает новому
    db.execute(update(Integration).where(Integration.id == item["id"]).values(
        running_since=utcnow() - timedelta(hours=3)))
    db.commit()
    assert admin.post(f"/api/integrations/{item['id']}/run", json={"action": "pull"}).json()["status"] == "ok"


def test_unexpected_exception_is_contained(admin, demo, fake, monkeypatch):
    item = _create(admin, fake)
    monkeypatch.setattr(DemoConnector, "run", lambda self, action, ctx: 1 / 0)
    data = admin.post(f"/api/integrations/{item['id']}/run", json={"action": "pull"}).json()
    assert data["status"] == "error" and "журнале сервера" in data["error"]


def test_runs_are_pruned(admin, demo, fake, db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "integration_runs_keep", 2)
    item = _create(admin, fake)
    for _ in range(4):
        admin.post(f"/api/integrations/{item['id']}/run", json={"action": "manual"})
    assert db.scalar(select(func.count()).select_from(IntegrationRun)) == 2
    assert admin.delete(f"/api/integrations/{item['id']}").status_code == 200
    assert db.scalar(select(func.count()).select_from(IntegrationRun)) == 0


def test_folder_connector(admin, tmp_path, monkeypatch):
    from app.core.config import settings

    tmp_path = tmp_path / "inbox"
    tmp_path.mkdir()
    created = admin.post("/api/integrations", json={"kind": "folder"}).json()
    check = admin.post(f"/api/integrations/{created['id']}/check").json()
    assert not check["ok"] and "INBOX_DIR" in check["message"]
    monkeypatch.setattr(settings, "inbox_dir", str(tmp_path))
    monkeypatch.setattr(settings, "inbox_settle_seconds", 0)
    (tmp_path / "tp-weekly").mkdir()
    (tmp_path / "tp-weekly" / "w.xlsx").write_bytes(tp_file())
    check = admin.post(f"/api/integrations/{created['id']}/check").json()
    assert check["ok"] and "ждут разбора: 1" in check["message"]
    run = admin.post(f"/api/integrations/{created['id']}/run", json={"action": "scan"}).json()
    assert run["status"] == "ok" and run["summary"]["taken"] == 1 and run["summary"]["items"]


# ---------------------------------------------------------------- расписание

def test_schedule_normalization(demo):
    assert runner.normalize_schedule(DemoConnector, None) == {}
    assert runner.normalize_schedule(DemoConnector, {"mode": "interval", "minutes": 30}) == \
        {"mode": "interval", "actions": ["pull"], "minutes": 30}
    daily = runner.normalize_schedule(DemoConnector, {"mode": "daily", "time": "06:30", "weekdays": [5, 1],
                                                      "actions": ["structure"]})
    assert daily == {"mode": "daily", "actions": ["structure"], "time": "06:30", "weekdays": [1, 5]}
    for bad in ({"mode": "interval", "minutes": 1}, {"mode": "interval"}, {"mode": "daily", "time": "25:00"},
                {"mode": "daily", "time": "06:00", "weekdays": [8]}, {"mode": "interval", "minutes": 60,
                                                                       "actions": ["manual"]}, {"mode": "cron"}):
        with pytest.raises(ValidationFailed):
            runner.normalize_schedule(DemoConnector, bad)
    assert runner.schedule_label(daily) == "В 06:30 (пн, пт)"
    assert runner.schedule_label({"mode": "interval", "minutes": 15}) == "Каждые 15 мин"


def test_next_run_uses_company_timezone():
    now = datetime(2026, 11, 2, 10, 0)  # понедельник, 13:00 по Москве
    assert runner.next_run({"mode": "interval", "minutes": 45}, now) == datetime(2026, 11, 2, 10, 45)
    assert runner.next_run({"mode": "daily", "time": "14:00"}, now) == datetime(2026, 11, 2, 11, 0)
    assert runner.next_run({"mode": "daily", "time": "06:30"}, now) == datetime(2026, 11, 3, 3, 30)
    assert runner.next_run({"mode": "daily", "time": "06:30", "weekdays": [5]}, now) == datetime(2026, 11, 6, 3, 30)
    assert runner.next_run({}, now) is None


def test_schedule_via_api(admin, demo, fake):
    item = _create(admin, fake, schedule={"mode": "interval", "minutes": 60})
    assert item["schedule"]["minutes"] == 60 and item["next_run_at"] is None, "выключенное не планируется"
    data = _enable(admin, item["id"])
    assert data["next_run_at"] and data["schedule_label"] == "Каждые 60 мин"
    off = admin.patch(f"/api/integrations/{item['id']}", json={"schedule": {"mode": "off"}}).json()
    assert off["schedule"] == {} and off["next_run_at"] is None
    bad = admin.patch(f"/api/integrations/{item['id']}", json={"schedule": {"mode": "interval", "minutes": 2}})
    assert bad.status_code == 422


def _due(db, name="Демо", minutes=60) -> int:
    row = Integration(kind="demo", name=name, enabled=True, config={"base_url": "http://127.0.0.1:9", "login": "x"},
                      schedule={"mode": "interval", "minutes": minutes, "actions": ["manual"]}, state={},
                      last_error="", next_run_at=utcnow() - timedelta(minutes=1))
    db.add(row)
    db.commit()
    return row.id


def test_claim_is_taken_once(db, demo):
    integration_id = _due(db)
    now = utcnow()
    first = runner.claim_due(now)
    second = runner.claim_due(now)
    assert first == [(integration_id, ["manual"])] and second == []
    db.expire_all()
    assert db.get(Integration, integration_id).next_run_at == now + timedelta(minutes=60)


def test_worker_tick_runs_due_and_writes_heartbeat(db, demo, engine):
    from app.worker import Worker

    integration_id = _due(db)
    worker = Worker(tick_seconds=1)
    out = worker.tick()
    assert len(out["runs"]) == 1 and "cleanup" in out
    db.expire_all()
    run = db.scalar(select(IntegrationRun).where(IntegrationRun.integration_id == integration_id))
    assert run.trigger == "schedule" and run.status == "error" and run.username == "system"
    assert db.get(AppSetting, "worker_status").value["tick_seconds"] == 1
    assert worker.tick()["runs"] == [], "следующий запуск — через интервал"


def test_worker_stops_gracefully_on_sigterm(engine):
    import signal

    from app.worker import Worker

    worker = Worker(tick_seconds=60)
    previous = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)
    try:
        worker.install_signals()
        thread = threading.Thread(target=worker.run)
        thread.start()
        time.sleep(0.3)
        signal.raise_signal(signal.SIGTERM)
        thread.join(5)
        assert not thread.is_alive() and worker.ticks >= 1
    finally:
        signal.signal(signal.SIGTERM, previous[0])
        signal.signal(signal.SIGINT, previous[1])


def test_worker_waits_for_schema(engine, monkeypatch):
    from app.core import migrate
    from app.worker import Worker

    calls = {"n": 0}

    def not_yet(_conn):
        calls["n"] += 1
        return calls["n"] > 2, "0015_reports", "0016_integrations"

    monkeypatch.setattr(migrate, "check_schema_is_current", not_yet)
    worker = Worker()
    assert worker.wait_for_schema(poll=0.01) and calls["n"] == 3


def test_cli_integrations(db, demo, fake, capsys):
    from app.cli import main

    row = Integration(kind="demo", name="Демо", enabled=True, config={"base_url": fake.url, "login": "svc"},
                      schedule={}, state={}, last_error="")
    db.add(row)
    db.flush()
    from app.core.secrets import seal

    row.secret_encrypted, row.secret_bound_url = seal(runner.PURPOSE, {"token": TOKEN}, fake.url,
                                                      owner=runner.owner(row.id))
    db.commit()
    assert main(["integrations", "list"]) == 0 and "Демо" in capsys.readouterr().out
    assert main(["integrations", "run", str(row.id)]) == 0, "по умолчанию — первое действие"
    assert "Успешно" in capsys.readouterr().out
    assert main(["integrations", "run", "demo", "--action", "manual"]) == 1
    assert main(["integrations", "run", "999"]) == 2
    assert main(["integrations", "run", "jira"]) == 2
    db.execute(update(Integration).values(enabled=False))
    db.commit()
    assert main(["integrations", "run", str(row.id)]) == 2
    runs = list(db.scalars(select(IntegrationRun).order_by(IntegrationRun.id)))
    assert [r.trigger for r in runs] == ["cli", "cli"]
    assert db.scalar(select(AuditEntry.username).where(AuditEntry.entity_type == "integration",
                                                       AuditEntry.action == "run").limit(1)) == "Командная строка"


def test_cli_inbox(monkeypatch, tmp_path, engine, capsys):
    from app.cli import main
    from app.core.config import settings

    tmp_path = tmp_path / "inbox"
    tmp_path.mkdir()
    monkeypatch.setattr(settings, "inbox_dir", "")
    assert main(["inbox", "scan"]) == 2
    monkeypatch.setattr(settings, "inbox_dir", str(tmp_path))
    monkeypatch.setattr(settings, "inbox_settle_seconds", 0)
    (tmp_path / "tp-weekly").mkdir()
    (tmp_path / "tp-weekly" / "w.xlsx").write_bytes(tp_file())
    assert main(["inbox", "scan"]) == 0 and '"taken": 1' in capsys.readouterr().out
    assert main(["inbox", "cleanup"]) == 0


# ---------------------------------------------------------------- PostgreSQL: два процесса одновременно

PG_URL = os.environ.get("TEST_POSTGRES_URL")


@pytest.fixture()
def pg_factory():
    if not PG_URL:
        pytest.skip("TEST_POSTGRES_URL не задан")
    from app.core.migrate import upgrade

    name = f"claim_{uuid.uuid4().hex[:8]}"
    admin_engine = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = PG_URL.rsplit("/", 1)[0] + f"/{name}"
    upgrade(url)
    engine = create_engine(url, pool_size=10)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()
    drop_pg_database(admin_engine, name)
    admin_engine.dispose()


@pytest.mark.postgres
def test_claim_waits_for_row_lock_on_postgres(pg_factory):
    """Второй процесс ждёт блокировку строки первого и после его commit условие уже не выполняется."""
    with pg_factory() as db:
        integration_id = _due(db)
    now = utcnow()
    first, second = pg_factory(), pg_factory()
    first.execute(update(Integration).where(Integration.id == integration_id, Integration.next_run_at <= now)
                  .values(next_run_at=now + timedelta(hours=1)))  # занято, commit ещё не сделан
    outcome: list[bool] = []
    thread = threading.Thread(target=lambda: outcome.append(runner._claim(second, integration_id, now, None)))
    thread.start()
    time.sleep(0.5)
    assert thread.is_alive(), "второй ждёт блокировку строки"
    first.commit()
    thread.join(5)
    assert outcome == [False]
    first.close()
    second.close()


@pytest.mark.postgres
def test_parallel_claims_on_postgres(pg_factory):
    with pg_factory() as db:
        ids = [_due(db, name=f"Демо {n}") for n in range(3)]
    now = utcnow()
    barrier = threading.Barrier(6)
    results: list[list] = []

    def worker():
        with pg_factory() as db:
            barrier.wait()
            results.append(runner.claim_due(now, db))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    claimed = sorted(i for batch in results for i, _ in batch)
    assert claimed == sorted(ids), "каждое подключение занято ровно одним процессом"


def test_json_field_accepts_parsed_and_text_values():
    from app.integrations.base import Connector, Field, _coerce

    f = Field("rules", "Правила", "json")
    assert _coerce(Connector, f, [{"a": 1}]) == [{"a": 1}]
    assert _coerce(Connector, f, '[{"a": 1}]') == [{"a": 1}]
    assert _coerce(Connector, f, "  ") is None
    with pytest.raises(ValidationFailed) as exc:
        _coerce(Connector, f, "[{'a': 1}]")
    assert "ошибка JSON в строке 1" in exc.value.detail and "config.rules" in exc.value.fields
    with pytest.raises(ValidationFailed) as exc:
        _coerce(Connector, f, [{"x": "я" * 40000}])
    assert "64 КБ" in exc.value.detail


# ---------------------------------------------------------------- секреты не выходят наружу

LEAK = "S3cr3t-Hook-0042"


class LeakyConnector(Connector):
    """Коннектор, чей секрет уходит в пути адреса (как вебхук Bitrix24) и возвращается в текстах ошибок."""

    kind = "leaky"
    title = "Протекающая система"
    fields = (Field("base_url", "Адрес", "url", required=True),
              Field("hook", "Код вебхука", "password", required=True, secret=True))
    actions = (Action("pull", "Забрать"), Action("crash", "Упасть"), Action("echo", "Эхо"), Action("raise", "Ошибка"))

    def check(self) -> CheckResult:
        with self.http() as c:
            c.get_json(f"rest/{self.secrets['hook']}/profile")
        return CheckResult(True, "Подключено")

    def run(self, action: str, ctx: RunContext) -> RunResult:
        hook = self.secrets["hook"]
        if action == "crash":
            raise RuntimeError(f"сбой при обращении к {self.config['base_url']}/rest/{hook}/x")
        if action == "echo":
            return RunResult.partial(f"ответ системы: ключ {hook} принят частично", error=f"код {hook} устарел",
                                     details={"url": f"{self.config['base_url']}/rest/{hook}/", "note": [hook]})
        if action == "raise":
            raise IntegrationError(f"Система вернула {hook}", code="http_error", short=f"Ошибка ({hook})")
        with self.http() as c:
            c.post_json(f"rest/{hook}/pull", {})
        return RunResult.ok("Забрано")


@pytest.fixture()
def leaky(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    base.register(LeakyConnector)
    server = FakeServer()
    server.route("GET", f"/rest/{LEAK}/profile", lambda r: (500, {"message": f"hook {LEAK} is invalid"}))
    server.route("POST", f"/rest/{LEAK}/pull", lambda r: (503, {"message": f"busy, retry {LEAK}"},
                                                         {"Retry-After": "1"}))
    with server:
        yield server
    base.unregister("leaky")


def test_secret_never_leaks_to_logs_rows_or_api(admin, leaky, db, caplog):
    import json as jsonlib
    import logging

    caplog.set_level(logging.DEBUG)
    body = {"kind": "leaky", "name": "Протечка", "config": {"base_url": leaky.url}, "secrets": {"hook": LEAK}}
    created = admin.post("/api/integrations", json=body)
    assert created.status_code == 201, created.text
    item = created.json()
    responses = [created.text,
                 admin.post("/api/integrations/check", json={"kind": "leaky", "config": {"base_url": leaky.url},
                                                             "secrets": {"hook": LEAK}}).text,
                 admin.post(f"/api/integrations/{item['id']}/check").text,
                 admin.post(f"/api/integrations/{item['id']}/check", json={"secrets": {"hook": LEAK}}).text]
    runs = {}
    for action in ("pull", "crash", "echo", "raise"):
        response = admin.post(f"/api/integrations/{item['id']}/run", json={"action": action})
        assert response.status_code == 200, response.text
        runs[action] = response.json()
        responses.append(response.text)
    responses += [admin.get(f"/api/integrations/{item['id']}").text, admin.get("/api/integrations").text,
                  admin.get(f"/api/integrations/{item['id']}/runs").text]
    assert runs["pull"]["status"] == "error" and "временно недоступна (503)" in runs["pull"]["error"]
    assert sum(1 for r in leaky.requests if r.path.endswith("/pull")) == 1, "POST при 503 не повторяется"
    assert runs["crash"]["error"] == runner.INTERNAL_ERROR
    assert runs["echo"]["status"] == "partial" and "ключ … принят" in runs["echo"]["message"]
    assert "…" in runs["raise"]["error"]
    assert "сбой при обращении к" in caplog.text and "Traceback" in caplog.text, "в журнале — сообщение и трассировка"
    db.expire_all()
    row = db.get(Integration, item["id"])
    stored = [row.last_error, jsonlib.dumps(row.state, ensure_ascii=False), row.secret_bound_url or ""]
    for run in db.scalars(select(IntegrationRun).where(IntegrationRun.integration_id == item["id"])):
        stored += [run.message, run.error, jsonlib.dumps(run.summary, ensure_ascii=False)]
    stored += [f"{e.summary} {jsonlib.dumps(e.after, ensure_ascii=False)}"
               for e in db.scalars(select(AuditEntry).where(AuditEntry.entity_type == "integration"))]
    for where, content in (("журнал сервера", caplog.text), *(("ответ API", t) for t in responses),
                           *(("база", t) for t in stored)):
        assert LEAK not in content, f"{where}: {content[:300]}"


# ---------------------------------------------------------------- каталог показателей через каркас

def test_ensure_indicator_creates_as_source_commits_and_returns_existing(db, demo):
    from app.core import db as core_db
    from app.core.errors import Conflict
    from app.models import Indicator
    from app.services import reports

    integration = Integration(kind="demo", name="Демо", enabled=False, config={}, schedule={}, state={},
                              last_error="")
    db.add(integration)
    db.commit()
    ctx = RunContext(db=db, integration=integration)
    body = {"key": "demo.tickets", "name": "Заявки демо", "unit": "шт.", "owner_service": "tech",
            "source_type": "manual", "description": "Значения загружает подключение «Демо»"}
    ind = ctx.plans.ensure_indicator(body)
    assert isinstance(ind, reports.IndicatorDef) and ind.key == "demo.tickets" and ind.is_active and not ind.computed
    with core_db.SessionLocal() as other:
        assert other.scalar(select(Indicator.name).where(Indicator.key == "demo.tickets")) == "Заявки демо", \
            "создан и зафиксирован: виден другим сессиям и плану значений"
    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "indicator", AuditEntry.action == "create")
                      .order_by(AuditEntry.id.desc()))
    assert entry.username == "Подключение «Демо»" and entry.user_id is None, "журнал — от имени подключения"
    plan = ctx.plans.indicator_values([{"line": 1, "department": "TECH", "indicator": "demo.tickets",
                                        "period": "2026-07", "value": "5", "target": None, "comment": ""}])
    assert plan["can_apply"] and plan["summary"]["create"] == 1, "план значений в том же запуске видит показатель"
    again = ctx.plans.ensure_indicator({**body, "name": "Другое название", "unit": "%"})
    assert again.id == ind.id and again.name == "Заявки демо" and again.unit == "шт.", "существующий — как есть"
    computed = ctx.plans.ensure_indicator({"key": "tech.in_work", "name": "x"})
    assert computed.computed, "вычисляемый возвращается, решение — за коннектором"
    with pytest.raises(Conflict):
        ctx.plans.ensure_indicator({**body, "key": "demo.other"})          # название занято
    with pytest.raises(ValidationFailed) as exc:
        ctx.plans.ensure_indicator({"key": "Bad Key", "name": "Плохой"})
    assert "не создан" in exc.value.detail
    assert db.scalar(select(func.count()).select_from(Indicator).where(Indicator.key == "demo.other")) == 0
    assert ctx.plans.ensure_indicator(body).id == ind.id, "после ошибки сессия работает"


def test_zero_fill_writes_zero_not_clear(db, demo):
    """zero_fill: сумма, у которой данных больше нет, становится 0 — значение остаётся (не очищается)."""
    from app.integrations.connectors import _metrics as metrics
    from app.services import report_admin
    from app.services.inbox import source_actor

    integration = Integration(kind="demo", name="Демо", enabled=False, config={}, schedule={}, state={},
                              last_error="")
    db.add(integration)
    db.commit()
    ctx = RunContext(db=db, integration=integration)
    units = metrics.Units.load(db)
    month = metrics.Month(datetime(2026, 7, 1).date())
    tech = units.by_code["tech"]
    report_admin.apply_import(db, source_actor("x"), [{"line": 1, "department": "TECH", "indicator": "ops.plan",
                                                       "period": "2026-07", "value": "5", "target": None,
                                                       "comment": ""}])
    db.commit()
    ctx.state["written"] = {f"ops.plan|{month.key}": [tech]}
    cells = metrics.zero_fill(ctx, [], [month], {"ops.plan"}, units, "из демо")
    assert [(c.unit, c.value) for c in cells] == [(tech, 0.0)]
    result = metrics.write(ctx, cells, units, apply=True, label="демо")
    assert (result.update, result.cleared) == (1, 0) and result.applied
    assert result.sample[0]["action"] == "update"


class DualConnector(DemoConnector):
    """Секрет уходит на два адреса: основной и «для запросов сервера» (как у «По Делу»)."""

    kind = "dual"
    fields = (*DemoConnector.fields, Field("server_url", "Адрес для запросов сервера", "url"))
    secret_url_fields = ("base_url", "server_url")

    @classmethod
    def secret_url(cls, config: dict) -> str:
        return " → ".join(u for u in (config.get("base_url"), config.get("server_url")) if u)

    @property
    def url(self) -> str | None:
        return self.config.get("server_url") or self.config.get("base_url")


def test_secret_binding_by_connector_secret_url(admin, fake, db):
    base.register(DualConnector)
    try:
        kinds = {k["kind"]: k for k in admin.get("/api/integrations/kinds").json()}
        assert kinds["dual"]["secret_url_fields"] == ["base_url", "server_url"]
        created = admin.post("/api/integrations", json={
            "kind": "dual", "name": "Два адреса", "config": {"base_url": "https://demo.company.ru", "login": "svc",
                                                            "server_url": fake.url},
            "secrets": {"token": TOKEN}})
        assert created.status_code == 201, created.text
        item = created.json()
        assert item["secret_bound_url"] == f"https://demo.company.ru → {fake.url}"
        assert admin.post(f"/api/integrations/{item['id']}/check").json()["ok"], "секрет — для обоих адресов"
        moved = admin.patch(f"/api/integrations/{item['id']}", json={"config": {"server_url": "http://10.0.0.9"}})
        assert moved.status_code == 422 and moved.json()["code"] == "secret_rebind_required"
        draft = admin.post(f"/api/integrations/{item['id']}/check", json={"config": {"server_url": "http://10.0.0.9"}})
        assert not draft.json()["ok"] and draft.json()["details"]["code"] == "secret_missing", \
            "проверка с другим адресом не берёт сохранённый секрет"
        db.execute(update(Integration).where(Integration.id == item["id"]).values(config={
            **item["config"], "server_url": "http://10.0.0.9"}))
        db.commit()
        assert admin.get(f"/api/integrations/{item['id']}").json()["secret_problem"]
    finally:
        base.unregister("dual")
