"""Миграции: схема совпадает с моделями, базы прежних версий обновляются без потери данных.

PostgreSQL проверяется, если задан TEST_POSTGRES_URL (в CI — сервис postgres:16).
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.core.db import Base
from app.core.migrate import LEGACY_HEAD, alembic_config, upgrade

FIXTURES = Path(__file__).parent / "fixtures"
PG_URL = os.environ.get("TEST_POSTGRES_URL")
HEAD = "0014_org_access"


def _diff(url: str) -> list:
    engine = create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    engine.dispose()
    return diff


@pytest.fixture()
def pg_url():
    if not PG_URL:
        pytest.skip("TEST_POSTGRES_URL не задан")
    name = f"mig_{uuid.uuid4().hex[:8]}"
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = PG_URL.rsplit("/", 1)[0] + f"/{name}"
    yield url
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def test_single_head():
    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    assert heads == [HEAD]


def test_fresh_sqlite_matches_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    assert upgrade(url) == HEAD
    assert _diff(url) == []


def test_upgrade_is_idempotent(tmp_path):
    url = f"sqlite:///{tmp_path / 'twice.db'}"
    upgrade(url)
    assert upgrade(url) == HEAD


def test_0013_downgrade_and_upgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'rev.db'}"
    upgrade(url)
    cfg = alembic_config(url)
    command.downgrade(cfg, "0012_v0_1_0_schema")
    engine = create_engine(url)
    with engine.connect() as conn:
        assert "data_revisions" not in inspect(conn).get_table_names()
    engine.dispose()
    assert upgrade(url) == HEAD
    engine = create_engine(url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM data_revisions")).scalar() == 9
    engine.dispose()


def _org_fixture(conn):
    """Структура из двух уровней, руководитель, пользователь с основным и дополнительным подразделением."""
    conn.execute(text("INSERT INTO departments (id, name, name_key, code, kind, sort_order, org_source, "
                      "created_at, updated_at) VALUES "
                      "(101, 'Компания', 'компания', NULL, 'company', 0, 'manual', "
                      "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    conn.execute(text("INSERT INTO departments (id, name, name_key, code, parent_id, kind, sort_order, org_source, "
                      "created_at, updated_at) VALUES "
                      "(102, 'Отдел', 'отдел', 'D102', 101, 'department', 0, 'manual', CURRENT_TIMESTAMP, "
                      "CURRENT_TIMESTAMP), (103, 'Отдел', 'отдел', NULL, 102, 'group', 0, 'manual', "
                      "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    conn.execute(text("INSERT INTO users (id, username, full_name, role, is_active, must_change_password, "
                      "reports_to_none, auth_source, access_overrides, department_id, created_at, updated_at) VALUES "
                      "(101, 'u101', 'Без пароля', 'user', true, false, false, 'ldap', '{}', 102, "
                      "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    conn.execute(text("INSERT INTO user_access_units (user_id, department_id) VALUES (101, 103)"))
    conn.execute(text("INSERT INTO department_heads (department_id, user_id, is_primary) VALUES (102, 101, true)"))
    conn.execute(text("INSERT INTO service_access (user_id, service_key, level, org_scope, granted_at) "
                      "VALUES (101, 'hr', 'viewer', 'branch', CURRENT_TIMESTAMP), "
                      "(101, 'tech', 'none', NULL, CURRENT_TIMESTAMP)"))


def test_0014_downgrade_and_upgrade(tmp_path):
    """Откат 0014 сохраняет доступ и подразделения пользователей (в виде 0.1.0) и повторно применяется."""
    url = f"sqlite:///{tmp_path / 'org.db'}"
    upgrade(url)
    engine = create_engine(url)
    with engine.begin() as conn:
        _org_fixture(conn)
    engine.dispose()

    command.downgrade(alembic_config(url), "0013_data_revisions")
    engine = create_engine(url)
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        assert {"access_profiles", "department_heads", "user_access_units", "app_settings"}.isdisjoint(tables)
        links = conn.execute(text("SELECT department_id FROM user_departments WHERE user_id = 101")).scalars()
        assert set(links) == {102, 103}
        assert conn.execute(text("SELECT service_key, level, department_scope FROM service_access "
                                 "WHERE user_id = 101")).all() == [("hr", "viewer", 1)]
        names = set(conn.execute(text("SELECT name FROM departments WHERE id IN (102, 103)")).scalars())
        assert len(names) == 2, "одинаковые имена в разных ветках разведены — в 0.1.0 имя уникально"
    engine.dispose()

    assert upgrade(url) == HEAD
    assert _diff(url) == []
    engine = create_engine(url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT department_id FROM users WHERE id = 101")).scalar() == 102
        assert conn.execute(text("SELECT org_scope FROM service_access WHERE user_id = 101")).scalar() == "branch"
    engine.dispose()


def test_downgrade_of_0012_is_refused(tmp_path):
    url = f"sqlite:///{tmp_path / 'down.db'}"
    upgrade(url)
    cfg = alembic_config(url)
    with pytest.raises(RuntimeError, match="резервную копию"):
        command.downgrade(cfg, LEGACY_HEAD)


def test_legacy_create_all_database_is_upgraded(tmp_path):
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(path)
    con.executescript((FIXTURES / "legacy_create_all.sql").read_text(encoding="utf-8"))
    con.close()
    url = f"sqlite:///{path}"
    assert upgrade(url) == HEAD
    assert _diff(url) == []

    engine = create_engine(url)
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        assert not any(t.startswith("_legacy") for t in tables)
        assert not {"month_records", "tp_report_rows", "user_service_access", "audit_logs"} & tables

        def rows(sql):
            return conn.execute(text(sql)).all()

        roles = dict(rows("SELECT username, role FROM users"))
        assert roles == {"admin": "admin", "hr_head": "user", "viewer": "user", "it_viewer": "user"}
        access = {(u, s): (lvl, scope) for u, s, lvl, scope in rows(
            "SELECT u.username, a.service_key, a.level, a.org_scope FROM service_access a "
            "JOIN users u ON u.id = a.user_id")}
        assert access[("hr_head", "hr")] == ("manager", None)
        assert access[("it_viewer", "hr")] == ("viewer", "branch"), "«свои подразделения» → своя ветка"
        assert access[("viewer", "tech")] == ("viewer", None)
        homes = dict(rows("SELECT u.username, d.code FROM users u JOIN departments d ON d.id = u.department_id"))
        assert homes.get("it_viewer") == "IT", "подразделение пользователя стало основным"

        assert rows("SELECT COUNT(*) FROM hr_months")[0][0] == 2
        assert rows("SELECT comment FROM hr_months ORDER BY month")[0][0].startswith("Подписано соглашение")
        assert rows("SELECT COUNT(*) FROM hr_employee_events")[0][0] == 6
        values = rows("SELECT metric_key, value FROM hr_metric_values WHERE metric_key = 'turnover'")
        assert values and all(v is not None for _, v in values)

        tech_rules = dict(rows("SELECT metric_key, direction FROM traffic_light_rules WHERE service_key = 'tech'"))
        assert tech_rules["total_in_work"] == "lower_is_better"
        assert tech_rules["ratio_solved_received"] == "higher_is_better"
        assert rows("SELECT COUNT(*) FROM traffic_light_rules WHERE service_key = 'hr'")[0][0] == 7

        weeks = rows("SELECT year, week, total_in_work FROM tp_weekly_reports ORDER BY year, week")
        assert len(weeks) == 6, "дубль недели схлопнут, строка без года и недели отброшена"
        assert all(isinstance(y, int) and isinstance(w, int) for y, w, _ in weeks)
        assert 999 in [v for _, _, v in weeks], "из дублей недели остаётся последняя строка"

        tickets = rows("SELECT number, status, is_reopened FROM naumen_tickets")
        numbers = [n for n, _, _ in tickets]
        assert len(numbers) == len(set(numbers)) == 6
        assert ("Выполнена", 1) in [(s, r) for _, s, r in tickets]

        assert rows("SELECT COUNT(*) FROM partnerships")[0][0] == 4
        targets = rows("SELECT metric_key, year, reference_value, target_value FROM hr_targets ORDER BY year")
        assert ("turnover", 2025, 5.17, None) in [tuple(t) for t in targets]
        assert all(ref is None for key, year, ref, target in targets if year == 2026)
        assert rows("SELECT COUNT(*) FROM color_palettes WHERE is_active")[0][0] == 1
        assert rows("SELECT COUNT(*) FROM services")[0][0] == 9
    engine.dispose()


def test_legacy_alembic_database_is_upgraded_on_sqlite(tmp_path):
    _legacy_chain_with_data(f"sqlite:///{tmp_path / 'chain.db'}")


@pytest.mark.postgres
def test_fresh_postgres_matches_models(pg_url):
    assert upgrade(pg_url) == HEAD
    assert _diff(pg_url) == []


@pytest.mark.postgres
def test_legacy_alembic_database_is_upgraded_on_postgres(pg_url):
    _legacy_chain_with_data(pg_url)
    engine = create_engine(pg_url)
    with engine.connect() as conn:
        leftovers = conn.execute(text("SELECT relname FROM pg_class WHERE relname LIKE '\\_lg%'")).all()
        assert leftovers == []
        # последовательности продолжают нумерацию после перенесённых строк
        conn.execute(text("INSERT INTO departments (name, name_key, code, kind, sort_order, org_source, created_at, "
                          "updated_at) VALUES ('Новый', 'новый', 'NEW', 'department', 0, 'manual', now(), now())"))
        new_id = conn.execute(text("SELECT id FROM departments WHERE code = 'NEW'")).scalar()
        assert new_id > 1
    engine.dispose()


def _legacy_chain_with_data(url: str) -> None:
    """Старая цепочка миграций Docker-установки (0001…0011) с данными → 0012."""
    cfg = alembic_config(url)
    cfg.attributes["legacy_naming"] = True
    command.upgrade(cfg, LEGACY_HEAD)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO departments (id, name, code) VALUES (1, 'ИТ-служба', 'IT')"))
        conn.execute(text(
            "INSERT INTO users (id, username, full_name, hashed_password, role, is_active, must_change_password) "
            "VALUES (1, 'boss', 'Начальник', 'x', 'HR_HEAD', true, false), "
            "(2, 'dept', 'Отдел', 'x', 'department_viewer', true, false)"))
        conn.execute(text("INSERT INTO user_departments (user_id, department_id) VALUES (2, 1)"))
        conn.execute(text("INSERT INTO month_records (id, year, month, notes) VALUES (1, 2026, 5, 'май')"))
        conn.execute(text(
            "INSERT INTO metric_definitions (key, label, sort_order) VALUES ('turnover', 'Текучесть', 1)"))
        conn.execute(text(
            "INSERT INTO metric_values (month_record_id, metric_key, numeric_value) VALUES (1, 'turnover', 2.5), "
            "(1, 'orphan_metric', 7)"))
        conn.execute(text("INSERT INTO tp_report_rows (year, week, total_in_work) VALUES (2026.0, 3.0, 200)"))
        conn.execute(text("INSERT INTO tp_settings (key, value) VALUES ('traffic_rules', "
                          "'{\"total_in_work\": {\"direction\": \"less\", \"green\": 1, \"yellow\": 2, "
                          "\"enabled\": true}}')"))
        conn.execute(text("INSERT INTO user_service_access (user_id, service_key, access_level) "
                          "VALUES (1, 'product_partnerships', 'edit_metrics')"))
    engine.dispose()

    assert upgrade(url) == HEAD
    assert _diff(url) == []
    engine = create_engine(url)
    with engine.connect() as conn:
        access = {tuple(r) for r in conn.execute(text(
            "SELECT u.username, a.service_key, a.level FROM service_access a JOIN users u ON u.id = a.user_id"))}
        assert access == {("boss", "hr", "manager"), ("boss", "project_product", "editor"), ("dept", "hr", "viewer")}
        orphan = conn.execute(text(
            "SELECT is_active FROM hr_metric_definitions WHERE key = 'orphan_metric'")).scalar()
        assert orphan in (False, 0), "значение неизвестной метрики сохранено, метрика выключена"
        week = conn.execute(text("SELECT year, week FROM tp_weekly_reports")).one()
        assert tuple(week) == (2026, 3)
        rule = conn.execute(text(
            "SELECT direction, green_threshold FROM traffic_light_rules WHERE service_key = 'tech'")).one()
        assert tuple(rule) == ("lower_is_better", 1.0)
    engine.dispose()


@pytest.mark.postgres
def test_demo_and_reference_data_fit_postgres_constraints(pg_url):
    """PostgreSQL, в отличие от SQLite, проверяет длину строк и типы: все наборы данных должны входить."""
    from sqlalchemy.orm import sessionmaker

    from app.core.db import make_engine
    from app.services.demo_data import load_demo_data
    from app.services.reference_data import ensure_initial_admin, sync_reference_data

    upgrade(pg_url)
    engine = make_engine(pg_url)
    with sessionmaker(bind=engine)() as session:
        sync_reference_data(session)
        load_demo_data(session)
        ensure_initial_admin(session)
        session.commit()
    with engine.connect() as conn:
        counts = {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                  for t in ("users", "hr_months", "tp_weekly_reports", "naumen_tickets", "partnerships")}
    engine.dispose()
    assert counts == {"users": 6, "hr_months": 7, "tp_weekly_reports": 109, "naumen_tickets": 1868, "partnerships": 142}
