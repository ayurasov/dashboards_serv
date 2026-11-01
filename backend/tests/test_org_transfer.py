"""Перенос структуры (JSON), выгрузка и загрузка сотрудников, быстрая загрузка списком."""
from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

import openpyxl
import pytest
from sqlalchemy import select

from app.models import AccessProfile, AuditEntry, Department, DepartmentHead, User

from .test_org_api import PASSWORDS, _grant, _set, _units, _users

HEADERS = ["Email", "Логин", "ФИО", "Должность", "Телефон", "Подразделение", "Руководитель (явно)", "Первое лицо",
           "Руководит", "Роль", "Профиль доступа", "Активен", "Способ входа", "Внешний ID"]


@pytest.fixture()
def emails(db):
    """У демо-пользователей нет email — для переноса он нужен."""
    for user in db.scalars(select(User)):
        user.email = f"{user.username}@example.local"
    db.commit()


def _bundle(admin) -> dict:
    response = admin.get("/api/org/export")
    assert response.status_code == 200
    return response.json()


def _structure(admin, bundle, **options):
    return admin.post("/api/org/import/structure", json={"bundle": bundle, **options})


def _employees(client, content, fmt="json", **options):
    return client.post("/api/org/employees/import", json={"format": fmt, "content": content, **options})


def _list(client, text, **options):
    return client.post("/api/org/import/list", json={"content": text, **options})


def _record(email, **values) -> dict:
    return {"email": email, **values}


# ================================================================ структура: выгрузка

def test_structure_export(db, admin, emails, login):
    response = admin.get("/api/org/export")
    stamp = datetime.now(UTC).date().isoformat()
    assert response.headers["content-disposition"] == f'attachment; filename="dashboards-structure-{stamp}.json"'
    assert response.headers["content-type"].startswith("application/json")
    bundle = response.json()
    assert bundle["format"] == "dashboards.org-structure" and bundle["version"] == 1
    assert bundle["settings"]["org_max_depth"] == 15 and len(bundle["settings"]["org_unit_kinds"]) == 8
    keys = [d["key"] for d in bundle["departments"]]
    assert len(keys) == 13
    for item in bundle["departments"]:
        assert item["parent"] is None or keys.index(item["parent"]) < keys.index(item["key"])
    tech = next(d for d in bundle["departments"] if d["code"] == "TECH")
    assert tech["path"] == "АЛМИ Партнер / Техническая дирекция / Техническая служба" and tech["kind"] == "service"
    assert tech["heads"] == [{"email": "tp_lead@example.local", "name": "Руководитель техподдержки", "primary": True}]
    assert login("viewer").get("/api/org/export").status_code == 403


# ================================================================ структура: загрузка

def test_structure_reimport_is_unchanged(db, admin, emails):
    plan = _structure(admin, _bundle(admin)).json()
    assert plan["can_apply"] and not plan["applied"]
    assert plan["summary"]["unchanged"] == 13 and plan["summary"]["create"] == 0
    assert plan["summary"]["existing_heads"] == 7 and plan["summary"]["add_heads"] == 0
    assert plan["missing_in_file"] == [] and plan["settings"] == []


def test_structure_into_new_branch(db, admin, emails):
    bundle = _bundle(admin)
    root = bundle["departments"][0]
    root["name"] = "Дочерняя компания"
    for item in bundle["departments"]:
        item["code"] = None
    bundle["departments"].append({"key": "x1", "name": "Новый отдел", "parent": root["key"], "kind": "department",
                                  "heads": [{"email": "nobody@example.local", "primary": True},
                                            {"email": "VIEWER@example.local", "primary": True}]})
    plan = _structure(admin, bundle).json()
    assert plan["summary"]["create"] == 14 and len(plan["missing_in_file"]) == 13
    assert {h["action"] for h in plan["heads"]} == {"add", "pending"}
    pending = next(h for h in plan["heads"] if h["action"] == "pending")
    assert pending["email"] == "nobody@example.local"
    before = db.scalar(select(Department.id).order_by(Department.id.desc()))
    result = _structure(admin, bundle, apply=True)
    assert result.status_code == 200 and result.json()["applied"]
    created = list(db.scalars(select(Department).where(Department.id > before)))
    assert len(created) == 14 and {d.org_source for d in created} == {"import"}
    new_root = next(d for d in created if d.name == "Дочерняя компания")
    assert new_root.parent_id is None and new_root.kind == "company"
    new_dept = next(d for d in created if d.name == "Новый отдел")
    heads = list(db.scalars(select(DepartmentHead).where(DepartmentHead.department_id == new_dept.id)))
    assert [(h.user_id, h.is_primary) for h in heads] == [(_users(db)["viewer"], True)]
    tech_copy = next(d for d in created if d.name == "Техническая служба")
    primary = db.scalar(select(DepartmentHead).where(DepartmentHead.department_id == tech_copy.id))
    assert primary.user_id == _users(db)["tp_lead"] and primary.is_primary, "основной перенесён"
    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "org_import"))
    assert entry.action == "structure" and entry.after["create"] == 14
    # повторная загрузка того же файла — ничего нового
    again = _structure(admin, bundle).json()
    assert again["summary"]["create"] == 0 and again["summary"]["add_heads"] == 0


