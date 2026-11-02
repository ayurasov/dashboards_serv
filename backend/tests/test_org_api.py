"""Структура компании: оргсхема, карточка, подразделения, руководители, настройки, подчинение, история.

Демо-структура (app/services/demo_data.py, DEMO_ORG): АЛМИ Партнер → дирекции → службы → группы;
руководители — ceo, hr_head, tech_dir, tp_lead, it_viewer, product; engineer — в группе SUP-OS.
"""
from __future__ import annotations

import base64
import os
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.errors import Conflict
from app.models import AuditEntry, Department, DepartmentHead, User
from app.schemas.org import DepartmentCreateIn
from app.services import org, org_admin
from tests.conftest import drop_pg_database

from .conftest import ApiClient

PASSWORDS = {"ceo": "ceo12345", "tech_dir": "td123456", "engineer": "en123456"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PG_URL = os.environ.get("TEST_POSTGRES_URL")


def _users(db) -> dict[str, int]:
    return {u.username: u.id for u in db.scalars(select(User))}


def _units(db) -> dict[str, int]:
    return {d.code: d.id for d in db.scalars(select(Department)) if d.code}


def _grant(db, username: str, *capabilities: str) -> None:
    user = db.scalar(select(User).where(User.username == username))
    user.capabilities = list(capabilities)
    db.commit()


def _set(db, username: str, **values) -> None:
    user = db.scalar(select(User).where(User.username == username))
    for key, value in values.items():
        setattr(user, key, value)
    db.commit()


def _as(login, username: str) -> ApiClient:
    return login(username, PASSWORDS.get(username))


# ================================================================ оргсхема

def test_tree_shape_counts_and_reporting_lines(db, login):
    ids, units = _users(db), _units(db)
    body = login("viewer").get("/api/org/tree").json()
    assert body["revision"] == org.current_revision(db)
    assert body["settings"]["max_depth"] == 15 and body["settings"]["default_view"] == "chart"
    assert [k["value"] for k in body["settings"]["unit_kinds"]][:2] == ["company", "division"]
    order = [u["id"] for u in body["units"]]
    assert len(order) == 13 and order[0] == units["ALMI"]
    by_id = {u["id"]: u for u in body["units"]}
    for unit in body["units"]:   # родители раньше вложенных
        assert unit["parent_id"] is None or order.index(unit["parent_id"]) < order.index(unit["id"])
    tech, techdir, sup = by_id[units["TECH"]], by_id[units["TECHDIR"]], by_id[units["SUP-OS"]]
    assert tech["level"] == 3 and tech["kind"] == "service" and tech["child_count"] == 2
    assert tech["head_ids"] == [ids["tp_lead"]] and tech["primary_head_id"] == ids["tp_lead"]
    assert (tech["employee_count"], tech["staff_count"], tech["branch_employee_count"], tech["branch_unit_count"]) \
        == (1, 0, 2, 2)
    assert (sup["employee_count"], sup["staff_count"]) == (1, 1)
    assert (techdir["branch_employee_count"], techdir["branch_unit_count"]) == (4, 4)

    people = {p["id"]: p for p in body["people"]}
    engineer = people[ids["engineer"]]
    assert engineer["direct_manager_id"] == ids["tp_lead"] and engineer["manager_source"] == "structure"
    assert engineer["home_unit_id"] == units["SUP-OS"] and engineer["report_count"] == 0
    assert "email" not in engineer and "username" not in engineer
    assert (people[ids["tp_lead"]]["report_count"], people[ids["tp_lead"]]["branch_count"]) == (1, 1)
    assert (people[ids["tech_dir"]]["report_count"], people[ids["tech_dir"]]["branch_count"]) == (2, 3)
    ceo = people[ids["ceo"]]
    assert ceo["manager_source"] == "top" and ceo["reports_to_none"] and ceo["report_count"] == 3
    assert ceo["branch_count"] == 6 and sorted(ceo["head_of"]) == sorted([units["ALMI"], units["ADMIN"]])
    # hr_head без своего подразделения: числится в руководимом
    assert people[ids["hr_head"]]["home_unit_id"] == units["HR"]
    assert people[ids["viewer"]]["manager_source"] == "none"
    assert body["me"] == {"id": ids["viewer"], "home_unit_id": None}
    assert login("engineer", "en123456").get("/api/org/tree").json()["me"]["home_unit_id"] == units["SUP-OS"]


def test_tree_requires_login(client):
    assert client.get("/api/org/tree").status_code == 401


def test_tree_hides_inactive_and_contacts_from_regular_users(db, admin, login):
    ids = _users(db)
    _set(db, "viewer", is_active=False, email="viewer@example.local")
    regular = {p["id"] for p in login("hr_head").get("/api/org/tree").json()["people"]}
    assert ids["viewer"] not in regular and ids["engineer"] in regular
    privileged = {p["id"]: p for p in admin.get("/api/org/tree").json()["people"]}
    assert privileged[ids["viewer"]]["is_active"] is False
    assert privileged[ids["viewer"]]["email"] == "viewer@example.local"
    assert privileged[ids["viewer"]]["username"] == "viewer"
    # ведущий структуру (не администратор) видит то же, что администратор
    _grant(db, "hr_head", "org.manage")
    assert ids["viewer"] in {p["id"] for p in login("hr_head").get("/api/org/tree").json()["people"]}


def test_inactive_head_is_hidden_from_regular_users(db, admin, login):
    ids, units = _users(db), _units(db)
    _set(db, "tp_lead", is_active=False)
    tech = next(u for u in login("viewer").get("/api/org/tree").json()["units"] if u["id"] == units["TECH"])
    assert tech["head_ids"] == [] and tech["primary_head_id"] is None
    tech = next(u for u in admin.get("/api/org/tree").json()["units"] if u["id"] == units["TECH"])
    assert tech["head_ids"] == [ids["tp_lead"]] and tech["primary_head_id"] is None
    engineer = next(p for p in admin.get("/api/org/tree").json()["people"] if p["id"] == ids["engineer"])
    assert engineer["direct_manager_id"] == ids["tech_dir"], "отключённый руководитель пропускается"
    listed = login("viewer").get(f"/api/departments/{units['TECH']}").json()
    assert listed["heads"] == [] and listed["primary_head_id"] is None
    listed = admin.get(f"/api/departments/{units['TECH']}").json()
    assert listed["heads"][0]["is_active"] is False and listed["primary_head_id"] == ids["tp_lead"]


def test_openapi_documents_org_endpoints(client):
    paths = client.get("/api/openapi.json").json()["paths"]
    for path in ("/api/org/tree", "/api/org/people/{person_id}", "/api/org/settings", "/api/org/export",
                 "/api/org/import/structure", "/api/org/employees/export", "/api/org/employees/import",
                 "/api/org/import/list", "/api/org/sync/ad", "/api/org/history", "/api/departments/{dept_id}/heads"):
        assert path in paths, path
    assert "multipart/form-data" in paths["/api/org/employees/import"]["post"]["requestBody"]["content"]


def test_tree_is_serialized_once_per_revision(db, login, monkeypatch):
    calls = []
    original = org_admin._tree_payload
    monkeypatch.setattr(org_admin, "_tree_payload", lambda *a: calls.append(1) or original(*a))
    viewer, hr = login("viewer"), login("hr_head")
    first = viewer.get("/api/org/tree").json()
    assert hr.get("/api/org/tree").json()["me"]["id"] != first["me"]["id"]
    viewer.get("/api/org/tree")
    assert len(calls) == 1, "один ответ на ревизию для всех обычных пользователей"
    _set(db, "engineer", position="Старший инженер")
    org.invalidate()   # другой процесс увидел бы новую ревизию через секунду; здесь — сразу
    after = viewer.get("/api/org/tree").json()
    assert len(calls) == 2 and after["revision"] == first["revision"] + 1
    assert any(p["position"] == "Старший инженер" for p in after["people"])


def test_tree_reflects_avatar_and_settings(db, admin, login):
    ids = _users(db)
    _set(db, "engineer", avatar="data:image/png;base64," + base64.b64encode(PNG).decode())
    org.invalidate()
    person = next(p for p in login("viewer").get("/api/org/tree").json()["people"] if p["id"] == ids["engineer"])
    assert person["has_avatar"] is True
    assert admin.put("/api/org/settings", json={"default_view": "tree"}).status_code == 200
    assert login("viewer").get("/api/org/tree").json()["settings"]["default_view"] == "tree"


# ================================================================ карточка и фото

def test_person_card(db, login):
    ids, units = _users(db), _units(db)
    viewer = login("viewer")
    card = viewer.get(f"/api/org/people/{ids['engineer']}").json()
    assert card["manager"]["id"] == ids["tp_lead"] and card["manager_source"] == "structure"
    assert [p["id"] for p in card["chain"]] == [ids["tp_lead"], ids["tech_dir"], ids["ceo"]]
    assert [u["id"] for u in card["department_path"]] == [units["ALMI"], units["TECHDIR"], units["TECH"],
                                                          units["SUP-OS"]]
    assert card["structure_manager"]["id"] == ids["tp_lead"] and card["subordinates_count"] == 0
    assert "email" not in card or card["email"] is None
    lead = viewer.get(f"/api/org/people/{ids['tp_lead']}").json()
    assert [p["id"] for p in lead["direct_reports"]] == [ids["engineer"]] and lead["subordinates_count"] == 1
    assert lead["head_of"] == [{"id": units["TECH"], "name": "Техническая служба", "kind": "service",
                                "primary": True, "path": "АЛМИ Партнер / Техническая дирекция / Техническая служба"}]
    hr = viewer.get(f"/api/org/people/{ids['hr_head']}").json()
    assert hr["department_path"] == [] and [u["id"] for u in hr["home_unit_path"]][-1] == units["HR"]
    assert viewer.get("/api/org/people/99999").status_code == 404


def test_person_card_of_inactive_user(db, admin, login):
    ids = _users(db)
    _set(db, "product", is_active=False, email="product@example.local")
    assert login("viewer").get(f"/api/org/people/{ids['product']}").status_code == 404
    card = admin.get(f"/api/org/people/{ids['product']}").json()
    assert card["is_active"] is False and card["email"] == "product@example.local"


def test_avatar(db, login, admin):
    ids = _users(db)
    viewer = login("viewer")
    assert viewer.get(f"/api/org/people/{ids['engineer']}/avatar").status_code == 404
    _set(db, "engineer", avatar="data:image/png;base64," + base64.b64encode(PNG).decode())
    response = viewer.get(f"/api/org/people/{ids['engineer']}/avatar")
    assert response.status_code == 200 and response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, max-age=300"
    # SVG и повреждённые данные не отдаём; тип — по содержимому, а не по data URL
    _set(db, "tp_lead", avatar="data:image/svg+xml;base64," + base64.b64encode(b"<svg onload=x>").decode())
    assert viewer.get(f"/api/org/people/{ids['tp_lead']}/avatar").status_code == 404
    _set(db, "tech_dir", avatar="data:image/png;base64,!!!")
    assert viewer.get(f"/api/org/people/{ids['tech_dir']}/avatar").status_code == 404
    _set(db, "engineer", is_active=False)
    org.invalidate()
    assert viewer.get(f"/api/org/people/{ids['engineer']}/avatar").status_code == 404
    assert admin.get(f"/api/org/people/{ids['engineer']}/avatar").status_code == 200


# ================================================================ справочник подразделений

def test_departments_list_for_everyone(db, login):
    units, ids = _units(db), _users(db)
    rows = login("viewer").get("/api/departments").json()
    assert len(rows) == 13 and rows[0]["path"] == "АЛМИ Партнер" and rows[0]["level"] == 1
    tech = next(r for r in rows if r["id"] == units["TECH"])
    assert tech["path"] == "АЛМИ Партнер / Техническая дирекция / Техническая служба"
    assert tech["parent_id"] == units["TECHDIR"] and tech["kind"] == "service" and tech["level"] == 3
    assert tech["heads"] == [{"user_id": ids["tp_lead"], "full_name": "Руководитель техподдержки",
                              "position": "Руководитель группы", "is_primary": True, "is_active": True}]
    assert tech["primary_head_id"] == ids["tp_lead"] and tech["employee_count"] == 1
    assert tech["branch_employee_count"] == 2 and tech["child_count"] == 2
    one = login("viewer").get(f"/api/departments/{units['IT']}").json()
    assert one["code"] == "IT" and one["heads"][0]["user_id"] == ids["it_viewer"]
    assert login("viewer").get("/api/departments/99999").status_code == 404


def test_create_department(db, admin):
    units = _units(db)
    response = admin.post("/api/departments", json={"name": "  Группа   мониторинга ", "parent_id": units["TECH"],
                                                    "kind": "group", "code": "mon", "sort_order": 5})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Группа мониторинга" and body["code"] == "MON" and body["level"] == 4
    assert body["path"].endswith("Техническая служба / Группа мониторинга") and body["org_source"] == "manual"
    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "department",
                                               AuditEntry.entity_id == str(body["id"])))
    assert entry.action == "create" and entry.service_key is None and entry.after["kind"] == "group"
    # тип по умолчанию — «Отдел»; на верхнем уровне тоже можно
    root = admin.post("/api/departments", json={"name": "Дочерняя компания"}).json()
    assert root["kind"] == "department" and root["parent_id"] is None and root["level"] == 1


