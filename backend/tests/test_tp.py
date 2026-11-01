"""Техподдержка: недельный отчёт, импорт, экспорт, настройки."""
import io

import pytest
from openpyxl import Workbook, load_workbook

from app.services import tp as tp_service


@pytest.fixture()
def lead(login):
    return login("tp_lead")


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Лист1"
    for header in tp_service.XLSX_HEADERS:
        ws.append(header)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row(year, week, in_work, solved=None):
    out = [None] * 42
    out[0], out[1], out[2] = year, week, in_work
    out[22] = solved
    return out


def test_columns_cover_all_metrics(lead):
    cols = lead.get("/api/tp/columns").json()
    assert len(cols) == 39 and cols[0]["group_label"] == "Нагрузка"


def test_reports_sorted_with_period(lead):
    rows = lead.get("/api/tp/reports").json()
    assert len(rows) == 109
    assert [(r["year"], r["week"]) for r in rows] == sorted((r["year"], r["week"]) for r in rows)
    assert rows[-1]["period"] == f"{rows[-1]['year']}-W{rows[-1]['week']:02d}"
    assert len(lead.get("/api/tp/reports", params={"year": 2025}).json()) == 51


def test_report_crud_and_unique_week(lead):
    created = lead.post("/api/tp/reports", json={"year": 2030, "week": 5, "total_in_work": 210, "note": "праздники"})
    assert created.status_code == 201 and created.json()["period"] == "2030-W05"
    dup = lead.post("/api/tp/reports", json={"year": 2030, "week": 5})
    assert dup.status_code == 409 and "week" in dup.json()["fields"]
    assert lead.post("/api/tp/reports", json={"year": 2030, "week": 54}).status_code == 422
    rid = created.json()["id"]
    patched = lead.patch(f"/api/tp/reports/{rid}", json={"total_in_work": 199.5, "week": 6})
    assert patched.json()["total_in_work"] == 199.5 and patched.json()["period"] == "2030-W06"
    assert lead.delete(f"/api/tp/reports/{rid}").status_code == 200
    assert lead.patch(f"/api/tp/reports/{rid}", json={"note": "x"}).status_code == 404


def test_import_xlsx_merge(lead):
    rows = lead.get("/api/tp/reports").json()
    last = rows[-1]
    content = _xlsx([_row(last["year"], last["week"], 111, 20), _row(2030, 1, 150, 30), _row(None, None, 1)])
    response = lead.post("/api/tp/reports/import", data={"mode": "merge"},
                         files={"file": ("Итоговый отчёт.xlsx", content)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["rows_created"], body["rows_updated"], body["rows_skipped"]) == (1, 1, 1)
    after = lead.get("/api/tp/reports").json()
    assert len(after) == 110
    assert next(r for r in after if r["id"] == last["id"])["total_in_work"] == 111
    imports = lead.get("/api/imports", params={"service": "tech"}).json()
    assert imports[0]["filename"] == "Итоговый отчёт.xlsx" and imports[0]["username"] == "tp_lead"


def test_import_replace(lead):
    content = _xlsx([_row(2030, 1, 100), _row(2030, 2, 120), _row(2030, 2, 130)])
    body = lead.post("/api/tp/reports/import", data={"mode": "replace"},
                     files={"file": ("week.xlsx", content)}).json()
    assert body["rows_created"] == 2 and body["rows_skipped"] == 1
    rows = lead.get("/api/tp/reports").json()
    assert [(r["week"], r["total_in_work"]) for r in rows] == [(1, 100), (2, 130)]


def test_import_requires_manager(login):
    content = _xlsx([_row(2030, 1, 100)])
    response = login("viewer").post("/api/tp/reports/import", files={"file": ("w.xlsx", content)})
    assert response.status_code == 403


def test_import_rejects_bad_files(lead):
    assert lead.post("/api/tp/reports/import", files={"file": ("a.txt", b"hello")}).status_code == 422
    assert lead.post("/api/tp/reports/import", files={"file": ("a.xlsx", b"not excel")}).status_code == 422
    assert lead.post("/api/tp/reports/import", files={"file": ("a.csv", b"")}).status_code == 422


def test_csv_round_trip(lead):
    exported = lead.get("/api/tp/reports/export.csv")
    assert exported.status_code == 200 and exported.content.startswith("﻿".encode())
    body = lead.post("/api/tp/reports/import", data={"mode": "replace"},
                     files={"file": ("export.csv", exported.content)}).json()
    assert body["rows_created"] == 109
    rows = lead.get("/api/tp/reports").json()
    original = tp_service.parse_csv(exported.content)[0]
    assert rows[10]["avail_total"] == original[10]["avail_total"]


def test_export_xlsx_keeps_source_layout(lead):
    response = lead.get("/api/tp/reports/export.xlsx")
    ws = load_workbook(io.BytesIO(response.content)).active
    assert ws.title == "Лист1" and ws["A1"].value == "Год" and ws.max_row == 4 + 109
    records, skipped = tp_service.parse_xlsx(response.content)
    assert len(records) == 109 and skipped == 0


def test_settings_roundtrip(lead, login):
    assert lead.get("/api/tp/settings/block_settings").json() == {"key": "block_settings", "value": {}}
    saved = lead.put("/api/tp/settings/block_settings", json={"value": {"channels": False}})
    assert saved.json()["value"] == {"channels": False}
    assert login("viewer").get("/api/tp/settings/block_settings").json()["value"] == {"channels": False}
    assert login("viewer").put("/api/tp/settings/block_settings", json={"value": {}}).status_code == 403
    assert lead.get("/api/tp/settings/unknown").status_code == 404


@pytest.mark.parametrize(("raw", "expected"), [
    ("1 234,5", 1234.5), ("—", None), ("", None), (12, 12.0), ("abc", None), ("3.5", 3.5),
])
def test_to_number(raw, expected):
    assert tp_service.to_number(raw) == expected