def test_structure_updates_and_settings(db, admin, emails):
    bundle = _bundle(admin)
    tech = next(d for d in bundle["departments"] if d["code"] == "TECH")
    tech.update(kind="direction", sort_order=42, code="TS")
    bundle["settings"]["org_unit_kinds"] = [{"value": "company", "label": "Компания", "color": "#000000"},
                                            {"value": "direction", "label": "Направление", "color": "#111111"},
                                            {"value": "team", "label": "Команда", "color": "#222222"}]
    bundle["settings"]["org_max_depth"] = 8
    bundle["settings"]["org_default_view"] = "table"
    plan = _structure(admin, bundle).json()
    assert plan["can_apply"], plan["errors"]
    change = next(d for d in plan["departments"] if d["key"] == tech["key"])
    assert change["action"] == "update" and {c["field"] for c in change["changes"]} == {"kind", "sort_order", "code"}
    assert {s["key"] for s in plan["settings"]} == {"org_unit_kinds", "org_max_depth", "org_default_view"}
    kinds = next(s for s in plan["settings"] if s["key"] == "org_unit_kinds")["incoming"]
    assert "Команда (team)" in kinds and "Группа (group)" in kinds, "используемые типы сохраняются"
    result = _structure(admin, bundle, apply=True).json()
    assert result["applied"] and result["settings_applied"]
    settings = admin.get("/api/org/settings").json()
    assert settings["max_depth"] == 8 and settings["default_view"] == "table"
    assert {"team", "group", "service"} <= {k["value"] for k in settings["unit_kinds"]}
    dept = db.get(Department, int(tech["key"]))
    db.refresh(dept)
    assert (dept.kind, dept.sort_order, dept.code) == ("direction", 42, "TS")
    # без настроек: файл настроек не трогает
    bundle["settings"]["org_max_depth"] = 20
    plan = _structure(admin, bundle, apply_settings=False).json()
    assert plan["settings"] == []


@pytest.mark.parametrize(("mutate", "error"), [
    (lambda b: b["departments"][1].update(kind="bogus"), "тип «bogus»"),
    (lambda b: b["departments"].append({**b["departments"][1], "key": "dup"}), "повторяется в файле"),
    (lambda b: b["departments"][2].update(code="TECH"), "код «TECH»"),
    (lambda b: b["settings"].update(org_max_depth=3), "Вложенность после загрузки — 4"),
    (lambda b: b["settings"].update(org_max_depth="много"), "Предел вложенности"),
    (lambda b: b["settings"].update(org_default_view="cards"), "Вид оргсхемы"),
    (lambda b: b["settings"].update(org_unit_kinds=[{"value": "Плохой"}]), "Типы уровней"),
])
def test_structure_plan_errors(db, admin, emails, mutate, error):
    bundle = _bundle(admin)
    mutate(bundle)
    plan = _structure(admin, bundle).json()
    assert not plan["can_apply"] and any(error in e for e in plan["errors"]), plan["errors"]
    response = _structure(admin, bundle, apply=True)
    assert response.status_code == 409 and response.json()["code"] == "import_has_errors"
    assert response.json()["errors"] == plan["errors"] and response.json()["applied"] is False


def test_structure_heads_cycle_is_an_error(db, admin, emails):
    bundle = _bundle(admin)
    techdir = next(d for d in bundle["departments"] if d["code"] == "TECHDIR")
    techdir["heads"] = [{"email": "engineer@example.local", "primary": False}]
    _set(db, "tech_dir", is_active=False)   # основной отключён — руководить уровнем будет инженер
    plan = _structure(admin, bundle).json()
    assert any("цикл подчинения" in e for e in plan["errors"])


