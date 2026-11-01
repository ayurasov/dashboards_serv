"""Синхронизация с Active Directory: настройка, TLS, чтение каталога (ldap3 MOCK_SYNC), план и применение,
команда python -m app.cli org-sync. Сеть не используется: каталог — офлайн-макет ldap3."""
from __future__ import annotations

import json
import uuid

import ldap3
import pytest
from ldap3 import MOCK_SYNC, OFFLINE_AD_2012_R2, Connection, Server
from sqlalchemy import select

from app import cli
from app.core.config import Settings, settings
from app.models import AuditEntry, Department, DepartmentHead, User
from app.services import ad_sync
from app.services.ad_sync import AdConfig

from .test_org_api import _set, _units, _users

BASE = "DC=example,DC=local"
SALES = f"OU=Продажи,OU=АЛМИ Партнер,{BASE}"
BOSS_DN = f"CN=Сидоров Пётр,{SALES}"
GUIDS = {name: uuid.uuid4() for name in ("boss", "seller", "disabled", "tp_lead", "escaped")}
PATH = {"company": "АЛМИ Партнер", "division": "Коммерческая дирекция", "department": "Отдел продаж"}


def _entry(key: str, dn: str, mail: str, name: str, login: str, *, manager: str | None = None, uac: int = 512,
           **attrs) -> tuple[str, dict]:
    values = {"mail": mail, "displayName": name, "sAMAccountName": login, "userAccountControl": uac,
              "objectGUID": GUIDS[key].bytes_le, "title": attrs.pop("title", "Менеджер"), **attrs}
    if manager:
        values["manager"] = manager
    return dn, values


def _people(**overrides) -> list[tuple[str, dict]]:
    people = {
        "boss": _entry("boss", BOSS_DN, "boss@corp.example", "Сидоров Пётр", "psidorov",
                       title="Начальник отдела продаж", **PATH),
        "seller": _entry("seller", f"CN=Орлова Анна,{SALES}", "seller@corp.example", "Орлова Анна", "aorlova",
                         manager=BOSS_DN, **PATH),
        "disabled": _entry("disabled", f"CN=Уволен Иван,{SALES}", "fired@corp.example", "Уволенный Иван",
                           "ifired", manager=BOSS_DN, uac=514, **PATH),
        "tp_lead": _entry("tp_lead", f"CN=Руководитель ТП,OU=ТС,{BASE}", "tp.lead@corp.example",
                          "Руководитель техподдержки", "tplead", title="Руководитель группы", company="АЛМИ Партнер",
                          division="Техническая дирекция", department="Техническая служба"),
    }
    for key, value in overrides.items():
        if value is None:
            people.pop(key, None)
        else:
            people[key] = value
    return list(people.values())


def directory(entries: list[tuple[str, dict]]) -> Connection:
    """Офлайн-каталог AD: схема Windows 2012 R2, служебная учётная запись и сотрудники."""
    server = Server("fake", get_info=OFFLINE_AD_2012_R2)
    conn = Connection(server, user=f"CN=svc,{BASE}", password="secret", client_strategy=MOCK_SYNC)
    conn.strategy.add_entry(f"CN=svc,{BASE}", {"userPassword": "secret", "sAMAccountName": "svc"})
    for dn, attrs in entries:
        conn.strategy.add_entry(dn, {"objectClass": ["top", "person", "organizationalPerson", "user"],
                                     "objectCategory": "person", **attrs})
    assert conn.bind()
    return conn


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setattr(settings, "ad_sync_url", "ldaps://dc.example.local")
    monkeypatch.setattr(settings, "ad_sync_base_dn", BASE)
    monkeypatch.setattr(settings, "ad_sync_bind_dn", f"CN=svc,{BASE}")
    monkeypatch.setattr(settings, "ad_sync_bind_password", "secret")
    state = {"entries": _people()}
    monkeypatch.setattr(ad_sync, "connect", lambda config: directory(state["entries"]))
    return state


@pytest.fixture()
def tp_lead_email(db):
    _set(db, "tp_lead", email="tp.lead@corp.example")


def _sync(client, **options):
    return client.post("/api/org/sync/ad", json=options)


# ================================================================ настройка

