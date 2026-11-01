"""Администрирование пользователей (ADR-0008): список с фильтрами и сводкой, создание со способом
входа, изменение с защитами, «Выдать доступ», сброс пароля, удаление, полномочие users.manage."""
import pytest

from app.core.config import settings


def _users(client, **params):
    response = client.get("/api/users", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _user(admin, username):
    return next(u for u in _users(admin)["items"] if u["username"] == username)


def _names(client, **params):
    return {u["username"] for u in _users(client, **params)["items"]}


@pytest.fixture()
def ldap_enabled(monkeypatch):
    """Вход по домену включён; каталог (без сети) не подтверждает ни один пароль."""
    from app.services import ldap_auth

    class Directory:
        def authenticate(self, login, password):
            return None

    monkeypatch.setattr(settings, "auth_ldap_enabled", True)
    monkeypatch.setattr(settings, "auth_ldap_url", "ldaps://dc.test:636")
    monkeypatch.setattr(settings, "auth_ldap_base_dn", "ou=staff,dc=test")
    monkeypatch.setattr(ldap_auth, "directory_for", lambda config: Directory())


@pytest.fixture()
def manager(admin, login):
    """viewer с полномочием users.manage (без роли администратора)."""
    viewer = _user(admin, "viewer")
    assert admin.patch(f"/api/users/{viewer['id']}", json={"capabilities": ["users.manage"]}).status_code == 200
    return login("viewer")


# ---------------------------------------------------------------- права

def test_only_admin_or_users_manage_manage_users(login):
    for username in ("hr_head", "viewer"):
        c = login(username)
        assert c.get("/api/users").status_code == 403
        assert c.post("/api/users", json={"username": "x1", "full_name": "X"}).status_code == 403
        assert c.get("/api/users").json()["detail"] == "Недостаточно полномочий: пользователи и доступ (кроме " \
                                                       "администраторов)"


def test_users_manage_capability_manages_non_admins(admin, manager):
    assert manager.get("/api/users").status_code == 200
    created = manager.post("/api/users", json={"username": "helper", "full_name": "Помощник"})
    assert created.status_code == 201 and created.json()["temporary_password"]
    helper = created.json()["user"]
    assert manager.patch(f"/api/users/{helper['id']}", json={"position": "Стажёр"}).json()["position"] == "Стажёр"
    assert manager.post(f"/api/users/{helper['id']}/reset-password").status_code == 200
    assert manager.delete(f"/api/users/{helper['id']}").status_code == 200


def test_users_manage_cannot_touch_admins_roles_or_capabilities(admin, manager):
    target = _user(admin, "admin")
    assert manager.patch(f"/api/users/{target['id']}", json={"position": "x"}).status_code == 403
    assert manager.delete(f"/api/users/{target['id']}").status_code == 403
    assert manager.post(f"/api/users/{target['id']}/reset-password").status_code == 403
    assert manager.post(f"/api/users/{target['id']}/grant-access", json={"method": "password"}).status_code == 403
    assert manager.put(f"/api/users/{target['id']}/access", json={"overrides": {}}).status_code == 403
    hr_head = _user(admin, "hr_head")
    promote = manager.patch(f"/api/users/{hr_head['id']}", json={"role": "admin"})
    assert promote.status_code == 403 and promote.json()["detail"] == "Роль администратора назначает только " \
                                                                     "администратор"
    caps = manager.patch(f"/api/users/{hr_head['id']}", json={"capabilities": ["org.manage"]})
    assert caps.status_code == 403 and caps.json()["detail"] == "Полномочия выдаёт только администратор"
    # те же полномочия, что уже есть, — не изменение
    assert manager.patch(f"/api/users/{hr_head['id']}", json={"capabilities": []}).status_code == 200
    assert manager.post("/api/users", json={"username": "boss2", "full_name": "Ещё админ", "role": "admin"}) \
        .status_code == 403
    assert manager.post("/api/users", json={"username": "cap2", "full_name": "С полномочием",
                                            "capabilities": ["org.manage"]}).status_code == 403


# ---------------------------------------------------------------- список

def test_list_shape_and_summary(admin):
    data = _users(admin)
    assert data["total"] == len(data["items"]) == 9
    assert data["summary"] == {"total": 9, "active": 9, "disabled": 0, "no_access": 0, "ldap": 0, "admins": 1}
    engineer = next(u for u in data["items"] if u["username"] == "engineer")
    assert engineer["department"]["path"] == "АЛМИ Партнер / Техническая дирекция / Техническая служба / " \
                                             "Группа поддержки AlterOS"
    assert engineer["manager"]["username"] == "tp_lead" and engineer["manager"]["source"] == "structure"
    assert engineer["profile"]["key"] == "employee"
    assert engineer["auth_source"] == "local" and engineer["has_password"] and engineer["status"] == "active"
    assert engineer["capabilities"] == [] and engineer["auth_linked_at"] is None
    assert next(u for u in data["items"] if u["username"] == "viewer")["profile"] is None


def test_users_filters(admin):
    assert [u["username"] for u in _users(admin, search="техпод")["items"]] == ["tp_lead"]
    tech = _names(admin, service="tech")
    # служба из профиля тоже даёт доступ: руководитель направления и первое лицо видят дашборды
    assert {"admin", "tp_lead", "viewer", "hr_head", "ceo", "tech_dir"} <= tech and "product" not in tech
    # поиск без учёта регистра (кириллица) по должности и пути подразделения
    assert _names(admin, search="ИНЖЕНЕР") == {"engineer"}
    assert _names(admin, search="техническая дирекция") == {"tech_dir", "tp_lead", "it_viewer", "engineer"}
    assert _names(admin, role="admin") == {"admin"}
    assert _names(admin, auth_source="ldap") == set()


def test_filters_by_department_profile_and_status(admin):
    tech = next(u for u in _users(admin)["items"] if u["username"] == "tp_lead")["department"]
    assert _names(admin, department_id=tech["id"]) == {"tp_lead"}
    assert _names(admin, department_id="none") == {"admin", "hr_head", "viewer"}
    head = next(u for u in _users(admin)["items"] if u["username"] == "tp_lead")["profile"]
    assert _names(admin, profile_id=head["id"]) == {"tp_lead", "it_viewer"}
    assert _names(admin, profile_id="none") == {"admin", "hr_head", "viewer", "product"}
    assert admin.get("/api/users", params={"department_id": "abc"}).status_code == 422
    assert admin.get("/api/users", params={"status": "broken"}).status_code == 422

    admin.post("/api/users", json={"username": "listed", "full_name": "Загружен списком", "access_method": "none"})
    viewer = _user(admin, "viewer")
    admin.patch(f"/api/users/{viewer['id']}", json={"is_active": False})
    data = _users(admin)
    assert data["summary"]["no_access"] == 1 and data["summary"]["disabled"] == 1
    assert data["summary"]["active"] == 9 and data["summary"]["total"] == 10
    assert _names(admin, status="no_access") == {"listed"}
    assert _names(admin, status="disabled") == {"viewer"}
    assert "listed" in _names(admin, status="active") and "viewer" not in _names(admin, status="active")


# ---------------------------------------------------------------- создание

def test_create_user_with_password_and_access(admin, client):
    response = admin.post("/api/users", json={
        "username": "analyst", "full_name": "Аналитик", "email": "Analyst@Example.com", "password": "Strong-pass-1",
        "access": [{"service_key": "tech", "level": "editor"}, {"service_key": "hr", "level": "viewer",
                                                                 "department_scope": True}],
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["temporary_password"] is None
    user = body["user"]
    assert user["email"] == "analyst@example.com" and user["status"] == "active" and user["has_password"]
    assert {(a["service_key"], a["level"], a["department_scope"]) for a in user["access"]} == {
        ("tech", "editor", False), ("hr", "viewer", True)}
    me = client.login("analyst", "Strong-pass-1")
    assert me["must_change_password"] is True


def test_create_with_department_profile_and_capabilities(admin):
    depts = {u["username"]: u["department"] for u in _users(admin)["items"]}
    head = next(p for p in admin.get("/api/access/profiles").json() if p["key"] == "head")
    response = admin.post("/api/users", json={
        "username": "lead2", "full_name": "Руководитель группы", "department_id": depts["engineer"]["id"],
        "profile_id": head["id"], "capabilities": ["org.manage"]})
    assert response.status_code == 201, response.text
    user = response.json()["user"]
    assert user["department"]["id"] == depts["engineer"]["id"] and user["profile"]["key"] == "head"
    assert user["capabilities"] == ["org.manage"]
    assert admin.post("/api/users", json={"username": "x2", "full_name": "X", "profile_id": 9999}).status_code == 422
    assert admin.post("/api/users", json={"username": "x3", "full_name": "X", "department_id": 9999}).status_code == 422
    bad = admin.post("/api/users", json={"username": "x4", "full_name": "X", "capabilities": ["root"]})
    assert bad.status_code == 422 and "capabilities" in bad.json()["fields"]


def test_create_without_access_then_grant_password(admin, client):
    created = admin.post("/api/users", json={"username": "listed", "full_name": "Загружен списком",
                                             "access_method": "none"})
    assert created.status_code == 201
    body = created.json()
    assert body["temporary_password"] is None
    user = body["user"]
    assert user["status"] == "no_access" and not user["has_password"]
    assert client.post("/api/auth/login", json={"username": "listed", "password": "anything-1"}).status_code == 401
    granted = admin.post(f"/api/users/{user['id']}/grant-access", json={"method": "password"})
    assert granted.status_code == 200
    temporary = granted.json()["temporary_password"]
    assert temporary and granted.json()["user"]["status"] == "active"
    assert client.login("listed", temporary)["must_change_password"] is True
    log = admin.get("/api/audit", params={"entity_type": "user", "action": "grant"}).json()
    assert log["total"] == 1 and "временный пароль" in log["items"][0]["summary"]


def test_password_only_for_password_method(admin):
    response = admin.post("/api/users", json={"username": "x5", "full_name": "X", "access_method": "none",
                                              "password": "Strong-pass-1"})
    assert response.status_code == 422 and "password" in response.json()["fields"]


def test_create_domain_account_requires_ldap_and_email(admin, ldap_enabled, monkeypatch):
    without_email = admin.post("/api/users", json={"username": "dom1", "full_name": "Домен",
                                                   "access_method": "ldap"})
    assert without_email.status_code == 422 and "email" in without_email.json()["fields"]
    created = admin.post("/api/users", json={"username": "dom1", "full_name": "Домен", "email": "dom1@example.com",
                                             "access_method": "ldap"})
    assert created.status_code == 201
    user = created.json()["user"]
    assert user["auth_source"] == "ldap" and not user["has_password"] and user["status"] == "active"
    assert created.json()["temporary_password"] is None
    monkeypatch.setattr(settings, "auth_ldap_enabled", False)
    off = admin.post("/api/users", json={"username": "dom2", "full_name": "Домен", "email": "dom2@example.com",
                                         "access_method": "ldap"})
    assert off.status_code == 422 and off.json()["detail"].startswith("Вход по домену не включён")


def test_duplicate_username_and_email(admin):
    assert admin.post("/api/users", json={"username": "VIEWER", "full_name": "Дубль"}).status_code == 409
    admin.put("/api/auth/profile", json={"email": "boss@example.com"})
    dup = admin.post("/api/users", json={"username": "other", "full_name": "Другой", "email": "BOSS@example.com"})
    assert dup.status_code == 422


def test_invalid_username_rejected(admin):
    assert admin.post("/api/users", json={"username": "имя с пробелом", "full_name": "X"}).status_code == 422


def test_weak_password_error_points_to_password_field(admin):
    response = admin.post("/api/users", json={"username": "weak", "full_name": "Слабый пароль", "password": "short"})
    assert response.status_code == 422
    assert "password" in response.json()["fields"]


# ---------------------------------------------------------------- доступ к службам (совместимость 0.1.0)

def test_access_replace_and_audit(admin):
    viewer = _user(admin, "viewer")
    response = admin.put(f"/api/users/{viewer['id']}/access", json=[{"service_key": "tech", "level": "manager"}])
    assert response.status_code == 200
    assert response.json()["services"] == [{"service_key": "tech", "level": "manager", "org_scope": None,
                                            "department_scope": False}]
    assert admin.get(f"/api/users/{viewer['id']}").json()["access"][0]["level"] == "manager"
    log = admin.get("/api/audit", params={"entity_type": "user_access"}).json()
    assert log["total"] == 1 and "viewer" in log["items"][0]["summary"]


def test_access_validation(admin):
    viewer = _user(admin, "viewer")
    bad = admin.put(f"/api/users/{viewer['id']}/access", json=[{"service_key": "nope", "level": "viewer"}])
    assert bad.status_code == 422
    twice = admin.put(f"/api/users/{viewer['id']}/access", json=[{"service_key": "hr", "level": "viewer"},
                                                                  {"service_key": "hr", "level": "editor"}])
    assert twice.status_code == 422
    level = admin.put(f"/api/users/{viewer['id']}/access", json=[{"service_key": "hr", "level": "owner"}])
    assert level.status_code == 422


def test_service_scope_applies_to_any_level(admin):
    """С 0.2.0 область структуры службы действует на любом уровне доступа (ADR-0009)."""
    viewer = _user(admin, "viewer")
    response = admin.put(f"/api/users/{viewer['id']}/access",
                         json=[{"service_key": "hr", "level": "editor", "department_scope": True}])
    row = response.json()["services"][0]
    assert row["org_scope"] == "branch" and row["department_scope"] is True
    response = admin.put(f"/api/users/{viewer['id']}/access",
                         json=[{"service_key": "hr", "level": "viewer", "org_scope": "unit"}])
    assert response.json()["services"][0]["org_scope"] == "unit"


# ---------------------------------------------------------------- изменение

def test_admin_cannot_lock_themselves_out(admin):
    me = admin.get("/api/auth/me").json()
    assert admin.patch(f"/api/users/{me['id']}", json={"role": "user"}).status_code == 422
    assert admin.patch(f"/api/users/{me['id']}", json={"is_active": False}).status_code == 422
    assert admin.delete(f"/api/users/{me['id']}").status_code == 422


def test_last_admin_is_protected(admin):
    created = admin.post("/api/users", json={"username": "admin2", "full_name": "Второй", "role": "admin",
                                             "password": "Admin-two-22"}).json()["user"]
    # двух администраторов можно понизить до одного
    assert admin.patch(f"/api/users/{created['id']}", json={"role": "user"}).status_code == 200


def test_last_active_admin_rule(db):
    from app.core.errors import ValidationFailed
    from app.models import User
    from app.services import users as users_service

    admin = db.query(User).filter_by(username="admin").one()
    other = db.query(User).filter_by(username="viewer").one()
    other.role = "admin"
    db.flush()
    admin.is_active = False  # единственный активный администратор — viewer
    db.flush()
    with pytest.raises(ValidationFailed, match="хотя бы один активный администратор"):
        users_service.update_user(db, admin, other, {"role": "user"})
    with pytest.raises(ValidationFailed, match="последнего администратора"):
        users_service.delete_user(db, admin, other)


def test_update_user_fields_departments_profile(admin):
    viewer = _user(admin, "viewer")
    depts = {u["username"]: u["department"] for u in _users(admin)["items"]}
    legacy = admin.get("/api/departments").json()
    response = admin.patch(f"/api/users/{viewer['id']}", json={"full_name": "Обновлённый", "position": "Аналитик BI",
                                                               "department_ids": [legacy[0]["id"]]})
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Обновлённый" and body["departments"][0]["id"] == legacy[0]["id"]
    assert admin.patch(f"/api/users/{viewer['id']}", json={"department_ids": [99999]}).status_code == 422

    specialist = next(p for p in admin.get("/api/access/profiles").json() if p["key"] == "specialist")
    body = admin.patch(f"/api/users/{viewer['id']}", json={"department_id": depts["tp_lead"]["id"],
                                                           "profile_id": specialist["id"]}).json()
    assert body["department"]["path"] == "АЛМИ Партнер / Техническая дирекция / Техническая служба"
    assert body["profile"]["key"] == "specialist" and body["manager"]["username"] == "tp_lead"
    body = admin.patch(f"/api/users/{viewer['id']}", json={"department_id": None, "profile_id": None}).json()
    assert body["department"] is None and body["profile"] is None
    assert admin.patch(f"/api/users/{viewer['id']}", json={"profile_id": 9999}).status_code == 422
    log = admin.get("/api/audit", params={"entity_type": "user", "action": "update"}).json()
    assert log["total"] == 3


def test_admin_grants_capabilities(admin, login):
    viewer = _user(admin, "viewer")
    body = admin.patch(f"/api/users/{viewer['id']}", json={"capabilities": ["org.manage", "users.manage"]}).json()
    assert body["capabilities"] == ["org.manage", "users.manage"]
    assert login("viewer").get("/api/auth/me").json()["capabilities"] == ["org.manage", "users.manage"]
    assert admin.patch(f"/api/users/{viewer['id']}", json={"capabilities": ["nope"]}).status_code == 422


def test_reset_password_gives_temporary_one(admin, login, client):
    viewer_client = login("viewer")
    viewer = _user(admin, "viewer")
    response = admin.post(f"/api/users/{viewer['id']}/reset-password")
    temporary = response.json()["temporary_password"]
    assert len(temporary) >= 12
    assert viewer_client.get("/api/auth/me").status_code == 401
    assert client.login("viewer", temporary)["must_change_password"] is True


def test_reset_password_moves_domain_account_to_local(admin, ldap_enabled, client):
    created = admin.post("/api/users", json={"username": "dom3", "full_name": "Домен", "email": "dom3@example.com",
                                             "access_method": "ldap"}).json()["user"]
    response = admin.post(f"/api/users/{created['id']}/reset-password")
    assert response.status_code == 200
    user = response.json()["user"]
    assert user["auth_source"] == "local" and user["has_password"] and user["must_change_password"]
    assert client.login("dom3", response.json()["temporary_password"])["auth_source"] == "local"
    log = admin.get("/api/audit", params={"action": "password"}).json()
    assert "вход по домену заменён паролем системы" in log["items"][0]["summary"]


def test_grant_access(admin, ldap_enabled, monkeypatch):
    viewer = _user(admin, "viewer")
    admin.patch(f"/api/users/{viewer['id']}", json={"is_active": False})
    # пароль уже есть — учётная запись просто включается
    granted = admin.post(f"/api/users/{viewer['id']}/grant-access", json={"method": "password"})
    assert granted.json()["temporary_password"] is None and granted.json()["user"]["is_active"]
    no_email = admin.post(f"/api/users/{viewer['id']}/grant-access", json={"method": "ldap"})
    assert no_email.status_code == 422 and "email" in no_email.json()["fields"]
    admin.patch(f"/api/users/{viewer['id']}", json={"email": "viewer@example.com"})
    domain = admin.post(f"/api/users/{viewer['id']}/grant-access", json={"method": "ldap"}).json()["user"]
    assert domain["auth_source"] == "ldap" and not domain["has_password"] and domain["status"] == "active"
    # учётной записи домена «пароль системы» — временный пароль и переход на пароль системы
    back = admin.post(f"/api/users/{viewer['id']}/grant-access", json={"method": "password"}).json()
    assert back["temporary_password"] and back["user"]["auth_source"] == "local"
    monkeypatch.setattr(settings, "auth_ldap_enabled", False)
    off = admin.post(f"/api/users/{viewer['id']}/grant-access", json={"method": "ldap"})
    assert off.status_code == 422
    assert admin.post("/api/users/99999/grant-access", json={"method": "password"}).status_code == 404


def test_delete_user(admin):
    viewer = _user(admin, "viewer")
    assert admin.delete(f"/api/users/{viewer['id']}").status_code == 200
    assert admin.get(f"/api/users/{viewer['id']}").status_code == 404
    log = admin.get("/api/audit", params={"entity_type": "user", "action": "delete"}).json()
    assert log["total"] == 1


def test_departments_crud(admin):
    created = admin.post("/api/departments", json={"name": "Отдел качества", "code": "qa"})
    assert created.status_code == 201 and created.json()["code"] == "QA"
    dept_id = created.json()["id"]
    assert admin.post("/api/departments", json={"name": "отдел качества", "code": "QA2"}).status_code == 409
    assert admin.put(f"/api/departments/{dept_id}", json={"name": "Отдел контроля качества", "code": "QC"}).json()[
        "name"] == "Отдел контроля качества"
    assert admin.delete(f"/api/departments/{dept_id}").status_code == 200


def test_grant_access_defaults_to_password(admin):
    created = admin.post("/api/users", json={"username": "later", "full_name": "Позже", "access_method": "none"})
    response = admin.post(f"/api/users/{created.json()['user']['id']}/grant-access")
    assert response.status_code == 200 and response.json()["temporary_password"]
    assert _names(admin, status="all") == _names(admin)