@pytest.mark.parametrize(("bundle", "message"), [
    ({"format": "podelu.org-structure", "version": 1, "departments": []}, "не файл структуры"),
    ({"format": "dashboards.org-structure", "version": 2, "departments": []}, "Версия файла 2"),
    ({"format": "dashboards.org-structure", "version": 1}, "нет списка"),
    ({"format": "dashboards.org-structure", "version": 1, "departments": [{"key": "a"}]}, "нужны key и name"),
    ({"format": "dashboards.org-structure", "version": 1,
      "departments": [{"key": "a", "name": "A", "parent": "b"}, {"key": "b", "name": "B"}]}, "раньше"),
    ({"format": "dashboards.org-structure", "version": 1,
      "departments": [{"key": "a", "name": "A"}, {"key": "a", "name": "B"}]}, "повторяется"),
    ("{не json", "не является JSON"),
])
def test_structure_format_errors(admin, bundle, message):
    response = _structure(admin, bundle)
    assert response.status_code == 422 and message in response.json()["detail"]


def test_structure_bundle_as_text_and_permissions(db, admin, login, emails):
    assert _structure(admin, json.dumps(_bundle(admin), ensure_ascii=False)).json()["can_apply"]
    assert login("viewer").post("/api/org/import/structure", json={"bundle": {}}).status_code == 403


# ================================================================ сотрудники: выгрузка

def test_employees_export_csv(db, admin, emails):
    _set(db, "engineer", manager_id=_users(db)["product"], phone="+7 900 111-22-33")
    response = admin.get("/api/org/employees/export", params={"format": "csv"})
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    raw = response.content
    assert raw.startswith("﻿".encode()) and b"\r\n" in raw
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))
    assert rows[0] == HEADERS
    by_login = {r[1]: dict(zip(HEADERS, r, strict=True)) for r in rows[1:]}
    engineer = by_login["engineer"]
    assert engineer["Подразделение"] == "АЛМИ Партнер / Техническая дирекция / Техническая служба / " \
                                       "Группа поддержки AlterOS"
    assert engineer["Руководитель (явно)"] == "product@example.local" and engineer["Телефон"] == "+7 900 111-22-33"
    assert engineer["Профиль доступа"] == "Сотрудник" and engineer["Активен"] == "да" and engineer["Роль"] == \
        "Пользователь"
    assert engineer["Способ входа"] == "Пароль" and engineer["Первое лицо"] == "нет"
    ceo = by_login["ceo"]
    assert ceo["Первое лицо"] == "да"
    assert ceo["Руководит"] == "АЛМИ Партнер (основной) | АЛМИ Партнер / Аппарат генерального директора (основной)"
    assert by_login["admin"]["Роль"] == "Администратор" and by_login["viewer"]["Профиль доступа"] == \
        "Индивидуальная настройка"
    assert b"password" not in raw.lower() and "$2b$" not in raw.decode("utf-8-sig")


def test_employees_export_xlsx_and_json(db, admin, emails, login):
    _set(db, "viewer", is_active=False)
    response = admin.get("/api/org/employees/export")
    wb = openpyxl.load_workbook(io.BytesIO(response.content))
    ws = wb.active
    assert [c.value for c in ws[1]] == HEADERS and ws.max_row == 10
    data = admin.get("/api/org/employees/export", params={"format": "json", "inactive": 0})
    assert data.headers["content-type"].startswith("application/json")
    doc = data.json()
    assert doc["format"] == "dashboards.employees" and doc["version"] == 1
    assert len(doc["employees"]) == 8 and "viewer" not in {e["login"] for e in doc["employees"]}
    ceo = next(e for e in doc["employees"] if e["login"] == "ceo")
    assert ceo["heads"][0] == {"department": ["АЛМИ Партнер"], "primary": True}
    assert admin.get("/api/org/employees/export", params={"format": "pdf"}).status_code == 422
    assert login("hr_head").get("/api/org/employees/export").status_code == 403


# ================================================================ сотрудники: загрузка

def test_employees_round_trip_is_unchanged(db, admin, emails):
    exported = admin.get("/api/org/employees/export", params={"format": "csv"}).content
    files = {"file": ("Сотрудники.csv", exported, "text/csv")}
    plan = admin.post("/api/org/employees/import", files=files).json()
    assert plan["can_apply"], [r for r in plan["records"] if r["errors"]]
    assert plan["summary"]["unchanged"] == 9 and plan["summary"]["conflicts"] == 0
    xlsx = admin.get("/api/org/employees/export").content
    plan = admin.post("/api/org/employees/import",
                      files={"file": ("s.xlsx", xlsx, "application/octet-stream")}).json()
    assert plan["summary"]["unchanged"] == 9
    doc = admin.get("/api/org/employees/export", params={"format": "json"}).content
    plan = admin.post("/api/org/employees/import", files={"file": ("s.json", doc, "application/json")}).json()
    assert plan["summary"]["unchanged"] == 9