def test_config_falls_back_to_login_settings():
    s = Settings(auth_ldap_url="ldap://dc.example.local", auth_ldap_base_dn=BASE, auth_ldap_bind_dn="CN=login",
                 auth_ldap_bind_password="p1", auth_ldap_ca_file="/etc/ssl/ca.pem", auth_ldap_start_tls=True)
    config = AdConfig.from_settings(s)
    assert (config.url, config.base_dn, config.bind_dn, config.bind_password) == \
        ("ldap://dc.example.local", BASE, "CN=login", "p1")
    assert config.ca_file == "/etc/ssl/ca.pem" and config.use_start_tls
    own = AdConfig.from_settings(Settings(
        ad_sync_url="ldaps://ad.example.local", ad_sync_base_dn="OU=Staff," + BASE, ad_sync_bind_dn="CN=sync",
        ad_sync_bind_password="p2", auth_ldap_url="ldap://login", auth_ldap_bind_dn="CN=login",
        auth_ldap_bind_password="p1", auth_ldap_start_tls=True, ad_sync_path_source="ou",
        ad_sync_path_attributes="company, department", ad_sync_detect_heads=False))
    assert (own.url, own.bind_dn, own.bind_password) == ("ldaps://ad.example.local", "CN=sync", "p2")
    assert not own.start_tls and not own.use_start_tls, "StartTLS входа не переносится на свой адрес"
    assert own.path_source == "ou" and own.path_attributes == ("company", "department") and not own.detect_heads
    # служебная учётная запись — парой: пароль входа не подставляется к своему DN синхронизации
    pair = AdConfig.from_settings(Settings(auth_ldap_url="ldap://x", auth_ldap_base_dn=BASE, ad_sync_bind_dn="CN=s",
                                           auth_ldap_bind_password="login-secret"))
    assert pair.bind_password == ""
    assert AdConfig.from_settings(Settings(auth_ldap_url="ldap://x")) is None


def test_describe_has_no_secrets():
    config = AdConfig(url="ldap://dc", base_dn=BASE, bind_dn="CN=svc", bind_password="top-secret", ca_file="/ca")
    described = config.describe()
    assert "top-secret" not in json.dumps(described) and "bind_password" not in described
    assert described["start_tls"] is True and "top-secret" not in repr(config)


@pytest.fixture()
def ca_file(tmp_path) -> str:
    path = tmp_path / "ca.pem"
    path.write_text("-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n")
    return str(path)


@pytest.mark.parametrize(("url", "start_tls", "with_ca", "tls", "auto_bind"), [
    ("ldap://dc", False, True, True, ldap3.AUTO_BIND_TLS_BEFORE_BIND),   # в todo-planner StartTLS не было
    ("ldap://dc", True, False, True, ldap3.AUTO_BIND_TLS_BEFORE_BIND),
    ("ldap://dc", False, False, False, ldap3.AUTO_BIND_NO_TLS),
    ("ldaps://dc", True, True, True, ldap3.AUTO_BIND_NO_TLS),
])
def test_connection_options(url, start_tls, with_ca, tls, auto_bind, ca_file):
    config = AdConfig(url=url, base_dn=BASE, start_tls=start_tls, ca_file=ca_file if with_ca else "")
    options = ad_sync.connection_options(config)
    assert (options["tls"] is not None) == tls and options["auto_bind"] == auto_bind
    if with_ca:
        assert options["tls"].ca_certs_file == ca_file


def test_connect_uses_start_tls_and_reports_failures(monkeypatch, ca_file):
    captured = {}

    def fake_connection(server, **kwargs):
        captured.update(kwargs, server=server)
        return "connection"

    monkeypatch.setattr(ldap3, "Connection", fake_connection)
    config = AdConfig(url="ldap://dc.example.local", base_dn=BASE, bind_dn="CN=svc", bind_password="x",
                      ca_file=ca_file)
    assert ad_sync.connect(config) == "connection"
    assert captured["auto_bind"] == ldap3.AUTO_BIND_TLS_BEFORE_BIND and captured["read_only"]
    assert captured["user"] == "CN=svc" and captured["server"].tls is not None

    def refuse(server, **kwargs):
        raise ldap3.core.exceptions.LDAPSocketOpenError("connection refused")

    monkeypatch.setattr(ldap3, "Connection", refuse)
    with pytest.raises(ad_sync.AdSyncError) as error:
        ad_sync.connect(config)
    assert error.value.status_code == 503 and "LDAPSocketOpenError" in error.value.detail
    with pytest.raises(ad_sync.AdSyncError) as error:
        ad_sync.connect(AdConfig(url="ldaps://dc", base_dn=BASE, ca_file="/nonexistent/ca.pem"))
    assert "CA-сертификат" in error.value.detail