@pytest.mark.parametrize(("payload", "status", "code"), [
    ({"name": "Новая", "kind": "unknown"}, 422, "validation_error"),
    ({"name": "Новая", "parent_id": 99999}, 422, "validation_error"),
    ({"name": "  группа поддержки   ALTEROS "}, 409, "department_name_taken"),
    ({"name": "Новая", "code": "it"}, 409, "department_code_taken"),
    ({"name": "   "}, 422, "validation_error"),
])
def test_create_department_errors(db, admin, payload, status, code):
    payload = dict(payload)
    if "группа" in payload["name"]:
        payload["parent_id"] = _units(db)["TECH"]
    response = admin.post("/api/departments", json=payload)
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def test_unknown_kind_message_lists_configured_kinds(db, admin):
    detail = admin.post("/api/departments", json={"name": "X", "kind": "bogus"}).json()["detail"]
    assert "«bogus»" in detail and "Отдел" in detail


def test_create_department_depth_limit(db, admin):
    units = _units(db)
    assert admin.put("/api/org/settings", json={"max_depth": 4}).status_code == 200
    response = admin.post("/api/departments", json={"name": "Слишком глубоко", "parent_id": units["SUP-OS"]})
    assert response.status_code == 409 and response.json()["code"] == "org_too_deep"
    assert "4 уровнями" in response.json()["detail"]


