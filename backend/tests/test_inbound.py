"""Приём по API (/api/inbound/v1) и ключи для входящих вызовов: выпуск (показывается один раз), хранение
SHA-256, области, отзыв и перевыпуск, ограничение частоты (общий счётчик в базе), формат ошибок, без CSRF и без
сессии."""
from __future__ import annotations

import hashlib
import os
import threading
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.db import utcnow
from app.models import AuditEntry, InboundKey, InboxItem, InboxRule
from app.services import integration_admin
from tests.conftest import drop_pg_database
from tests.test_inbox import partnerships_file, tp_file


@pytest.fixture()
def raw(app):
    """Клиент без сессии и без CSRF — как 1С или скрипт."""
    with TestClient(app) as c:
        yield c


def issue(admin, name="1С: ЗУП", scopes=("files", "status")) -> dict:
    response = admin.post("/api/integrations/keys", json={"name": name, "scopes": list(scopes)})
    assert response.status_code == 201, response.text
    return response.json()


def bearer(key: dict | str) -> dict:
    return {"Authorization": f"Bearer {key['key'] if isinstance(key, dict) else key}"}


def test_issue_key_is_shown_once_and_stored_hashed(admin, db):
    key = issue(admin)
    assert key["key"].startswith("dash_") and len(key["key"]) > 40
    assert key["prefix"] == key["key"][:12] and key["active"] and key["scopes"] == ["files", "status"]
    row = db.get(InboundKey, key["id"])
    assert row.sha256 == hashlib.sha256(key["key"].encode()).hexdigest()
    listing = admin.get("/api/integrations/keys").json()
    assert key["key"] not in str(listing) and listing[0]["prefix"] == key["prefix"]
    from app.core.config import settings

    assert key["rate_limit"] == listing[0]["rate_limit"] == settings.inbound_rate_limit == 120, \
        "частота вызовов ключа в минуту (INBOUND_RATE_LIMIT) — для интерфейса"
    assert db.scalar(select(AuditEntry.summary).where(AuditEntry.entity_type == "inbound_key")).startswith("Выпущен")
    assert admin.post("/api/integrations/keys", json={"name": "x", "scopes": ["admin"]}).status_code == 422
    assert admin.post("/api/integrations/keys", json={"name": " ", "scopes": ["files"]}).status_code == 422


def test_ping_and_auth_errors(admin, raw, db):
    key = issue(admin)
    ok = raw.get("/api/inbound/v1/ping", headers=bearer(key))
    assert ok.status_code == 200 and ok.json()["ok"] and ok.json()["app"] == "dashboards"
    assert ok.json()["key"] == {"name": "1С: ЗУП", "prefix": key["prefix"], "scopes": ["files", "status"]}
    assert ok.headers["cache-control"] == "no-store"
    assert db.get(InboundKey, key["id"]).last_used_at is not None
    missing = raw.get("/api/inbound/v1/ping")
    body = missing.json()
    assert missing.status_code == 401 and body["code"] == body["error"] == "auth_required"
    assert body["message"] == body["detail"] and "Bearer" in body["message"]
    wrong = raw.get("/api/inbound/v1/ping", headers=bearer("dash_" + "x" * 43))
    assert wrong.status_code == 401 and wrong.json()["error"] == "invalid_key"
    assert raw.get("/api/inbound/v1/ping", headers=bearer("not-a-key")).status_code == 401
    unknown = raw.get("/api/inbound/v1/nothing", headers=bearer(key))
    assert unknown.status_code == 404 and unknown.json()["error"] == "not_found" and unknown.json()["message"]


def test_session_does_not_authenticate_inbound(admin):
    """Вход в интерфейс (cookie) не открывает приём по API: нужен ключ."""
    response = admin.get("/api/inbound/v1/ping")
    assert response.status_code == 401


def test_revoke_and_reissue(admin, raw, db):
    key = issue(admin)
    reissued = admin.post(f"/api/integrations/keys/{key['id']}/reissue").json()
    assert reissued["key"] != key["key"] and reissued["prefix"] != key["prefix"]
    assert raw.get("/api/inbound/v1/ping", headers=bearer(key)).status_code == 401, "старое значение не работает"
    assert raw.get("/api/inbound/v1/ping", headers=bearer(reissued)).status_code == 200
    revoked = admin.post(f"/api/integrations/keys/{key['id']}/revoke").json()
    assert revoked["active"] is False and revoked["revoked_at"]
    assert raw.get("/api/inbound/v1/ping", headers=bearer(reissued)).status_code == 401
    assert admin.post(f"/api/integrations/keys/{key['id']}/reissue").status_code == 409
    actions = set(db.scalars(select(AuditEntry.action).where(AuditEntry.entity_type == "inbound_key")))
    assert actions == {"create", "reissue", "revoke"}


