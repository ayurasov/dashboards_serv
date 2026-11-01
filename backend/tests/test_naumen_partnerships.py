"""Заявки Naumen и технологические партнёрства."""
import io
from datetime import date, datetime

import pytest
from openpyxl import Workbook

from app.models import Partnership
from app.services import naumen as naumen_service
from app.services import partnerships as p_service
from app.services import registry

NAUMEN_HEADER = list(naumen_service.IMPORT_COLUMNS)


def _naumen_xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(NAUMEN_HEADER)
    for row in rows:
        ws.append([row.get(col) for col in NAUMEN_HEADER])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _ticket(number, registered, **kw):
    return {"Номер": number, "Название": f"SD{number}", "Дата регистрации": registered, "Статус": "Закрыта",
            "Наименование организации": "Саяно-Шушенская ГЭС", "Способ обращения": "E-mail",
            "Просрочен": "Не просрочен", "Возобновлялась": "Нет", "Время обработки заявки": "10:30", **kw}


# ---------------------------------------------------------------- Naumen

def test_naumen_summary(login):
    data = login("viewer").get("/api/tp/naumen/summary").json()
    assert data["empty"] is False and data["total"] == 1868
    assert data["closed"] + data["in_progress"] == data["total"]
    assert data["months"][0]["month"] <= data["months"][-1]["month"]
    assert data["orgs"][0]["total"] >= data["orgs"][-1]["total"]


def test_naumen_filters_and_last_months(login):
    c = login("viewer")
    filters = c.get("/api/tp/naumen/filters").json()
    assert 2024 in filters["years"] and filters["orgs"][0]["count"] >= filters["orgs"][-1]["count"]
    year = c.get("/api/tp/naumen/summary", params={"year": 2024}).json()
    assert all(m["month"].startswith("2024") for m in year["months"] if m["registered"])
    org = filters["orgs"][0]["org"]
    by_org = c.get("/api/tp/naumen/summary", params={"org": org}).json()
    assert [o["org"] for o in by_org["orgs"]] == [org]
    recent = c.get("/api/tp/naumen/summary", params={"months": 3}).json()
    assert recent["total"] < 1868
    assert c.get("/api/tp/naumen/summary", params={"year": 2001}).json() == {"empty": True}
    assert c.get("/api/tp/naumen/summary", params={"year": 1990}).status_code == 422


def test_naumen_import_merge_by_number(login):
    lead = login("tp_lead")
    content = _naumen_xlsx([
        _ticket(885948, datetime(2023, 6, 27, 7, 38), **{"Статус": "Выполнена", "Возобновлялась": "Да"}),
        _ticket(999001, datetime(2026, 10, 1, 9, 0), **{"Просрочен": "Просрочен"}),
        _ticket(999001, datetime(2026, 10, 1, 9, 0)),
        {"Номер": 1, "Название": "без даты"},
    ])
    body = lead.post("/api/tp/naumen/import", data={"mode": "merge"}, files={"file": ("export.xlsx", content)}).json()
    assert (body["rows_created"], body["rows_updated"], body["rows_skipped"]) == (1, 1, 2)
    assert lead.get("/api/tp/naumen/summary").json()["total"] == 1869


def test_naumen_import_replace_and_validation(login):
    lead = login("tp_lead")
    content = _naumen_xlsx([_ticket(1, datetime(2026, 1, 5, 10, 0)), _ticket(2, "05.01.2026 11:00")])
    body = lead.post("/api/tp/naumen/import", data={"mode": "replace"}, files={"file": ("x.xlsx", content)}).json()
    assert body["rows_created"] == 2
    summary = lead.get("/api/tp/naumen/summary").json()
    assert summary["total"] == 2 and summary["avg_proc_hours"] == 10.5
    wb = Workbook()
    wb.active.append(["Что-то", "другое"])
    buf = io.BytesIO()
    wb.save(buf)
    bad = lead.post("/api/tp/naumen/import", files={"file": ("x.xlsx", buf.getvalue())})
    assert bad.status_code == 422 and "Дата регистрации" in bad.json()["detail"]


def test_naumen_match(login):
    data = login("viewer").get("/api/tp/naumen/match").json()
    assert data["weeks_count"] == 109 and len(data["weeks"]) == 109
    assert {"tp_new_received", "naumen_registered", "naumen_rushydro"} <= set(data["weeks"][0])
    assert data["months"] and data["months"][0]["period"] <= data["months"][-1]["period"]


@pytest.mark.parametrize(("raw", "expected"), [("12:30", 12.5), ("0:15", 0.25), (3.333, 3.33), ("", None),
                                               ("abc", None)])
def test_parse_hours(raw, expected):
    assert naumen_service.parse_hours(raw) == expected


