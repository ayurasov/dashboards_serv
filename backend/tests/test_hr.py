"""Служба персонала: месяцы, метрики, реестр, аналитика, цели."""
import io

import pytest
from openpyxl import load_workbook

from app.services import hr as hr_service


def test_months_list(admin):
    months = admin.get("/api/hr/months").json()
    assert [m["key"] for m in months][:2] == ["2026-01", "2026-02"]
    june = next(m for m in months if m["key"] == "2026-06")
    assert june["label"] == "Июнь 2026" and june["hired"] == 2 and june["fired"] == 6
    assert june["filled_metrics"] > 10 and june["total_metrics"] == 16


def test_create_month_and_duplicates(admin):
    assert admin.post("/api/hr/months", json={"year": 2026, "month": 8, "comment": "Отпуска"}).status_code == 201
    assert admin.post("/api/hr/months", json={"year": 2026, "month": 8}).status_code == 409
    assert admin.post("/api/hr/months", json={"year": 2026, "month": 13}).status_code == 422


def test_month_detail_has_lights_and_deltas(admin):
    month = admin.get("/api/hr/months/2026-07").json()
    assert month["previous_key"] == "2026-06"
    turnover = next(m for m in month["metrics"] if m["key"] == "turnover")
    assert turnover["value"] == 2.0 and turnover["previous"] == 3.87
    assert turnover["delta"] == pytest.approx(-1.87)
    assert turnover["light"] == "green" and turnover["target"] == 5.0
    assert admin.get("/api/hr/months/2026-13").status_code == 422
    assert admin.get("/api/hr/months/1999-01").status_code == 422
    assert admin.get("/api/hr/months/2025-01").status_code == 404


def test_save_metrics_upserts_and_audits(admin):
    payload = [{"metric_key": "turnover", "value": 4.2, "source_note": "по данным 1С"},
               {"metric_key": "avg_time_to_fill", "value": None}]
    response = admin.put("/api/hr/months/2026-07/metrics", json=payload)
    assert response.status_code == 200 and "Сохранено значений: 2" in response.json()["message"]
    metrics = {m["key"]: m for m in admin.get("/api/hr/months/2026-07").json()["metrics"]}
    assert metrics["turnover"]["value"] == 4.2 and metrics["turnover"]["source_note"] == "по данным 1С"
    # Незаполненная метрика со светофором — «Нет данных» (серая) и отдельная отметка о нарушении
    assert metrics["avg_time_to_fill"]["value"] is None and metrics["avg_time_to_fill"]["light"] == "gray"
    assert metrics["avg_time_to_fill"]["missing"] is True
    assert admin.put("/api/hr/months/2026-07/metrics", json=payload).json()["message"] == "Изменений нет"
    unknown = admin.put("/api/hr/months/2026-07/metrics", json=[{"metric_key": "nope", "value": 1}])
    assert unknown.status_code == 422
    audit = admin.get("/api/audit", params={"entity_type": "hr_metrics"}).json()
    assert audit["total"] == 1 and audit["items"][0]["after"]["turnover"] == 4.2


def test_events_crud_with_date_validation(admin):
    event = {"event_type": "hired", "event_date": "2026-07-20", "full_name": "Иванова Анна Сергеевна",
             "position": "Аналитик", "department": "ИТ-служба", "employment_type": "ТД"}
    created = admin.post("/api/hr/months/2026-07/events", json=event)
    assert created.status_code == 201
    event_id = created.json()["id"]
    wrong_month = admin.post("/api/hr/months/2026-07/events", json={**event, "event_date": "2026-06-30"})
    assert wrong_month.status_code == 422 and "event_date" in wrong_month.json()["fields"]
    updated = admin.patch(f"/api/hr/events/{event_id}", json={**event, "event_type": "fired", "reason": "Собственное"})
    assert updated.json()["event_type"] == "fired" and updated.json()["reason"] == "Собственное"
    assert admin.delete(f"/api/hr/events/{event_id}").status_code == 200
    assert admin.delete(f"/api/hr/events/{event_id}").status_code == 404


