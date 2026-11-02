"""Коннектор Confluence (ADR-0011): поддельная Confluence (Server и Cloud с /wiki) на настоящем HTTP-сервере —
страницы с версиями, 409 на устаревшую версию, уникальность названия в пространстве; публикация сквозного
отчёта: создание, обновление той же страницы (версия + 1), поиск по id и по названию, еженедельный режим,
скрытие финансовых показателей, вершина отчёта, формат хранения (макросы статуса и панели)."""
from __future__ import annotations

import base64
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from urllib.parse import unquote

import pytest
from sqlalchemy import select

from app.core.errors import ValidationFailed
from app.core.timeutil import local_now
from app.integrations.connectors.confluence import ConfluenceConnector
from app.models import Department, Indicator, IndicatorValue
from app.services import reports
from tests.conftest import assert_counters_labelled
from tests.fake_http import FakeServer

TOKEN = "conf-pat-0123456789"
PERIOD = reports.add_months(reports.current_period(), -1)    # последний завершённый месяц


class Routes(dict):
    """Маршруты FakeServer с шаблонами путей (номер страницы, ключ пространства)."""

    def __init__(self):
        super().__init__()
        self.patterns: list[tuple[str, re.Pattern, object]] = []

    def add(self, method: str, pattern: str, handler) -> None:
        self.patterns.append((method, re.compile(pattern + "$"), handler))

    def get(self, key, default=None):
        method, path = key
        for m, rx, handler in self.patterns:
            match = rx.match(unquote(path))
            if m == method and match:
                return lambda request, h=handler, g=match.groups(): h(request, *g)
        return default


class FakeConfluence:
    def __init__(self, mode: str = "server", login: str = "", token: str = TOKEN, prefix: str = ""):
        self.mode, self.login, self.token, self.prefix = mode, login, token, prefix
        self.spaces = {"REP": "Отчёты", "ARCH": "Архив"}
        self.pages: dict[str, dict] = {"500": {"id": "500", "title": "Отчёты компании", "space": "REP", "version": 3,
                                               "body": "", "parent": None}}
        self.hidden_titles: set[tuple[str, str]] = set()   # в корзине: создать нельзя, поиском не находится
        self.concurrent = 0                                # столько раз «кто-то» правит страницу перед нашим PUT
        self.next_id = 1000
        self.puts: list[dict] = []
        routes = Routes()
        api = re.escape(prefix) + "/rest/api"
        routes.add("GET", api + r"/user/current", self.guard(self.current))
        routes.add("GET", api + r"/space/([^/]+)", self.guard(self.space))
        routes.add("GET", api + r"/content", self.guard(self.search))
        routes.add("POST", api + r"/content", self.guard(self.create))
        routes.add("GET", api + r"/content/(\d+)", self.guard(self.get_page))
        routes.add("PUT", api + r"/content/(\d+)", self.guard(self.update))
        self.server = FakeServer(routes=routes)

    def __enter__(self) -> FakeConfluence:
        self.server.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.server.stop()

    @property
    def url(self) -> str:
        return self.server.url + self.prefix

    @property
    def requests(self):
        return self.server.requests

    def guard(self, handler):
        def wrapped(request, *args):
            header = request.headers.get("authorization", "")
            if self.mode == "server":
                ok = header == f"Bearer {self.token}"
            else:
                ok = header == "Basic " + base64.b64encode(f"{self.login}:{self.token}".encode()).decode()
            if not ok:
                return 401, {"statusCode": 401, "message": "Unauthorized"}
            return handler(request, *args)
        return wrapped

    def page_json(self, page: dict) -> dict:
        return {"id": page["id"], "type": "page", "status": "current", "title": page["title"],
                "space": {"key": page["space"]}, "version": {"number": page["version"]},
                "_links": {"webui": f"/pages/viewpage.action?pageId={page['id']}", "base": self.url}}

    def current(self, _request):
        return 200, {"type": "known", "username": "dash", "displayName": "Служебная учётная запись"}

    def space(self, _request, key):
        if key not in self.spaces:
            return 404, {"statusCode": 404, "message": f"No space with key : {key}"}
        return 200, {"key": key, "name": self.spaces[key]}

    def search(self, request):
        space, title = request.query.get("spaceKey", [""])[0], request.query.get("title", [""])[0]
        found = [self.page_json(p) for p in self.pages.values() if p["space"] == space and p["title"] == title]
        return 200, {"results": found, "size": len(found)}

    def get_page(self, _request, page_id):
        page = self.pages.get(page_id)
        return (200, self.page_json(page)) if page else (404, {"statusCode": 404, "message": "No content found"})

    def create(self, request):
        body = request.json()
        space = body["space"]["key"]
        if space not in self.spaces:
            return 404, {"statusCode": 404, "message": f"No space with key : {space}"}
        parent = (body.get("ancestors") or [{}])[0].get("id")
        if parent and parent not in self.pages:
            return 404, {"statusCode": 404, "message": "Parent page not found"}
        if (space, body["title"]) in self.hidden_titles or any(
                p["space"] == space and p["title"] == body["title"] for p in self.pages.values()):
            return 400, {"statusCode": 400, "message": "A page with this title already exists: A page already "
                                                       f"exists with the title {body['title']} in the space with key "
                                                       f"{space}"}
        self.next_id += 1
        page = {"id": str(self.next_id), "title": body["title"], "space": space, "version": 1,
                "body": body["body"]["storage"]["value"], "parent": parent}
        self.pages[page["id"]] = page
        return 200, self.page_json(page)

    def update(self, request, page_id):
        page = self.pages.get(page_id)
        if page is None:
            return 404, {"statusCode": 404, "message": "No content found"}
        if self.concurrent:
            self.concurrent -= 1
            page["version"] += 1
        body = request.json()
        self.puts.append(body)
        if body["version"]["number"] != page["version"] + 1:
            return 409, {"statusCode": 409, "message": "Version must be incremented on update. Current version is: "
                                                       f"{page['version']}"}
        page.update(title=body["title"], version=page["version"] + 1, body=body["body"]["storage"]["value"])
        return 200, self.page_json(page)


