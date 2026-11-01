"""Входящие данные (ADR-0011): распознавание всех наборов, план и применение через конвейер, повтор,
«применять сразу» и ожидание, права, загрузка в интерфейсе, повтор обработки, срок хранения."""
from __future__ import annotations

import hashlib
import io
import json
from datetime import date, datetime, timedelta

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from app.models import (
    AuditEntry,
    DataRevision,
    HrEmployeeEvent,
    HrMetricValue,
    HrMonth,
    InboxItem,
    InboxRule,
    IndicatorValue,
    NaumenTicket,
    Partnership,
    TpWeeklyReport,
    User,
)
from app.services import inbox, org_transfer
from app.services import inbox_datasets as datasets
from app.services import tp as tp_service

# Построенные книги кэшируются: openpyxl пишет текущее время (свойства книги, даты записей zip)
# с точностью до секунды, и два построения одного файла на границе секунды давали разные байты —
# а тесты повторов ждут одинаковый SHA-256
_XLSX_CACHE: dict[str, bytes] = {}


def xlsx(rows, title="Лист1") -> bytes:
    key = repr((rows, title))
    if key in _XLSX_CACHE:
        return _XLSX_CACHE[key]
    wb = Workbook()
    ws = wb.active
    ws.title = title
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    _XLSX_CACHE[key] = buf.getvalue()
    return _XLSX_CACHE[key]


def csv_bytes(rows) -> bytes:
    return ("﻿" + "\n".join(";".join(str(c) for c in row) for row in rows)).encode("utf-8")


# ---------------------------------------------------------------- образцы файлов каждого набора

def hr_months_file() -> bytes:
    return xlsx([["Метрика", "Ключ", "Единица", "2031-01", "2031-02"],
                 ["Всего сотрудников", "total_employees", "чел.", 200, 205],
                 ["Текучесть кадров", "", "%", "0,7", None]])


def hr_events_file() -> bytes:
    return xlsx([["Месяц", "Событие", "Дата", "ФИО", "Должность", "Подразделение", "Тип занятости", "Причина"],
                 ["2031-01", "Приём", "2031-01-12", "Тестов Тест Тестович", "Аналитик", "ИТ-служба", "ТД", ""],
                 ["2031-01", "Увольнение", "15.01.2031", "Пробный Пётр", "Инженер", "Техническая служба", "",
                  "Переезд"]])


def tp_file() -> bytes:
    row = [None] * 42
    row[0], row[1], row[2], row[22] = 2031, 2, 150, 30
    return xlsx([*tp_service.XLSX_HEADERS, row])


def naumen_file() -> bytes:
    header = ["Номер", "Название", "Дата регистрации", "Дата решения", "Статус", "Наименование организации"]
    return xlsx([header, [990001, "Тест", datetime(2031, 1, 5, 10, 0), None, "Зарегистрирована", "ООО Тест"],
                 [990002, "Тест 2", datetime(2031, 1, 6, 10, 0), datetime(2031, 1, 7, 10), "Закрыта", "ООО Тест"]])


def partnerships_file() -> bytes:
    return xlsx([["№", "Партнёр", "Продукт партнёра", "Направление", "Продукт АЛМИ", "Версия", "Тип", "Статус",
                  "Дата сертификата", "NDA", "Соглашение", "Светофор", "Битрикс", "Сайт", "Комментарий"],
                 ["", "ООО Новый партнёр", "Продукт X", "СУБД", "АльтерОС", "АльтерОС 8", "ПО", "В работе",
                  "2031-01-10", "да", "нет", "Норма", "", "", "из входящих"]])


def indicators_file() -> bytes:
    return csv_bytes([["Подразделение", "Показатель", "Период", "Значение", "Цель", "Комментарий"],
                      ["COMM", "fin.revenue", "2031-01", "61,5", "64", "из 1С"]])


def structure_file(db) -> bytes:
    bundle = org_transfer.export_structure(db)
    bundle["departments"].append({"key": "new-1", "name": "Отдел входящих", "parent": bundle["departments"][0]["key"],
                                  "kind": "department", "sort_order": 99, "code": "INBOX", "heads": []})
    return json.dumps(bundle, ensure_ascii=False).encode("utf-8")