def test_events_filters(admin):
    fired_june = admin.get("/api/hr/events", params={"month": "2026-06", "event_type": "fired"}).json()
    assert len(fired_june) == 6 and all(e["event_type"] == "fired" for e in fired_june)
    marketing = admin.get("/api/hr/events", params={"department": "Служба маркетинга"}).json()
    assert marketing and all(e["department"] == "Служба маркетинга" for e in marketing)
    found = admin.get("/api/hr/events", params={"search": "лапин"}).json()
    assert [e["full_name"] for e in found] == ["Лапин Максим Витальевич"]


def test_events_export_xlsx(admin):
    response = admin.get("/api/hr/events/export.xlsx", params={"month": "2026-06"})
    assert response.status_code == 200
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    ws = load_workbook(io.BytesIO(response.content)).active
    assert ws.max_row == 1 + 8 and ws["A1"].value == "Месяц"


def test_notes(admin):
    note = admin.post("/api/hr/months/2026-07/notes", json={"content": "Проверить данные о найме"})
    assert note.status_code == 201 and note.json()["author"] == "Администратор системы"
    notes = admin.get("/api/hr/months/2026-07").json()["notes"]
    assert any(n["content"] == "Проверить данные о найме" for n in notes)
    assert admin.delete(f"/api/hr/notes/{note.json()['id']}").status_code == 200


def test_month_comment_and_delete(admin):
    assert admin.patch("/api/hr/months/2026-01", json={"comment": "Сверено с бухгалтерией"}).status_code == 200
    assert admin.get("/api/hr/months/2026-01").json()["comment"] == "Сверено с бухгалтерией"
    assert admin.delete("/api/hr/months/2026-01").status_code == 200
    assert admin.get("/api/hr/months/2026-01").status_code == 404


def test_dashboard_uses_last_filled_month(admin):
    admin.post("/api/hr/months", json={"year": 2026, "month": 8})
    data = admin.get("/api/hr/analytics/dashboard").json()
    assert data["latest"]["key"] == "2026-07"
    assert data["totals"]["hired"] == sum(s["hired"] for s in data["series"])
    selected = admin.get("/api/hr/analytics/dashboard", params={"months": "2026-06,2026-07"}).json()
    assert selected["selected"] == ["2026-06", "2026-07"] and len(selected["series"]) == 2
    assert selected["departments"][0]["department"]
    assert admin.get("/api/hr/analytics/dashboard", params={"months": "bad"}).status_code == 422


def test_period_summary_aggregation(admin):
    quarters = admin.get("/api/hr/analytics/summary", params={"period_type": "quarter"}).json()
    q2 = next(q for q in quarters if q["key"] == "2026-Q2")
    assert q2["label"] == "2 кв. 2026" and q2["months"] == ["2026-04", "2026-05", "2026-06"]
    # «latest» — значение последнего месяца, «sum» — сумма
    assert q2["metrics"]["turnover"] == 3.87
    months = ["2026-04", "2026-05", "2026-06"]
    assert q2["metrics"]["resumes_screened"] == sum(_values(admin, "resumes_screened", months))
    assert set(q2["light_counts"]) == {"green", "yellow", "red", "gray"}
    years = admin.get("/api/hr/analytics/summary", params={"period_type": "year"}).json()
    assert [y["label"] for y in years] == ["2026 год"]
    assert admin.get("/api/hr/analytics/summary", params={"period_type": "week"}).status_code == 422


def _values(admin, key, months):
    out = []
    for m in months:
        metric = next(x for x in admin.get(f"/api/hr/months/{m}").json()["metrics"] if x["key"] == key)
        out.append(metric["value"])
    return out