@pytest.mark.parametrize(("mode", "active", "auth"), [("no_access", True, "local"), ("active", True, "ldap"),
                                                      ("inactive", False, "local")])
def test_employees_create_new(db, admin, emails, mode, active, auth):
    content = [_record("new.person@example.local", full_name="Новикова Анна", login="anovikova",
                       position="Аналитик", department="АЛМИ Партнер / Аналитический отдел / Группа BI",
                       manager="tp_lead@example.local", heads="да", phone="123")]
    plan = _employees(admin, content, new_users=mode).json()
    assert plan["can_apply"], plan
    assert plan["summary"]["create"] == 1 and plan["summary"]["create_departments"] == 2
    assert [d["path"] for d in plan["departments"]] == ["АЛМИ Партнер / Аналитический отдел",
                                                       "АЛМИ Партнер / Аналитический отдел / Группа BI"]
    result = _employees(admin, content, new_users=mode, apply=True).json()
    assert result["applied"] and "new.person@example.local" in result["user_ids"]
    user = db.get(User, result["user_ids"]["new.person@example.local"])
    assert (user.username, user.is_active, user.auth_source, user.password_hash) == ("anovikova", active, auth, None)
    assert user.org_source == "import" and user.phone == "123" and user.role == "user"
    group = db.scalar(select(Department).where(Department.name == "Группа BI"))
    assert user.department_id == group.id and group.org_source == "import"
    head = db.scalar(select(DepartmentHead).where(DepartmentHead.user_id == user.id))
    assert head.department_id == group.id and head.is_primary, "«Руководит: да» — своим подразделением"
    assert user.manager_id == _users(db)["tp_lead"], "явный руководитель отличается от структурного"
    assert db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "user", AuditEntry.action == "org_import",
                                              AuditEntry.entity_id == str(user.id))) is not None


def test_employees_explicit_manager_only_when_different(db, admin, emails):
    content = [_record("n2@example.local", full_name="Новый инженер", department="АЛМИ Партнер / "
                       "Техническая дирекция / Техническая служба / Группа поддержки AlterOS",
                       manager="tp_lead@example.local")]
    result = _employees(admin, content, apply=True).json()
    user = db.get(User, result["user_ids"]["n2@example.local"])
    assert user.manager_id is None, "руководитель совпадает со структурным — явный не записывается"


def test_employees_conflicts_and_decisions(db, admin, emails):
    _set(db, "engineer", position="Инженер", phone=None)
    record = _record("ENGINEER@example.local", position="Ведущий инженер", phone="+7 1", full_name="",
                     department="", login="")
    plan = _employees(admin, [record]).json()
    entry = plan["records"][0]
    assert entry["action"] == "update" and entry["user_id"] == _users(db)["engineer"]
    assert [c["field"] for c in entry["changes"]] == ["phone"], "пустое в системе заполняется из файла"
    conflict = entry["conflicts"][0]
    assert conflict["field"] == "position" and conflict["choice"] == "current"
    assert conflict["choices"] == ["current", "incoming", "custom"] and conflict["current"] == "Инженер"
    # по умолчанию остаётся значение системы
    _employees(admin, [record], apply=True)
    db.expire_all()
    engineer = db.get(User, _users(db)["engineer"])
    assert engineer.position == "Инженер" and engineer.phone == "+7 1"
    decisions = {"engineer@example.local": {"fields": {"position": {"choice": "incoming"}}}}
    assert _employees(admin, [record], apply=True, decisions=decisions).json()["applied"]
    db.expire_all()
    assert db.get(User, engineer.id).position == "Ведущий инженер"
    decisions = {"engineer@example.local": {"fields": {"position": {"choice": "custom", "value": " Эксперт "}}}}
    _set(db, "engineer", position="Инженер")
    _employees(admin, [record], apply=True, decisions=decisions)
    db.expire_all()
    assert db.get(User, engineer.id).position == "Эксперт"
    # пустое в файле ничего не стирает
    assert _employees(admin, [_record("engineer@example.local", position="")]).json()["records"][0]["action"] \
        == "unchanged"
    bad = {"engineer@example.local": {"fields": {"full_name": {"choice": "custom", "value": " "}}}}
    plan = _employees(admin, [_record("engineer@example.local", full_name="Другое имя")], decisions=bad).json()
    assert not plan["can_apply"] and "ФИО" in plan["records"][0]["errors"][0]