def employees_file() -> bytes:
    return csv_bytes([["Email", "ФИО", "Должность", "Подразделение"],
                      ["inbox.person@example.com", "Входящий Сотрудник", "Аналитик", "ИТ-служба"]])


SAMPLES = {
    "hr-months": ("Метрики.xlsx", lambda db: hr_months_file()),
    "hr-events": ("Реестр.xlsx", lambda db: hr_events_file()),
    "tp-weekly": ("Итоговый отчёт ТП.xlsx", lambda db: tp_file()),
    "naumen": ("Выгрузка.xlsx", lambda db: naumen_file()),
    "partnerships": ("Реестр.xlsx", lambda db: partnerships_file()),
    "indicators": ("values.csv", lambda db: indicators_file()),
    "structure": ("export.json", structure_file),
    "employees": ("staff.csv", lambda db: employees_file()),
}


def _rule(db, source, dataset, value=True):
    db.merge(InboxRule(source=source, dataset=dataset, auto_apply=value))
    db.commit()


def _revision(db, service):
    return db.scalar(select(DataRevision.revision).where(DataRevision.service_key == service))


# ---------------------------------------------------------------- распознавание

@pytest.mark.parametrize("key", list(SAMPLES))
def test_every_dataset_is_detected(db, key):
    name, build = SAMPLES[key]
    handler, scores = datasets.detect(name, build(db))
    assert handler is not None and handler.key == key, scores


def test_unknown_file_is_not_detected():
    assert datasets.detect("notes.txt", "просто текст\nбез таблицы".encode())[0] is None
    assert datasets.detect("x.xlsx", xlsx([["Что-то", "другое"]]))[0] is None
    assert datasets.detect("x.bin", b"\x00\x01\x02")[0] is None


def test_filename_pattern_breaks_ties():
    # Таблица со столбцом «Партнёр» без столбцов продукта — по содержимому не набор, по имени — да
    content = xlsx([["Партнёр", "Статус"], ["ООО", "В работе"]])
    assert datasets.detect("x.xlsx", content)[0] is None
    assert datasets.get("partnerships").score(datasets.peek("реестр партнёрств.xlsx", content)) == 20


def test_json_format_converter_extension_point(db):
    """Формат другой системы подключается переводом в формат набора (так подключит «По Делу»)."""
    bundle = org_transfer.export_structure(db)

    def convert(doc):
        return {**bundle, "departments": bundle["departments"] + [
            {"key": "x", "name": doc["units"][0], "parent": bundle["departments"][0]["key"], "heads": []}]}

    datasets.register_json_format("partner.org", "structure", convert)
    try:
        content = json.dumps({"format": "partner.org", "units": ["Отдел партнёра"]}).encode()
        assert datasets.detect("org.json", content)[0].key == "structure"
        item = inbox.add(db, content, "org.json", source="api", label="тест")
        db.commit()
        assert item.status == "pending" and item.plan["summary"]["create"] == 1
    finally:
        datasets.JSON_FORMATS.pop("partner.org")


# ---------------------------------------------------------------- план и применение каждого набора

CHECKS = {
    "hr-months": lambda db: db.scalar(select(HrMetricValue.value).join(HrMonth).where(
        HrMonth.year == 2031, HrMonth.month == 2, HrMetricValue.metric_key == "total_employees")) == 205,
    "hr-events": lambda db: db.scalar(select(func.count()).select_from(HrEmployeeEvent).where(
        HrEmployeeEvent.event_date >= date(2031, 1, 1))) == 2,
    "tp-weekly": lambda db: db.scalar(select(TpWeeklyReport.total_in_work).where(
        TpWeeklyReport.year == 2031, TpWeeklyReport.week == 2)) == 150,
    "naumen": lambda db: db.scalar(select(func.count()).select_from(NaumenTicket).where(
        NaumenTicket.number.in_([990001, 990002]))) == 2,
    "partnerships": lambda db: db.scalar(select(Partnership.comment).where(
        Partnership.partner == "ООО Новый партнёр")) == "из входящих",
    "indicators": lambda db: db.scalar(select(IndicatorValue.value).where(
        IndicatorValue.period == date(2031, 1, 1), IndicatorValue.comment == "из 1С")) == 61.5,
    "structure": lambda db: "INBOX" in {d["code"] for d in org_transfer.export_structure(db)["departments"]},
    "employees": lambda db: db.scalar(select(User.full_name).where(
        User.email == "inbox.person@example.com")) == "Входящий Сотрудник",
}
REVISIONS = {"hr-months": "hr", "hr-events": "hr", "tp-weekly": "tech", "naumen": "tech",
             "partnerships": "project_product"}