def test_targets_crud_and_status(admin, login):
    rows = admin.get("/api/hr/targets").json()
    turnover = next(r for r in rows if r["metric_key"] == "turnover" and r["year"] == 2026)
    assert turnover["current_value"] == 2.0 and turnover["status"] == "green"
    viewer = login("viewer")
    assert viewer.patch(f"/api/hr/targets/{turnover['id']}", json={"target_value": 1}).status_code == 403
    updated = admin.patch(f"/api/hr/targets/{turnover['id']}", json={"target_value": 1.9})
    assert updated.json()["status"] == "yellow"
    assert admin.patch(f"/api/hr/targets/{turnover['id']}", json={"target_value": 1.0}).json()["status"] == "red"
    created = admin.post("/api/hr/targets", json={"metric_key": "turnover_company", "year": 2026,
                                                  "target_value": 2.5})
    assert created.status_code == 201 and created.json()["label"] == "Цель 2026"
    assert admin.post("/api/hr/targets", json={"metric_key": "turnover_company", "year": 2026}).status_code == 409
    assert admin.delete(f"/api/hr/targets/{created.json()['id']}").status_code == 200


@pytest.mark.parametrize(("current", "target", "lower", "expected"), [
    (5.0, 5.0, True, "green"), (5.4, 5.0, True, "yellow"), (5.6, 5.0, True, "red"),
    (95, 95, False, "green"), (90, 95, False, "yellow"), (80, 95, False, "red"), (None, 1, True, "gray"),
])
def test_target_status(current, target, lower, expected):
    assert hr_service.target_status(current, target, lower) == expected


@pytest.mark.parametrize(("values", "method", "expected"), [
    ([1, 2, 3], "sum", 6), ([1, 2, 3], "avg", 2), ([1, 2, 3], "latest", 3), ([1, 5, 3], "max", 5), ([], "avg", None),
])
def test_aggregate(values, method, expected):
    assert hr_service.aggregate(values, method) == expected


def test_custom_dashboards(admin, login):
    body = {"name": "Мой найм", "widgets": [
        {"widget_type": "metric_card", "title": "Офферы", "config": {"metric_key": "offers_accepted_pct"}},
        {"widget_type": "line_chart", "config": {"metric_keys": ["turnover", "turnover_company"]}},
        {"widget_type": "note", "config": {"text": "Заметка"}}]}
    created = admin.post("/api/dashboards", json=body)
    assert created.status_code == 201 and len(created.json()["widgets"]) == 3
    viewer = login("viewer")
    assert viewer.get("/api/dashboards").json() == []
    shared = viewer.post("/api/dashboards", json={**body, "is_shared": True})
    assert shared.status_code == 403
    admin.put(f"/api/dashboards/{created.json()['id']}", json={**body, "is_shared": True})
    seen = viewer.get("/api/dashboards").json()
    assert seen[0]["name"] == "Мой найм" and seen[0]["can_edit"] is False
    assert viewer.delete(f"/api/dashboards/{created.json()['id']}").status_code == 403
    bad = admin.post("/api/dashboards", json={"name": "x", "widgets": [{"widget_type": "line_chart", "config": {}}]})
    assert bad.status_code == 422


def test_missing_metrics_are_no_data_but_flagged(admin):
    """Решение владельца продукта: незаполненный показатель со светофором — «Нет данных»,
    а сам факт незаполненного поля — критичное нарушение (список missing на дашборде и в «Обзоре»)."""
    admin.put("/api/hr/months/2026-07/metrics", json=[{"metric_key": "turnover", "value": None}])
    dashboard = admin.get("/api/hr/analytics/dashboard", params={"months": "2026-07"}).json()
    july = dashboard["series"][-1]
    turnover = next(m for m in july["metrics"] if m["key"] == "turnover")
    assert turnover["light"] == "gray" and turnover["missing"] is True
    assert "Текучесть кадров" in july["missing"]
    hr_card = next(s for s in admin.get("/api/overview").json()["services"] if s["key"] == "hr")
    assert "Текучесть кадров" in hr_card["missing"]
    assert admin.get("/api/pdf/hr/dashboard", params={"months": "2026-07"}).content.startswith(b"%PDF")