# ================================================================ чтение и преобразование

def test_split_dn_with_escapes():
    assert ad_sync.split_dn(r"CN=Иванов\, Иван,OU=Отдел продаж,DC=example,DC=local") == \
        ["CN=Иванов, Иван", "OU=Отдел продаж", "DC=example", "DC=local"]
    assert ad_sync.split_dn(r"CN=A\2CB,OU=R\26D\, QA,DC=x") == ["CN=A,B", "OU=R&D, QA", "DC=x"]
    assert ad_sync.split_dn(r"OU=\D0\9E\D1\82\D0\B4\D0\B5\D0\BB,DC=x") == ["OU=Отдел", "DC=x"]
    assert ad_sync.path_from_ou(r"CN=Иванов\, Иван,OU=Группа,OU=Отдел\, продажи,OU=Компания," + BASE, BASE) == \
        ["Компания", "Отдел, продажи", "Группа"]


def test_fetch_entries_from_mock_directory():
    config = AdConfig(url="ldaps://fake", base_dn=BASE)
    entries = ad_sync.fetch_entries(config, connection=directory(_people()))
    assert len(entries) == 4, "служебная запись без mail в выборку не попадает"
    rows, refs = ad_sync.entries_to_rows(entries, config)
    by_email = {r.email: r for r in rows}
    boss, seller, fired = by_email["boss@corp.example"], by_email["seller@corp.example"], \
        by_email["fired@corp.example"]
    assert boss.external_id == str(GUIDS["boss"]) and boss.login == "psidorov" and boss.name == "Сидоров Пётр"
    assert boss.department == ["АЛМИ Партнер", "Коммерческая дирекция", "Отдел продаж"]
    assert boss.position == "Начальник отдела продаж" and boss.is_head and not seller.is_head
    assert seller.manager_ref == BOSS_DN.lower() and refs[BOSS_DN.lower()] == str(GUIDS["boss"])
    assert fired.disabled and not seller.disabled
    assert not by_email["tp.lead@corp.example"].is_head, "подчинённых в своём подразделении нет"
    ou_rows, _ = ad_sync.entries_to_rows(entries, AdConfig(url="ldaps://fake", base_dn=BASE, path_source="ou"))
    assert next(r for r in ou_rows if r.email == "boss@corp.example").department == ["АЛМИ Партнер", "Продажи"]
    quiet, _ = ad_sync.entries_to_rows(entries, AdConfig(url="ldaps://fake", base_dn=BASE, detect_heads=False))
    assert not any(r.is_head for r in quiet)


def test_head_detection_rules():
    from app.services.org_import import Row

    rows = [Row(1, external_id="a", department=["X"]), Row(2, external_id="b", department=["X"], manager_ref="dn-a"),
            Row(3, external_id="c", department=["X", "Y"], manager_ref="dn-b"),
            Row(4, external_id="d", department=["X", "Y"], manager_ref="dn-c")]
    ad_sync.mark_heads(rows, {"dn-a": "a", "dn-b": "b", "dn-c": "c"})
    assert [r.is_head for r in rows] == [True, False, True, False]


def test_guid_from_text_when_no_raw_value():
    assert ad_sync.guid({}, {"objectguid": "{ABC-1}"}) == "abc-1"
    assert ad_sync.first([b"\xd0\x90"]) == "А" and ad_sync.first(None) == "" and ad_sync.uac_disabled("x") is False


def test_search_failure_is_reported():
    class Broken:
        class extend:  # noqa: N801
            class standard:  # noqa: N801
                @staticmethod
                def paged_search(*a, **k):
                    raise ldap3.core.exceptions.LDAPSessionTerminatedByServerError("bye")

        def unbind(self):
            raise RuntimeError("уже закрыто")

    with pytest.raises(ad_sync.AdSyncError):
        ad_sync.fetch_entries(AdConfig(url="ldap://x", base_dn=BASE), connection=Broken())


# ================================================================ API

