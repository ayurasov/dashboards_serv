"""Модель доступа 2.0 (ADR-0009): справочник, профили доступа, доступ пользователя, проверки
исходных записей, выгрузки и классов данных, ключи кэша ответов."""
import asyncio

import pytest
from sqlalchemy import select

from app.api.deps import require_data_class, require_export, require_records
from app.core.errors import Forbidden
from app.models import ServiceAccess, User
from app.services import access
from app.services.registry import ACCESS_DIMENSIONS, MAX_DRILL_DEPTH

PASSWORDS = {"ceo": "ceo12345", "tech_dir": "td123456", "engineer": "en123456"}


def _as(login, username):
    return login(username, PASSWORDS.get(username))


def _user_id(admin, username):
    return next(u["id"] for u in admin.get("/api/users").json()["items"] if u["username"] == username)


def _profile(admin, key):
    return next(p for p in admin.get("/api/access/profiles").json() if p["key"] == key)


def _grant(db, username, service_key, level="viewer"):
    user = db.scalar(select(User).where(User.username == username))
    db.add(ServiceAccess(user_id=user.id, service_key=service_key, level=level))
    db.commit()


def _override(db, username, **overrides):
    user = db.scalar(select(User).where(User.username == username))
    user.access_overrides = {**(user.access_overrides or {}), **overrides}
    db.commit()


# ---------------------------------------------------------------- справочник

def test_meta_for_any_user(client, login):
    assert client.get("/api/access/meta").status_code == 401
    data = _as(login, "engineer").get("/api/access/meta").json()
    assert [c["key"] for c in data["data_classes"]] == ["operational", "personal", "financial"]
    assert data["data_classes"][0]["always"] and data["data_classes"][1]["hint"].startswith("ФИО")
    assert [s["key"] for s in data["org_scopes"]] == ["company", "branch", "unit"]
    assert [d["key"] for d in data["dimensions"]] == list(ACCESS_DIMENSIONS)
    assert [lvl["key"] for lvl in data["levels"]] == ["none", "viewer", "editor", "manager"]
    assert data["levels"][0]["label"] == "Нет" and data["max_drill_depth"] == MAX_DRILL_DEPTH
    assert {c["key"] for c in data["capabilities"]} == {"org.manage", "users.manage", "reports.manage", "data.manage",
                                                    "integrations.manage"}
    labels = {c["key"]: c["label"] for c in data["capabilities"]}
    assert "содержимое каждого входящего файла" in labels["data.manage"] and \
        "персональные и финансовые данные" in labels["data.manage"], "выдающий полномочие видит, что оно открывает"
    assert all(word in labels["integrations.manage"] for word in ("подключения", "запускает", "ключи", "Confluence"))
    hr = data["services"][0]
    assert hr["key"] == "hr" and hr["has_dashboard"] and hr["levels"] == ["none", "viewer", "editor", "manager"]
    assert len(data["services"]) == 9


# ---------------------------------------------------------------- профили доступа

def test_profiles_list_with_usage(admin, login):
    profiles = admin.get("/api/access/profiles").json()
    assert [(p["key"], p["users_count"], p["is_system"]) for p in profiles] == [
        ("executive", 1, True), ("director", 1, True), ("head", 2, True), ("specialist", 0, True),
        ("employee", 1, True)]
    executive = profiles[0]
    assert executive["org_scope"] == "company" and executive["drill_depth"] == 1
    assert not executive["can_view_records"] and executive["service_levels"]["hr"] == "viewer"
    assert login("viewer").get("/api/access/profiles").status_code == 403


def test_create_custom_profile(admin, db):
    body = {"key": "fin_control", "name": "Финансовый контролёр", "description": "Без персональных данных",
            "org_scope": "company", "data_classes": ["financial", "financial"], "drill_depth": 3,
            "can_view_records": False, "service_levels": {"project_product": "viewer", "hr": "viewer"}}
    response = admin.post("/api/access/profiles", json=body)
    assert response.status_code == 201, response.text
    profile = response.json()
    assert profile["data_classes"] == ["operational", "financial"] and not profile["is_system"]
    assert list(profile["service_levels"]) == ["hr", "project_product"] and profile["users_count"] == 0
    # ключ и название уникальны (название — без учёта регистра)
    assert admin.post("/api/access/profiles", json={**body, "name": "Другое"}).status_code == 409
    dup = admin.post("/api/access/profiles", json={**body, "key": "fin2", "name": "  финансовый   КОНТРОЛЁР "})
    assert dup.status_code == 409 and dup.json()["fields"] == {"name": "Название занято"}
    log = admin.get("/api/audit", params={"entity_type": "access_profile"}).json()
    assert log["total"] == 1 and "Финансовый контролёр" in log["items"][0]["summary"]