def test_department_changes_need_org_manage(db, login):
    units = _units(db)
    hr = login("hr_head")
    assert hr.post("/api/departments", json={"name": "Отдел"}).status_code == 403
    assert hr.patch(f"/api/departments/{units['AHO']}", json={"name": "X"}).status_code == 403
    assert hr.delete(f"/api/departments/{units['AHO']}").status_code == 403
    assert hr.put(f"/api/departments/{units['AHO']}/heads", json={"user_ids": []}).status_code == 403
    _grant(db, "hr_head", "org.manage")
    hr = login("hr_head")
    assert hr.post("/api/departments", json={"name": "Отдел кадрового учёта", "parent_id": units["HR"]}) \
        .status_code == 201


def test_update_department(db, admin):
    units = _units(db)
    response = admin.patch(f"/api/departments/{units['AHO']}", json={"name": "Хозяйственный отдел", "code": "",
                                                                     "sort_order": 9})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Хозяйственный отдел" and body["code"] is None and body["sort_order"] == 9
    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "department", AuditEntry.action == "update",
                                               AuditEntry.entity_id == str(units["AHO"])))
    assert entry.before == {"name": "АХО", "code": "AHO", "sort_order": 2}
    assert entry.after == {"name": "Хозяйственный отдел", "code": None, "sort_order": 9}
    # перенос в другую ветку и на верхний уровень
    moved = admin.patch(f"/api/departments/{units['MKT']}", json={"parent_id": units["TECHDIR"]}).json()
    assert moved["path"] == "АЛМИ Партнер / Техническая дирекция / Служба маркетинга" and moved["level"] == 3
    assert admin.patch(f"/api/departments/{units['MKT']}", json={"parent_id": None}).json()["level"] == 1
    # PUT — совместимость с интерфейсом 0.1.0 (частичное изменение)
    assert admin.put(f"/api/departments/{units['MKT']}", json={"kind": "direction"}).json()["kind"] == "direction"
    # регистр в названии можно поменять — это то же имя
    assert admin.patch(f"/api/departments/{units['HR']}", json={"name": "служба персонала"}).status_code == 200