@pytest.mark.parametrize("key", list(SAMPLES))
def test_plan_then_apply_every_dataset(db, key):
    name, build = SAMPLES[key]
    content = build(db)
    item = inbox.add(db, content, name, source="folder", source_ref=f"{key}/{name}", label="Входящие · папка")
    db.commit()
    assert item.dataset == key and item.status == "pending", (item.error, item.message)
    assert item.plan["can_apply"] and item.plan["summary"]["errors"] == 0
    assert "не включено «применять сразу»" in item.message
    assert not CHECKS[key](db), "план не пишет в базу"

    admin = db.scalar(select(User).where(User.username == "admin"))
    service = REVISIONS.get(key)
    before = _revision(db, service) if service else None
    applied = inbox.apply(db, item.id, admin)
    db.commit()
    assert applied.status == "applied", (applied.error, applied.message)
    assert applied.applied_by == "admin" and applied.result["applied"]
    assert CHECKS[key](db)
    if service:
        assert _revision(db, service) > before
    actions = set(db.scalars(select(AuditEntry.action).where(AuditEntry.entity_type == "inbox_item",
                                                             AuditEntry.entity_id == str(item.id))))
    assert {"receive", "apply"} <= actions


# ---------------------------------------------------------------- повтор

def test_same_file_twice_is_a_duplicate(db):
    content = tp_file()
    first = inbox.add(db, content, "a.xlsx", source="folder", label="папка")
    second = inbox.add(db, content, "b.xlsx", source="api", label="ключ")
    db.commit()
    assert first.status == "pending" and second.status == "duplicate"
    assert second.duplicate_of_id == first.id and not second.has_content and "№" in second.message
    # Тот же файл как другой набор — не повтор
    other = inbox.add(db, content, "a.xlsx", source="folder", dataset="partnerships", label="папка")
    assert other.status != "duplicate"
    # Отклонённый файл можно прислать снова — он обработается заново
    admin = db.scalar(select(User).where(User.username == "admin"))
    inbox.reject(db, first.id, admin, "не та неделя")
    again = inbox.add(db, content, "c.xlsx", source="folder", label="папка")
    db.commit()
    assert again.status == "pending" and again.duplicate_of_id is None


def test_duplicate_race_is_caught_by_unique_index(db, monkeypatch):
    """Два процесса одновременно приняли один файл: второй упирается в уникальный индекс и становится повтором."""
    content = tp_file()
    first = inbox.add(db, content, "a.xlsx", source="folder", label="папка")
    db.commit()
    real = inbox._live_twin
    calls = {"n": 0}

    def blind(*args, **kwargs):
        calls["n"] += 1
        return None if calls["n"] == 1 else real(*args, **kwargs)

    monkeypatch.setattr(inbox, "_live_twin", blind)
    second = inbox.add(db, content, "a.xlsx", source="folder", label="папка")
    db.commit()
    assert second.status == "duplicate" and second.duplicate_of_id == first.id
    assert db.scalar(select(func.count()).select_from(InboxItem).where(InboxItem.sha256 == first.sha256)) == 2


# ---------------------------------------------------------------- «применять сразу» и ожидание

def test_auto_apply_by_rule_and_source_actor(db):
    _rule(db, "folder", "tp-weekly")
    before = _revision(db, "tech")
    item = inbox.add(db, tp_file(), "w.xlsx", source="folder", label="Входящие · папка")
    db.commit()
    assert item.status == "applied" and item.applied_by == "Входящие · папка" and item.applied_by_id is None
    assert item.result["created"] == 1 and _revision(db, "tech") > before
    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "tp_week", AuditEntry.action == "import")
                      .order_by(AuditEntry.id.desc()))
    assert entry.username == "Входящие · папка" and entry.user_id is None, "журнал — от имени источника"
    # Правило не для этого источника — ждёт
    other = inbox.add(db, partnerships_file(), "p.xlsx", source="api", label="ключ")
    assert other.status == "pending"


