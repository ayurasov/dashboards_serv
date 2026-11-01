"""Матрица доступа: кто что видит и меняет в каждой службе."""
import pytest

READS = {
    "hr": ["/api/hr/months", "/api/hr/analytics/dashboard", "/api/hr/events", "/api/hr/targets",
           "/api/pdf/hr/summary", "/api/traffic-light/hr", "/api/dashboards"],
    "tech": ["/api/tp/reports", "/api/tp/columns", "/api/tp/naumen/summary", "/api/tp/naumen/match",
             "/api/traffic-light/tech", "/api/pdf/tp/naumen"],
    "project_product": ["/api/partnerships", "/api/partnerships/analytics", "/api/partnerships/summary",
                        "/api/partnerships/light-rules", "/api/pdf/partnerships/summary"],
}

# Демо-пользователи: hr_head — персонал: управление, партнёрства и ТП: просмотр;
# tp_lead — ТП: управление; product — партнёрства: управление; viewer — всё на просмотр;
# it_viewer — персонал: просмотр своих подразделений.
EXPECTED_READ = {
    "hr_head": {"hr", "tech", "project_product"},
    "tp_lead": {"tech"},
    "product": {"project_product"},
    "viewer": {"hr", "tech", "project_product"},
    "it_viewer": {"hr"},
}


@pytest.mark.parametrize("username", sorted(EXPECTED_READ))
def test_read_access_by_service(login, username):
    c = login(username)
    for service, urls in READS.items():
        allowed = service in EXPECTED_READ[username]
        for url in urls:
            status = c.get(url).status_code
            assert (status == 200) == allowed, f"{username} {url} → {status}"


def test_services_list_reflects_access(login):
    services = login("tp_lead").get("/api/services").json()
    assert [(s["key"], s["level"]) for s in services] == [("tech", "manager")]


def test_admin_sees_every_service(admin):
    keys = [s["key"] for s in admin.get("/api/services").json()]
    assert keys[:3] == ["hr", "tech", "project_product"] and len(keys) == 9


def test_viewer_cannot_change_data(login):
    c = login("viewer")
    assert c.post("/api/hr/months", json={"year": 2031, "month": 1}).status_code == 403
    assert c.post("/api/tp/reports", json={"year": 2031, "week": 1}).status_code == 403
    assert c.post("/api/partnerships", json={"partner": "Тест"}).status_code == 403
    response = c.put("/api/traffic-light/hr/turnover", json={"direction": "lower_is_better", "green_threshold": 1,
                                                             "yellow_threshold": 2, "enabled": True})
    assert response.status_code == 403


def test_forbidden_message_names_the_level(admin, login):
    viewer = next(u for u in admin.get("/api/users").json() if u["username"] == "viewer")
    admin.put(f"/api/users/{viewer['id']}/access", json=[{"service_key": "hr", "level": "editor"}])
    c = login("viewer")
    assert c.post("/api/hr/months", json={"year": 2031, "month": 2}).status_code == 201
    response = c.delete("/api/hr/months/2031-02")
    assert response.status_code == 403
    assert response.json()["detail"] == "Нужен уровень доступа «Управление» к службе «Служба персонала»"
    no_access = c.get("/api/tp/reports").json()["detail"]
    assert no_access == "Нет доступа к службе «Техническая поддержка»"


def test_manager_can_configure_service(login):
    c = login("tp_lead")
    response = c.put("/api/traffic-light/tech/total_in_work",
                     json={"direction": "lower_is_better", "green_threshold": 150, "yellow_threshold": 200,
                           "enabled": True})
    assert response.status_code == 200
    assert c.put("/api/traffic-light/hr/turnover", json={"direction": "lower_is_better", "green_threshold": 1,
                                                         "yellow_threshold": 2, "enabled": True}).status_code == 403


def test_department_scope_limits_registry(login, admin):
    scoped = login("it_viewer").get("/api/hr/events").json()
    everything = admin.get("/api/hr/events").json()
    assert scoped and len(scoped) < len(everything)
    assert {e["department"] for e in scoped} == {"ИТ-служба"}
    month = login("it_viewer").get("/api/hr/months/2026-06").json()
    assert month["department_scope"] and all(e["department"] == "ИТ-служба" for e in month["events"])


def test_admin_pages_forbidden_for_non_admins(login):
    c = login("hr_head")
    for url in ("/api/audit", "/api/palettes", "/api/system/info", "/api/departments"):
        assert c.get(url).status_code == 403, url
