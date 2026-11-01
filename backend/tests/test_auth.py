"""Вход, сессии, CSRF, смена пароля."""
from app.core.config import settings


def test_login_sets_httponly_session_and_readable_csrf(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "admin" and body["role"] == "admin"
    assert body["csrf_token"]
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith(f"{settings.session_cookie_name}="))
    csrf_cookie = next(c for c in cookies if c.startswith(f"{settings.csrf_cookie_name}="))
    assert "HttpOnly" in session_cookie and "samesite=lax" in session_cookie.lower()
    assert "HttpOnly" not in csrf_cookie


def test_login_is_case_insensitive_for_username(client):
    assert client.post("/api/auth/login", json={"username": "ADMIN", "password": "admin123"}).status_code == 200


def test_wrong_password_and_unknown_user_look_the_same(client):
    a = client.post("/api/auth/login", json={"username": "admin", "password": "nope-nope"})
    b = client.post("/api/auth/login", json={"username": "ghost", "password": "nope-nope"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json() == {"detail": "Неверный логин или пароль", "code": "invalid_credentials"}


def test_login_rate_limit(client, monkeypatch):
    from app.api.routers import auth

    monkeypatch.setattr(auth.login_limiter, "limit", 3)
    for _ in range(3):
        client.post("/api/auth/login", json={"username": "viewer", "password": "wrong-pass1"})
    blocked = client.post("/api/auth/login", json={"username": "viewer", "password": "view1234"})
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "too_many_requests"


def test_me_requires_session(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_unsafe_methods_require_csrf_header(admin):
    response = admin.post("/api/hr/months", json={"year": 2030, "month": 1}, headers={"X-CSRF-Token": "forged"})
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    assert admin.post("/api/hr/months", json={"year": 2030, "month": 1}).status_code == 201


def test_logout_invalidates_session(admin):
    assert admin.post("/api/auth/logout").status_code == 200
    assert admin.get("/api/auth/me").status_code == 401


def test_disabled_user_cannot_login(admin, client):
    user = next(u for u in admin.get("/api/users").json()["items"] if u["username"] == "viewer")
    admin.patch(f"/api/users/{user['id']}", json={"is_active": False})
    response = client.post("/api/auth/login", json={"username": "viewer", "password": "view1234"})
    assert response.status_code == 403
    assert response.json()["code"] == "account_disabled"


def test_disabling_user_ends_their_sessions(admin, login):
    viewer = login("viewer")
    user_id = viewer.get("/api/auth/me").json()["id"]
    admin.patch(f"/api/users/{user_id}", json={"is_active": False})
    assert viewer.get("/api/auth/me").status_code == 401


def test_temporary_password_must_be_changed_before_working(admin, client):
    created = admin.post("/api/users", json={"username": "newbie", "full_name": "Новый сотрудник",
                                             "access": [{"service_key": "hr", "level": "viewer"}]}).json()
    temporary = created["temporary_password"]
    assert temporary and created["user"]["must_change_password"]
    me = client.login("newbie", temporary)
    assert me["must_change_password"] is True
    blocked = client.get("/api/hr/months")
    assert blocked.status_code == 403 and blocked.json()["code"] == "password_change_required"
    changed = client.post("/api/auth/change-password",
                          json={"current_password": temporary, "new_password": "Spring2026!"})
    assert changed.status_code == 200
    assert client.get("/api/hr/months").status_code == 200


def test_password_policy(admin):
    def change(new):
        return admin.post("/api/auth/change-password", json={"current_password": "admin123", "new_password": new})

    assert change("short1").status_code == 422
    assert change("onlyletters").status_code == 422
    assert change("12345678901").status_code == 422
    assert change("admin123").json()["detail"] == "Новый пароль совпадает с текущим"
    wrong = admin.post("/api/auth/change-password", json={"current_password": "bad", "new_password": "Good-pass-1"})
    assert wrong.status_code == 422 and "current_password" in wrong.json()["fields"]
    assert change("Good-pass-1").status_code == 200


def test_change_password_closes_other_sessions(login):
    first = login("viewer")
    second = login("viewer")
    response = first.post("/api/auth/change-password",
                          json={"current_password": "view1234", "new_password": "New-pass-2026"})
    assert "завершено других сессий: 1" in response.json()["message"]
    assert second.get("/api/auth/me").status_code == 401
    assert first.get("/api/auth/me").status_code == 200


def test_sessions_list_and_revoke(login):
    a = login("viewer")
    b = login("viewer")
    sessions = a.get("/api/auth/sessions").json()
    assert len(sessions) == 2
    current = next(s for s in sessions if s["current"])
    other = next(s for s in sessions if not s["current"])
    assert a.delete(f"/api/auth/sessions/{current['id']}").status_code == 422
    assert a.delete(f"/api/auth/sessions/{other['id']}").status_code == 200
    assert b.get("/api/auth/me").status_code == 401


def test_profile_update(admin):
    response = admin.put("/api/auth/profile", json={"full_name": "  Иван Петров  ", "email": "IVAN@example.com",
                                                    "phone": "+7 900 000-00-00"})
    assert response.status_code == 200
    me = response.json()
    assert me["full_name"] == "Иван Петров" and me["email"] == "IVAN@example.com"
    assert admin.put("/api/auth/profile", json={"full_name": " "}).status_code == 422
    assert admin.put("/api/auth/profile", json={"avatar": "javascript:alert(1)"}).status_code == 422


def test_expired_session_is_rejected(admin, db):
    from datetime import timedelta

    from app.models import UserSession

    for s in db.query(UserSession).all():
        s.expires_at = s.expires_at - timedelta(days=30)
    db.commit()
    assert admin.get("/api/auth/me").status_code == 401


def test_login_by_email_for_local_account(admin, client):
    admin.put("/api/auth/profile", json={"email": "Boss@Example.com"})
    response = client.post("/api/auth/login", json={"username": "boss@example.com", "password": "admin123"})
    assert response.status_code == 200 and response.json()["username"] == "admin"


def test_login_config_without_domain(client):
    assert client.get("/api/auth/config").json() == {"ldap": {"enabled": False, "hint": ""}}


def test_me_includes_access_and_account(admin):
    me = admin.get("/api/auth/me").json()
    assert me["effective_access"]["is_admin"] and me["effective_access"]["can_export"]
    assert me["auth_source"] == "local" and me["has_password"] and me["status"] == "active"
    assert me["capabilities"] == [] and me["department"] is None and me["profile"] is None
    assert me["csrf_token"]


def test_user_without_password_cannot_login(admin, client):
    admin.post("/api/users", json={"username": "nopass", "full_name": "Без пароля", "access_method": "none"})
    response = client.post("/api/auth/login", json={"username": "nopass", "password": "anything-1"})
    assert response.status_code == 401 and response.json()["code"] == "invalid_credentials"