@pytest.mark.parametrize(("target", "payload", "code"), [
    ("TECH", {"parent_id": "TECH"}, "org_cycle"),
    ("TECHDIR", {"parent_id": "SUP-OS"}, "org_cycle"),
    ("SUP-OS", {"name": "группа поддержки alteroffice"}, "department_name_taken"),
    ("COMM", {"parent_id": "TECHDIR", "name": "ИТ-служба"}, "department_name_taken"),
    ("COMM", {"code": "tech"}, "department_code_taken"),
    ("COMM", {"kind": "nope"}, "validation_error"),
    ("COMM", {"parent_id": 99999}, "validation_error"),
])
def test_update_department_errors(db, admin, target, payload, code):
    units = _units(db)
    payload = {k: units.get(v, v) if k == "parent_id" else v for k, v in payload.items()}
    response = admin.patch(f"/api/departments/{units[target]}", json=payload)
    assert response.json()["code"] == code, response.text
    assert response.status_code in (409, 422)


def test_move_respects_depth_limit(db, admin):
    units = _units(db)
    assert admin.put("/api/org/settings", json={"max_depth": 4}).status_code == 200
    # ветка TECH (2 уровня) под SUP-OFFICE (уровень 4) → 6 уровней
    response = admin.patch(f"/api/departments/{units['PROJ']}", json={"parent_id": units["SUP-OS"]})
    assert response.status_code == 409 and response.json()["code"] == "org_too_deep"
    assert admin.patch(f"/api/departments/{units['PROJ']}", json={"parent_id": units["TECH"]}).status_code == 200