def test_apply_false_waits_even_with_rule(db):
    _rule(db, "api", "tp-weekly")
    item = inbox.add(db, tp_file(), "w.xlsx", source="api", label="ключ", apply=False)
    assert item.status == "pending" and "только план" in item.message


def test_plan_with_errors_waits_and_is_not_applied(db):
    _rule(db, "folder", "indicators")
    content = csv_bytes([["Подразделение", "Показатель", "Период", "Значение"],
                         ["Нет такого отдела", "fin.revenue", "2031-01", "1"]])
    item = inbox.add(db, content, "v.csv", source="folder", label="папка")
    db.commit()
    assert item.status == "pending" and not item.plan["can_apply"] and "ошибки" in item.message
    assert inbox.plan_errors(item.plan) and "не найдено" in inbox.plan_errors(item.plan)[0]
    admin = db.scalar(select(User).where(User.username == "admin"))
    with pytest.raises(inbox.PlanHasErrors):
        inbox.apply(db, item.id, admin)


def test_broken_file_is_an_error(db):
    item = inbox.add(db, b"not excel at all", "x.xlsx", source="folder", dataset="tp-weekly", label="папка")
    assert item.status == "error" and "Excel" in item.error and item.has_content


def test_unrecognized_waits_for_dataset_then_retry(db):
    content = csv_bytes([["Что-то", "Непонятное"], ["1", "2"]])
    item = inbox.add(db, content, "x.csv", source="folder", label="папка")
    db.commit()
    assert item.status == "received" and item.dataset is None and "не распознан" in item.message
    admin = db.scalar(select(User).where(User.username == "admin"))
    retried = inbox.retry(db, item.id, admin, dataset="hr-events")
    assert retried.status == "error" and "Событие" in retried.error
    good = inbox.add(db, hr_events_file(), "reg.bin", source="folder", label="папка")
    assert good.dataset == "hr-events"


def test_too_large_and_empty(db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "inbox_max_mb", 1)
    big = inbox.add(db, b"x" * (1024 * 1024 + 1), "big.csv", source="folder", label="папка")
    empty = inbox.add(db, b"", "e.csv", source="folder", label="папка")
    assert big.status == empty.status == "error" and "1 МБ" in big.error and "пустой" in empty.error
    assert not big.has_content


def test_retention_purges_content_of_finished_items(db):
    admin = db.scalar(select(User).where(User.username == "admin"))
    done = inbox.add(db, tp_file(), "w.xlsx", source="folder", label="папка")
    inbox.apply(db, done.id, admin)
    waiting = inbox.add(db, partnerships_file(), "p.xlsx", source="folder", label="папка")
    db.commit()
    from app.core.db import utcnow

    assert inbox.purge(db) == 0
    assert inbox.purge(db, utcnow() + timedelta(days=400)) == 1
    db.commit()
    db.expire_all()
    assert not db.get(InboxItem, done.id).has_content and db.get(InboxItem, done.id).content_purged_at
    assert db.get(InboxItem, waiting.id).has_content, "ожидающий элемент хранится"
    assert inbox.item_out(db.get(InboxItem, done.id), admin)["actions"]["download"] is False


# ---------------------------------------------------------------- API «Входящие»

def test_api_upload_plan_apply_and_download(login, db):
    hr = login("hr_head")
    response = hr.post("/api/inbox", files={"file": ("Метрики.xlsx", hr_months_file())})
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["status"] == "pending" and item["dataset"] == "hr-months" and item["received_by"] == "hr_head"
    assert item["actions"]["apply"] and item["plan"]["summary"]["create_months"] == 2
    assert item["summary"]["create"] == 3 and item["option_fields"] == []
    file = hr.get(f"/api/inbox/{item['id']}/file")
    assert file.status_code == 200 and hashlib.sha256(file.content).hexdigest() == item["sha256"]
    assert "filename*=UTF-8''" in file.headers["content-disposition"]
    applied = hr.post(f"/api/inbox/{item['id']}/apply")
    assert applied.status_code == 200 and applied.json()["status"] == "applied", applied.text
    assert applied.json()["applied_by"] == "hr_head" and applied.json()["actions"]["apply"] is False
    again = hr.post(f"/api/inbox/{item['id']}/apply")
    assert again.status_code == 409 and again.json()["code"] == "wrong_status"
    month = hr.get("/api/hr/months/2031-02").json()
    assert next(m for m in month["metrics"] if m["key"] == "total_employees")["value"] == 205


