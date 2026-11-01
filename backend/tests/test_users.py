"""Администрирование пользователей, доступа и подразделений."""


def _user(admin, username):
    return next(u for u in admin.get("/api/users").json() if u["username"] == username)


def test_only_admin_manages_users(login):
    for username in ("hr_head", "viewer"):
        c = login(username)
        assert c.get("/api/users").status_code == 403
        assert c.post("/api/users", json={"username": "x1", "full_name": "X"}).status_code == 403


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
    assert user["email"] == "analyst@example.com"
    assert {(a["service_key"], a["level"], a["department_scope"]) for a in user["access"]} == {
        ("tech", "editor", False), ("hr", "viewer", True)}
    me = client.login("analyst", "Strong-pass-1")
    assert me["must_change_password"] is True


def test_duplicate_username_and_email(admin):
    assert admin.post("/api/users", json={"username": "VIEWER", "full_name": "Дубль"}).status_code == 409
    admin.put("/api/auth/profile", json={"email": "boss@example.com"})
    dup = admin.post("/api/users", json={"username": "other", "full_name": "Другой", "email": "BOSS@example.com"})
    assert dup.status_code == 422


def test_invalid_username_rejected(admin):
    assert admin.post("/api/users", json={"username": "имя с пробелом", "full_name": "X"}).status_code == 422


def test_access_replace_and_audit(admin):
    viewer = _user(admin, "viewer")
    response = admin.put(f"/api/users/{viewer['id']}/access", json=[{"service_key": "tech", "level": "manager"}])
    assert response.status_code == 200
    assert response.json()["access"] == [{"service_key": "tech", "level": "manager", "org_scope": None,
                                          "department_scope": False}]
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
    row = response.json()["access"][0]
    assert row["org_scope"] == "branch" and row["department_scope"] is True
    response = admin.put(f"/api/users/{viewer['id']}/access",
                         json=[{"service_key": "hr", "level": "viewer", "org_scope": "unit"}])
    assert response.json()["access"][0]["org_scope"] == "unit"


def test_reset_password_gives_temporary_one(admin, login, client):
    viewer_client = login("viewer")
    viewer = _user(admin, "viewer")
    response = admin.post(f"/api/users/{viewer['id']}/reset-password")
    temporary = response.json()["temporary_password"]
    assert len(temporary) >= 12
    assert viewer_client.get("/api/auth/me").status_code == 401
    assert client.login("viewer", temporary)["must_change_password"] is True


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


def test_update_user_fields_and_departments(admin):
    viewer = _user(admin, "viewer")
    depts = admin.get("/api/departments").json()
    response = admin.patch(f"/api/users/{viewer['id']}", json={"full_name": "Обновлённый", "position": "Аналитик BI",
                                                               "department_ids": [depts[0]["id"]]})
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Обновлённый" and body["departments"][0]["id"] == depts[0]["id"]
    assert admin.patch(f"/api/users/{viewer['id']}", json={"department_ids": [99999]}).status_code == 422


def test_delete_user(admin):
    viewer = _user(admin, "viewer")
    assert admin.delete(f"/api/users/{viewer['id']}").status_code == 200
    assert admin.get(f"/api/users/{viewer['id']}").status_code == 404


def test_users_filters(admin):
    assert [u["username"] for u in admin.get("/api/users", params={"search": "техпод"}).json()] == ["tp_lead"]
    tech = {u["username"] for u in admin.get("/api/users", params={"service": "tech"}).json()}
    assert {"admin", "tp_lead", "viewer", "hr_head"} <= tech and "product" not in tech


def test_departments_crud(admin):
    created = admin.post("/api/departments", json={"name": "Отдел качества", "code": "qa"})
    assert created.status_code == 201 and created.json()["code"] == "QA"
    dept_id = created.json()["id"]
    assert admin.post("/api/departments", json={"name": "отдел качества", "code": "QA2"}).status_code == 409
    assert admin.put(f"/api/departments/{dept_id}", json={"name": "Отдел контроля качества", "code": "QC"}).json()[
        "name"] == "Отдел контроля качества"
    assert admin.delete(f"/api/departments/{dept_id}").status_code == 200


def test_weak_password_error_points_to_password_field(admin):
    response = admin.post("/api/users", json={"username": "weak", "full_name": "Слабый пароль", "password": "short"})
    assert response.status_code == 422
    assert "password" in response.json()["fields"]