@pytest.mark.parametrize("patch", [
    {"key": "Fin"}, {"key": "1fin"}, {"key": "fin control"}, {"service_levels": {"nope": "viewer"}},
    {"service_levels": {"hr": "none"}}, {"service_levels": {"hr": "owner"}}, {"drill_depth": MAX_DRILL_DEPTH + 1},
    {"drill_depth": -1}, {"org_scope": "world"}, {"data_classes": ["secret"]}, {"name": ""}, {"extra": 1},
])
def test_profile_validation(admin, patch):
    body = {"key": "custom", "name": "Свой профиль", **patch}
    assert admin.post("/api/access/profiles", json=body).status_code == 422, patch


def test_update_system_profile_changes_effective_access(admin, login):
    executive = _profile(admin, "executive")
    response = admin.patch(f"/api/access/profiles/{executive['id']}",
                           json={"drill_depth": 3, "can_view_records": True, "name": "Первые лица"})
    assert response.status_code == 200
    assert response.json()["drill_depth"] == 3 and response.json()["users_count"] == 1
    me = _as(login, "ceo").get("/api/auth/me").json()
    assert me["effective_access"]["drill_depth"] == 3 and me["effective_access"]["can_view_records"]
    assert me["profile"]["name"] == "Первые лица"
    # null — «без ограничения»; ключ не меняется
    assert admin.patch(f"/api/access/profiles/{executive['id']}", json={"drill_depth": None}).json()[
        "drill_depth"] is None
    assert admin.patch(f"/api/access/profiles/{executive['id']}", json={"key": "boss"}).status_code == 422
    head = _profile(admin, "head")
    assert admin.patch(f"/api/access/profiles/{executive['id']}", json={"name": head["name"]}).status_code == 409
    assert admin.get(f"/api/access/profiles/{executive['id']}").json()["name"] == "Первые лица"
    assert admin.get("/api/access/profiles/9999").status_code == 404


def test_delete_profiles(admin):
    executive = _profile(admin, "executive")
    system = admin.delete(f"/api/access/profiles/{executive['id']}")
    assert system.status_code == 422 and "Встроенный профиль" in system.json()["detail"]
    custom = admin.post("/api/access/profiles", json={"key": "temp", "name": "Временный"}).json()
    for username in ("viewer", "hr_head"):
        admin.patch(f"/api/users/{_user_id(admin, username)}", json={"profile_id": custom["id"]})
    in_use = admin.delete(f"/api/access/profiles/{custom['id']}")
    assert in_use.status_code == 409 and in_use.json()["code"] == "profile_in_use"
    assert "назначен 2 пользователям" in in_use.json()["detail"]
    admin.patch(f"/api/users/{_user_id(admin, 'hr_head')}", json={"profile_id": None})
    assert "назначен 1 пользователю" in admin.delete(f"/api/access/profiles/{custom['id']}").json()["detail"]
    admin.patch(f"/api/users/{_user_id(admin, 'viewer')}", json={"profile_id": None})
    assert admin.delete(f"/api/access/profiles/{custom['id']}").status_code == 200
    assert admin.get(f"/api/access/profiles/{custom['id']}").status_code == 404


def test_users_manage_can_manage_profiles(admin, login):
    admin.patch(f"/api/users/{_user_id(admin, 'viewer')}", json={"capabilities": ["users.manage"]})
    c = login("viewer")
    assert c.post("/api/access/profiles", json={"key": "by_manager", "name": "От ведущего"}).status_code == 201


# ---------------------------------------------------------------- доступ пользователя

def test_get_user_access(admin):
    data = admin.get(f"/api/users/{_user_id(admin, 'engineer')}/access").json()
    assert data["profile"]["key"] == "employee" and data["overrides"] == {} and data["services"] == []
    assert data["extra_units"] == [] and not data["is_admin"]
    assert data["effective"]["org_scope"] == "unit" and data["effective"]["sources"]["org_scope"] == "profile"
    assert data["scope_units"] == [{"id": data["scope_units"][0]["id"], "name": "Группа поддержки AlterOS",
                                    "path": "АЛМИ Партнер / Техническая дирекция / Техническая служба / "
                                            "Группа поддержки AlterOS"}]
    boss = admin.get(f"/api/users/{_user_id(admin, 'admin')}/access").json()
    assert boss["is_admin"] and boss["effective"]["is_admin"] and boss["scope_units"] is None
    assert admin.get("/api/users/99999/access").status_code == 404