def test_api_upload_with_apply_flag_and_options(login):
    lead = login("tp_lead")
    response = lead.post("/api/inbox", files={"file": ("w.xlsx", tp_file())},
                         data={"apply": "true", "options": json.dumps({"mode": "merge"})})
    assert response.status_code == 201 and response.json()["status"] == "applied", response.text
    assert response.json()["options"] == {"mode": "merge"}
    bad = lead.post("/api/inbox", files={"file": ("w2.xlsx", tp_file())}, data={"options": json.dumps({"mode": "x"})})
    assert bad.status_code == 422


def test_api_access_rules(login, admin):
    assert login("viewer").get("/api/inbox").status_code == 403
    lead = login("tp_lead")
    forbidden = lead.post("/api/inbox", files={"file": ("Метрики.xlsx", hr_months_file())})
    assert forbidden.status_code == 403 and forbidden.json()["code"] == "dataset_forbidden"
    item = admin.post("/api/inbox", files={"file": ("Метрики.xlsx", hr_months_file())}).json()
    assert lead.get(f"/api/inbox/{item['id']}").status_code == 404, "чужой набор не виден"
    assert lead.post(f"/api/inbox/{item['id']}/apply").status_code == 404
    hr = login("hr_head")
    assert hr.get(f"/api/inbox/{item['id']}").status_code == 200
    listing = lead.get("/api/inbox").json()
    assert all(i["dataset"] in ("tp-weekly", "naumen", "indicators") for i in listing["items"])
    datasets_out = lead.get("/api/inbox/datasets").json()
    allowed = {d["key"] for d in datasets_out["datasets"] if d["can_apply"]}
    assert allowed == {"tp-weekly", "naumen", "indicators"} and not datasets_out["can_manage"]
    assert lead.get("/api/inbox/rules").status_code == 403


def test_data_manage_capability(login, admin, db):
    """data.manage: видит всё и применяет любой набор от имени источника, а журнал — на себя."""
    viewer = db.scalar(select(User).where(User.username == "viewer"))
    assert admin.patch(f"/api/users/{viewer.id}", json={"capabilities": ["data.manage"]}).status_code == 200
    v = login("viewer")
    item = v.post("/api/inbox", files={"file": ("values.csv", indicators_file())}).json()
    assert item["dataset"] == "indicators" and item["plan"]["can_apply"], item
    applied = v.post(f"/api/inbox/{item['id']}/apply").json()
    assert applied["status"] == "applied", applied
    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == "indicator_value",
                                               AuditEntry.action == "import").order_by(AuditEntry.id.desc()))
    assert entry.user_id == viewer.id and entry.username == "viewer"
    assert v.get("/api/inbox/rules").status_code == 200


def test_api_list_filters_counts_and_paging(admin, db):
    for name, build in (("w.xlsx", tp_file), ("p.xlsx", partnerships_file)):
        admin.post("/api/inbox", files={"file": (name, build())})
    admin.post("/api/inbox", files={"file": ("w-copy.xlsx", tp_file())})
    data = admin.get("/api/inbox").json()
    assert data["total"] == 3 and data["counts"]["pending"] == 2 and data["counts"]["duplicate"] == 1
    assert admin.get("/api/inbox", params={"status": "duplicate"}).json()["total"] == 1
    assert admin.get("/api/inbox", params={"dataset": "partnerships"}).json()["total"] == 1
    assert admin.get("/api/inbox", params={"q": "COPY"}).json()["total"] == 1
    assert admin.get("/api/inbox", params={"source": "api"}).json()["total"] == 0
    page = admin.get("/api/inbox", params={"page_size": 2, "page": 2}).json()
    assert len(page["items"]) == 1 and page["page"] == 2
    from app.core.timeutil import local_today

    today = local_today().isoformat()
    assert admin.get("/api/inbox", params={"date_from": today, "date_to": today}).json()["total"] == 3
    assert admin.get("/api/inbox", params={"status": "unknown"}).status_code == 422