def test_scopes(admin, raw):
    files_only = issue(admin, "Файлы", ["files"])
    status_only = issue(admin, "Статусы", ["status"])
    sent = raw.post("/api/inbound/v1/files", headers=bearer(files_only), files={"file": ("w.xlsx", tp_file())})
    assert sent.status_code == 201
    forbidden = raw.get(f"/api/inbound/v1/files/{sent.json()['id']}", headers=bearer(files_only))
    assert forbidden.status_code == 403 and forbidden.json()["error"] == "scope_forbidden"
    assert raw.post("/api/inbound/v1/files", headers=bearer(status_only),
                    files={"file": ("w.xlsx", tp_file())}).status_code == 403
    assert raw.get(f"/api/inbound/v1/files/{sent.json()['id']}", headers=bearer(status_only)).status_code == 404, \
        "статусы — только своих файлов"


def test_receive_file_dedup_rules_and_status(admin, raw, db):
    key = issue(admin)
    sent = raw.post("/api/inbound/v1/files", headers=bearer(key), files={"file": ("Отчёт ТП.xlsx", tp_file())})
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert body["status"] == "pending" and body["dataset"] == "tp-weekly" and body["summary"]["create"] == 1
    assert "не включено «применять сразу»" in body["message"]
    item = db.get(InboxItem, body["id"])
    assert item.source == "api" and item.inbound_key_id == key["id"] and item.received_by == "Ключ «1С: ЗУП»"
    again = raw.post("/api/inbound/v1/files", headers=bearer(key), files={"file": ("copy.xlsx", tp_file())})
    assert again.status_code == 200 and again.json()["status"] == "duplicate" and again.json()["duplicate_of"]
    status = raw.get(f"/api/inbound/v1/files/{body['id']}", headers=bearer(key)).json()
    assert status["status"] == "pending" and status["id"] == body["id"]
    # «Применять сразу» для API и набора — файл применяется; apply=false — только план
    db.merge(InboxRule(source="api", dataset="partnerships", auto_apply=True))
    db.commit()
    plan_only = raw.post("/api/inbound/v1/files", headers=bearer(key), data={"apply": "false"},
                         files={"file": ("p.xlsx", partnerships_file())}).json()
    assert plan_only["status"] == "pending" and "только план" in plan_only["message"]
    admin.post(f"/api/inbox/{plan_only['id']}/reject")
    applied = raw.post("/api/inbound/v1/files", headers=bearer(key), data={"dataset": "partnerships"},
                       files={"file": ("p.xlsx", partnerships_file())}).json()
    assert applied["status"] == "applied" and applied["applied_at"]
    receive = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "inbox_item",
                                                 AuditEntry.entity_id == str(applied["id"]),
                                                 AuditEntry.action == "apply"))
    assert receive.username == "Ключ «1С: ЗУП»" and receive.user_id is None


def test_receive_validation_errors_have_interop_format(admin, raw, monkeypatch):
    from app.core.config import settings

    key = issue(admin)
    unknown = raw.post("/api/inbound/v1/files", headers=bearer(key), data={"dataset": "nope"},
                       files={"file": ("w.xlsx", tp_file())})
    assert unknown.status_code == 422 and unknown.json()["error"] == "validation_error"
    no_file = raw.post("/api/inbound/v1/files", headers=bearer(key))
    assert no_file.status_code == 422 and no_file.json()["message"]
    monkeypatch.setattr(settings, "inbox_max_mb", 1)
    big = raw.post("/api/inbound/v1/files", headers=bearer(key), files={"file": ("b.csv", b"x" * (1024 * 1024 + 1))})
    assert big.status_code == 413 and big.json()["error"] == "payload_too_large"
    broken = raw.post("/api/inbound/v1/files", headers=bearer(key), data={"dataset": "tp-weekly"},
                      files={"file": ("w.xlsx", b"garbage")}).json()
    assert broken["status"] == "error" and broken["ok"] is False and broken["error"]


def test_rate_limit_per_key(admin, raw, db, monkeypatch):
    monkeypatch.setattr(settings, "inbound_rate_limit", 3)
    first, second = issue(admin, "A"), issue(admin, "B")
    for _ in range(3):
        assert raw.get("/api/inbound/v1/ping", headers=bearer(first)).status_code == 200
    limited = raw.get("/api/inbound/v1/ping", headers=bearer(first))
    assert limited.status_code == 429 and limited.json()["error"] == limited.json()["code"] == "rate_limited"
    assert "Не больше 3 запросов в минуту" in limited.json()["message"]
    assert 1 <= int(limited.headers["retry-after"]) <= 60
    assert raw.post("/api/inbound/v1/files", headers=bearer(first), files={"file": ("w.xlsx", tp_file())}) \
        .status_code == 429, "и приём файлов"
    assert raw.get("/api/inbound/v1/ping", headers=bearer(second)).status_code == 200, "у каждого ключа свой счёт"
    db.expire_all()
    row = db.get(InboundKey, first["id"])
    assert row.rate_count == 5 and row.rate_window_start is not None, "счётчик окна — в строке ключа в базе"
    # Окно истекло — счёт заново
    db.query(InboundKey).filter(InboundKey.id == first["id"]).update(
        {"rate_window_start": utcnow() - timedelta(seconds=61)})
    db.commit()
    assert raw.get("/api/inbound/v1/ping", headers=bearer(first)).status_code == 200
    db.expire_all()
    assert db.get(InboundKey, first["id"]).rate_count == 1


