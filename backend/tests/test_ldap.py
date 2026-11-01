"""Вход по учётной записи домена (ADR-0008): каталог ldap3 MOCK_SYNC через подменяемые фабрики
сервера и соединения. Привязка существующих учётных записей, создание при первом входе с профилем
по группам, отказы, недоступный каталог, экранирование фильтра, StartTLS, страница администратора."""
import ssl
import uuid
import warnings

import pytest
from sqlalchemy import select

with warnings.catch_warnings():  # ldap3 2.9 импортирует устаревшие имена pyasn1
    warnings.simplefilter("ignore", DeprecationWarning)
    import ldap3
    from ldap3.core.exceptions import LDAPSocketOpenError

from app.core.config import settings
from app.models import AuditEntry, User
from app.services import ldap_auth

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

GUID = uuid.UUID("83853056-a567-4f4f-9ec4-e7c706345c72")
BASE = "ou=staff,dc=test"
SVC_DN, SVC_PW = "cn=svc,dc=test", "svc-secret-value"
PASSWORD = "domain-pass-1"


class FakeDirectory:
    """Каталог в памяти: служебная запись и сотрудники с паролями; down — каталог не отвечает."""

    def __init__(self, monkeypatch):
        self.server = ldap3.Server("fake_ad", get_info=ldap3.OFFLINE_AD_2012_R2)
        self.seed = ldap3.Connection(self.server, user=SVC_DN, password=SVC_PW, client_strategy=ldap3.MOCK_SYNC)
        self.seed.strategy.add_entry(SVC_DN, {"objectClass": ["person"], "userPassword": SVC_PW,
                                              "sAMAccountName": "svc"})
        self.down = False
        self.connection_class = ldap3.Connection
        self.filters: list[str] = []
        monkeypatch.setattr(ldap_auth, "server_factory", lambda config: self.server)
        monkeypatch.setattr(ldap_auth, "connection_factory", self.connect)

    def connect(self, server, *, user, password, config):
        if self.down:
            return DownConnection()
        directory = self

        class Recording(self.connection_class):
            def search(self, search_base, search_filter, *args, **kwargs):
                directory.filters.append(search_filter)
                return super().search(search_base, search_filter, *args, **kwargs)

        return Recording(server, user=user, password=password, client_strategy=ldap3.MOCK_SYNC, read_only=True,
                         raise_exceptions=False)

    def add(self, login, *, email="", password=PASSWORD, name="Иванов Иван", guid=GUID, disabled=False, title="",
            groups=()):
        attrs = {"objectClass": ["person", "user"], "sAMAccountName": login, "userPassword": password,
                 "displayName": name, "objectGUID": guid.bytes_le, "userAccountControl": "514" if disabled else "512"}
        if email:
            attrs["mail"] = email
        if title:
            attrs["title"] = title
        if groups:
            attrs["memberOf"] = list(groups)
        dn = f"cn={login},{BASE}"
        self.seed.strategy.add_entry(dn, attrs)
        return dn


class DownConnection:
    def open(self):
        raise LDAPSocketOpenError("socket connection error while opening: [Errno 111] Connection refused")

    def unbind(self):
        return True


@pytest.fixture()
def directory(monkeypatch):
    values = {"auth_ldap_enabled": True, "auth_ldap_url": "ldap://dc.test", "auth_ldap_base_dn": BASE,
              "auth_ldap_bind_dn": SVC_DN, "auth_ldap_bind_password": SVC_PW,
              "auth_ldap_login_hint": "Логин и пароль домена TEST", "auth_ldap_create_users": "",
              "auth_ldap_group_profiles": "", "auth_ldap_default_profile": "", "auth_ldap_admin_group": "",
              "auth_ldap_start_tls": False, "auth_ldap_ca_file": ""}
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
    return FakeDirectory(monkeypatch)