def test_move_that_creates_reporting_cycle_is_refused(db, admin):
    units, ids = _units(db), _users(db)
    # it_viewer числится в TECH, руководит IT; перенос TECH внутрь IT замкнёт подчинение
    _set(db, "it_viewer", department_id=units["SUP-OFFICE"])
    response = admin.patch(f"/api/departments/{units['TECH']}", json={"parent_id": units["IT"]})
    assert response.status_code == 409 and response.json()["code"] == "org_reporting_cycle"
    assert db.get(Department, units["TECH"]).parent_id == units["TECHDIR"]
    assert ids


def test_delete_department(db, admin):
    units, ids = _units(db), _users(db)
    response = admin.delete(f"/api/departments/{units['TECH']}")
    assert response.status_code == 409 and response.json()["code"] == "department_has_children"
    assert "Перенесите" in response.json()["detail"] and "Группа поддержки AlterOS" in response.json()["detail"]
    response = admin.delete(f"/api/departments/{units['SUP-OS']}")
    assert response.status_code == 200 and "удалено" in response.json()["message"]
    db.expire_all()
    assert db.get(User, ids["engineer"]).department_id is None, "сотрудники остаются без подразделения"
    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "department", AuditEntry.action == "delete"))
    assert entry.entity_id == str(units["SUP-OS"]) and entry.before["employees"] == ["Петров Илья Сергеевич"]
    assert entry.before["path"].endswith("Группа поддержки AlterOS")
    # руководители удаляются вместе с подразделением
    assert admin.delete(f"/api/departments/{units['IT']}").status_code == 200
    assert db.scalar(select(DepartmentHead).where(DepartmentHead.department_id == units["IT"])) is None
    assert admin.delete(f"/api/departments/{units['IT']}").status_code == 404


def test_sibling_name_race_is_caught_by_unique_index(db, admin, monkeypatch):
    """Проверка в коде пропустила дубль (параллельный запрос) — индекс ловит, ответ тот же 409."""
    units = _units(db)
    monkeypatch.setattr(org_admin, "check_sibling_name", lambda *a, **k: None)
    monkeypatch.setattr(org_admin, "check_code", lambda *a, **k: None)
    response = admin.post("/api/departments", json={"name": "Группа поддержки AlterOS", "parent_id": units["TECH"]})
    assert response.status_code == 409 and response.json()["code"] == "department_name_taken"
    response = admin.post("/api/departments", json={"name": "Новая", "code": "IT"})
    assert response.status_code == 409 and response.json()["code"] == "department_code_taken"
    assert admin.post("/api/departments", json={"name": "Новая"}).status_code == 201, "сессия после отката рабочая"


# ================================================================ руководители

def test_set_heads_keeps_primary(db, admin):
    units, ids = _units(db), _users(db)
    url = f"/api/departments/{units['TECH']}/heads"
    body = admin.put(url, json={"user_ids": [ids["tp_lead"], ids["viewer"]], "primary_id": ids["viewer"]}).json()
    assert body["primary_head_id"] == ids["viewer"] and [h["user_id"] for h in body["heads"]][0] == ids["viewer"]
    # состав меняется без primary_id — основной сохраняется (в todo-planner терялся)
    body = admin.put(url, json={"user_ids": [ids["product"], ids["tp_lead"], ids["viewer"]]}).json()
    assert body["primary_head_id"] == ids["viewer"] and len(body["heads"]) == 3
    # основной ушёл из состава и руководителей несколько — основного нет
    body = admin.put(url, json={"user_ids": [ids["product"], ids["tp_lead"]]}).json()
    assert body["primary_head_id"] is None
    # единственный руководитель — основной сам
    body = admin.put(url, json={"user_ids": [ids["product"]]}).json()
    assert body["primary_head_id"] == ids["product"]
    assert admin.put(url, json={"user_ids": []}).json()["heads"] == []
    entries = list(db.scalars(select(AuditEntry).where(AuditEntry.action == "heads")))
    assert len(entries) == 5 and entries[0].after["primary"] == "Пользователь (просмотр)"


def test_set_heads_switches_primary_in_one_step(db, admin):
    units, ids = _units(db), _users(db)
    url = f"/api/departments/{units['TECH']}/heads"
    admin.put(url, json={"user_ids": [ids["tp_lead"], ids["viewer"]], "primary_id": ids["tp_lead"]})
    body = admin.put(url, json={"user_ids": [ids["tp_lead"], ids["viewer"]], "primary_id": ids["viewer"]}).json()
    assert body["primary_head_id"] == ids["viewer"]
    assert db.scalar(text("SELECT COUNT(*) FROM department_heads WHERE department_id = :d AND is_primary"),
                     {"d": units["TECH"]}) == 1


