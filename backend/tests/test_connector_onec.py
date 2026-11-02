"""Коннектор 1С (OData) (ADR-0011): поддельная публикация стандартного интерфейса OData на настоящем
HTTP-сервере — $metadata (XML), наборы с $filter / $select / $top / $skip, виртуальная таблица оборотов
с odata.nextLink, ошибки odata.error; значения по подразделениям и месяцам (sum, count, avg), сопоставление
подразделений 1С по коду, наименованию и списку, итоги веток, нули, повторный запуск без изменений."""
from __future__ import annotations

import base64
import re
from datetime import timedelta
from urllib.parse import quote, unquote

import pytest
from sqlalchemy import select

from app.core.errors import ValidationFailed
from app.integrations.connectors import onec
from app.integrations.connectors.onec import OneCConnector
from app.models import Department, Indicator, IndicatorValue
from app.services import reports
from tests.fake_http import FakeServer

LOGIN, PASSWORD = "Обмен", "пароль-1С"
ROOT = "/zup/odata/standard.odata"
CUR = reports.current_period()
PREV = reports.add_months(CUR, -1)
C, P = reports.period_key(CUR), reports.period_key(PREV)
REF = {"hr": "aaaaaaaa-0000-0000-0000-000000000001", "tech": "aaaaaaaa-0000-0000-0000-000000000002",
       "os": "aaaaaaaa-0000-0000-0000-000000000003", "store": "aaaaaaaa-0000-0000-0000-000000000004"}
CATALOG = [{"Ref_Key": REF["hr"], "Code": "HR", "Description": "Служба персонала"},
           {"Ref_Key": REF["tech"], "Code": "000000003", "Description": "Техническая служба"},
           {"Ref_Key": REF["os"], "Code": "000000012", "Description": "Группа поддержки AlterOS"},
           {"Ref_Key": REF["store"], "Code": "000000099", "Description": "Склад"}]
METADATA = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx" Version="1.0">
 <edmx:DataServices xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" m:DataServiceVersion="3.0">
  <Schema xmlns="http://schemas.microsoft.com/ado/2009/11/edm" Namespace="StandardODATA">
   <EntityType Name="Catalog_ПодразделенияОрганизаций"/><EntityType Name="Document_НачислениеЗарплаты"/>
   <EntityType Name="AccumulationRegister_ВзаиморасчетыСПерсоналом_RecordType"/>
   <EntityType Name="AccumulationRegister_ВзаиморасчетыСПерсоналом_Turnover"/>
   <EntityContainer Name="StandardODATA" m:IsDefaultEntityContainer="true">
    <EntitySet Name="Catalog_ПодразделенияОрганизаций" EntityType="StandardODATA.Catalog_ПодразделенияОрганизаций"/>
    <EntitySet Name="Catalog_Сотрудники" EntityType="StandardODATA.Catalog_Сотрудники"/>
    <EntitySet Name="Document_НачислениеЗарплаты" EntityType="StandardODATA.Document_НачислениеЗарплаты"/>
    <EntitySet Name="AccumulationRegister_ВзаиморасчетыСПерсоналом"
               EntityType="StandardODATA.AccumulationRegister_ВзаиморасчетыСПерсоналом_RecordType"/>
    <FunctionImport Name="Turnovers" IsBindable="true"
      ReturnType="Collection(StandardODATA.AccumulationRegister_ВзаиморасчетыСПерсоналом_Turnover)"/>
   </EntityContainer>
  </Schema>
 </edmx:DataServices>
