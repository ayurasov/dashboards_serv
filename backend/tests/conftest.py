"""Общие фикстуры тестов.

Шаблонная база создаётся один раз за прогон настоящими миграциями (как в эксплуатации)
и заполняется справочниками и демонстрационными данными. Каждый тест получает свою
копию файла базы, поэтому тесты независимы и могут менять данные как угодно.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

# Настройки до импорта приложения
_TMP = Path(tempfile.mkdtemp(prefix="dashboards-tests-"))
os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": f"sqlite:///{_TMP / 'bootstrap.db'}",
    "SECRET_KEY": "test-secret-key-0123456789abcdef0123456789abcdef",
    "BCRYPT_ROUNDS": "4",
    "DEMO_DATA": "false",
    "LOG_LEVEL": "WARNING",
    "FRONTEND_DIST": str(_TMP / "no-frontend"),
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core import db as core_db  # noqa: E402
from app.core.migrate import upgrade  # noqa: E402

TEMPLATE = _TMP / "template.db"

DEMO_PASSWORDS = {
    "admin": "admin123", "hr_head": "hr123456", "tp_lead": "tp123456", "product": "pp123456",
    "viewer": "view1234", "it_viewer": "it123456",
}


def _build_template() -> None:
    from app.services.demo_data import load_demo_data
    from app.services.reference_data import sync_reference_data

    url = f"sqlite:///{TEMPLATE}"
    upgrade(url)
    engine = core_db.make_engine(url)
    with sessionmaker(bind=engine)() as session:
        sync_reference_data(session)
        load_demo_data(session)
        session.commit()
    engine.dispose()


_build_template()


@pytest.fixture()
def db_url(tmp_path) -> str:
    path = tmp_path / "test.db"
    shutil.copyfile(TEMPLATE, path)
    return f"sqlite:///{path}"


@pytest.fixture()
def engine(db_url, monkeypatch):
    engine = core_db.make_engine(db_url)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(core_db, "engine", engine)
    monkeypatch.setattr(core_db, "SessionLocal", factory)
    from app.api.routers import system

    monkeypatch.setattr(system, "engine", engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(engine):
    session = core_db.SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def app(engine):
    from app.api.routers.auth import login_limiter
    from app.main import app as fastapi_app

    def override_db():
        session = core_db.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[core_db.get_db] = override_db
    login_limiter.clear()
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


class ApiClient(TestClient):
    """TestClient, который сам подставляет CSRF-токен из cookie в изменяющие запросы."""

    def request(self, method, url, *args, **kwargs):
        if method.upper() not in ("GET", "HEAD", "OPTIONS"):
            headers = dict(kwargs.pop("headers", None) or {})
            token = self.cookies.get("ds_csrf")
            if token and "x-csrf-token" not in {k.lower() for k in headers}:
                headers["X-CSRF-Token"] = token
            kwargs["headers"] = headers
        return super().request(method, url, *args, **kwargs)

    def login(self, username: str, password: str | None = None):
        response = self.post("/api/auth/login", json={"username": username,
                                                       "password": password or DEMO_PASSWORDS[username]})
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture()
def client(app) -> ApiClient:
    with ApiClient(app) as c:
        yield c


@pytest.fixture()
def login(app):
    """login('viewer') → клиент с сессией этого пользователя."""
    clients: list[ApiClient] = []

    def _login(username: str, password: str | None = None) -> ApiClient:
        c = ApiClient(app)
        c.__enter__()
        c.login(username, password)
        clients.append(c)
        return c

    yield _login
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture()
def admin(login) -> ApiClient:
    return login("admin")