@pytest.fixture()
def fake(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.delenv("CONFLUENCE_ALLOWED_HOSTS", raising=False)
    with FakeConfluence() as server:
        yield server


@pytest.fixture()
def report_data(db):
    """Значения за последний завершённый месяц: ops.plan с разными статусами, выручка (финансовый класс)."""
    by_code = {d.code: d.id for d in db.scalars(select(Department))}
    ind = {i.key: i.id for i in db.scalars(select(Indicator))}
    for code, value in (("TECH", 70), ("IT", 97), ("SUP-OS", 90)):
        db.add(IndicatorValue(indicator_id=ind["ops.plan"], department_id=by_code[code], period=PERIOD, value=value,
                              comment="", source="manual"))
    db.add(IndicatorValue(indicator_id=ind["fin.revenue"], department_id=by_code["COMM"], period=PERIOD, value=12.5,
                          target=10, comment="", source="manual"))
    db.get(Department, by_code["AHO"]).name = "АХО & склад <1>"
    db.commit()


@pytest.fixture(autouse=True)
def public_url(monkeypatch):
    """Адрес «Дашбордов» для ссылки со страницы — настройка сервера PUBLIC_URL."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "public_url", "https://dash.company.ru")


def create(admin, fake, name="Confluence", **config) -> dict:
    body = {"kind": "confluence", "name": name, "config": {
        "base_url": fake.url, "instance": fake.mode, "login": fake.login, "space": "REP", "parent_id": "500",
        **config}, "secrets": {"token": fake.token}}
    response = admin.post("/api/integrations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def publish(admin, item) -> dict:
    response = admin.post(f"/api/integrations/{item['id']}/run", json={"action": "publish"})
    assert response.status_code == 200, response.text
    return assert_counters_labelled(response.json(), "confluence")


def state(db, item) -> dict:
    from app.models import Integration

    db.expire_all()
    return db.get(Integration, item["id"]).state


def as_xml(body: str) -> ET.Element:
    return ET.fromstring('<root xmlns:ac="http://atlassian.com/content" xmlns:ri="http://atlassian.com/ri">'
                         + body + "</root>")


# ---------------------------------------------------------------- описание и настройки

def test_kind_is_described_in_russian(admin):
    meta = {k["kind"]: k for k in admin.get("/api/integrations/kinds").json()}["confluence"]
    fields = {f["key"]: f for f in meta["fields"]}
    assert meta["allowed_hosts_env"] == "CONFLUENCE_ALLOWED_HOSTS"
    assert {"space", "parent_id", "title", "mode", "root", "period_offset", "hide_financial"} <= set(fields)
    assert "app_url" not in fields, "адрес «Дашбордов» — общая настройка сервера PUBLIC_URL"
    assert fields["hide_financial"]["default"] is True and fields["token"]["secret"]
    assert "как его видит администратор" in fields["space"]["hint"] and "права" in fields["hide_financial"]["hint"]
    assert [o["value"] for o in fields["mode"]["options"]] == ["single", "weekly"]
    assert meta["actions"] == [{"key": "publish", "label": "Опубликовать сквозной отчёт", "schedulable": True,
                                "description": meta["actions"][0]["description"]}]


def test_validate_config():
    base = {"base_url": "https://confluence.company.ru", "instance": "server", "space": "REP"}
    out = ConfluenceConnector.validate_config(base)
    assert out["title"] == "Сквозной отчёт компании" and "app_url" not in out
    assert out["hide_financial"] is True and out["mode"] == "single" and out["period_offset"] == 0
    for bad, field in (({"instance": "cloud", "login": "a@b.ru", "base_url": "https://x.atlassian.net"}, "base_url"),
                       ({"space": "R E P"}, "space"), ({"parent_id": "abc"}, "parent_id"),
                       ({"title": "Отчёт {month}"}, "title"), ({"app_url": "https://x.ru"}, "app_url")):
        with pytest.raises(ValidationFailed) as exc:
            ConfluenceConnector.validate_config({**base, **bad})
        assert f"config.{field}" in exc.value.fields
    cloud = ConfluenceConnector.validate_config({**base, "instance": "cloud", "login": "a@b.ru",
                                                 "base_url": "https://x.atlassian.net/wiki/"})
    assert cloud["base_url"] == "https://x.atlassian.net/wiki"


# ---------------------------------------------------------------- проверка

def test_check_ok_and_parent(admin, fake):
    item = create(admin, fake)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"], check
    assert check["message"] == ("Подключено как Служебная учётная запись · пространство «Отчёты» (REP) · "
                                "родительская страница «Отчёты компании»")
    assert fake.requests[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert check["warnings"] == []
    missing = admin.post(f"/api/integrations/{item['id']}/check",
                         json={"config": {"parent_id": "777", "root": "NOPE"}}).json()
    assert missing["ok"]
    assert missing["message"] == "Подключено как Служебная учётная запись · пространство «Отчёты» (REP)"
    assert missing["warnings"][0] == "родительская страница 777 не найдена или недоступна"
    assert "подразделение «NOPE» не найдено" in missing["warnings"][1] and "warnings" not in missing["details"]


def test_check_failures(admin, fake):
    item = create(admin, fake)
    url = f"/api/integrations/{item['id']}/check"
    space = admin.post(url, json={"config": {"space": "NOPE"}}).json()
    assert not space["ok"] and space["message"] == "Пространство NOPE не найдено или нет прав на него"
    wrong = admin.post(url, json={"secrets": {"token": "wrong"}}).json()
    assert not wrong["ok"] and "Confluence отклонила логин или токен (401)" in wrong["message"]


# ---------------------------------------------------------------- публикация

def test_publish_creates_page_with_report(admin, fake, db, report_data):
    item = create(admin, fake)
    data = publish(admin, item)
    assert data["status"] == "ok", data
    assert data["message"].startswith("Создана страница «Сквозной отчёт компании», версия 1: отчёт за "
                                      f"{reports.period_label(PERIOD).lower()}, статус «Критично»")
    created = [p for p in fake.pages.values() if p["id"] != "500"]
    assert len(created) == 1
    page = created[0]
    assert (page["title"], page["space"], page["parent"], page["version"]) == \
        ("Сквозной отчёт компании", "REP", "500", 1)
    body = page["body"]
    as_xml(body)  # формат хранения — корректный XHTML
    assert "Страница обновляется автоматически" in body and "вся компания, финансовые показатели скрыты" in body
    assert '<ac:structured-macro ac:name="warning"><ac:parameter ac:name="title">Статус: Критично' in body
    assert "Почему такой статус" in body and "Выполнение плана работ в «Техническая служба»" in body
    for colour, title in (("Red", "70"), ("Green", "97"), ("Yellow", "90"), ("Red", "Нет данных"),
                          ("Red", "Критично")):
        assert (f'<ac:parameter ac:name="colour">{colour}</ac:parameter><ac:parameter ac:name="title">{title}'
                "</ac:parameter>") in body, (colour, title)
    assert "<sub>цель 100</sub>" in body and "<th>Выполнение плана работ, %</th>" in body
    assert "<h2>Нарушения полноты данных</h2>" in body and "АЛМИ Партнер / Коммерческая дирекция" in body
    assert "АХО &amp; склад &lt;1&gt;" in body and "АХО & склад" not in body
    assert "Выручка" not in body and "12,5" not in body, "финансовые показатели скрыты"
    assert '<a href="https://dash.company.ru/reports">' in body
    saved = state(db, item)
    assert saved["page_id"] == page["id"] and saved["version"] == 1 and saved["space"] == "REP"
    assert saved["page_url"].endswith(f"/pages/viewpage.action?pageId={page['id']}")
    assert data["summary"]["created"] == 1 and data["summary"]["details"]["url"] == saved["page_url"]


def test_without_public_url_page_has_no_link(admin, fake, db, report_data, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "public_url", "")
    data = publish(admin, create(admin, fake))
    assert data["status"] == "ok", data
    body = next(p for p in fake.pages.values() if p["id"] != "500")["body"]
    assert "<a href=" not in body and "Подробности — в разделе «Сквозной отчёт»" in body


def test_second_publish_updates_same_page(admin, fake, db, report_data):
    item = create(admin, fake)
    first = publish(admin, item)
    second = publish(admin, item)
    assert second["status"] == "ok" and "Обновлена (найдена по сохранённому id) страница" in second["message"]
    assert "версия 2" in second["message"] and second["summary"]["version"] == 2
    created = [p for p in fake.pages.values() if p["id"] != "500"]
    assert len(created) == 1 and created[0]["version"] == 2
    assert fake.puts[-1]["version"]["number"] == 2 and fake.puts[-1]["version"]["message"]
    assert first["summary"]["details"]["page_id"] == second["summary"]["details"]["page_id"]


def test_deleted_page_is_recreated(admin, fake, db, report_data):
    item = create(admin, fake)
    publish(admin, item)
    old = state(db, item)["page_id"]
    del fake.pages[old]
    data = publish(admin, item)
    assert data["status"] == "ok" and data["message"].startswith("Создана страница")
    assert state(db, item)["page_id"] != old and len(fake.pages) == 2


def test_existing_page_is_found_by_title(admin, fake, db, report_data):
    fake.pages["900"] = {"id": "900", "title": "Сквозной отчёт компании", "space": "REP", "version": 5, "body": "",
                         "parent": None}
    item = create(admin, fake)
    data = publish(admin, item)
    assert "Обновлена (найдена по названию)" in data["message"] and "версия 6" in data["message"]
    assert len(fake.pages) == 2 and fake.pages["900"]["version"] == 6 and state(db, item)["page_id"] == "900"


def test_stale_version_is_retried_once(admin, fake, db, report_data):
    item = create(admin, fake)
    publish(admin, item)
    fake.concurrent = 1   # между чтением и записью страницу правят в Confluence
    data = publish(admin, item)
    assert data["status"] == "ok" and data["summary"]["version"] == 3, data  # 1, чужая правка — 2, наша — 3
    fake.concurrent = 5
    failed = publish(admin, item)
    assert failed["status"] == "error" and "одновременно изменили в Confluence" in failed["error"]


def test_title_taken_by_invisible_page(admin, fake, report_data):
    fake.hidden_titles.add(("REP", "Сквозной отчёт компании"))
    data = publish(admin, create(admin, fake))
    assert data["status"] == "error" and "уже есть в пространстве REP" in data["error"]
    assert "в корзине" in data["error"]


def test_weekly_mode_creates_page_per_week(admin, fake, db, report_data):
    item = create(admin, fake, mode="weekly", title="Сквозной отчёт — {period}")
    data = publish(admin, item)
    today = local_now().date()
    monday = today - timedelta(days=today.weekday())
    title = (f"Сквозной отчёт — {reports.period_label(PERIOD)} — неделя {today.isocalendar()[1]} "
             f"({monday:%d.%m}–{monday + timedelta(days=6):%d.%m.%Y})")
    assert data["summary"]["details"]["title"] == title
    again = publish(admin, item)
    assert "найдена по названию" in again["message"] and len(fake.pages) == 2


def test_cloud_with_wiki_prefix(admin, monkeypatch, report_data):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    with FakeConfluence(mode="cloud", login="svc@company.ru", prefix="/wiki") as cloud:
        item = create(admin, cloud)
        assert admin.post(f"/api/integrations/{item['id']}/check").json()["ok"]
        data = publish(admin, item)
        assert data["status"] == "ok", data
        assert all(r.path.startswith("/wiki/rest/api/") for r in cloud.requests)
        raw = cloud.requests[0].headers["authorization"].split()[1]
        assert base64.b64decode(raw).decode() == f"svc@company.ru:{TOKEN}"
        assert data["summary"]["details"]["url"].startswith(cloud.url + "/pages/")


def test_financial_shown_on_request_and_root(admin, fake, report_data):
    item = create(admin, fake, hide_financial=False, root="COMMDIR", title="Отчёт: {root}")
    data = publish(admin, item)
    assert data["status"] == "ok", data
    page = fake.pages[data["summary"]["details"]["page_id"]]
    assert page["title"] == "Отчёт: Коммерческая дирекция"
    body = page["body"]
    assert "<th>Выручка, млн ₽</th>" in body and "12,5" in body and "<sub>цель 10</sub>" in body
    assert "«Коммерческая дирекция» с вложенными подразделениями" in body
    assert "Техническая служба" not in body and "Коммерческая служба" in body


def test_space_change_ignores_stored_page(admin, fake, db, report_data):
    item = create(admin, fake, parent_id="")
    publish(admin, item)
    first = state(db, item)["page_id"]
    admin.patch(f"/api/integrations/{item['id']}", json={"config": {"space": "ARCH"}})
    data = publish(admin, item)
    assert data["message"].startswith("Создана страница")
    assert fake.pages[state(db, item)["page_id"]]["space"] == "ARCH" and fake.pages[first]["version"] == 1


def test_period_offset_and_unknown_root(admin, fake, db):
    item = create(admin, fake, period_offset=2, title="Отчёт за {period_key}")
    data = publish(admin, item)
    expected = reports.period_key(reports.add_months(reports.current_period(), -3))
    assert data["summary"]["details"]["title"] == f"Отчёт за {expected}"
    broken = create(admin, fake, name="Другая ветка", root="NOPE")
    failed = publish(admin, broken)
    assert failed["status"] == "error" and "Вершина отчёта: подразделение «NOPE» не найдено" in failed["error"]