</edmx:Edmx>"""


def at(month, day: int) -> str:
    return f"{(month + timedelta(days=day - 1)).isoformat()}T12:00:00"


def doc(n: int, month, ref: str, amount: float, posted: bool = True) -> dict:
    return {"Ref_Key": f"dddddddd-0000-0000-0000-{n:012d}", "Date": at(month, 2 + n % 20), "Posted": posted,
            "Подразделение_Key": ref, "ВсегоНачислено": amount, "Комментарий": ""}


def default_docs() -> list[dict]:
    docs = [doc(1, CUR, REF["hr"], 1_000_000), doc(2, CUR, REF["hr"], 200_000), doc(3, CUR, REF["tech"], 3_000_000),
            doc(4, CUR, REF["os"], 500_000), doc(5, CUR, REF["store"], 100_000), doc(6, CUR, REF["hr"], 999, False),
            doc(7, CUR, onec.EMPTY_REF, 50_000), doc(8, PREV, REF["hr"], 900_000), doc(9, PREV, REF["tech"], 2_800_000)]
    docs += [doc(100 + n, PREV, REF["tech"], 1_000) for n in range(60)]
    return docs


TURNOVERS = {C: [{"Подразделение_Key": REF["hr"], "СуммаTurnover": 10_000},
                 {"Подразделение_Key": REF["hr"], "СуммаTurnover": 5_000},
                 {"Подразделение_Key": REF["tech"], "СуммаTurnover": 20_000}],
             P: [{"Подразделение_Key": REF["hr"], "СуммаTurnover": 1_000}]}


class FilterError(Exception):
    pass


def odata_filter(row: dict, text: str) -> bool:
    for part in [p for p in re.split(r"\s+and\s+", text or "") if p.strip()]:
        m = re.fullmatch(r"\s*(\w+)\s+(eq|ge|le|gt|lt)\s+(datetime'([^']+)'|true|false|'([^']*)')\s*", part)
        if not m or m.group(1) not in row:
            raise FilterError(f"Неизвестное поле или ошибка в условии: {part.strip()}")
        actual = row[m.group(1)]
        expected = m.group(4) if m.group(4) else (m.group(5) if m.group(5) is not None else m.group(3) == "true")
        ok = {"eq": actual == expected, "ge": actual >= expected, "le": actual <= expected,
              "gt": actual > expected, "lt": actual < expected}[m.group(2)]
        if not ok:
            return False
    return True


class Routes(dict):
    def __init__(self, fake):
        super().__init__()
        self.fake = fake

    def get(self, key, default=None):
        method, path = key
        path = unquote(path)
        if method != "GET" or not path.startswith(ROOT + "/"):
            return default
        return lambda request: self.fake.dispatch(request, path[len(ROOT) + 1:])


class FakeOData:
    def __init__(self):
        self.docs = default_docs()
        self.catalog = list(CATALOG)
        self.metadata = METADATA
        self.server = FakeServer(routes=Routes(self))

    def __enter__(self) -> FakeOData:
        self.server.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.server.stop()

    @property
    def url(self) -> str:
        return self.server.url + ROOT

    @property
    def requests(self):
        return self.server.requests

    @staticmethod
    def error(status: int, text: str):
        return status, {"odata.error": {"code": "-1", "message": {"lang": "ru", "value": text}}}

    def dispatch(self, request, path: str):
        header = request.headers.get("authorization", "")
        if header != "Basic " + base64.b64encode(f"{LOGIN}:{PASSWORD}".encode()).decode():
            return 401, "<html>401 Unauthorized</html>"
        if path == "$metadata":
            return 200, self.metadata.encode(), {"Content-Type": "application/xml"}
        q = {k: v[0] for k, v in request.query.items()}
        if q.get("$format") != "json":
            return self.error(400, "Нужен $format=json")
        turnovers = re.fullmatch(r"AccumulationRegister_ВзаиморасчетыСПерсоналом/Turnovers\(StartPeriod=datetime"
                                 r"'([^']+)',\s*EndPeriod=datetime'([^']+)'\)", path)
        if turnovers:
            rows = TURNOVERS.get(turnovers.group(1)[:7], [])
            skip = int(q.get("$skiptoken") or 0)
            more = skip + 2 < len(rows)
            link = f"{self.url}/{quote(path, safe='/()=,:')}?$format=json&$skiptoken={skip + 2}"
            page = {"odata.metadata": "…", "value": rows[skip:skip + 2]}
            return 200, {**page, "odata.nextLink": link} if more else page
        sources = {"Document_НачислениеЗарплаты": self.docs, "Catalog_ПодразделенияОрганизаций": self.catalog}
        if path not in sources:
            return self.error(404, f"Не найден ресурс: {path}")
        try:
            rows = [r for r in sources[path] if odata_filter(r, q.get("$filter", ""))]
        except FilterError as exc:
            return self.error(400, str(exc))
        if q.get("$select"):
            fields = q["$select"].split(",")
            rows = [{k: r.get(k) for k in fields} for r in rows]
        skip, top = int(q.get("$skip") or 0), int(q.get("$top") or 1000)
        return 200, {"odata.metadata": f"{self.url}/$metadata#{path}", "value": rows[skip:skip + top]}


@pytest.fixture()
def fake(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.delenv("ONEC_ALLOWED_HOSTS", raising=False)
    with FakeOData() as server:
        yield server


PAYROLL = {"name": "ФОТ", "entity": "Document_НачислениеЗарплаты",
           "filter": "Date ge datetime'{month_start}' and Date le datetime'{month_end}' and Posted eq true",
           "select": "Подразделение_Key,ВсегоНачислено", "value_field": "ВсегоНачислено", "aggregate": "sum",
           "department_field": "Подразделение_Key", "scale": 0.000001, "indicator": "onec.payroll",
           "indicator_name": "ФОТ (1С)", "unit": "млн ₽", "direction": "lower_is_better"}
COUNT = {"name": "Начисления", "entity": "Document_НачислениеЗарплаты",
         "filter": "Date ge datetime'{month_start}' and Date le datetime'{month_end}' and Posted eq true",
         "select": "Ref_Key", "aggregate": "count", "department_field": "Подразделение_Key",
         "indicator": "onec.docs", "indicator_name": "Начислений (1С)", "unit": "шт.", "data_class": "operational"}
TURNOVER = {"name": "Взаиморасчёты", "entity": "AccumulationRegister_ВзаиморасчетыСПерсоналом/Turnovers("
            "StartPeriod=datetime'{month_start}', EndPeriod=datetime'{month_end}')",
            "select": "Подразделение_Key,СуммаTurnover", "value_field": "СуммаTurnover",
            "department_field": "Подразделение_Key", "scale": 0.001, "indicator": "onec.settlements",
            "indicator_name": "Взаиморасчёты (1С)", "unit": "тыс. ₽"}
QUERIES = [PAYROLL, COUNT, TURNOVER]


def create(admin, fake, queries=None, name="1С ЗУП", password=PASSWORD, **config) -> dict:
    body = {"kind": "onec", "name": name, "config": {
        "base_url": fake.url, "login": LOGIN, "queries": queries if queries is not None else QUERIES,
        "department_map": "000000003 = TECH, Склад = AHO", "page_size": 50, **config},
        "secrets": {"password": password}}
    response = admin.post("/api/integrations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def run(admin, item, action="load") -> dict:
    response = admin.post(f"/api/integrations/{item['id']}/run", json={"action": action})
    assert response.status_code == 200, response.text
    return response.json()


def values(db, key: str, comments: bool = False) -> dict:
    db.expire_all()
    rows = db.execute(select(Department.code, IndicatorValue.period, IndicatorValue.value, IndicatorValue.comment)
                      .join(Indicator, Indicator.id == IndicatorValue.indicator_id)
                      .join(Department, Department.id == IndicatorValue.department_id)
                      .where(Indicator.key == key)).all()
    return {(code, reports.period_key(period)): (value, comment) if comments else value
            for code, period, value, comment in rows}


# ---------------------------------------------------------------- описание и настройки

def test_kind_is_described_in_russian(admin):
    meta = {k["kind"]: k for k in admin.get("/api/integrations/kinds").json()}["onec"]
    assert meta["title"] == "1С (OData)" and meta["allowed_hosts_env"] == "ONEC_ALLOWED_HOSTS"
    for text in ("POST /api/inbound/v1/files", "Новый HTTPСоединение", "Новый HTTPЗапрос", "Bearer"):
        assert text in meta["description"], text
    fields = {f["key"]: f for f in meta["fields"]}
    assert fields["password"]["secret"] and fields["queries"]["type"] == "json"
    assert [o["value"] for o in fields["department_match"]["options"]] == ["code", "name", "map"]
    assert {a["key"]: a["label"] for a in meta["actions"]} == {"load": "Загрузить данные",
                                                               "preview": "Проверить без записи"}


def test_validate_config():
    base = {"base_url": "https://1c.company.ru/zup/odata/standard.odata/", "login": "x"}
    out = OneCConnector.validate_config({**base, "queries": QUERIES})
    assert out["base_url"].endswith("/standard.odata") and len(onec.parse_queries(out["queries"])) == 3
    with pytest.raises(ValidationFailed) as exc:
        OneCConnector.validate_config({**base, "base_url": "https://1c.company.ru/zup", "queries": QUERIES})
    assert "config.base_url" in exc.value.fields
    bad = [({**PAYROLL, "filter": "Posted eq true"}, "нельзя разнести по месяцам"),
           ({**PAYROLL, "unit_code": "HR"}, "department_field"),
           ({**PAYROLL, "department_field": None}, "department_field"),
           ({**PAYROLL, "aggregate": "max"}, "aggregate"),
           ({**PAYROLL, "value_field": ""}, "value_field"),
           ({**PAYROLL, "entity": "Document_X?$top=1"}, "entity"),
           ({**PAYROLL, "name": ""}, "name"),
           ({**PAYROLL, "period": "x"}, "period"),
           ({**PAYROLL, "filter": "Date ge datetime'{start}'"}, "{start}")]
    for query, text in bad:
        with pytest.raises(ValidationFailed) as exc:
            OneCConnector.validate_config({**base, "queries": [query]})
        assert text in exc.value.detail and "config.queries" in exc.value.fields, query
    with pytest.raises(ValidationFailed) as exc:
        OneCConnector.validate_config({**base, "queries": [PAYROLL, {**COUNT, "indicator": "onec.payroll"}]})
    assert "уже заполняет запрос 1" in exc.value.detail


# ---------------------------------------------------------------- проверка

def test_check_reads_metadata_with_utf8_basic(admin, fake):
    item = create(admin, fake)
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"], check
    assert check["message"].startswith("Подключено, опубликовано наборов: 4; запросов: 3, наборы на месте")
    assert check["details"]["entity_sets"] == 4
    request = fake.requests[-1]
    assert request.path.endswith("/$metadata") and "xml" in request.headers["accept"]
    raw = request.headers["authorization"].split()[1]
    assert base64.b64decode(raw).decode("utf-8") == f"{LOGIN}:{PASSWORD}"


def test_check_validates_entity_sets(admin, fake):
    queries = [{**PAYROLL, "entity": "Document_НачислениеЗП"},
               {**TURNOVER, "entity": "AccumulationRegister_ВзаиморасчетыСПерсоналом_Turnovers",
                "filter": "Period ge datetime'{month_start}'"}]
    item = create(admin, fake, queries=queries, department_catalog="Catalog_Подразделения")
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"]
    assert "набора «Document_НачислениеЗП» нет в $metadata" in check["message"]
    assert "есть, например: Document_НачислениеЗарплаты" in check["message"]
    assert ("«AccumulationRegister_ВзаиморасчетыСПерсоналом_Turnovers» — не набор; виртуальная таблица задаётся так: "
            "AccumulationRegister_ВзаиморасчетыСПерсоналом/Turnovers(…)") in check["message"]
    assert "справочника подразделений «Catalog_Подразделения» нет" in check["message"]


def test_check_failures(admin, fake):
    item = create(admin, fake, password="wrong")
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and "(401)" in check["message"]
    fake.metadata = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>'
    check = admin.post(f"/api/integrations/{item['id']}/check", json={"secrets": {"password": PASSWORD}}).json()
    assert not check["ok"] and "DTD" in check["message"]
    fake.metadata = "<html>вход</html"
    check = admin.post(f"/api/integrations/{item['id']}/check", json={"secrets": {"password": PASSWORD}}).json()
    assert not check["ok"] and "не XML" in check["message"]
    assert PASSWORD not in str(check)


# ---------------------------------------------------------------- загрузка

def test_load_values_per_unit_and_month(admin, fake, db):
    item = create(admin, fake)
    data = run(admin, item)
    assert data["status"] == "ok", data
    assert values(db, "onec.payroll") == {("HR", C): 1.2, ("TECH", C): 3.0, ("AHO", C): 0.1,
                                          ("HR", P): 0.9, ("TECH", P): 2.86}
    assert values(db, "onec.docs") == {("HR", C): 2, ("TECH", C): 1, ("AHO", C): 1, ("HR", P): 1, ("TECH", P): 61}
    assert values(db, "onec.settlements") == {("HR", C): 15.0, ("TECH", C): 20.0, ("HR", P): 1.0}
    assert values(db, "onec.payroll", comments=True)[("HR", C)][1] == "из 1С: «ФОТ», строк — 2"
    summary = data["summary"]
    assert summary["rows_unmapped"] == 4, "AlterOS (код без соответствия) и строка без подразделения — дважды"
    assert summary["details"]["unmapped"] == {"Группа поддержки AlterOS (000000012)": 2, "без подразделения": 2}
    assert "строки подразделений 1С без соответствия не учтены" in data["message"]
    payroll = db.scalar(select(Indicator).where(Indicator.key == "onec.payroll"))
    assert (payroll.name, payroll.unit, payroll.data_class, payroll.owner_service, payroll.direction) == \
        ("ФОТ (1С)", "млн ₽", "financial", "finance", "lower_is_better")
    assert db.scalar(select(Indicator.data_class).where(Indicator.key == "onec.docs")) == "operational"
    # $top / $skip: 62 документа прошлого месяца — две страницы по 50; обороты — по odata.nextLink
    docs = [r for r in fake.requests if r.path.endswith(quote("Document_НачислениеЗарплаты"))
            and PREV.isoformat() in r.query.get("$filter", [""])[0] and r.query.get("$select") == [PAYROLL["select"]]]
    assert [r.query["$skip"] for r in docs] == [["0"], ["50"]] and docs[0].query["$top"] == ["50"]
    assert docs[0].query["$filter"] == [f"Date ge datetime'{PREV.isoformat()}T00:00:00' and Date le datetime'"
                                        f"{reports.month_end(PREV).isoformat()}T23:59:59' and Posted eq true"]
    pages = [r for r in fake.requests if "Turnovers" in unquote(r.path)]
    assert [r.query.get("$skiptoken") for r in pages] == [None, None, ["2"]], "прошлый месяц — 1 страница, текущий — 2"
    catalog = [r for r in fake.requests if r.path.endswith(quote("Catalog_ПодразделенияОрганизаций"))]
    assert len(catalog) == 1, "справочник подразделений читается один раз за запуск"


def test_rerun_unchanged_and_vanished_unit_gets_zero(admin, fake, db):
    item = create(admin, fake, queries=[PAYROLL, COUNT])
    first = run(admin, item)
    second = run(admin, item)
    assert second["summary"]["created"] == second["summary"]["updated"] == 0
    assert second["summary"]["unchanged"] == first["summary"]["values"] == 10
    fake.docs = [d for d in fake.docs if d["Подразделение_Key"] != REF["store"]]
    third = run(admin, item)
    assert values(db, "onec.payroll", comments=True)[("AHO", C)] == (0, "из 1С — за месяц данных нет")
    assert values(db, "onec.docs")[("AHO", C)] == 0 and third["summary"]["updated"] == 2
    fourth = run(admin, item)
    assert fourth["summary"]["created"] == fourth["summary"]["updated"] == 0


def test_name_matching_with_branch_totals(admin, fake, db):
    item = create(admin, fake, queries=[PAYROLL], department_match="name", department_map="Склад = AHO", months=1)
    data = run(admin, item)
    assert data["status"] == "ok", data
    assert values(db, "onec.payroll") == {("HR", C): 1.2, ("TECH", C): 3.5, ("SUP-OS", C): 0.5, ("AHO", C): 0.1}
    assert values(db, "onec.payroll", comments=True)[("TECH", C)][1].endswith("(вместе с вложенными подразделениями)")


def test_map_only_mode_and_fixed_unit(admin, fake, db):
    queries = [PAYROLL, {**COUNT, "department_field": None, "unit_code": "ALMI", "indicator": "onec.all_docs",
                         "indicator_name": "Начислений в компании (1С)"},
               {**PAYROLL, "aggregate": "avg", "scale": 0.001, "indicator": "onec.avg", "indicator_name": "Среднее",
                "unit": "тыс. ₽"}]
    item = create(admin, fake, queries=queries, department_match="map",
                  department_map=f"{REF['hr']} = HR, 000000003 = TECH", months=1)
    data = run(admin, item)
    assert data["status"] == "ok", data
    assert values(db, "onec.payroll") == {("HR", C): 1.2, ("TECH", C): 3.0}
    assert values(db, "onec.all_docs") == {("ALMI", C): 6}
    assert values(db, "onec.avg") == {("HR", C): 600.0, ("TECH", C): 3000.0}
    assert db.scalar(select(Indicator.rollup).where(Indicator.key == "onec.avg")) == "avg"


def test_query_error_gives_partial_result(admin, fake, db):
    queries = [PAYROLL, {**COUNT, "filter": "Дата ge datetime'{month_start}'", "indicator": "onec.bad",
                         "indicator_name": "Плохой"}]
    item = create(admin, fake, queries=queries, months=1)
    data = run(admin, item)
    assert data["status"] == "partial", data
    assert "1С отклонила запрос «Начисления» за" in data["error"] and "(400): Неизвестное поле" in data["error"]
    assert values(db, "onec.payroll")[("HR", C)] == 1.2 and values(db, "onec.bad") == {}
    missing = create(admin, fake, name="1С другая", queries=[{**PAYROLL, "entity": "Document_Нет"}], months=1)
    failed = run(admin, missing)
    assert failed["status"] == "error" and "(404)" in failed["error"] and "составе стандартного интерфейса" in \
        failed["error"]
    assert db.scalar(select(Indicator).where(Indicator.key == "onec.bad")) is None, "запрос не удался — не создаём"


def test_preview_writes_nothing(admin, fake, db):
    item = create(admin, fake)
    data = run(admin, item, "preview")
    assert data["status"] == "ok" and data["message"].startswith("План без записи")
    assert db.scalar(select(Indicator).where(Indicator.key.like("onec.%"))) is None


def test_auth_failure_during_load(admin, fake, db):
    item = create(admin, fake, password="wrong")
    data = run(admin, item)
    assert data["status"] == "error" and "(401)" in data["error"]
    assert db.scalar(select(Indicator).where(Indicator.key.like("onec.%"))) is None