def _login(client, username, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _user(db, username) -> User:
    db.expire_all()
    return db.scalar(select(User).where(User.username == username))


def _set(db, username, **fields):
    user = _user(db, username)
    for key, value in fields.items():
        setattr(user, key, value)
    db.commit()
    return user


# ---------------------------------------------------------------- страница входа

def test_login_config(client, directory, monkeypatch):
    assert client.get("/api/auth/config").json() == {"ldap": {"enabled": True, "hint": "Логин и пароль домена TEST"}}
    monkeypatch.setattr(settings, "auth_ldap_enabled", False)
    assert client.get("/api/auth/config").json() == {"ldap": {"enabled": False, "hint": ""}}


# ---------------------------------------------------------------- привязка существующих учётных записей

def test_existing_account_is_linked_by_email(client, db, directory):
    _set(db, "viewer", email="Viewer@Example.com", position=None)
    user_id = _user(db, "viewer").id
    directory.add("i.viewer", email="viewer@example.com", title="Аналитик BI")

    response = _login(client, "i.viewer")
    assert response.status_code == 200, response.text
    me = response.json()
    assert me["id"] == user_id and me["auth_source"] == "ldap" and me["has_password"] is False
    row = _user(db, "viewer")
    assert row.auth_external_id == str(GUID) and row.auth_linked_at is not None and row.password_hash is None
    assert row.full_name == "Пользователь (просмотр)"      # данные системы не перезаписываются
    assert row.position == "Аналитик BI"                    # пустое заполняется из каталога
    assert row.email == "Viewer@Example.com" and row.username == "viewer"
    link = db.scalars(select(AuditEntry).where(AuditEntry.action == "link")).all()
    assert len(link) == 1 and "по e-mail" in link[0].summary
    client.post("/api/auth/logout")
    # пароль системы больше не подходит (не проверяется), пароль домена — подходит
    assert _login(client, "viewer", "view1234").status_code == 401
    assert _login(client, "i.viewer").status_code == 200
    assert len(db.scalars(select(AuditEntry).where(AuditEntry.action == "link")).all()) == 1


def test_existing_position_is_kept(client, db, directory):
    _set(db, "viewer", email="viewer@example.com")
    directory.add("i.viewer", email="viewer@example.com", title="Другая должность")
    assert _login(client, "i.viewer").status_code == 200
    assert _user(db, "viewer").position == "Аналитик"


def test_link_by_ad_sync_id_and_by_directory_id(client, db, directory):
    _set(db, "hr_head", org_source="ad", external_id=str(GUID))
    directory.add("hr.head", email="someone-else@example.com")
    assert _login(client, "hr.head").json()["username"] == "hr_head"
    entry = db.scalars(select(AuditEntry).where(AuditEntry.action == "link")).one()
    assert entry.after["matched_by"] == "ad_sync"
    client.post("/api/auth/logout")
    # следующий вход — по записи каталога (auth_external_id), без новой привязки
    assert _login(client, "hr.head").json()["username"] == "hr_head"
    assert len(db.scalars(select(AuditEntry).where(AuditEntry.action == "link")).all()) == 1


def test_account_linked_to_other_entry_is_not_taken_over(client, db, directory):
    _set(db, "viewer", email="viewer@example.com", auth_source="ldap", auth_external_id=str(uuid.uuid4()),
         password_hash=None)
    directory.add("viewer2", email="viewer@example.com")
    response = _login(client, "viewer2")
    assert response.status_code == 403 and response.json()["code"] == "no_account"


def test_wrong_domain_password_falls_back_to_local_password(client, db, directory):
    directory.add("admin", email="someone@example.com", guid=uuid.uuid4())
    response = _login(client, "admin", "admin123")
    assert response.status_code == 200 and response.json()["auth_source"] == "local"
    assert _user(db, "admin").auth_source == "local"


# ---------------------------------------------------------------- отказы

def test_wrong_password_and_unknown_user(client, directory):
    directory.add("i.ivanov", email="ivanov@example.com")
    wrong = _login(client, "i.ivanov", "bad-password-1")
    unknown = _login(client, "nobody", PASSWORD)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Неверный логин или пароль", "code": "invalid_credentials"}


def test_wrong_domain_password_counts_for_rate_limit(client, directory, monkeypatch):
    from app.api.routers import auth

    monkeypatch.setattr(auth.login_limiter, "limit", 2)
    directory.add("i.ivanov", email="ivanov@example.com")
    for _ in range(2):
        _login(client, "i.ivanov", "bad-password-1")
    assert _login(client, "i.ivanov").status_code == 429


def test_unknown_employee_is_rejected_without_creation(client, db, directory):
    directory.add("p.petrov", email="petrov@example.com", name="Пётр Петров")
    response = _login(client, "p.petrov")
    assert response.status_code == 403
    assert response.json() == {"detail": "Учётной записи в системе нет — обратитесь к администратору",
                               "code": "no_account"}
    assert db.scalar(select(User).where(User.email == "petrov@example.com")) is None


def test_ambiguous_login_is_rejected(client, directory):
    directory.add("twin1", email="twin@example.com", guid=uuid.uuid4())
    directory.add("twin2", email="twin@example.com", guid=uuid.uuid4())
    assert _login(client, "twin@example.com").status_code == 401


def test_disabled_directory_account_does_not_log_in(client, db, directory):
    _set(db, "viewer", email="viewer@example.com")
    directory.add("i.viewer", email="viewer@example.com", disabled=True)
    assert _login(client, "i.viewer").status_code == 401
    assert _user(db, "viewer").auth_source == "local"


def test_disabled_system_account_does_not_log_in_through_domain(client, db, directory):
    _set(db, "viewer", email="viewer@example.com", is_active=False)
    directory.add("i.viewer", email="viewer@example.com")
    response = _login(client, "i.viewer")
    assert response.status_code == 403 and response.json()["code"] == "account_disabled"


def test_filter_escaping(client, db, directory):
    """Логин подставляется в фильтр экранированным: «*» и «*)(uid=*» не находят чужую запись."""
    directory.add("i.ivanov", email="ivanov@example.com")
    _set(db, "viewer", email="ivanov@example.com")
    for login in ("*", "*)(uid=*", "i.ivan*"):
        assert _login(client, login).status_code == 401, login
    assert "(sAMAccountName=\\2a\\29\\28uid=\\2a)" in directory.filters[1]
    assert "*" not in directory.filters[1].replace("(objectClass=person)", "")
    assert _login(client, "i.ivanov").status_code == 200


def test_empty_password_never_reaches_directory():
    config = ldap_auth.LdapConfig(url="ldap://dc.test", base_dn=BASE)
    assert ldap_auth.LdapDirectory(config).authenticate("i.ivanov", "") is None
    assert ldap_auth.LdapDirectory(config).authenticate("  ", PASSWORD) is None


# ---------------------------------------------------------------- каталог недоступен

def test_directory_down(client, db, directory):
    _set(db, "viewer", email="viewer@example.com")
    directory.add("viewer", email="viewer@example.com")
    assert _login(client, "viewer").status_code == 200          # привязана к каталогу
    client.post("/api/auth/logout")
    directory.down = True
    response = _login(client, "viewer")
    assert response.status_code == 503 and response.json() == {
        "detail": "Сервер домена не отвечает — попробуйте войти позже", "code": "directory_unavailable"}
    assert response.headers["retry-after"] == "5"
    # локальная учётная запись входит по паролю системы
    assert _login(client, "admin", "admin123").status_code == 200
    client.post("/api/auth/logout")
    assert _login(client, "admin", "wrong-pass-1").status_code == 401


def test_service_account_rejected_means_directory_unavailable(client, db, directory, monkeypatch):
    _set(db, "viewer", auth_source="ldap", password_hash=None, email="viewer@example.com")
    monkeypatch.setattr(settings, "auth_ldap_bind_password", "wrong-secret")
    response = _login(client, "viewer")
    assert response.status_code == 503 and response.json()["code"] == "directory_unavailable"


# ---------------------------------------------------------------- создание при первом входе

def test_first_login_creates_account_with_group_profile(client, db, directory, monkeypatch):
    monkeypatch.setattr(settings, "auth_ldap_create_users", "active")
    monkeypatch.setattr(settings, "auth_ldap_group_profiles",
                        "CN=Missing,DC=test=nope;CN=Heads,OU=Groups,DC=test=head;CN=Staff,DC=test=employee")
    monkeypatch.setattr(settings, "auth_ldap_default_profile", "specialist")
    monkeypatch.setattr(settings, "auth_ldap_admin_group", "CN=Dash Admins,DC=test")
    directory.add("s.sidorov", email="Sidorov@Example.com", name="Сидоров Семён", title="Руководитель группы",
                  groups=["cn=staff, dc=test", "cn=heads , ou=groups,dc=test", "CN=Missing,DC=test"])
    response = _login(client, "s.sidorov")
    assert response.status_code == 200, response.text
    me = response.json()
    assert me["username"] == "s.sidorov" and me["full_name"] == "Сидоров Семён" and me["email"] == "sidorov@example.com"
    # первое совпадение по порядку настройки; неизвестный профиль пропускается
    assert me["profile"]["key"] == "head" and me["role"] == "user" and me["auth_source"] == "ldap"
    assert me["position"] == "Руководитель группы" and me["effective_access"]["profile_key"] == "head"
    created = db.scalars(select(AuditEntry).where(AuditEntry.action == "create")).one()
    assert "первый вход по домену" in created.summary and created.after["profile"] == "head"


def test_first_login_default_profile_and_admin_group(client, db, directory, monkeypatch):
    monkeypatch.setattr(settings, "auth_ldap_create_users", "active")
    monkeypatch.setattr(settings, "auth_ldap_group_profiles", "CN=Heads,OU=Groups,DC=test=head")
    monkeypatch.setattr(settings, "auth_ldap_default_profile", "specialist")
    monkeypatch.setattr(settings, "auth_ldap_admin_group", "CN=Dash Admins,DC=test")
    directory.add("boss", email="boss@example.com", guid=uuid.uuid4(), groups=["cn=dash admins,dc=test"])
    directory.add("viewer", email="new-viewer@example.com", guid=uuid.uuid4())   # логин занят в системе
    boss = _login(client, "boss").json()
    assert boss["role"] == "admin" and boss["profile"]["key"] == "specialist"
    client.post("/api/auth/logout")
    second = _login(client, "viewer").json()
    assert second["username"] == "viewer2" and second["profile"]["key"] == "specialist"
    # группа администраторов действует только при создании
    _set(db, "viewer2", role="user")
    client.post("/api/auth/logout")
    assert _login(client, "viewer").json()["role"] == "user"


def test_first_login_inactive_mode(client, db, directory, monkeypatch):
    monkeypatch.setattr(settings, "auth_ldap_create_users", "inactive")
    directory.add("p.petrov", email="petrov@example.com", name="Пётр Петров")
    response = _login(client, "p.petrov")
    assert response.status_code == 403 and response.json()["code"] == "account_disabled"
    created = _user(db, "p.petrov")
    assert created is not None and not created.is_active and created.auth_source == "ldap"
    assert created.access_profile_id is None
    _set(db, "p.petrov", is_active=True)
    assert _login(client, "petrov@example.com").status_code == 200


def test_no_creation_without_email(client, directory, monkeypatch):
    monkeypatch.setattr(settings, "auth_ldap_create_users", "active")
    directory.add("noemail")
    assert _login(client, "noemail").json()["code"] == "no_account"


# ---------------------------------------------------------------- пароль доменной учётной записи

def test_domain_user_cannot_change_password_in_system(client, db, directory):
    _set(db, "viewer", email="viewer@example.com")
    directory.add("i.viewer", email="viewer@example.com")
    _login(client, "i.viewer")
    response = client.post("/api/auth/change-password", json={"current_password": PASSWORD,
                                                              "new_password": "New-pass-2026"},
                           headers={"X-CSRF-Token": client.cookies.get("ds_csrf")})
    assert response.status_code == 409 and response.json()["code"] == "directory_password"


# ---------------------------------------------------------------- StartTLS и TLS

def test_start_tls_before_bind(client, db, directory, monkeypatch):
    events: list[str] = []

    class Spy(ldap3.Connection):
        def start_tls(self, read_server_info=True):
            events.append("start_tls")
            return True

        def bind(self, *args, **kwargs):
            events.append("bind")
            return super().bind(*args, **kwargs)

    directory.connection_class = Spy
    monkeypatch.setattr(settings, "auth_ldap_start_tls", True)
    _set(db, "viewer", email="viewer@example.com")
    directory.add("i.viewer", email="viewer@example.com")
    assert _login(client, "i.viewer").status_code == 200
    # служебная привязка и привязка сотрудника — каждая после StartTLS
    assert events == ["start_tls", "bind", "start_tls", "bind"]


def test_start_tls_failure_is_directory_unavailable(directory, monkeypatch):
    monkeypatch.setattr(settings, "auth_ldap_start_tls", True)   # MOCK_SYNC отвечает на StartTLS отказом
    directory.add("i.ivanov", email="ivanov@example.com")
    with pytest.raises(ldap_auth.DirectoryUnavailable):
        ldap_auth.directory_for(ldap_auth.current_config()).authenticate("i.ivanov", PASSWORD)


def test_default_server_tls():
    ldaps = ldap_auth.default_server(ldap_auth.LdapConfig(url="ldaps://dc.test:636", base_dn=BASE))
    assert ldaps.ssl and ldaps.tls.validate == ssl.CERT_REQUIRED
    start = ldap_auth.default_server(ldap_auth.LdapConfig(url="ldap://dc.test", base_dn=BASE, start_tls=True))
    assert not start.ssl and start.tls.validate == ssl.CERT_REQUIRED
    assert ldap_auth.LdapConfig(url="ldap://dc.test", base_dn=BASE).tls_mode == "none"
    assert ldap_auth.LdapConfig(url="ldap://dc.test", base_dn=BASE, ca_file="/etc/ca.pem").tls_mode == "starttls"
    assert ldap_auth.LdapConfig(url="ldaps://dc.test", base_dn=BASE, start_tls=True).tls_mode == "ldaps"


def test_parse_group_profiles_and_match():
    pairs = ldap_auth.parse_group_profiles("CN=A,OU=G,DC=t=head; broken ;\nCN=B,DC=t = employee;=x")
    assert pairs == (("CN=A,OU=G,DC=t", "head"), ("CN=B,DC=t", "employee"))
    config = ldap_auth.LdapConfig(url="ldap://x", base_dn=BASE, group_profiles=pairs, default_profile="specialist",
                                  admin_group="CN=Adm,DC=t")
    assert config.profile_for(["cn=b, dc=t", "CN=A ,OU=G,DC=T"]) == "head"
    assert config.profile_for(["cn=b,dc=t"], known={"specialist"}) == "specialist"
    assert config.profile_for([], known=set()) is None
    assert config.is_admin_member(["cn=adm,dc=t"]) and not config.is_admin_member(["cn=a,ou=g,dc=t"])


# ---------------------------------------------------------------- страница администратора

def test_ldap_status_without_secrets(admin, login, directory, monkeypatch):
    monkeypatch.setattr(settings, "auth_ldap_group_profiles", "CN=Heads,DC=test=head;CN=X,DC=test=nope")
    response = admin.get("/api/system/ldap")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] and data["configured"] and data["ldap3_available"] and data["ldap3_version"]
    assert data["config"]["url"] == "ldap://dc.test" and data["config"]["bind_password_set"] is True
    assert data["config"]["tls"] == "none" and data["config"]["group_profiles"][0] == {"group": "CN=Heads,DC=test",
                                                                                       "profile": "head"}
    assert SVC_PW not in response.text
    assert any("«nope»" in p for p in data["problems"]) and any("без шифрования" in p for p in data["problems"])
    assert login("hr_head").get("/api/system/ldap").status_code == 403
    monkeypatch.setattr(settings, "auth_ldap_enabled", False)
    monkeypatch.setattr(settings, "auth_ldap_url", "")
    off = admin.get("/api/system/ldap").json()
    assert off["enabled"] is False and off["configured"] is False and off["config"] is None