def test_set_heads_errors(db, admin):
    units, ids = _units(db), _users(db)
    url = f"/api/departments/{units['AHO']}/heads"
    r = admin.put(url, json={"user_ids": [ids["viewer"]], "primary_id": ids["product"]})
    assert r.status_code == 422 and "среди руководителей" in r.json()["detail"]
    assert admin.put(url, json={"user_ids": [99999]}).status_code == 422
    _set(db, "viewer", is_active=False)
    r = admin.put(url, json={"user_ids": [ids["viewer"]]})
    assert r.status_code == 422 and "активного" in r.json()["detail"]
    assert admin.put("/api/departments/99999/heads", json={"user_ids": []}).status_code == 404
    # руководитель TECHDIR — подчинённый руководителя TECH: цикл подчинения
    r = admin.put(f"/api/departments/{units['TECHDIR']}/heads", json={"user_ids": [ids["engineer"]]})
    assert r.status_code == 409 and r.json()["code"] == "org_reporting_cycle"
    assert "Петров" in r.json()["detail"]
    assert db.scalar(select(DepartmentHead.user_id).where(DepartmentHead.department_id == units["TECHDIR"])) \
        == ids["tech_dir"]


def test_inactive_existing_head_can_stay(db, admin):
    units, ids = _units(db), _users(db)
    _set(db, "tp_lead", is_active=False)
    body = admin.put(f"/api/departments/{units['TECH']}/heads",
                     json={"user_ids": [ids["tp_lead"], ids["viewer"]]}).json()
    assert {h["user_id"] for h in body["heads"]} == {ids["tp_lead"], ids["viewer"]}
    assert body["primary_head_id"] == ids["tp_lead"]


# ================================================================ настройки структуры

def test_settings_read_and_update(db, admin, login):
    settings = login("viewer").get("/api/org/settings").json()
    assert settings["max_depth"] == 15 and settings["current_depth"] == 4 and settings["default_view"] == "chart"
    assert settings["used_kinds"]["group"] == 2 and settings["views"] == ["chart", "people", "tree", "table"]
    assert login("viewer").put("/api/org/settings", json={"max_depth": 10}).status_code == 403
    revision = org.current_revision(db)
    kinds = settings["unit_kinds"] + [{"value": "project_team", "label": "Проектная команда", "color": "#123abc"}]
    body = admin.put("/api/org/settings", json={"unit_kinds": kinds, "max_depth": 6}).json()
    assert body["max_depth"] == 6 and body["unit_kinds"][-1]["value"] == "project_team"
    assert body["default_view"] == "chart", "непереданное не меняется"
    assert org.current_revision(db) == revision + 1
    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "org_settings"))
    assert entry.before["max_depth"] == 15 and entry.after["max_depth"] == 6
    assert admin.post("/api/departments", json={"name": "Команда X", "kind": "project_team"}).status_code == 201


@pytest.mark.parametrize(("payload", "status", "code"), [
    ({"unit_kinds": [{"value": "Bad Kind", "label": "X"}]}, 422, "validation_error"),
    ({"unit_kinds": []}, 422, "validation_error"),
    ({"unit_kinds": [{"value": f"k{i}", "label": "X"} for i in range(31)]}, 422, "validation_error"),
    ({"unit_kinds": [{"value": "a", "label": "A"}, {"value": "a", "label": "B"}]}, 422, "validation_error"),
    ({"unit_kinds": [{"value": "company", "label": "Компания", "color": "#000"}]}, 422, "validation_error"),
    ({"max_depth": 1}, 422, "validation_error"),
    ({"max_depth": 31}, 422, "validation_error"),
    ({"max_depth": 3}, 409, "org_depth_in_use"),
    ({"default_view": "cards"}, 422, "validation_error"),
])
def test_settings_errors(admin, payload, status, code):
    response = admin.put("/api/org/settings", json=payload)
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def test_used_kind_cannot_be_removed(admin):
    kinds = [k for k in admin.get("/api/org/settings").json()["unit_kinds"] if k["value"] != "group"]
    response = admin.put("/api/org/settings", json={"unit_kinds": kinds})
    assert response.status_code == 409 and response.json()["code"] == "org_kind_in_use"
    assert "Группа" in response.json()["detail"] and "2" in response.json()["detail"]
    unused = [k for k in admin.get("/api/org/settings").json()["unit_kinds"] if k["value"] != "sector"]
    assert admin.put("/api/org/settings", json={"unit_kinds": unused}).status_code == 200


# ================================================================ подчинение сотрудника