def test_status_endpoint(admin, login, monkeypatch):
    body = admin.get("/api/org/sync/ad").json()
    assert body == {"configured": False, "ldap3_available": True, "config": None}
    monkeypatch.setattr(settings, "auth_ldap_url", "ldap://dc.example.local")
    monkeypatch.setattr(settings, "auth_ldap_base_dn", BASE)
    monkeypatch.setattr(settings, "auth_ldap_bind_password", "very-secret")
    body = admin.get("/api/org/sync/ad")
    assert body.json()["configured"] and body.json()["config"]["url"] == "ldap://dc.example.local"
    assert "very-secret" not in body.text
    assert login("viewer").get("/api/org/sync/ad").status_code == 403


def test_sync_not_configured_or_unavailable(admin, monkeypatch):
    response = _sync(admin)
    assert response.status_code == 409 and response.json()["code"] == "ad_not_configured"
    monkeypatch.setattr(settings, "ad_sync_url", "ldap://dc.example.local")
    monkeypatch.setattr(settings, "ad_sync_base_dn", BASE)

    def down(config):
        raise ad_sync.AdSyncError("Не удалось подключиться к каталогу (LDAPSocketOpenError)")

    monkeypatch.setattr(ad_sync, "connect", down)
    response = _sync(admin)
    assert response.status_code == 503 and response.json()["code"] == "ad_unavailable"
    assert response.headers["retry-after"] == "5"


def test_sync_plan_and_apply(db, admin, configured, tp_lead_email):
    ids, units = _users(db), _units(db)
    plan = _sync(admin).json()
    assert not plan["can_apply"] and plan["summary"]["errors"] == 3, "без «Создавать новых» новые — ошибки"
    plan = _sync(admin, create_missing=True).json()
    assert plan["can_apply"], plan["users"]
    assert plan["source"] == "ad" and plan["summary"]["create_users"] == 3 and plan["summary"]["update_users"] == 1
    assert [d["path"] for d in plan["departments"]] == ["АЛМИ Партнер / Коммерческая дирекция / Отдел продаж"]
    lead = next(u for u in plan["users"] if u["email"] == "tp.lead@corp.example")
    assert lead["user_id"] == ids["tp_lead"] and {c["field"] for c in lead["changes"]} == {"external_id"}
    result = _sync(admin, create_missing=True, apply=True).json()
    assert result["applied"]
    users = {u.email: u for u in db.scalars(select(User))}
    boss, seller, fired = users["boss@corp.example"], users["seller@corp.example"], users["fired@corp.example"]
    assert (boss.org_source, boss.auth_source, boss.password_hash) == ("ad", "ldap", None)
    assert boss.external_id == str(GUIDS["boss"]) and boss.username == "psidorov"
    assert fired.is_active is False and seller.is_active is True
    sales = db.scalar(select(Department).where(Department.name == "Отдел продаж"))
    assert sales.parent_id == units["COMMDIR"] and sales.org_source == "ad"
    head = db.scalar(select(DepartmentHead).where(DepartmentHead.department_id == sales.id))
    assert head.user_id == boss.id and head.is_primary
    assert seller.manager_id is None, "руководитель из AD совпал со структурным"
    db.expire_all()
    lead_user = db.get(User, ids["tp_lead"])
    assert lead_user.org_source == "ad" and lead_user.external_id == str(GUIDS["tp_lead"])
    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "org_import", AuditEntry.action == "ad"))
    assert entry.after["create_users"] == 3
    # повторная синхронизация — без изменений
    assert _sync(admin, create_missing=True).json()["summary"]["unchanged"] == 4


def test_sync_deactivates_only_ad_users_and_never_reactivates(db, admin, configured, tp_lead_email):
    _sync(admin, create_missing=True, apply=True)
    ids = _users(db)
    _set(db, "admin", org_source="ad")   # себя синхронизация не отключает
    configured["entries"] = _people(seller=None, disabled=_entry(
        "disabled", f"CN=Уволен Иван,{SALES}", "fired@corp.example", "Уволенный Иван", "ifired", manager=BOSS_DN,
        **PATH))
    plan = _sync(admin, deactivate_missing=True).json()
    assert [d["email"] for d in plan["deactivate"]] == ["seller@corp.example"]
    fired = next(u for u in plan["users"] if u["email"] == "fired@corp.example")
    assert fired["action"] == "unchanged", "включённый в AD не включается в системе"
    assert _sync(admin, deactivate_missing=True, apply=True).json()["applied"]
    db.expire_all()
    users = {u.email: u for u in db.scalars(select(User))}
    assert users["seller@corp.example"].is_active is False and users["fired@corp.example"].is_active is False
    assert db.get(User, ids["viewer"]).is_active and db.get(User, ids["admin"]).is_active
    assert _sync(admin).json()["deactivate"] == [], "без deactivate_missing никого не отключает"