def test_api_reject_and_retry(admin):
    item = admin.post("/api/inbox", files={"file": ("w.xlsx", tp_file())}).json()
    rejected = admin.post(f"/api/inbox/{item['id']}/reject", json={"reason": "лишний"}).json()
    assert rejected["status"] == "rejected" and "лишний" in rejected["message"]
    assert admin.post(f"/api/inbox/{item['id']}/reject").status_code == 409
    retried = admin.post(f"/api/inbox/{item['id']}/retry", json={"apply": True}).json()
    assert retried["status"] == "applied", retried
    assert admin.post(f"/api/inbox/{item['id']}/retry").json()["code"] == "wrong_status"


def test_api_apply_conflict_returns_fresh_plan(admin):
    content = csv_bytes([["Подразделение", "Показатель", "Период", "Значение"], ["Нет такого", "fin.revenue",
                                                                              "2031-01", "1"]])
    item = admin.post("/api/inbox", files={"file": ("v.csv", content)}).json()
    response = admin.post(f"/api/inbox/{item['id']}/apply")
    assert response.status_code == 409 and response.json()["code"] == "import_has_errors"
    assert response.json()["item"]["plan"]["summary"]["errors"] == 1


def test_api_rules(admin, login):
    rules = admin.get("/api/inbox/rules").json()
    assert len(rules) == 3 * 8 and not any(r["auto_apply"] for r in rules)
    saved = admin.put("/api/inbox/rules", json={"rules": [{"source": "folder", "dataset": "naumen",
                                                           "auto_apply": True}]})
    assert saved.status_code == 200
    assert next(r for r in saved.json() if r["source"] == "folder" and r["dataset"] == "naumen")["auto_apply"]
    assert admin.put("/api/inbox/rules", json={"rules": [{"source": "upload", "dataset": "naumen",
                                                          "auto_apply": True}]}).status_code == 422
    assert admin.put("/api/inbox/rules", json={"rules": [{"source": "api", "dataset": "nope",
                                                          "auto_apply": True}]}).status_code == 422
    datasets_out = admin.get("/api/inbox/datasets").json()
    naumen = next(d for d in datasets_out["datasets"] if d["key"] == "naumen")
    assert naumen["rules"] == {"folder": True, "api": False, "integration": False}
    assert login("hr_head").put("/api/inbox/rules", json={"rules": []}).status_code == 403


def test_api_upload_limits(admin, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "inbox_max_mb", 1)
    big = admin.post("/api/inbox", files={"file": ("big.csv", b"x" * (1024 * 1024 + 10))})
    assert big.status_code == 413 and big.json()["code"] == "payload_too_large"
    assert admin.post("/api/inbox", files={"file": ("e.csv", b"")}).status_code == 422
    assert admin.post("/api/inbox", files={"file": ("a.csv", b"x")}, data={"dataset": "nope"}).status_code == 422
    assert admin.post("/api/inbox", files={"file": ("a.csv", b"x")}, data={"options": "[1]"}).status_code == 422


def test_indicator_items_of_others_are_hidden_from_service_editors(admin, login):
    """План файла от источника строится со всеми классами данных: чужие элементы показателей видит только
    ведущий отчётов, а редактор службы — свои загрузки (план — с его правами)."""
    foreign = admin.post("/api/inbox", files={"file": ("values.csv", indicators_file())}).json()
    lead = login("tp_lead")
    assert lead.get(f"/api/inbox/{foreign['id']}").status_code == 404
    mine = csv_bytes([["Подразделение", "Показатель", "Период", "Значение"], ["COMM", "fin.revenue", "2031-02", "7"]])
    own = lead.post("/api/inbox", files={"file": ("mine.csv", mine)})
    assert own.status_code == 201 and own.json()["dataset"] == "indicators"
    detail = lead.get(f"/api/inbox/{own.json()['id']}").json()
    assert detail["plan"]["summary"]["errors"] == 1, "выручку вводит финансовая служба — у него нет права"
    assert {i["id"] for i in lead.get("/api/inbox").json()["items"]} == {own.json()["id"]}


def test_download_content_type_is_not_taken_from_sender(admin):
    item = admin.post("/api/inbox", files={"file": ("x.html", b"<script>alert(1)</script>", "text/html")}).json()
    response = admin.get(f"/api/inbox/{item['id']}/file")
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")