def test_person_manager_rules(db, admin):
    ids = _users(db)
    url = f"/api/org/people/{ids['engineer']}"
    card = admin.patch(url, json={"manager_id": ids["product"]}).json()
    assert card["manager"]["id"] == ids["product"] and card["manager_source"] == "explicit"
    assert card["structure_manager"]["id"] == ids["tp_lead"]
    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "user", AuditEntry.action == "org_update"))
    assert entry.entity_id == str(ids["engineer"]) and entry.after == {"manager": "Руководитель продуктового офиса"}
    assert admin.patch(url, json={"manager_id": None}).json()["manager_source"] == "structure"
    r = admin.patch(url, json={"manager_id": ids["engineer"]})
    assert r.status_code == 422 and "самому себе" in r.json()["detail"]
    assert admin.patch(url, json={"manager_id": 99999}).status_code == 422
    _set(db, "viewer", is_active=False)
    r = admin.patch(url, json={"manager_id": ids["viewer"]})
    assert r.status_code == 422 and "активный" in r.json()["detail"]
    # руководитель подчиняется своему сотруднику — цикл
    r = admin.patch(f"/api/org/people/{ids['tp_lead']}", json={"manager_id": ids["engineer"]})
    assert r.status_code == 409 and r.json()["code"] == "org_reporting_cycle"
    assert admin.patch("/api/org/people/99999", json={"position": "X"}).status_code == 404


def test_person_reports_to_none_and_manager_exclude_each_other(db, admin):
    ids = _users(db)
    url = f"/api/org/people/{ids['viewer']}"
    card = admin.patch(url, json={"manager_id": ids["product"]}).json()
    assert card["manager_id"] == ids["product"]
    card = admin.patch(url, json={"reports_to_none": True}).json()
    assert card["reports_to_none"] and card["manager_id"] is None and card["manager_source"] == "top"
    card = admin.patch(url, json={"manager_id": ids["product"]}).json()
    assert not card["reports_to_none"] and card["manager_source"] == "explicit"
    r = admin.patch(url, json={"manager_id": ids["product"], "reports_to_none": True})
    assert r.status_code == 422 and "Выберите одно" in r.json()["detail"]


def test_person_department_position_and_heads(db, admin, login):
    ids, units = _users(db), _units(db)
    url = f"/api/org/people/{ids['viewer']}"
    card = admin.patch(url, json={"department_id": units["MKT"], "position": "  Маркетолог "}).json()
    assert card["department_id"] == units["MKT"] and card["position"] == "Маркетолог"
    assert admin.patch(url, json={"department_id": 99999}).status_code == 422
    card = admin.patch(url, json={"head_of": [{"department_id": units["IT"], "primary": True},
                                              {"department_id": units["MKT"]}]}).json()
    assert {h["id"]: h["primary"] for h in card["head_of"]} == {units["IT"]: True, units["MKT"]: True}
    it = login("viewer").get(f"/api/departments/{units['IT']}").json()
    assert it["primary_head_id"] == ids["viewer"] and len(it["heads"]) == 2
    mkt = login("viewer").get(f"/api/departments/{units['MKT']}").json()
    assert mkt["primary_head_id"] == ids["viewer"], "единственный руководитель — основной"
    # снятие с руководства: основным IT снова становится it_viewer (единственный)
    card = admin.patch(url, json={"head_of": []}).json()
    assert card["head_of"] == []
    assert login("viewer").get(f"/api/departments/{units['IT']}").json()["primary_head_id"] == ids["it_viewer"]
    assert admin.patch(url, json={"head_of": [{"department_id": 99999}]}).status_code == 422
    assert admin.patch(url, json={"department_id": None}).json()["department_id"] is None


def test_person_heads_cycle_is_refused(db, admin):
    ids, units = _users(db), _units(db)
    r = admin.patch(f"/api/org/people/{ids['engineer']}",
                    json={"head_of": [{"department_id": units["TECHDIR"], "primary": True}]})
    assert r.status_code == 409 and r.json()["code"] == "org_reporting_cycle"


def test_person_update_needs_org_manage(db, login):
    ids = _users(db)
    assert login("hr_head").patch(f"/api/org/people/{ids['viewer']}", json={"position": "X"}).status_code == 403


# ================================================================ история

def test_history(db, admin, login):
    units, ids = _units(db), _users(db)
    admin.patch(f"/api/departments/{units['AHO']}", json={"name": "Хозяйственный отдел"})
    admin.patch(f"/api/org/people/{ids['viewer']}", json={"position": "Аналитик данных"})
    admin.patch("/api/users/" + str(ids["viewer"]), json={"phone": "+7 900 000-00-00"})   # не структура
    rows = admin.get("/api/org/history").json()
    assert [r["entity_type"] for r in rows[:2]] == ["user", "department"]
    assert all(r["action"] != "update" or r["entity_type"] != "user" for r in rows)
    dept = admin.get("/api/org/history", params={"entity_type": "department", "entity_id": units["AHO"]}).json()
    assert len(dept) == 1 and dept[0]["after"] == {"name": "Хозяйственный отдел"} and dept[0]["username"] == "admin"
    users = admin.get("/api/org/history", params={"entity_type": "user", "entity_id": ids["viewer"]}).json()
    assert [r["action"] for r in users] == ["org_update"]
    assert len(admin.get("/api/org/history", params={"limit": 1}).json()) == 1
    assert admin.get("/api/org/history", params={"entity_type": "palette"}).status_code == 422
    assert admin.get("/api/org/history", params={"limit": 0}).status_code == 422
    assert login("viewer").get("/api/org/history").status_code == 403