def test_employees_department_heads_and_merge(db, admin, emails):
    units = _units(db)
    record = _record("tp_lead@example.local", heads="АЛМИ Партнер / Проектная служба")
    plan = _employees(admin, [record]).json()
    conflict = plan["records"][0]["conflicts"][0]
    assert conflict["field"] == "heads" and "merge" in conflict["choices"]
    decisions = {"tp_lead@example.local": {"fields": {"heads": {"choice": "merge"}}}}
    assert _employees(admin, [record], apply=True, decisions=decisions).json()["applied"]
    heads = {h.department_id for h in db.scalars(select(DepartmentHead).where(
        DepartmentHead.user_id == _users(db)["tp_lead"]))}
    assert heads == {units["TECH"], units["PROJ"]}
    decisions = {"tp_lead@example.local": {"fields": {"heads": {"choice": "incoming"}}}}
    assert _employees(admin, [record], apply=True, decisions=decisions).json()["applied"]
    links = list(db.scalars(select(DepartmentHead).where(DepartmentHead.user_id == _users(db)["tp_lead"])))
    assert [link.department_id for link in links] == [units["PROJ"]]
    tech = db.scalar(select(DepartmentHead).where(DepartmentHead.department_id == units["TECH"]))
    assert tech is None, "снят с руководства TECH"


def test_employees_primary_mark_follows_decision(db, admin, emails):
    units, ids = _units(db), _users(db)
    admin.put(f"/api/departments/{units['TECH']}/heads", json={"user_ids": [ids["tp_lead"], ids["viewer"]],
                                                               "primary_id": ids["tp_lead"]})
    path = "АЛМИ Партнер / Техническая дирекция / Техническая служба"
    record = _record("viewer@example.local", heads=f"{path} (основной)")
    plan = _employees(admin, [record]).json()
    conflict = plan["records"][0]["conflicts"][0]
    assert conflict["current"] == [path] and conflict["incoming"] == [f"{path} (основной)"]
    decisions = {"viewer@example.local": {"fields": {"heads": {"choice": "incoming"}}}}
    assert _employees(admin, [record], apply=True, decisions=decisions).json()["applied"]
    primary = db.scalar(select(DepartmentHead.user_id).where(DepartmentHead.department_id == units["TECH"],
                                                             DepartmentHead.is_primary.is_(True)))
    assert primary == ids["viewer"]


def test_employees_identity_question(db, admin, emails):
    ids = _users(db)
    record = _record("i.petrov@corp.example", login="engineer", full_name="Петров Илья Сергеевич",
                     position="Старший инженер")
    plan = _employees(admin, [record]).json()
    entry = plan["records"][0]
    assert entry["unresolved"] and entry["identity"]["user_id"] == ids["engineer"] and not plan["can_apply"]
    response = _employees(admin, [record], apply=True)
    assert response.status_code == 409 and "Ответьте" in response.json()["detail"]
    same = {"i.petrov@corp.example": {"identity": "same", "fields": {"email": {"choice": "incoming"},
                                                                       "position": {"choice": "incoming"}}}}
    result = _employees(admin, [record], apply=True, decisions=same).json()
    assert result["applied"]
    db.expire_all()
    engineer = db.get(User, ids["engineer"])
    assert engineer.email == "i.petrov@corp.example" and engineer.position == "Старший инженер"


def test_employees_identity_new_needs_login(db, admin, emails):
    record = _record("other.person@corp.example", login="engineer", full_name="Другой Человек")
    new = {"other.person@corp.example": {"identity": "new"}}
    plan = _employees(admin, [record], decisions=new).json()
    assert not plan["can_apply"] and "укажите другой" in plan["records"][0]["errors"][0]
    new["other.person@corp.example"]["fields"] = {"login": {"choice": "custom", "value": "dchelovek"}}
    result = _employees(admin, [record], decisions=new, apply=True).json()
    assert result["applied"]
    assert db.get(User, result["user_ids"]["other.person@corp.example"]).username == "dchelovek"


@pytest.mark.parametrize(("records", "error"), [
    ([_record("bad-email")], "некорректный"),
    ([_record("a@x.ru", full_name="А"), _record("A@x.ru", full_name="Б")], "повторяется"),
    ([_record("nobody@x.ru")], "нужно ФИО"),
    ([_record("a@x.ru", full_name="А", login="same"), _record("b@x.ru", full_name="Б", login="same")],
     "повторяется"),
    ([_record("a@x.ru", full_name="А", login="плохой логин")], "логин"),
    ([_record("a@x.ru", full_name="А", department=" / ".join(f"Уровень {i}" for i in range(16)))],
     "глубже предела"),
])
def test_employees_record_errors(db, admin, emails, records, error):
    plan = _employees(admin, records).json()
    assert not plan["can_apply"]
    assert any(error in e for r in plan["records"] for e in r["errors"]), plan["records"]
    response = _employees(admin, records, apply=True)
    assert response.status_code == 409 and response.json()["code"] == "import_has_errors"


