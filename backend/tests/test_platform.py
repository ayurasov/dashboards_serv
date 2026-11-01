"""Светофор, журнал, палитры, раскладки, обзор, PDF, состояние системы."""
import pytest

from app.models import TrafficLightRule
from app.services import traffic_light


@pytest.mark.parametrize(("value", "direction", "green", "yellow", "expected"), [
    (3, "lower_is_better", 5, 8, "green"), (6, "lower_is_better", 5, 8, "yellow"),
    (9, "lower_is_better", 5, 8, "red"), (95, "higher_is_better", 90, 75, "green"),
    (80, "higher_is_better", 90, 75, "yellow"), (60, "higher_is_better", 90, 75, "red"),
    (None, "higher_is_better", 90, 75, "gray"), (5, "lower_is_better", 5, 8, "green"),
])
def test_evaluate(value, direction, green, yellow, expected):
    rule = TrafficLightRule(metric_key="m", direction=direction, green_threshold=green, yellow_threshold=yellow,
                            enabled=True)
    assert traffic_light.evaluate(value, rule) == expected


def test_disabled_rule_is_gray():
    rule = TrafficLightRule(metric_key="m", direction="lower_is_better", green_threshold=1, yellow_threshold=2,
                            enabled=False)
    assert traffic_light.evaluate(100, rule) == "gray"


def test_worst_and_counts():
    assert traffic_light.worst(["green", "yellow", "gray"]) == "yellow"
    assert traffic_light.worst(["gray"]) == "gray"
    assert traffic_light.counts(["red", "red", "green"]) == {"green": 1, "yellow": 0, "red": 2, "gray": 0}


def test_light_rules_listing_and_update(admin):
    rules = admin.get("/api/traffic-light/hr").json()
    assert len(rules) == 16 and rules[0]["group"] == "Численность"
    turnover = next(r for r in rules if r["metric_key"] == "turnover")
    assert turnover["direction"] == "lower_is_better" and turnover["enabled"]
    body = {"direction": "lower_is_better", "green_threshold": 4, "yellow_threshold": 6, "enabled": True}
    assert admin.put("/api/traffic-light/hr/turnover", json=body).json()["green_threshold"] == 4
    swapped = admin.put("/api/traffic-light/hr/turnover", json={**body, "green_threshold": 7})
    assert swapped.status_code == 422
    missing = admin.put("/api/traffic-light/hr/turnover", json={**body, "yellow_threshold": None})
    assert missing.status_code == 422
    off = admin.put("/api/traffic-light/hr/turnover", json={**body, "yellow_threshold": None, "enabled": False})
    assert off.status_code == 200
    assert admin.put("/api/traffic-light/hr/nope", json=body).status_code == 404
    assert admin.get("/api/traffic-light/project_product").status_code == 404