def test_put_user_access_policy(admin, login):
    uid = _user_id(admin, "engineer")
    head = _profile(admin, "head")
    units = {u["username"]: u["department"] for u in admin.get("/api/users").json()["items"]}
    body = {"profile_id": head["id"],
            "overrides": {"drill_depth": None, "data_classes": ["financial"], "can_export": True},
            "services": [{"service_key": "tech", "level": "editor"}, {"service_key": "hr", "level": "none"}],
            "extra_unit_ids": [units["it_viewer"]["id"]]}
    response = admin.put(f"/api/users/{uid}/access", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["profile"]["key"] == "head"
    assert data["overrides"] == {"data_classes": ["operational", "financial"], "drill_depth": None,
                                 "can_export": True}
    assert [(s["service_key"], s["level"]) for s in data["services"]] == [("hr", "none"), ("tech", "editor")]
    assert [u["name"] for u in data["extra_units"]] == ["ИТ-служба"]
    eff = data["effective"]
    assert eff["drill_depth"] is None and eff["sources"]["drill_depth"] == "personal"
    assert eff["data_classes"] == ["operational", "financial"] and eff["org_scope"] == "branch"
    assert eff["services"] == {"tech": "editor"} and eff["sources"]["service:hr"] == "personal"
    assert {u["name"] for u in data["scope_units"]} == {"Группа поддержки AlterOS", "ИТ-служба"}
    # пользователь видит свой действующий доступ
    me = _as(login, "engineer").get("/api/auth/me").json()
    assert me["effective_access"]["services"] == {"tech": "editor"} and me["profile"]["key"] == "head"
    log = admin.get("/api/audit", params={"entity_type": "user_access"}).json()
    assert log["total"] == 1 and log["items"][0]["after"]["profile"] == "head"

    # передаются только меняемые части: профиль и службы остаются
    partial = admin.put(f"/api/users/{uid}/access", json={"overrides": {}}).json()
    assert partial["overrides"] == {} and partial["profile"]["key"] == "head" and len(partial["services"]) == 2
    individual = admin.put(f"/api/users/{uid}/access", json={"profile_id": None, "extra_unit_ids": []}).json()
    assert individual["profile"] is None and individual["extra_units"] == []
    assert individual["effective"]["sources"]["org_scope"] == "default"


@pytest.mark.parametrize("body", [
    {"overrides": {"color": "red"}}, {"overrides": {"drill_depth": MAX_DRILL_DEPTH + 1}},
    {"overrides": {"drill_depth": -1}}, {"overrides": {"drill_depth": True}}, {"overrides": {"drill_depth": "2"}},
    {"overrides": {"data_classes": ["secret"]}}, {"overrides": {"data_classes": "personal"}},
    {"overrides": {"org_scope": "world"}}, {"overrides": {"org_scope": None}}, {"overrides": {"can_export": "yes"}},
    {"overrides": {"can_view_records": None}}, {"overrides": []},
    {"services": [{"service_key": "hr", "level": "owner"}]}, {"services": [{"service_key": "nope", "level": "viewer"}]},
    {"extra_unit_ids": [99999]}, {"profile_id": 99999}, {"unknown": 1},
])
def test_put_user_access_validation(admin, body):
    response = admin.put(f"/api/users/{_user_id(admin, 'engineer')}/access", json=body)
    assert response.status_code == 422, body


def test_overrides_error_names_the_field(admin):
    response = admin.put(f"/api/users/{_user_id(admin, 'engineer')}/access",
                         json={"overrides": {"drill_depth": 12}})
    assert response.json()["fields"] == {"overrides.drill_depth": "Недопустимое значение"}
    assert "от 0 до 9" in response.json()["detail"]


# ---------------------------------------------------------------- /api/auth/me

def test_me_reports_access_and_account(login):
    me = _as(login, "ceo").get("/api/auth/me").json()
    eff = me["effective_access"]
    assert eff["profile_key"] == "executive" and eff["org_scope"] == "company" and not eff["can_view_records"]
    assert set(eff["services"]) == {"hr", "tech", "project_product"} and eff["data_classes"][-1] == "financial"
    assert me["profile"]["key"] == "executive" and me["profile"]["name"] == "Высшее руководство"
    assert me["department"]["name"] == "АЛМИ Партнер" and me["department"]["path"] == "АЛМИ Партнер"
    assert me["auth_source"] == "local" and me["has_password"] and me["capabilities"] == []
    viewer = login("viewer").get("/api/auth/me").json()
    assert viewer["department"] is None and viewer["profile"] is None
    assert viewer["effective_access"]["sources"]["org_scope"] == "default"


# ---------------------------------------------------------------- исходные записи и выгрузка

def test_executive_sees_dashboards_and_pdf_but_not_registries(login):
    c = _as(login, "ceo")
    for url in ("/api/hr/analytics/dashboard", "/api/hr/months", "/api/hr/analytics/summary",
                "/api/partnerships/analytics", "/api/partnerships/summary", "/api/tp/reports",
                "/api/tp/naumen/summary", "/api/overview"):
        assert c.get(url).status_code == 200, url
    for url in ("/api/hr/events", "/api/partnerships", "/api/partnerships/timeline", "/api/partnerships/1"):
        response = c.get(url)
        assert response.status_code == 403 and response.json()["code"] == "records_forbidden", url
    assert c.get("/api/hr/events").json()["detail"] == "Исходные записи вам недоступны — доступны дашборды и " \
                                                       "сводки службы"
    # выгрузка дашбордов разрешена, выгрузка реестров — нет
    assert c.get("/api/pdf/hr/summary").status_code == 200
    for url in ("/api/hr/events/export.xlsx", "/api/pdf/hr/registry", "/api/partnerships/export.xlsx",
                "/api/pdf/partnerships/registry", "/api/tp/reports/export.xlsx", "/api/tp/reports/export.csv"):
        response = c.get(url)
        assert response.status_code == 403 and response.json()["code"] == "records_forbidden", url
    month = c.get("/api/hr/months/2026-06").json()
    assert month["events"] == [] and month["events_hidden"] is True and month["metrics"]


def test_partnerships_dashboard_counts_without_registry(admin, login):
    analytics = _as(login, "ceo").get("/api/partnerships/analytics").json()
    records = admin.get("/api/partnerships").json()
    expected = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
    for r in records:
        expected[r["light"]] += 1
    assert analytics["record_lights"] == expected and sum(expected.values()) == analytics["total"] == 142


def test_employee_without_export(db, login):
    _grant(db, "engineer", "hr")
    c = _as(login, "engineer")
    assert c.get("/api/hr/analytics/dashboard").status_code == 200
    response = c.get("/api/pdf/hr/dashboard")
    assert response.status_code == 403 and response.json() == {
        "detail": "Выгрузка в Excel, CSV и PDF вам недоступна", "code": "export_forbidden"}
    assert c.get("/api/hr/events").json()["code"] == "records_forbidden"
    # нет доступа к службе — сообщение о службе, а не о выгрузке
    assert c.get("/api/pdf/tp/naumen").json()["detail"] == "Нет доступа к службе «Техническая поддержка»"


def test_export_override_enables_downloads(db, login):
    _grant(db, "engineer", "tech")
    _override(db, "engineer", can_export=True, can_view_records=True)
    c = _as(login, "engineer")
    assert c.get("/api/tp/reports/export.csv").status_code == 200
    assert c.get("/api/pdf/tp/naumen").status_code == 200


def test_personal_data_class(db, login):
    _override(db, "tech_dir", data_classes=["operational"])
    _grant(db, "tech_dir", "hr", "editor")
    c = _as(login, "tech_dir")
    response = c.get("/api/hr/events")
    assert response.status_code == 403 and response.json() == {
        "detail": "Нет доступа к персональным данным: ФИО, должностям, причинам увольнения",
        "code": "data_class_forbidden"}
    assert c.get("/api/hr/events/export.xlsx").json()["code"] == "data_class_forbidden"
    assert c.get("/api/pdf/hr/registry").json()["code"] == "data_class_forbidden"
    event = {"event_type": "hired", "event_date": "2026-06-10", "full_name": "Новый Сотрудник"}
    assert c.post("/api/hr/months/2026-06/events", json=event).json()["code"] == "data_class_forbidden"
    # агрегаты службы персонала — без ограничений
    assert c.get("/api/hr/analytics/dashboard").status_code == 200
    month = c.get("/api/hr/months/2026-06").json()
    assert month["events_hidden"] and month["events"] == []


def test_naumen_hides_responsibles_without_personal(db, login):
    from app.services.cache import cache

    cache.clear()
    full = login("viewer").get("/api/tp/naumen/summary").json()
    assert full["responsibles"] and "responsibles_hidden" not in full
    _override(db, "tech_dir", data_classes=["operational", "financial"])
    limited = _as(login, "tech_dir").get("/api/tp/naumen/summary").json()
    assert limited["responsibles"] == [] and limited["responsibles_hidden"] is True
    assert limited["total"] == full["total"]


def test_registry_scope_by_profile(login, admin):
    """Руководитель направления видит реестр своей ветки структуры."""
    everything = admin.get("/api/hr/events").json()
    branch = {e["department"] for e in _as(login, "tech_dir").get("/api/hr/events").json()}
    assert branch and branch <= {"Техническая дирекция", "Техническая служба", "ИТ-служба", "IT", "TECH",
                                 "Группа поддержки AlterOS", "Группа поддержки AlterOffice"}
    assert len(branch) < len({e["department"] for e in everything})


# ---------------------------------------------------------------- кэш ответов

def test_cache_key_includes_scope_and_classes(db, login):
    from app.services.cache import cache

    cache.clear()
    viewer = login("viewer").get("/api/hr/analytics/dashboard").json()
    director = _as(login, "tech_dir").get("/api/hr/analytics/dashboard").json()
    assert director["totals"] != viewer["totals"]     # своя ветка, а не ответ «всей компании» из кэша
    viewer_key = access.cache_scope(db, db.scalar(select(User).where(User.username == "viewer")))
    _override(db, "viewer", data_classes=["operational"])
    db.expire_all()
    restricted = access.cache_scope(db, db.scalar(select(User).where(User.username == "viewer")))
    assert viewer_key[0] == restricted[0] is None and viewer_key[1] != restricted[1]


def test_overview_cache_respects_scope(login):
    from app.services.cache import cache

    cache.clear()
    full = login("viewer").get("/api/overview").json()
    scoped = _as(login, "tech_dir").get("/api/overview").json()
    hr_full = next(c for c in full["services"] if c["key"] == "hr")
    hr_scoped = next(c for c in scoped["services"] if c["key"] == "hr")
    assert hr_full["kpis"][0]["value"] != hr_scoped["kpis"][0]["value"]


# ---------------------------------------------------------------- зависимости и финансовый класс

def _run(checker, user):
    return asyncio.run(checker(user=user))


def test_financial_class_dependency(db):
    """Финансовых показателей пока нет: проверяются EffectiveAccess.allows и require_data_class."""
    users = {u.username: u for u in db.scalars(select(User))}
    head = access.effective(users["tp_lead"])          # профиль «Руководитель подразделения»
    assert head.allows("operational") and head.allows("personal") and not head.allows("financial")
    assert access.effective(users["ceo"]).allows("financial")
    assert access.effective(users["admin"]).allows("financial")
    checker = require_data_class("financial")
    assert _run(checker, users["ceo"]) is users["ceo"]
    with pytest.raises(Forbidden) as error:
        _run(checker, users["tp_lead"])
    assert error.value.code == "data_class_forbidden" and error.value.detail == "Нет доступа к финансовым показателям"
    with pytest.raises(Forbidden, match="Нет доступа к службе"):
        _run(require_data_class("financial", "hr"), users["tp_lead"])
    # фабрики запоминают зависимость: FastAPI выполняет проверку один раз на запрос
    assert require_data_class("financial") is checker
    assert require_records("hr", "personal") is require_records("hr", "personal")
    assert require_export("hr", records=True) is require_export("hr", records=True)


def test_records_and_export_dependencies(db):
    users = {u.username: u for u in db.scalars(select(User))}
    assert _run(require_records("hr"), users["viewer"]) is users["viewer"]
    with pytest.raises(Forbidden) as error:
        _run(require_records("hr"), users["ceo"])
    assert error.value.code == "records_forbidden"
    assert _run(require_export(), users["ceo"]) is users["ceo"]
    with pytest.raises(Forbidden) as error:
        _run(require_export(), users["engineer"])
    assert error.value.code == "export_forbidden"