def test_employees_manager_cycle_and_unknown_manager(db, admin, emails):
    plan = _employees(admin, [_record("tp_lead@example.local", manager="engineer@example.local")],
                      decisions={"tp_lead@example.local": {"fields": {"manager": {"choice": "incoming"}}}}).json()
    assert "цикл подчинения" in plan["records"][0]["errors"][0]
    plan = _employees(admin, [_record("viewer@example.local", manager="ghost@example.local")]).json()
    assert plan["can_apply"] and "не найден" in plan["records"][0]["warnings"][0]
    # руководитель — новый сотрудник из того же файла
    content = [_record("boss@x.ru", full_name="Начальник", department="Новая компания"),
               _record("worker@x.ru", full_name="Работник", department="Новая компания / Отдел",
                       manager="boss@x.ru")]
    result = _employees(admin, content, apply=True).json()
    worker = db.get(User, result["user_ids"]["worker@x.ru"])
    assert worker.manager_id == result["user_ids"]["boss@x.ru"]


def test_employees_access_columns_need_users_manage(db, login, emails):
    _grant(db, "hr_head", "org.manage")
    hr = login("hr_head")
    record = _record("viewer@example.local", role="Администратор", access_profile="Специалист", is_active="нет")
    plan = _employees(hr, [record]).json()
    assert "users.manage" in plan["notes"][0] and plan["records"][0]["action"] == "unchanged"
    new = [_record("x@x.ru", full_name="Новый", role="Администратор", access_profile="Специалист")]
    result = _employees(hr, new, apply=True, new_users="active").json()
    assert any("без доступа" in n for n in result["notes"])
    user = db.get(User, result["user_ids"]["x@x.ru"])
    assert user.role == "user" and user.access_profile_id is None
    assert user.auth_source == "local", "вход по домену разрешает только ведущий пользователей"
    # администратора изменяет только администратор
    plan = _employees(hr, [_record("admin@example.local", position="Директор")]).json()
    assert plan["records"][0]["action"] == "skip" and "только администратор" in plan["records"][0]["warnings"][0]
    _grant(db, "hr_head", "org.manage", "users.manage")
    hr = login("hr_head")
    incoming = {"choice": "incoming"}
    plan = _employees(hr, [record], decisions={"viewer@example.local": {"fields": {
        "access_profile": incoming, "role": incoming, "is_active": incoming}}})
    body = plan.json()
    assert any("только администратор" in w for w in body["records"][0]["warnings"])
    assert {c["field"] for c in body["records"][0]["conflicts"]} == {"is_active"}
    assert [c["field"] for c in body["records"][0]["changes"]] == ["access_profile"], "без профиля — заполняется"
    result = _employees(hr, [record], apply=True, decisions={"viewer@example.local": {"fields": {
        "is_active": {"choice": "incoming"}}}}).json()
    assert result["applied"]
    db.expire_all()
    viewer = db.get(User, _users(db)["viewer"])
    specialist = db.scalar(select(AccessProfile).where(AccessProfile.key == "specialist"))
    assert viewer.access_profile_id == specialist.id and viewer.is_active is False and viewer.role == "user"
    new_admin = _employees(hr, [_record("y@x.ru", full_name="Y", role="Администратор")]).json()
    assert "только администратор" in new_admin["records"][0]["errors"][0]
    unknown = _employees(hr, [_record("viewer@example.local", access_profile="Нет такого")]).json()
    assert any("не найден" in w for w in unknown["records"][0]["warnings"])


def test_employees_own_account_is_protected(db, admin, emails):
    plan = _employees(admin, [_record("admin@example.local", role="Пользователь", is_active="нет")]).json()
    warnings = plan["records"][0]["warnings"]
    assert plan["records"][0]["action"] == "unchanged" and len(warnings) == 2 and "свою" in warnings[0]