def test_rushydro_markers():
    assert naumen_service.is_rushydro("Саяно-Шушенская ГЭС")
    assert not naumen_service.is_rushydro("ООО Ромашка")


# ---------------------------------------------------------------- партнёрства

def _rules():
    from app.models import PartnershipLightRule

    return {key: PartnershipLightRule(key=key, group_key=group, label=label, light=light, threshold=threshold,
                                      sort_order=i)
            for i, (key, group, label, light, threshold) in enumerate(registry.PARTNERSHIP_DEFAULT_RULES)}


def test_record_light_is_the_worst_part():
    rules = _rules()
    today = date(2026, 11, 1)
    good = Partnership(partner="A", status="Завершено", nda=True, agreement=True, cert_date=date(2026, 1, 1))
    assert p_service.record_light(good, rules, today)["light"] == "green"
    aging = Partnership(partner="B", status="Завершено", nda=True, agreement=True, cert_date=date(2023, 1, 1))
    assert p_service.record_light(aging, rules, today)["light"] == "yellow"
    refused = Partnership(partner="C", status="Не подписывают", nda=True, agreement=True)
    assert p_service.record_light(refused, rules, today)["light"] == "red"


@pytest.mark.parametrize(("cert", "key"), [(date(2025, 6, 1), "cert_age:fresh"), (date(2023, 6, 1), "cert_age:aging"),
                                           (date(2020, 1, 1), "cert_age:stale")])
def test_cert_age(cert, key):
    assert p_service.cert_age_key(cert, _rules(), date(2026, 11, 1)) == key


def test_partnerships_list_and_filters(login):
    c = login("product")
    rows = c.get("/api/partnerships").json()
    assert len(rows) == 142 and {"light", "light_parts", "status_light"} <= set(rows[0])
    options = c.get("/api/partnerships/options").json()
    product = options["almi_products"][0]
    filtered = c.get("/api/partnerships", params={"almi_product": product}).json()
    assert filtered and all(r["almi_product"] == product for r in filtered)
    red = c.get("/api/partnerships", params={"light": "red"}).json()
    assert all(r["light"] == "red" for r in red)
    searched = c.get("/api/partnerships", params={"search": rows[0]["partner"][:5]}).json()
    assert searched


def test_partnership_crud(login):
    c = login("product")
    created = c.post("/api/partnerships", json={"partner": "ООО Тест", "product": "Тест-Продукт",
                                                "almi_product": "АльтерОС", "cert_date": "2026-05-01", "nda": True})
    assert created.status_code == 201 and created.json()["light"] in ("green", "yellow")
    pid = created.json()["id"]
    patched = c.patch(f"/api/partnerships/{pid}", json={"status": "Не подписывают"})
    assert patched.json()["light"] == "red"
    cleared = c.patch(f"/api/partnerships/{pid}", json={"cert_date": None})
    assert cleared.json()["cert_date"] is None
    assert c.post("/api/partnerships", json={"partner": ""}).status_code == 422
    assert c.delete(f"/api/partnerships/{pid}").status_code == 200
    assert c.get(f"/api/partnerships/{pid}").status_code == 404


def test_light_rules_update_and_validation(login):
    c = login("product")
    response = c.put("/api/partnerships/light-rules", json=[{"key": "status:Отложено", "light": "red"},
                                                            {"key": "cert_age:fresh", "threshold": 1.5}])
    assert response.status_code == 200
    rules = {r["key"]: r for r in response.json()}
    assert rules["status:Отложено"]["light"] == "red" and rules["cert_age:fresh"]["threshold"] == 1.5
    assert c.put("/api/partnerships/light-rules", json=[{"key": "nda:yes", "threshold": 2}]).status_code == 422
    assert c.put("/api/partnerships/light-rules", json=[{"key": "cert_age:fresh", "threshold": 9}]).status_code == 422
    assert c.put("/api/partnerships/light-rules", json=[{"key": "nope", "light": "red"}]).status_code == 422
    assert login("viewer").put("/api/partnerships/light-rules", json=[]).status_code == 403


def test_partnership_analytics_summary_timeline(login):
    c = login("viewer")
    analytics = c.get("/api/partnerships/analytics").json()
    assert analytics["total"] == 142 and analytics["lights"]
    assert sum(r["count"] for r in analytics["lights"] if r["group_key"] == "nda") == 142
    summary = c.get("/api/partnerships/summary").json()
    assert summary == sorted(summary, key=lambda y: y["year"])
    assert all(y["green"] + y["yellow"] + y["red"] <= y["total"] for y in summary)
    timeline = c.get("/api/partnerships/timeline").json()
    dates = [r["last_modified"] or r["cert_date"] for r in timeline]
    assert dates == sorted(dates, reverse=True)
    export = c.get("/api/partnerships/export.xlsx")
    assert export.status_code == 200 and export.headers["content-type"].startswith("application/vnd.openxml")