# ================================================================ PostgreSQL

@pytest.fixture()
def pg_session_factory(monkeypatch):
    """Отдельная база PostgreSQL с миграциями, справочниками и демо-данными."""
    if not PG_URL:
        pytest.skip("TEST_POSTGRES_URL не задан")
    from app.api.routers import system
    from app.core import db as core_db
    from app.core.migrate import upgrade
    from app.services.demo_data import load_demo_data
    from app.services.reference_data import sync_reference_data

    name = f"org_{uuid.uuid4().hex[:8]}"
    server = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = PG_URL.rsplit("/", 1)[0] + f"/{name}"
    upgrade(url)
    engine = core_db.make_engine(url)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        sync_reference_data(session)
        load_demo_data(session)
        session.commit()
    monkeypatch.setattr(core_db, "engine", engine)
    monkeypatch.setattr(core_db, "SessionLocal", factory)
    monkeypatch.setattr(system, "engine", engine)
    org.invalidate()
    yield factory
    engine.dispose()
    org.invalidate()
    drop_pg_database(server, name)
    server.dispose()


@pytest.fixture()
def pg_admin(pg_session_factory):
    from app.api.routers.auth import login_limiter
    from app.core import db as core_db
    from app.main import app as fastapi_app

    def override_db():
        session = pg_session_factory()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[core_db.get_db] = override_db
    login_limiter.clear()
    with ApiClient(fastapi_app) as client:
        client.login("admin")
        yield client
    fastapi_app.dependency_overrides.clear()


@pytest.mark.postgres
def test_sibling_name_race_on_postgres(pg_session_factory, monkeypatch):
    """Два запроса создают одно имя: второй ждёт первый на уникальном индексе и получает 409."""
    monkeypatch.setattr(org_admin, "check_sibling_name", lambda *a, **k: None)   # оба «прошли» проверку
    first = pg_session_factory()
    tech = first.scalar(select(Department.id).where(Department.code == "TECH"))
    actor = first.scalar(select(User).where(User.username == "admin"))
    first.add(Department(name="Группа гонки", parent_id=tech))
    first.flush()
    result: dict = {}

    def second_request():
        session = pg_session_factory()
        try:
            user = session.get(User, actor.id)
            org_admin.create_department(session, user, DepartmentCreateIn(name="группа  ГОНКИ", parent_id=tech))
            session.commit()
            result["created"] = True
        except Conflict as exc:
            result["code"] = exc.code
        finally:
            session.close()

    worker = threading.Thread(target=second_request)
    worker.start()
    time.sleep(0.5)
    assert worker.is_alive(), "второй запрос ждёт завершения первой транзакции на уникальном индексе"
    first.commit()
    worker.join(10)
    first.close()
    assert result == {"code": "department_name_taken"}


@pytest.mark.postgres
def test_department_api_on_postgres(pg_admin, monkeypatch):
    units = {d["path"].split(" / ")[-1]: d["id"] for d in pg_admin.get("/api/departments").json()}
    tech = units["Техническая служба"]
    created = pg_admin.post("/api/departments", json={"name": "Отдел качества", "parent_id": tech, "code": "qa"})
    assert created.status_code == 201, created.text
    assert pg_admin.post("/api/departments", json={"name": "отдел  КАЧЕСТВА",
                                                   "parent_id": units["Техническая служба"]}).status_code == 409
    monkeypatch.setattr(org_admin, "check_sibling_name", lambda *a, **k: None)
    response = pg_admin.post("/api/departments", json={"name": "Отдел качества",
                                                       "parent_id": units["Техническая служба"]})
    assert response.status_code == 409 and response.json()["code"] == "department_name_taken"
    assert pg_admin.delete(f"/api/departments/{created.json()['id']}").status_code == 200
    tree = pg_admin.get("/api/org/tree").json()
    assert len(tree["units"]) == 13 and tree["people"]
    ids = {p["username"]: p["id"] for p in tree["people"]}
    heads = pg_admin.put(f"/api/departments/{units['Техническая служба']}/heads",
                         json={"user_ids": [ids["tp_lead"], ids["viewer"]], "primary_id": ids["viewer"]}).json()
    assert heads["primary_head_id"] == ids["viewer"]
    assert pg_admin.put("/api/org/settings", json={"max_depth": 3}).status_code == 409
    assert pg_admin.get("/api/org/history").json()