def test_ldap_test_endpoint(admin, db, login, directory, monkeypatch):
    connected = admin.post("/api/system/ldap/test", json={})
    assert connected.status_code == 200
    assert connected.json() == {"ok": True, "message": "Подключение установлено, служебная учётная запись принята",
                                "login": None, "entries": None}
    assert admin.post("/api/system/ldap/test").json()["ok"] is True

    _set(db, "viewer", email="viewer@example.com")
    directory.add("i.viewer", email="viewer@example.com", groups=["CN=Heads,DC=test"])
    found = admin.post("/api/system/ldap/test", json={"login": "i.viewer"}).json()
    assert found["ok"] and found["entries"][0]["account"]["username"] == "viewer"
    assert found["entries"][0]["account"]["matched_by"] == "email" and found["entries"][0]["guid"] == str(GUID)
    assert found["message"] == "Запись найдена и сопоставлена с пользователем viewer"
    # проверка ничего не меняет
    assert _user(db, "viewer").auth_source == "local"

    monkeypatch.setattr(settings, "auth_ldap_create_users", "active")
    monkeypatch.setattr(settings, "auth_ldap_group_profiles", "CN=Heads,DC=test=head")
    directory.add("newbie", email="newbie@example.com", guid=uuid.uuid4(), groups=["CN=Heads,DC=test"])
    new = admin.post("/api/system/ldap/test", json={"login": "newbie"}).json()
    assert new["entries"][0]["would_create"] and new["entries"][0]["profile"] == "head"
    assert admin.post("/api/system/ldap/test", json={"login": "ghost"}).json()["message"] == \
        "Запись с таким логином в каталоге не найдена"
    # пароль сотрудника не принимается и не проверяется
    assert admin.post("/api/system/ldap/test", json={"login": "i.viewer", "password": "x"}).status_code == 422

    directory.down = True
    down = admin.post("/api/system/ldap/test", json={"login": "i.viewer"}).json()
    assert down["ok"] is False and down["message"].startswith("Каталог недоступен")
    assert login("viewer", "view1234").post("/api/system/ldap/test", json={}).status_code == 403


def test_ldap_test_when_not_configured(admin, monkeypatch):
    monkeypatch.setattr(settings, "auth_ldap_url", "")
    data = admin.post("/api/system/ldap/test", json={}).json()
    assert data["ok"] is False and "не настроен" in data["message"]