def test_employees_upload_errors(admin, login):
    assert admin.post("/api/org/employees/import", files={"file": ("a.pdf", b"%PDF", "application/pdf")}) \
        .status_code == 422
    assert admin.post("/api/org/employees/import", files={"file": ("a.csv", b"", "text/csv")}).status_code == 422
    response = admin.post("/api/org/employees/import", files={"file": ("a.csv", "ФИО;Должность\nА;Б".encode(),
                                                                       "text/csv")})
    assert response.status_code == 422 and "Email" in response.json()["detail"]
    response = admin.post("/api/org/employees/import", files={"file": ("a.json", b'{"format": "x"}', "text/plain")})
    assert response.status_code == 422 and "dashboards.employees" in response.json()["detail"]
    assert admin.post("/api/org/employees/import", data={"apply": "true"}, files={}).status_code == 422
    response = admin.post("/api/org/employees/import", files={"file": ("a.csv", b"Email\nx@y.ru", "text/csv")},
                          data={"decisions": "{oops"})
    assert response.status_code == 422 and "decisions" in response.json()["detail"]
    response = admin.post("/api/org/employees/import", files={"file": ("a.csv", b"Email\nx@y.ru", "text/csv")},
                          data={"new_users": "everyone"})
    assert response.status_code == 422
    assert _employees(admin, {"format": "dashboards.employees", "version": 2, "employees": []}).status_code == 422
    assert _employees(admin, [], new_users="all").status_code == 422
    assert admin.post("/api/org/employees/import", content=b"[1]",
                      headers={"content-type": "application/json"}).status_code == 422
    assert login("viewer").post("/api/org/employees/import", json={"content": []}).status_code == 403


def test_employees_multipart_apply_and_csv_body(db, admin, emails):
    text = "Email;ФИО;Подразделение;Руководит;Первое лицо\r\nnew@x.ru;Новый Сотрудник;Новая компания;да;да\r\n"
    files = {"file": ("list.csv", text.encode("utf-8-sig"), "text/csv")}
    result = admin.post("/api/org/employees/import", files=files, data={"apply": "true", "new_users": "inactive"})
    assert result.status_code == 200, result.text
    user = db.get(User, result.json()["user_ids"]["new@x.ru"])
    assert user.is_active is False and user.reports_to_none is True
    plan = _employees(admin, text, fmt="csv").json()
    assert plan["summary"]["unchanged"] == 1
    assert _employees(admin, [1, 2], fmt="csv").status_code == 422


# ================================================================ быстрая загрузка списком

LIST = ("email;ФИО;Логин;Подразделение;Должность;Руководитель;Руководит;Внешний ID\r\n"
        "new.head@x.ru;Новиков Пётр;pnovikov;АЛМИ Партнер / Отдел продаж;Руководитель отдела;;да;T-1\r\n"
        "new.sales@x.ru;Смирнова Ольга;;АЛМИ Партнер / Отдел продаж;Менеджер;new.head@x.ru;;T-2\r\n"
        "new.other@x.ru;Козлов Иван;;АЛМИ Партнер / Отдел продаж;Менеджер;tp_lead@example.local;;\r\n"
        "engineer@example.local;;;АЛМИ Партнер / Отдел продаж;Инженер продаж;;;\r\n")


def test_list_import_plan_and_apply(db, admin, emails):
    plan = _list(admin, LIST).json()
    assert not plan["can_apply"] and "Создавать новых" in plan["users"][0]["errors"][0]
    plan = _list(admin, LIST, create_missing=True).json()
    assert plan["can_apply"], plan["users"]
    assert plan["summary"]["create_users"] == 3 and plan["summary"]["update_users"] == 1
    assert [d["path"] for d in plan["departments"]] == ["АЛМИ Партнер / Отдел продаж"]
    sales = next(u for u in plan["users"] if u["email"] == "new.sales@x.ru")
    assert sales["manager"] == "Новиков Пётр" and sales["manager_explicit"] is False
    other = next(u for u in plan["users"] if u["email"] == "new.other@x.ru")
    assert other["manager_explicit"] is True
    engineer = next(u for u in plan["users"] if u["email"] == "engineer@example.local")
    assert {c["field"] for c in engineer["changes"]} == {"department", "position"}
    result = _list(admin, LIST, create_missing=True, apply=True).json()
    assert result["applied"]
    users = {u.email: u for u in db.scalars(select(User))}
    head, sales_user, other_user = users["new.head@x.ru"], users["new.sales@x.ru"], users["new.other@x.ru"]
    assert (head.username, head.org_source, head.auth_source, head.password_hash) == ("pnovikov", "csv", "local", None)
    assert head.external_id == "T-1" and sales_user.username == "new.sales"
    link = db.scalar(select(DepartmentHead).where(DepartmentHead.user_id == head.id))
    assert link.is_primary and link.department_id == head.department_id
    assert sales_user.manager_id is None, "руководитель совпал со структурным"
    assert other_user.manager_id == _users(db)["tp_lead"]
    db.expire_all()
    assert db.get(User, _users(db)["engineer"]).department_id == head.department_id
    dept = db.get(Department, head.department_id)
    assert dept.org_source == "csv" and dept.kind == "department"
    assert db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "org_import", AuditEntry.action == "csv"))
    # повторно — без изменений
    plan = _list(admin, LIST, create_missing=True).json()
    assert plan["summary"]["unchanged"] == 4