def test_disabled_in_ad_local_user_is_not_deactivated(db, admin, configured, tp_lead_email):
    lead = _entry("tp_lead", f"CN=Руководитель ТП,OU=ТС,{BASE}", "tp.lead@corp.example", "Руководитель техподдержки",
                  "tplead", uac=514, company="АЛМИ Партнер", division="Техническая дирекция",
                  department="Техническая служба")
    configured["entries"] = [lead]
    plan = _sync(admin).json()
    user = plan["users"][0]
    assert user["action"] in ("update", "unchanged") and "не отключается" in user["warnings"][0]
    _sync(admin, apply=True)
    db.expire_all()
    lead_user = db.get(User, _users(db)["tp_lead"])
    assert lead_user.is_active and lead_user.org_source is None


def test_sync_without_department_keeps_current(db, admin, configured, tp_lead_email):
    lead = _entry("tp_lead", f"CN=Руководитель ТП,{BASE}", "tp.lead@corp.example", "Руководитель техподдержки",
                  "tplead")
    configured["entries"] = [lead]
    plan = _sync(admin).json()
    assert plan["can_apply"] and "не указано подразделение" in plan["users"][0]["warnings"][0]
    _sync(admin, apply=True)
    db.expire_all()
    assert db.get(User, _users(db)["tp_lead"]).department_id == _units(db)["TECH"]


def test_manager_outside_sync_scope_keeps_explicit_manager(db, admin, configured, tp_lead_email):
    _set(db, "tp_lead", manager_id=_users(db)["product"])
    lead = _entry("tp_lead", f"CN=Руководитель ТП,OU=ТС,{BASE}", "tp.lead@corp.example", "Руководитель техподдержки",
                  "tplead", title="Руководитель группы", manager=f"CN=Вне выборки,OU=Другое,{BASE}",
                  company="АЛМИ Партнер", division="Техническая дирекция", department="Техническая служба")
    configured["entries"] = [lead]
    plan = _sync(admin).json()
    user = plan["users"][0]
    assert "не входит в выборку" in user["warnings"][0] and "manager" not in {c["field"] for c in user["changes"]}


def test_sync_needs_org_manage(login, configured):
    assert _sync(login("viewer")).status_code == 403


# ================================================================ команда org-sync

def test_cli_org_sync(db, configured, tp_lead_email, capsys):
    assert cli.main(["org-sync", "--ad"]) == 1
    out = capsys.readouterr()
    assert "ошибок: 3" in out.out and "строка" in out.out and "ошибки" in out.err
    assert cli.main(["org-sync", "--ad", "--create-missing", "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["can_apply"] and not plan["applied"]
    assert db.scalar(select(User).where(User.email == "boss@corp.example")) is None, "план ничего не пишет"
    assert cli.main(["org-sync", "--ad", "--create-missing", "--apply", "--actor", "admin"]) == 0
    assert "применены" in capsys.readouterr().out
    boss = db.scalar(select(User).where(User.email == "boss@corp.example"))
    assert boss is not None and boss.org_source == "ad"
    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "org_import"))
    assert entry.username == "admin"
    assert cli.main(["org-sync", "--ad", "--actor", "nobody"]) == 2


def test_cli_org_sync_unavailable_and_csv(db, monkeypatch, tmp_path, capsys):
    assert cli.main(["org-sync", "--ad"]) == 2
    assert "не настроена" in capsys.readouterr().err
    monkeypatch.setattr(settings, "ad_sync_url", "ldap://dc")
    monkeypatch.setattr(settings, "ad_sync_base_dn", BASE)

    def down(config):
        raise ad_sync.AdSyncError("Не удалось подключиться к каталогу")

    monkeypatch.setattr(ad_sync, "connect", down)
    assert cli.main(["org-sync", "--ad"]) == 2
    path = tmp_path / "list.csv"
    path.write_text("Логин;Подразделение\r\nviewer;АЛМИ Партнер / Проектная служба\r\n", encoding="utf-8")
    assert cli.main(["org-sync", "--csv", str(path), "--apply"]) == 0
    db.expire_all()
    assert db.get(User, _users(db)["viewer"]).department_id == _units(db)["PROJ"]
    assert cli.main(["org-sync", "--csv", str(tmp_path / "missing.csv")]) == 2