def test_rate_limit_is_shared_between_processes(admin, raw, app, engine, monkeypatch):
    """Два процесса (gunicorn) — два пула соединений к одной базе: предел общий, а не N × INBOUND_RATE_LIMIT."""
    from app.core import db as core_db

    monkeypatch.setattr(settings, "inbound_rate_limit", 4)
    key = issue(admin, "Общий")
    other = core_db.make_engine(str(engine.url))
    other_sessions = sessionmaker(bind=other, autoflush=False, expire_on_commit=False)
    try:
        def second_process():
            session = other_sessions()
            try:
                yield session
            finally:
                session.close()

        first_process = app.dependency_overrides[core_db.get_db]
        statuses = []
        for n in range(6):
            app.dependency_overrides[core_db.get_db] = second_process if n % 2 else first_process
            statuses.append(raw.get("/api/inbound/v1/ping", headers=bearer(key)).status_code)
        assert statuses == [200, 200, 200, 200, 429, 429], "каждому «процессу» досталось по 2, а не по 4"
    finally:
        other.dispose()


def test_rate_limit_window_and_retry_after(db, admin):
    key = db.get(InboundKey, issue(admin, "Окно")["id"])
    start = utcnow()
    assert [integration_admin.hit_rate_limit(db, key, 2, start + timedelta(seconds=s)) for s in (0, 1)] == [0, 0]
    assert integration_admin.hit_rate_limit(db, key, 2, start + timedelta(seconds=20)) == 40, "секунд до конца окна"
    assert integration_admin.hit_rate_limit(db, key, 2, start + timedelta(seconds=59, milliseconds=500)) == 1
    assert integration_admin.hit_rate_limit(db, key, 2, start + timedelta(seconds=60)) == 0, "новое окно"
    db.commit()
    db.refresh(key)
    assert key.rate_window_start == start + timedelta(seconds=60) and key.rate_count == 1


def test_rate_limit_without_returning(db, admin, monkeypatch):
    """SQLite до 3.35 (без RETURNING): тот же UPDATE, итог читается в той же транзакции."""
    key = db.get(InboundKey, issue(admin, "Старый SQLite")["id"])
    monkeypatch.setattr(db.get_bind().dialect, "update_returning", False)
    now = utcnow()
    assert [integration_admin.hit_rate_limit(db, key, 2, now) for _ in range(3)] == [0, 0, 60]


PG_URL = os.environ.get("TEST_POSTGRES_URL")


@pytest.mark.postgres
def test_rate_limit_is_atomic_on_postgres():
    """Параллельные вызовы одного ключа из разных соединений: ровно limit разрешено (UPDATE … RETURNING)."""
    if not PG_URL:
        pytest.skip("TEST_POSTGRES_URL не задан")
    from app.core.migrate import upgrade

    name = f"rate_{uuid.uuid4().hex[:8]}"
    admin_engine = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = PG_URL.rsplit("/", 1)[0] + f"/{name}"
    try:
        upgrade(url)
        engine = create_engine(url, pool_size=12)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as db:
            key = InboundKey(name="Параллельный", sha256="0" * 64, prefix="dash_0000000", scopes=["files"],
                             issued_at=utcnow(), issued_by="admin")
            db.add(key)
            db.commit()
        barrier = threading.Barrier(10)
        waits: list[int] = []

        def call():
            with factory() as db:
                barrier.wait()
                waits.append(integration_admin.hit_rate_limit(db, key, 6))
                db.commit()

        threads = [threading.Thread(target=call) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        assert sorted(w == 0 for w in waits) == [False] * 4 + [True] * 6
        with factory() as db:
            assert db.get(InboundKey, key.id).rate_count == 10
        engine.dispose()
    finally:
        drop_pg_database(admin_engine, name)
        admin_engine.dispose()


def test_key_scopes_have_server_labels(admin):
    scopes = admin.get("/api/integrations/keys/scopes").json()
    assert scopes == [
        {"value": "files", "label": "Приём файлов", "hint": "POST /api/inbound/v1/files — файлы во «Входящие»"},
        {"value": "status", "label": "Чтение статусов принятых файлов",
         "hint": "GET /api/inbound/v1/files/{id} — статус файлов, принятых этим ключом"}]
    key = issue(admin)
    assert key["scope_labels"] == ["Приём файлов", "Чтение статусов принятых файлов"], "одна подпись везде"


def test_keys_need_integrations_manage(login):
    viewer = login("viewer")
    assert viewer.get("/api/integrations/keys").status_code == 403
    assert viewer.post("/api/integrations/keys", json={"name": "x"}).status_code == 403