def test_list_import_xlsx_upload(db, admin, emails):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["E-mail", "Сотрудник", "Отдел", "Должность", "Руководит"])
    ws.append(["xl@x.ru", "Эксель Сотрудник", "АЛМИ Партнер > Аппарат генерального директора > АХО", "Завхоз",
               True])
    buf = io.BytesIO()
    wb.save(buf)
    files = {"file": ("list.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    result = admin.post("/api/org/import/list", files=files, data={"create_missing": "true", "apply": "true"})
    assert result.status_code == 200, result.text
    user = db.scalar(select(User).where(User.email == "xl@x.ru"))
    assert user.department_id == _units(db)["AHO"] and user.position == "Завхоз"
    assert db.scalar(select(DepartmentHead).where(DepartmentHead.user_id == user.id)).is_primary


@pytest.mark.parametrize(("text", "error"), [
    ("email;Подразделение\r\nbad;АЛМИ Партнер\r\n", "некорректный email"),
    ("email;Подразделение\r\nengineer@example.local;А\r\nengineer@example.local;А\r\n", "повторяется"),
    ("email;Подразделение\r\nengineer@example.local;\r\n", "не указано подразделение"),
    ("email;Подразделение;Руководитель\r\nengineer@example.local;А;ghost@x.ru\r\n", "не найден"),
    ("email;Подразделение;Руководитель\r\nengineer@example.local;А;engineer@example.local\r\n", "своим руководителем"),
    ("email;Подразделение;Руководитель\r\ntp_lead@example.local;АЛМИ Партнер / Техническая дирекция / "
     "Техническая служба;engineer@example.local\r\n", "цикл подчинения"),
    ("email;ФИО;Подразделение\r\nnew@x.ru;;А\r\n", "нужно ФИО"),
])
def test_list_import_errors(db, admin, emails, text, error):
    plan = _list(admin, text, create_missing=True).json()
    assert not plan["can_apply"]
    assert any(error in e for u in plan["users"] for e in u["errors"]), plan["users"]
    response = _list(admin, text, create_missing=True, apply=True)
    assert response.status_code == 409 and response.json()["code"] == "import_has_errors"


@pytest.mark.parametrize(("text", "message"), [
    ("", "пустой"),
    ("ФИО;Должность\r\nА;Б\r\n", "email"),
    ("email;ФИО\r\na@x.ru;А\r\n", "Подразделение"),
    ("email;Подразделение\r\n", "нет ни одной строки"),
])
def test_list_import_format_errors(admin, text, message):
    response = _list(admin, text)
    assert response.status_code == 422 and message in response.json()["detail"]


def test_list_import_login_match_and_permissions(db, admin, login):
    plan = _list(admin, "Логин;Подразделение;Должность\r\nviewer;АЛМИ Партнер / АХО;Аналитик АХО\r\n").json()
    assert plan["can_apply"] and plan["users"][0]["user_id"] == _users(db)["viewer"]
    assert login("viewer").post("/api/org/import/list", json={"content": "x"}).status_code == 403
    assert admin.post("/api/org/import/list", files={"file": ("a.doc", b"xx", "application/msword")}).status_code \
        == 422


def test_list_import_keeps_explicit_manager_when_not_given(db, admin, emails):
    _set(db, "viewer", manager_id=_users(db)["product"])
    plan = _list(admin, "email;Подразделение\r\nviewer@example.local;АЛМИ Партнер / АХО\r\n").json()
    assert plan["can_apply"] and {c["field"] for c in plan["users"][0]["changes"]} == {"department"}
    _list(admin, "email;Подразделение\r\nviewer@example.local;АЛМИ Партнер / АХО\r\n", apply=True)
    db.expire_all()
    assert db.get(User, _users(db)["viewer"]).manager_id == _users(db)["product"]


def test_passwords_reference(login):
    assert PASSWORDS["engineer"] == "en123456" and login("engineer", PASSWORDS["engineer"])
