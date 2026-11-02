"""Загрузка данных служб через тот же движок, что и входящие: метрики месяцев и реестр службы персонала,
реестр партнёрств (новые загрузки 0.4.0), план загрузки недельного отчёта ТП и выгрузки Naumen."""
from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select

from app.models import DataImport, HrEmployeeEvent, NaumenTicket, Partnership
from app.services import hr_import, naumen, partnerships
from app.services import tp as tp_service
from tests.test_inbox import csv_bytes, hr_events_file, naumen_file, partnerships_file, xlsx


@pytest.fixture()
def hr(login):
    return login("hr_head")


# ---------------------------------------------------------------- метрики месяцев

@pytest.mark.parametrize(("text", "key"), [
    ("2026-01", "2026-01"), ("2026-1", "2026-01"), ("01.2026", "2026-01"), ("Январь 2026", "2026-01"),
    ("января 2026 г.", "2026-01"), ("янв 2026", "2026-01"), ("2026-03-01T00:00:00", "2026-03"),
    ("15.03.2026", "2026-03"), ("2026-13", None), ("весна 2026", None), ("", None),
])
def test_parse_month(text, key):
    assert hr_import.parse_month(text) == key


def test_months_export_import_round_trip_is_unchanged(hr):
    exported = hr.get("/api/hr/months/export.xlsx")
    assert exported.status_code == 200
    ws = load_workbook(io.BytesIO(exported.content)).active
    assert [c.value for c in ws[1]][:4] == ["Метрика", "Ключ", "Единица", "2026-01"]
    plan = hr.post("/api/hr/months/import", files={"file": ("m.xlsx", exported.content)}).json()
    assert plan["applied"] is False and plan["can_apply"]
    assert plan["summary"]["create"] == plan["summary"]["update"] == 0 and plan["summary"]["unchanged"] > 50


def test_months_import_wide_and_long(hr, db):
    wide = xlsx([["Метрика", "2031-01", "Февраль 2031"], ["Всего сотрудников", 200, 210],
                 ["turnover", "0,5", ""]])
    result = hr.post("/api/hr/months/import", files={"file": ("m.xlsx", wide)}, data={"apply": "true"}).json()
    assert result["applied"] and result["summary"]["create"] == 3 and result["summary"]["create_months"] == 2
    long = csv_bytes([["Месяц", "Метрика", "Значение", "Примечание"], ["2031-01", "Всего сотрудников", "201", "1С"],
                      ["2031-02", "turnover", "", "уточнить"]])
    plan = hr.post("/api/hr/months/import", files={"file": ("m.csv", long)}).json()
    assert plan["summary"] == {"rows": 2, "create": 1, "update": 1, "unchanged": 0, "errors": 0, "create_months": 0}
    hr.post("/api/hr/months/import", files={"file": ("m.csv", long)}, data={"apply": "true"})
    month = hr.get("/api/hr/months/2031-01").json()
    metric = next(m for m in month["metrics"] if m["key"] == "total_employees")
    assert metric["value"] == 201 and metric["source_note"] == "1С"
    assert db.scalar(select(DataImport.dataset).order_by(DataImport.id.desc())) == "hr_months"


def test_months_import_errors(hr):
    content = xlsx([["Метрика", "2031-01"], ["Нет такой", 1], ["Всего сотрудников", "много"],
                    ["Всего сотрудников", 5]])
    response = hr.post("/api/hr/months/import", files={"file": ("m.xlsx", content)}, data={"apply": "true"})
    assert response.status_code == 409 and response.json()["code"] == "import_has_errors"
    errors = [e for r in response.json()["rows"] for e in r["errors"]]
    assert any("не найдена" in e for e in errors) and any("не число" in e for e in errors)
    bad_month = xlsx([["Метрика", "Q1"], ["Всего сотрудников", 1]])
    assert hr.post("/api/hr/months/import", files={"file": ("m.xlsx", bad_month)}).status_code == 422
    assert hr.post("/api/hr/months/import", files={"file": ("m.xlsx", xlsx([["А", "Б"]]))}).status_code == 422


def test_months_import_needs_editor(login):
    content = xlsx([["Метрика", "2031-01"], ["Всего сотрудников", 1]])
    assert login("viewer").post("/api/hr/months/import", files={"file": ("m.xlsx", content)}).status_code == 403


# ---------------------------------------------------------------- реестр приёмов и увольнений

def test_events_export_import_round_trip(hr):
    exported = hr.get("/api/hr/events/export.xlsx").content
    plan = hr.post("/api/hr/events/import", files={"file": ("r.xlsx", exported)}).json()
    assert plan["can_apply"] and plan["summary"]["create"] == 0 and plan["summary"]["unchanged"] > 10