def test_audit_pagination_filters_export(admin):
    for month in (9, 10, 11):
        admin.post("/api/hr/months", json={"year": 2026, "month": month})
    page = admin.get("/api/audit", params={"entity_type": "hr_month", "page_size": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    assert page["items"][0]["occurred_at"] >= page["items"][1]["occurred_at"]
    second = admin.get("/api/audit", params={"entity_type": "hr_month", "page_size": 2, "page": 2}).json()
    assert len(second["items"]) == 1
    searched = admin.get("/api/audit", params={"search": "ноябрь"}).json()
    assert searched["total"] == 1
    facets = admin.get("/api/audit/facets").json()
    assert "hr_month" in facets["entity_types"] and "login" in facets["actions"]
    csv = admin.get("/api/audit/export.csv")
    assert csv.status_code == 200 and "Добавлен месяц" in csv.content.decode("utf-8-sig")


def test_audit_never_stores_secrets(admin):
    admin.post("/api/users", json={"username": "secretive", "full_name": "С паролем", "password": "Very-secret-1"})
    for item in admin.get("/api/audit").json()["items"]:
        assert "Very-secret-1" not in str(item)


def test_palettes(admin, login):
    active = login("viewer").get("/api/palette/active").json()
    assert active["is_active"] and active["colors"]["traffic_light"]
    palettes = admin.get("/api/palettes").json()
    assert {p["name"] for p in palettes} >= {"Сдержанная", "Мягкая", "Классическая"}
    colors = {"traffic_light": {"green": "#00aa00", "yellow": "#ffaa00", "red": "#ff0000", "neutral": "#999999"},
              "charts": ["#123456", "#abcdef"], "brand": {"primary": "#c8302c", "muted": "#666"}}
    created = admin.post("/api/palettes", json={"name": "Корпоративная", "colors": colors})
    assert created.status_code == 201
    pid = created.json()["id"]
    assert admin.post("/api/palettes", json={"name": "Корпоративная", "colors": colors}).status_code == 422
    assert admin.post("/api/palettes", json={"name": "Плохая", "colors": {**colors, "charts": ["red"]}}).status_code \
        == 422
    assert admin.post(f"/api/palettes/{pid}/activate").json()["is_active"]
    assert login("viewer").get("/api/palette/active").json()["name"] == "Корпоративная"
    assert admin.delete(f"/api/palettes/{pid}").status_code == 422
    preset = next(p for p in palettes if p["name"] == "Мягкая")
    admin.post(f"/api/palettes/{preset['id']}/activate")
    assert admin.delete(f"/api/palettes/{preset['id']}").status_code == 422
    assert admin.delete(f"/api/palettes/{pid}").status_code == 200


def test_layouts(login):
    c = login("viewer")
    assert c.get("/api/layouts/hr").json() == {"service_key": "hr", "widgets": []}
    widgets = [{"key": "kpi", "size": "wide", "visible": True, "order": 0},
               {"key": "turnover", "size": "small", "visible": False, "order": 1}]
    assert c.put("/api/layouts/hr", json={"widgets": widgets}).json()["widgets"] == widgets
    assert c.put("/api/layouts/hr", json={"widgets": widgets + [widgets[0]]}).status_code == 422
    assert c.put("/api/layouts/hr", json={"widgets": [{"key": "x", "size": "huge"}]}).status_code == 422
    assert c.delete("/api/layouts/hr").status_code == 200
    assert login("tp_lead").get("/api/layouts/hr").status_code == 403


def test_overview(login):
    data = login("hr_head").get("/api/overview").json()
    cards = {c["key"]: c for c in data["services"]}
    assert set(cards) == {"hr", "tech", "project_product"}
    assert cards["hr"]["period"] == "Июль 2026" and cards["hr"]["kpis"][0]["label"] == "Принято"
    assert cards["tech"]["kpis"] and cards["project_product"]["kpis"][0]["value"] == 142
    assert data["recent_imports"]
    scoped = login("it_viewer").get("/api/overview").json()
    assert {c["key"] for c in scoped["services"]} == {"hr", "it"}
    assert next(c for c in scoped["services"] if c["key"] == "it")["empty"]


@pytest.mark.parametrize("url", [
    "/api/pdf/hr/dashboard", "/api/pdf/hr/dashboard?months=2026-06", "/api/pdf/hr/summary?period_type=month",
    "/api/pdf/hr/registry?event_type=fired", "/api/pdf/hr/targets", "/api/pdf/tp/dashboard?weeks=8",
    "/api/pdf/tp/dashboard?year=2025", "/api/pdf/tp/naumen?year=2025", "/api/pdf/partnerships/registry?light=red",
    "/api/pdf/partnerships/summary",
])
def test_pdf_reports(admin, url):
    response = admin.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF") and len(response.content) > 5000


def test_pdf_respects_access(login):
    assert login("tp_lead").get("/api/pdf/hr/dashboard").status_code == 403
    assert login("product").get("/api/pdf/tp/naumen").status_code == 403


def test_health_and_version(client):
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and health["schema"]["current"] == health["schema"]["head"]
    assert client.get("/api/version").json()["version"] == "0.1.0"


def test_system_info(admin):
    info = admin.get("/api/system/info").json()
    assert info["database"]["dialect"] == "sqlite" and info["database"]["schema_ok"]
    assert info["counts"]["partnerships"] == 142


def test_unknown_api_path_is_json_404(client):
    response = client.get("/api/nothing-here")
    assert response.status_code == 404 and response.json()["code"] == "not_found"


def test_validation_errors_are_russian(admin):
    response = admin.post("/api/hr/months", json={"year": "abc"})
    body = response.json()
    assert response.status_code == 422 and body["code"] == "validation_error"
    assert body["fields"]["year"] == "Нужно целое число" and body["fields"]["month"] == "Обязательное поле"


def test_security_headers(client):
    headers = client.get("/api/version").headers
    assert headers["x-content-type-options"] == "nosniff" and headers["x-frame-options"] == "DENY"
    assert headers["cache-control"] == "no-store" and headers["x-request-id"]


def test_openapi_is_generated(client):
    schema = client.get("/api/openapi.json").json()
    assert schema["info"]["version"] == "0.1.0"
    assert "/api/hr/analytics/dashboard" in schema["paths"] and "/api/tp/naumen/import" in schema["paths"]


def test_response_cache_is_invalidated_by_writes(admin, login):
    from app.services.cache import cache

    cache.clear()
    viewer = login("viewer")
    first = viewer.get("/api/hr/analytics/dashboard", params={"months": "2026-07"}).json()
    again = viewer.get("/api/hr/analytics/dashboard", params={"months": "2026-07"}).json()
    assert first == again and cache.hits >= 1
    admin.put("/api/hr/months/2026-07/metrics", json=[{"metric_key": "turnover", "value": 9.9}])
    fresh = viewer.get("/api/hr/analytics/dashboard", params={"months": "2026-07"}).json()
    turnover = next(m for m in fresh["series"][0]["metrics"] if m["key"] == "turnover")
    assert turnover["value"] == 9.9 and turnover["light"] == "red"


def test_cache_respects_department_scope(login):
    full = login("viewer").get("/api/hr/events").json()
    scoped = login("it_viewer").get("/api/hr/events").json()
    assert len(scoped) < len(full)


def test_revision_bumps_only_for_changed_service(admin, db):
    from app.services.cache import revisions

    before = {k: rev for k, rev, _ts in revisions(db, ["hr", "tech"])}
    admin.post("/api/tp/reports", json={"year": 2031, "week": 1})
    db.expire_all()
    after = {k: rev for k, rev, _ts in revisions(db, ["hr", "tech"])}
    assert after["tech"] == before["tech"] + 1 and after["hr"] == before["hr"]