def test_events_import_create_update_and_errors(hr, db):
    result = hr.post("/api/hr/events/import", files={"file": ("r.xlsx", hr_events_file())},
                     data={"apply": "true"}).json()
    assert result["applied"] and result["summary"]["hired"] == 1 and result["summary"]["fired"] == 1
    assert result["summary"]["create_months"] == 1
    update = xlsx([["Событие", "Дата", "ФИО", "Должность"], ["принят", "12.01.2031", "тестов тест тестович",
                                                            "Ведущий аналитик"]])
    plan = hr.post("/api/hr/events/import", files={"file": ("u.xlsx", update)}).json()
    assert plan["summary"]["update"] == 1 and plan["rows"][0]["changes"][0]["after"] == "Ведущий аналитик"
    hr.post("/api/hr/events/import", files={"file": ("u.xlsx", update)}, data={"apply": "true"})
    assert db.scalar(select(HrEmployeeEvent.position).where(HrEmployeeEvent.full_name == "Тестов Тест Тестович")) \
        == "Ведущий аналитик"
    bad = xlsx([["Месяц", "Событие", "Дата", "ФИО"], ["2031-02", "Приём", "2031-01-12", "А"],
                ["", "Перевод", "2031-01-12", "Б"], ["", "Приём", "вчера", "В"], ["", "Приём", "2031-01-12", ""]])
    errors = [e for r in hr.post("/api/hr/events/import", files={"file": ("b.xlsx", bad)}).json()["rows"]
              for e in r["errors"]]
    assert len(errors) == 4 and any("вне месяца" in e for e in errors)
    no_columns = xlsx([["ФИО", "Должность"], ["А", "Б"]])
    assert hr.post("/api/hr/events/import", files={"file": ("n.xlsx", no_columns)}).status_code == 422


def test_events_import_needs_personal_data(login, db):
    from app.models import User

    hr_head = db.scalar(select(User).where(User.username == "hr_head"))
    hr_head.access_overrides = {"data_classes": ["operational"]}
    db.commit()
    response = login("hr_head").post("/api/hr/events/import", files={"file": ("r.xlsx", hr_events_file())})
    assert response.status_code == 403


# ---------------------------------------------------------------- партнёрства

def test_partnerships_export_import_round_trip(login):
    product = login("product")
    exported = product.get("/api/partnerships/export.xlsx").content
    plan = product.post("/api/partnerships/import", files={"file": ("p.xlsx", exported)}).json()
    assert plan["can_apply"] and plan["summary"]["create"] == 0 and plan["summary"]["update"] == 0
    assert plan["summary"]["unchanged"] == 142


def test_partnerships_import_by_id_key_and_errors(login, db):
    product = login("product")
    result = product.post("/api/partnerships/import", files={"file": ("p.xlsx", partnerships_file())},
                          data={"apply": "true"}).json()
    assert result["applied"] and result["created"] == 1
    created = db.scalar(select(Partnership).where(Partnership.partner == "ООО Новый партнёр"))
    assert created.nda is True and created.agreement is False and str(created.cert_date) == "2031-01-10"
    by_key = xlsx([["Партнёр", "Продукт партнёра", "Версия", "Статус"],
                   ["ооо новый   партнёр", "Продукт X", "АльтерОС 8", "Завершено"]])
    plan = product.post("/api/partnerships/import", files={"file": ("k.xlsx", by_key)}).json()
    assert plan["summary"]["update"] == 1 and plan["rows"][0]["id"] == created.id
    by_id = xlsx([["№", "Партнёр", "Комментарий"], [created.id, "", "по номеру"], [999999, "Другой", ""]])
    plan = product.post("/api/partnerships/import", files={"file": ("i.xlsx", by_id)}).json()
    assert [r["action"] for r in plan["rows"]] == ["update", "create"] and plan["rows"][1]["warnings"]
    bad = xlsx([["Партнёр", "NDA", "Дата сертификата"], ["", "", ""], ["А", "может", "вчера"]])
    response = product.post("/api/partnerships/import", files={"file": ("b.xlsx", bad)}, data={"apply": "true"})
    assert response.status_code == 409
    assert login("viewer").post("/api/partnerships/import", files={"file": ("p.xlsx", by_key)}).status_code == 403
    assert product.post("/api/partnerships/import", files={"file": ("n.xlsx", xlsx([["Статус"], ["x"]]))}) \
        .status_code == 422


# ---------------------------------------------------------------- план ТП и Naumen

def test_tp_plan_does_not_write(db):
    row = [None] * 42
    row[0], row[1], row[2] = 2030, 1, 10
    records, skipped = tp_service.parse_upload("w.xlsx", xlsx([*tp_service.XLSX_HEADERS, row]))
    before = db.scalar(select(func.count()).select_from(tp_service.TpWeeklyReport))
    plan = tp_service.plan_import(db, records, skipped, "replace")
    assert plan["summary"]["delete"] == before and plan["summary"]["create"] == 1 and plan["can_apply"]
    assert db.scalar(select(func.count()).select_from(tp_service.TpWeeklyReport)) == before
    with pytest.raises(Exception, match="merge или replace"):
        tp_service.plan_import(db, records, skipped, "wipe")


def test_naumen_plan_counts(db):
    records, skipped = naumen.parse_xlsx(naumen_file())
    plan = naumen.plan_import(db, records + records[:1], skipped)
    assert plan["summary"]["create"] == 2 and plan["summary"]["skipped"] == 1 and plan["summary"]["rows"] == 3
    assert db.scalar(select(func.count()).select_from(NaumenTicket).where(NaumenTicket.number == 990001)) == 0


def test_partnerships_plan_is_json_safe(db):
    import json

    from fastapi.encoders import jsonable_encoder

    plan = partnerships.plan_import(db, partnerships.parse_upload("p.xlsx", partnerships_file()))
    assert json.dumps(jsonable_encoder(plan), ensure_ascii=False)
