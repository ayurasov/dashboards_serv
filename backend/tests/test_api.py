"""Backend tests for HR Dashboard API."""
import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app
from app.seed import seed_all

SQLALCHEMY_TEST_URL = "sqlite:///./test_hr.db"
engine = create_engine(SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    seed_all(db)
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def get_auth_token(client, username="admin", password="admin123"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


class TestAuth:
    def test_login_admin(self, client):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "admin"
        assert data["must_change_password"] is True
        assert "access_token" in data

    def test_login_wrong_password(self, client):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401

    def test_me(self, client):
        token = get_auth_token(client)
        r = client.get("/api/auth/me", headers=auth_header(token))
        assert r.status_code == 200
        assert r.json()["username"] == "admin"
        assert r.json()["role"] == "admin"

    def test_me_no_token(self, client):
        r = client.get("/api/auth/me")
        assert r.status_code == 401


class TestProfile:
    def test_update_own_profile(self, client):
        token = get_auth_token(client)
        r = client.put("/api/auth/profile", json={
            "full_name": "Иванов Иван Иванович",
            "email": "ivanov@almi.ru",
            "phone": "+7 900 123-45-67",
            "avatar": "data:image/png;base64,AAAA",
        }, headers=auth_header(token))
        assert r.status_code == 200
        data = r.json()
        assert data["full_name"] == "Иванов Иван Иванович"
        assert data["email"] == "ivanov@almi.ru"
        assert data["phone"] == "+7 900 123-45-67"
        assert data["avatar"] == "data:image/png;base64,AAAA"
        # persisted
        assert client.get("/api/auth/me", headers=auth_header(token)).json()["phone"] == "+7 900 123-45-67"

    def test_partial_update_keeps_other_fields(self, client):
        token = get_auth_token(client)
        client.put("/api/auth/profile", json={"phone": "+7 000"}, headers=auth_header(token))
        r = client.put("/api/auth/profile", json={"full_name": "Новое Имя"}, headers=auth_header(token))
        assert r.status_code == 200
        assert r.json()["phone"] == "+7 000"
        assert r.json()["full_name"] == "Новое Имя"

    def test_blank_contacts_are_cleared(self, client):
        token = get_auth_token(client)
        client.put("/api/auth/profile", json={"phone": "+7 000"}, headers=auth_header(token))
        r = client.put("/api/auth/profile", json={"phone": ""}, headers=auth_header(token))
        assert r.json()["phone"] is None

    def test_viewer_can_edit_own_profile(self, client):
        token = get_auth_token(client, "viewer", "view123")
        r = client.put("/api/auth/profile", json={"full_name": "Смотрящий"}, headers=auth_header(token))
        assert r.status_code == 200
        assert r.json()["full_name"] == "Смотрящий"

    def test_profile_cannot_change_role(self, client):
        token = get_auth_token(client, "viewer", "view123")
        r = client.put("/api/auth/profile", json={"role": "admin"}, headers=auth_header(token))
        assert r.status_code == 200
        assert r.json()["role"] == "viewer"

    def test_empty_full_name_rejected(self, client):
        token = get_auth_token(client)
        assert client.put("/api/auth/profile", json={"full_name": "   "},
                          headers=auth_header(token)).status_code == 400
        assert client.put("/api/auth/profile", json={"full_name": ""},
                          headers=auth_header(token)).status_code == 422

    def test_duplicate_email_rejected(self, client):
        token = get_auth_token(client)
        other = get_auth_token(client, "viewer", "view123")
        client.put("/api/auth/profile", json={"email": "dup@almi.ru"}, headers=auth_header(other))
        r = client.put("/api/auth/profile", json={"email": "dup@almi.ru"}, headers=auth_header(token))
        assert r.status_code == 400

    def test_oversized_avatar_rejected(self, client):
        token = get_auth_token(client)
        r = client.put("/api/auth/profile", json={"avatar": "d" * 2_000_001}, headers=auth_header(token))
        assert r.status_code == 400

    def test_profile_requires_auth(self, client):
        assert client.put("/api/auth/profile", json={"full_name": "X"}).status_code == 401


class TestRBAC:
    def test_viewer_cannot_create_month(self, client):
        token = get_auth_token(client, "viewer", "view123")
        r = client.post("/api/hr/months", json={"year": 2026, "month": 8, "notes": ""},
                        headers=auth_header(token))
        assert r.status_code == 403

    def test_hr_head_can_create_month(self, client):
        token = get_auth_token(client, "hr_head", "hr123")
        r = client.post("/api/hr/months", json={"year": 2026, "month": 8, "notes": "test"},
                        headers=auth_header(token))
        assert r.status_code == 200

    def test_viewer_cannot_access_audit(self, client):
        token = get_auth_token(client, "viewer", "view123")
        r = client.get("/api/audit", headers=auth_header(token))
        assert r.status_code == 403

    def test_admin_can_access_audit(self, client):
        token = get_auth_token(client)
        r = client.get("/api/audit", headers=auth_header(token))
        assert r.status_code == 200

    def test_department_viewer_can_login(self, client):
        token = get_auth_token(client, "it_viewer", "it123")
        r = client.get("/api/auth/me", headers=auth_header(token))
        assert r.status_code == 200
        assert r.json()["role"] == "department_viewer"
        assert len(r.json()["departments"]) > 0

    def test_department_viewer_cannot_edit(self, client):
        token = get_auth_token(client, "it_viewer", "it123")
        r = client.post("/api/hr/months", json={"year": 2026, "month": 8},
                        headers=auth_header(token))
        assert r.status_code == 403


class TestHRData:
    def test_months(self, client):
        token = get_auth_token(client)
        r = client.get("/api/hr/months", headers=auth_header(token))
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        assert data[0]["key"] == "2026-06"

    def test_metric_definitions(self, client):
        token = get_auth_token(client)
        r = client.get("/api/hr/metric-definitions", headers=auth_header(token))
        assert r.status_code == 200
        assert len(r.json()) == 16

    def test_analytics_month(self, client):
        token = get_auth_token(client)
        r = client.get("/api/hr/analytics/month/2026-06", headers=auth_header(token))
        assert r.status_code == 200
        data = r.json()
        assert data["hired"] == 2
        assert data["fired"] == 6
        assert data["net"] == -4
        assert len(data["metrics"]) > 0

    def test_summary(self, client):
        token = get_auth_token(client)
        r = client.get("/api/hr/analytics/summary?period_type=quarter", headers=auth_header(token))
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1


class TestSummaryRange:
    """`from_period` / `to_period` narrow the summary to a span of period labels."""

    # httpx drops a URL query string when `params` is also given, so every bound
    # here travels in `params` alongside period_type.
    def summary(self, client, token, **params):
        params.setdefault("period_type", "quarter")
        return client.get("/api/hr/analytics/summary", params=params,
                          headers=auth_header(token))

    def all_labels(self, client, token, period_type="quarter"):
        r = self.summary(client, token, period_type=period_type)
        assert r.status_code == 200
        return [p["label"] for p in r.json()]

    def test_omitting_bounds_returns_every_period(self, client):
        token = get_auth_token(client)
        labels = self.all_labels(client, token)
        # The seeded months straddle two quarters, so the range has something to cut.
        assert len(labels) >= 2

    def test_single_bound_trims_one_side(self, client):
        token = get_auth_token(client)
        labels = self.all_labels(client, token)
        r = self.summary(client, token, from_period=labels[-1])
        assert [p["label"] for p in r.json()] == [labels[-1]]

        r = self.summary(client, token, to_period=labels[0])
        assert [p["label"] for p in r.json()] == [labels[0]]

    def test_both_bounds_are_inclusive(self, client):
        token = get_auth_token(client)
        labels = self.all_labels(client, token)
        r = self.summary(client, token, from_period=labels[0], to_period=labels[-1])
        assert [p["label"] for p in r.json()] == labels

    def test_inverted_range_is_swapped(self, client):
        token = get_auth_token(client)
        labels = self.all_labels(client, token)
        r = self.summary(client, token, from_period=labels[-1], to_period=labels[0])
        assert [p["label"] for p in r.json()] == labels

    def test_half_year_and_year_ranges(self, client):
        token = get_auth_token(client)
        for period_type in ("half", "year"):
            labels = self.all_labels(client, token, period_type)
            r = self.summary(client, token, period_type=period_type,
                             from_period=labels[0], to_period=labels[0])
            assert [p["label"] for p in r.json()] == [labels[0]]

    def test_unknown_period_rejected(self, client):
        token = get_auth_token(client)
        r = self.summary(client, token, from_period="Q1 1999")
        assert r.status_code == 400
        assert "Q1 1999" in r.json()["detail"]

    def test_pdf_accepts_the_same_range(self, client):
        token = get_auth_token(client)
        labels = self.all_labels(client, token)
        r = client.get("/api/pdf/summary",
                       params={"period_type": "quarter",
                               "from_period": labels[0], "to_period": labels[0]},
                       headers=auth_header(token))
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"


class TestMonthDeletion:
    def test_delete_month_removes_metrics_and_employees(self, client, db):
        from app.models import MetricValue, EmployeeEvent, MonthRecord
        token = get_auth_token(client)
        mr = db.query(MonthRecord).filter(MonthRecord.year == 2026, MonthRecord.month == 6).first()
        month_id = mr.id
        assert db.query(MetricValue).filter(MetricValue.month_record_id == month_id).count() > 0
        assert db.query(EmployeeEvent).filter(EmployeeEvent.month_record_id == month_id).count() > 0

        r = client.delete("/api/hr/months/2026-06", headers=auth_header(token))
        assert r.status_code == 200

        assert db.query(MonthRecord).filter(MonthRecord.id == month_id).first() is None
        assert db.query(MetricValue).filter(MetricValue.month_record_id == month_id).count() == 0
        assert db.query(EmployeeEvent).filter(EmployeeEvent.month_record_id == month_id).count() == 0

        r = client.get("/api/hr/months", headers=auth_header(token))
        assert [m["key"] for m in r.json()] == ["2026-07"]

    def test_delete_month_unknown(self, client):
        token = get_auth_token(client)
        r = client.delete("/api/hr/months/2099-01", headers=auth_header(token))
        assert r.status_code == 404

    def test_delete_month_bad_key(self, client):
        token = get_auth_token(client)
        r = client.delete("/api/hr/months/nope", headers=auth_header(token))
        assert r.status_code == 400

    def test_delete_month_forbidden_for_viewer(self, client):
        token = get_auth_token(client, "viewer", "view123")
        r = client.delete("/api/hr/months/2026-06", headers=auth_header(token))
        assert r.status_code == 403


class TestTrafficLight:
    def test_list_rules(self, client):
        token = get_auth_token(client)
        r = client.get("/api/traffic-light", headers=auth_header(token))
        assert r.status_code == 200
        assert len(r.json()) == 7

    def test_update_rule_admin(self, client):
        token = get_auth_token(client)
        r = client.put("/api/traffic-light/turnover", json={"green_threshold": 4, "yellow_threshold": 6, "enabled": True},
                       headers=auth_header(token))
        assert r.status_code == 200
        assert r.json()["green_threshold"] == 4

    def test_update_rule_viewer_forbidden(self, client):
        token = get_auth_token(client, "viewer", "view123")
        r = client.put("/api/traffic-light/turnover", json={"green_threshold": 4},
                       headers=auth_header(token))
        assert r.status_code == 403

    def test_light_follows_direction(self, client):
        """June turnover is 3.87 with thresholds 5/8: green when lower is better, red when flipped."""
        token = get_auth_token(client)
        light = lambda: next(m for m in client.get("/api/hr/analytics/month/2026-06",
                                                  headers=auth_header(token)).json()["metrics"]
                             if m["key"] == "turnover")
        assert light()["light"] == "green"
        r = client.put("/api/traffic-light/turnover", json={"direction": "higher_is_better"},
                       headers=auth_header(token))
        assert r.status_code == 200
        assert r.json()["direction"] == "higher_is_better"
        flipped = light()
        assert flipped["light"] == "red"
        assert flipped["direction"] == "lower_is_better"  # the definition, unchanged

    def test_yellow_band_respects_direction(self, client):
        token = get_auth_token(client)
        # offers_accepted_pct is 100 in June; higher is better with green 85 / yellow 65.
        client.put("/api/traffic-light/offers_accepted_pct",
                   json={"green_threshold": 120, "yellow_threshold": 90, "direction": "higher_is_better"},
                   headers=auth_header(token))
        metrics = client.get("/api/hr/analytics/month/2026-06", headers=auth_header(token)).json()["metrics"]
        assert next(m for m in metrics if m["key"] == "offers_accepted_pct")["light"] == "yellow"

    def test_with_metrics_uses_rule_direction(self, client):
        token = get_auth_token(client)
        client.put("/api/traffic-light/offers_accepted_pct", json={"direction": "lower_is_better"},
                   headers=auth_header(token))
        rows = client.get("/api/traffic-light/with-metrics", headers=auth_header(token)).json()
        row = next(r for r in rows if r["metric_key"] == "offers_accepted_pct")
        assert row["direction"] == "lower_is_better"
        # A metric without a rule falls back to its definition; a "neutral"
        # definition has no light direction, so the form shows the default.
        assert next(r for r in rows if r["metric_key"] == "avg_time_to_fill")["direction"] == "lower_is_better"
        assert next(r for r in rows if r["metric_key"] == "resumes_screened")["direction"] == "higher_is_better"

    def test_unknown_direction_rejected(self, client):
        token = get_auth_token(client)
        r = client.put("/api/traffic-light/turnover", json={"direction": "sideways"},
                       headers=auth_header(token))
        assert r.status_code == 400
        assert "sideways" in r.json()["detail"]


class TestUnfilledMetrics:
    def test_all_definitions_returned(self, client):
        token = get_auth_token(client)
        defs = client.get("/api/hr/metric-definitions", headers=auth_header(token)).json()
        metrics = client.get("/api/hr/analytics/month/2026-07", headers=auth_header(token)).json()["metrics"]
        assert len(metrics) == len(defs)

    def test_unfilled_metric_is_red(self, client):
        token = get_auth_token(client)
        metrics = client.get("/api/hr/analytics/month/2026-07", headers=auth_header(token)).json()["metrics"]
        # July has no avg_time_to_fill value.
        m = next(x for x in metrics if x["key"] == "avg_time_to_fill")
        assert m["value"] is None
        assert m["text_value"] is None
        assert m["filled"] is False
        assert m["light"] == "red"

    def test_filled_metric_keeps_its_light(self, client):
        token = get_auth_token(client)
        metrics = client.get("/api/hr/analytics/month/2026-07", headers=auth_header(token)).json()["metrics"]
        m = next(x for x in metrics if x["key"] == "turnover")
        assert m["filled"] is True
        assert m["value"] == 2.0
        assert m["light"] == "green"
        assert m["category"] == "turnover"

    def test_metrics_follow_sort_order(self, client):
        token = get_auth_token(client)
        defs = client.get("/api/hr/metric-definitions", headers=auth_header(token)).json()
        metrics = client.get("/api/hr/analytics/month/2026-06", headers=auth_header(token)).json()["metrics"]
        assert [m["key"] for m in metrics] == [d["key"] for d in defs]
        assert metrics[0]["key"] == "total_employees"
        assert metrics[-1]["key"] == "turnover_company"


class TestMetricsEditAccess:
    def test_read_only_user_cannot_save_metrics(self, client):
        token = get_auth_token(client, "it_viewer", "it123")
        r = client.put("/api/hr/months/2026-07/metrics", json=[], headers=auth_header(token))
        assert r.status_code == 403

    def test_edit_metrics_grant_allows_save(self, client):
        admin = get_auth_token(client)
        users = client.get("/api/users", headers=auth_header(admin)).json()
        uid = next(u["id"] for u in users if u["username"] == "it_viewer")
        client.put(f"/api/users/{uid}/access", json={"service_key": "hr", "access_level": "edit_metrics"},
                   headers=auth_header(admin))
        token = get_auth_token(client, "it_viewer", "it123")
        r = client.put("/api/hr/months/2026-07/metrics",
                       json=[{"metric_key": "turnover", "numeric_value": 2.5}],
                       headers=auth_header(token))
        assert r.status_code == 200


class TestBenchmarks:
    @staticmethod
    def _row(client, token, metric_key, year=2026):
        rows = client.get("/api/hr/benchmarks", headers=auth_header(token)).json()
        return next(r for r in rows if r["metric_key"] == metric_key and r["year"] == year)

    def test_list_benchmarks(self, client):
        token = get_auth_token(client)
        r = client.get("/api/hr/benchmarks", headers=auth_header(token))
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 6
        row = self._row(client, token, "turnover")
        assert row["target_value"] == 5.0
        assert row["metric_label"] == "Текучесть кадров"
        assert row["unit"] == "%"
        assert row["direction"] == "lower_is_better"
        assert row["description"]

    def test_current_value_from_latest_month(self, client):
        token = get_auth_token(client)
        # July turnover is 2.0; avg_time_to_fill was only filled in June (35.0).
        assert self._row(client, token, "turnover")["current_value"] == 2.0
        row = self._row(client, token, "avg_time_to_fill")
        assert row["current_value"] == 35.0
        assert row["current_month"] == "Июнь 2026"

    def test_status_is_direction_aware(self, client):
        token = get_auth_token(client)
        # 2.0 <= target 5.0 and lower is better -> green
        assert self._row(client, token, "turnover")["status"] == "green"
        # 35 days against a 30-day target is more than 10% over -> red
        assert self._row(client, token, "avg_time_to_fill")["status"] == "red"
        # 100% offers accepted against a 90% target -> green
        assert self._row(client, token, "offers_accepted_pct")["status"] == "green"

    def test_reference_row_without_target_is_gray(self, client):
        token = get_auth_token(client)
        row = self._row(client, token, "turnover", year=2025)
        assert row["target_value"] is None
        assert row["status"] == "gray"
        assert row["diff"] is None

    def test_update_target_admin(self, client):
        token = get_auth_token(client)
        row = self._row(client, token, "avg_time_to_fill")
        r = client.put(f"/api/hr/benchmarks/{row['id']}", json={"target_value": 33.0},
                       headers=auth_header(token))
        assert r.status_code == 200
        body = r.json()
        assert body["target_value"] == 33.0
        assert body["diff"] == 2.0
        assert body["status"] == "yellow"  # 35 is within 10% of 33
        assert self._row(client, token, "avg_time_to_fill")["target_value"] == 33.0

    def test_update_target_hr_head_forbidden(self, client):
        token = get_auth_token(client)
        row = self._row(client, token, "turnover")
        hr_token = get_auth_token(client, "hr_head", "hr123")
        r = client.put(f"/api/hr/benchmarks/{row['id']}", json={"target_value": 1.0},
                       headers=auth_header(hr_token))
        assert r.status_code == 403

    def test_update_missing_benchmark(self, client):
        token = get_auth_token(client)
        r = client.put("/api/hr/benchmarks/9999", json={"target_value": 1.0}, headers=auth_header(token))
        assert r.status_code == 404


class TestBenchmarkCreate:
    # A seeded metric that has no benchmark row yet.
    FREE_METRIC = "total_employees"

    def test_create_benchmark_admin(self, client):
        token = get_auth_token(client)
        before = client.get("/api/hr/benchmarks", headers=auth_header(token)).json()
        assert not any(r["metric_key"] == self.FREE_METRIC for r in before)

        r = client.post("/api/hr/benchmarks", json={
            "metric_key": self.FREE_METRIC,
            "target_value": 120.0,
            "description": "Целевая численность на конец периода",
            "source": "План службы персонала",
        }, headers=auth_header(token))
        assert r.status_code == 200
        body = r.json()
        assert body["metric_key"] == self.FREE_METRIC
        assert body["target_value"] == 120.0
        assert body["description"] == "Целевая численность на конец периода"
        assert body["source"] == "План службы персонала"
        assert body["year"] == datetime.datetime.now().year
        assert body["label"] == f"Цель {body['year']}"
        assert body["metric_label"]  # resolved from the metric definition

        rows = client.get("/api/hr/benchmarks", headers=auth_header(token)).json()
        assert len(rows) == len(before) + 1
        created = next(r for r in rows if r["id"] == body["id"])
        assert created["metric_key"] == self.FREE_METRIC
        assert created["target_value"] == 120.0

    def test_create_benchmark_optional_fields_default_empty(self, client):
        token = get_auth_token(client)
        r = client.post("/api/hr/benchmarks",
                        json={"metric_key": self.FREE_METRIC, "target_value": 10.0},
                        headers=auth_header(token))
        assert r.status_code == 200
        assert r.json()["description"] == ""
        assert r.json()["source"] == ""

    def test_create_benchmark_duplicate_metric(self, client):
        token = get_auth_token(client)
        payload = {"metric_key": self.FREE_METRIC, "target_value": 120.0}
        assert client.post("/api/hr/benchmarks", json=payload,
                           headers=auth_header(token)).status_code == 200
        r = client.post("/api/hr/benchmarks", json=payload, headers=auth_header(token))
        assert r.status_code == 400
        assert "уже существует" in r.json()["detail"]

    def test_create_benchmark_unknown_metric(self, client):
        token = get_auth_token(client)
        r = client.post("/api/hr/benchmarks",
                        json={"metric_key": "no_such_metric", "target_value": 1.0},
                        headers=auth_header(token))
        assert r.status_code == 400
        assert "не найдена" in r.json()["detail"]

    def test_create_benchmark_non_admin_forbidden(self, client):
        hr_token = get_auth_token(client, "hr_head", "hr123")
        r = client.post("/api/hr/benchmarks",
                        json={"metric_key": self.FREE_METRIC, "target_value": 1.0},
                        headers=auth_header(hr_token))
        assert r.status_code == 403


class TestPDF:
    def test_export_pdf(self, client):
        token = get_auth_token(client)
        r = client.get("/api/pdf/dashboard", headers=auth_header(token))
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert len(r.content) > 1000

    @pytest.mark.parametrize("report", [
        "dashboard", "summary", "registry", "benchmarks", "partnerships", "partnerships-summary",
    ])
    def test_every_report_renders(self, client, report):
        token = get_auth_token(client)
        r = client.get(f"/api/pdf/{report}", headers=auth_header(token))
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF")
        assert "attachment; filename=" in r.headers["content-disposition"]

    def test_filtered_reports(self, client):
        token = get_auth_token(client)
        r = client.get("/api/pdf/registry?event_type=hired", headers=auth_header(token))
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        r = client.get("/api/pdf/partnerships?status=Завершено", headers=auth_header(token))
        assert r.status_code == 200 and r.content.startswith(b"%PDF")

    def test_pdf_requires_auth(self, client):
        assert client.get("/api/pdf/summary").status_code == 401


class TestDashboardPreferences:
    LAYOUT = {"widgets": [
        {"key": "kpi", "visible": True, "size": "large", "sort_order": 0},
        {"key": "turnover", "visible": False, "size": "small", "sort_order": 1},
    ]}

    def test_defaults_are_empty(self, client):
        token = get_auth_token(client)
        r = client.get("/api/dashboard/preferences/hr", headers=auth_header(token))
        assert r.status_code == 200
        assert r.json() == {"service_key": "hr", "widgets": []}

    def test_save_and_read_back(self, client):
        token = get_auth_token(client)
        r = client.put("/api/dashboard/preferences/hr", json=self.LAYOUT, headers=auth_header(token))
        assert r.status_code == 200
        assert r.json()["widgets"] == [{**w, "settings": {}} for w in self.LAYOUT["widgets"]]

        r = client.get("/api/dashboard/preferences/hr", headers=auth_header(token))
        assert r.json()["widgets"][1] == {"key": "turnover", "visible": False, "size": "small",
                                         "sort_order": 1, "settings": {}}

    def test_per_chart_settings_round_trip(self, client):
        token = get_auth_token(client)
        settings = {"type": "line", "colors": ["#112233"], "legend": False,
                    "legendPos": "right", "height": 340}
        layout = {"widgets": [{"key": "turnover", "visible": True, "size": "wide",
                               "sort_order": 0, "settings": settings}]}
        r = client.put("/api/dashboard/preferences/hr", json=layout, headers=auth_header(token))
        assert r.status_code == 200

        w = client.get("/api/dashboard/preferences/hr", headers=auth_header(token)).json()["widgets"][0]
        assert w["size"] == "wide"
        assert w["settings"] == settings

    def test_rejects_unknown_size(self, client):
        token = get_auth_token(client)
        layout = {"widgets": [{"key": "kpi", "visible": True, "size": "huge", "sort_order": 0}]}
        r = client.put("/api/dashboard/preferences/hr", json=layout, headers=auth_header(token))
        assert r.status_code == 400

    def test_put_is_idempotent_upsert(self, client):
        token = get_auth_token(client)
        client.put("/api/dashboard/preferences/hr", json=self.LAYOUT, headers=auth_header(token))
        second = {"widgets": [{"key": "kpi", "visible": True, "size": "medium", "sort_order": 0}]}
        r = client.put("/api/dashboard/preferences/hr", json=second, headers=auth_header(token))
        assert r.status_code == 200
        assert len(r.json()["widgets"]) == 1
        assert client.get("/api/dashboard/preferences/hr", headers=auth_header(token)).json()["widgets"] \
            == [{**w, "settings": {}} for w in second["widgets"]]

    def test_preferences_are_per_service(self, client):
        token = get_auth_token(client)
        client.put("/api/dashboard/preferences/hr", json=self.LAYOUT, headers=auth_header(token))
        r = client.get("/api/dashboard/preferences/project_product", headers=auth_header(token))
        assert r.json()["widgets"] == []

    def test_preferences_are_per_user(self, client):
        admin = get_auth_token(client)
        client.put("/api/dashboard/preferences/hr", json=self.LAYOUT, headers=auth_header(admin))
        viewer = get_auth_token(client, "viewer", "view123")
        assert client.get("/api/dashboard/preferences/hr", headers=auth_header(viewer)).json()["widgets"] == []

    def test_viewer_can_save_own_layout(self, client):
        # Layout is a personal display setting, not data — read-only users may set it.
        token = get_auth_token(client, "viewer", "view123")
        r = client.put("/api/dashboard/preferences/hr", json=self.LAYOUT, headers=auth_header(token))
        assert r.status_code == 200

    def test_reset_removes_layout(self, client):
        token = get_auth_token(client)
        client.put("/api/dashboard/preferences/hr", json=self.LAYOUT, headers=auth_header(token))
        assert client.delete("/api/dashboard/preferences/hr", headers=auth_header(token)).status_code == 200
        assert client.get("/api/dashboard/preferences/hr", headers=auth_header(token)).json()["widgets"] == []

    def test_requires_auth(self, client):
        assert client.get("/api/dashboard/preferences/hr").status_code == 401


class TestCustomDashboards:
    BODY = {
        "name": "Найм и адаптация",
        "is_shared": False,
        "widgets": [
            {"widget_type": "metric_card", "title": "Текучесть", "config": {"metric_key": "turnover"}, "sort_order": 0},
            {"widget_type": "line_chart", "title": "Динамика",
             "config": {"metric_keys": ["turnover", "avg_time_to_fill"]}, "sort_order": 1},
            {"widget_type": "note", "title": "Пояснение", "config": {"text": "Данные за год"}, "sort_order": 2},
        ],
    }

    def create(self, client, token, **over):
        body = {**self.BODY, **over}
        r = client.post("/api/dashboards", json=body, headers=auth_header(token))
        assert r.status_code == 200, r.text
        return r.json()

    def test_create_with_widgets(self, client):
        token = get_auth_token(client)
        data = self.create(client, token)
        assert data["name"] == "Найм и адаптация"
        assert len(data["widgets"]) == 3
        by_type = {w["widget_type"]: w for w in data["widgets"]}
        assert by_type["metric_card"]["config"] == {"metric_key": "turnover"}
        assert by_type["line_chart"]["config"]["metric_keys"] == ["turnover", "avg_time_to_fill"]
        assert by_type["note"]["config"]["text"] == "Данные за год"

    def test_list_includes_created(self, client):
        token = get_auth_token(client)
        created = self.create(client, token)
        r = client.get("/api/dashboards", headers=auth_header(token))
        assert r.status_code == 200
        assert created["id"] in [d["id"] for d in r.json()]

    def test_update_replaces_widgets(self, client):
        token = get_auth_token(client)
        created = self.create(client, token)
        body = {"name": "Только таблица", "is_shared": True, "widgets": [
            {"widget_type": "table", "title": "Все метрики",
             "config": {"metric_keys": ["turnover"]}, "sort_order": 0},
        ]}
        r = client.put(f"/api/dashboards/{created['id']}", json=body, headers=auth_header(token))
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Только таблица"
        assert data["is_shared"] is True
        assert [w["widget_type"] for w in data["widgets"]] == ["table"]

    def test_delete(self, client):
        token = get_auth_token(client)
        created = self.create(client, token)
        assert client.delete(f"/api/dashboards/{created['id']}", headers=auth_header(token)).status_code == 200
        assert created["id"] not in [d["id"] for d in client.get("/api/dashboards", headers=auth_header(token)).json()]

    def test_unknown_widget_type_rejected(self, client):
        token = get_auth_token(client)
        r = client.post("/api/dashboards", json={"name": "X", "widgets": [
            {"widget_type": "pie_chart", "title": "", "config": {}, "sort_order": 0}]},
            headers=auth_header(token))
        assert r.status_code == 400

    def test_blank_name_rejected(self, client):
        token = get_auth_token(client)
        r = client.post("/api/dashboards", json={"name": "   ", "widgets": []}, headers=auth_header(token))
        assert r.status_code == 400

    def test_missing_dashboard_is_404(self, client):
        token = get_auth_token(client)
        assert client.put("/api/dashboards/9999", json=self.BODY, headers=auth_header(token)).status_code == 404
        assert client.delete("/api/dashboards/9999", headers=auth_header(token)).status_code == 404

    def test_private_dashboard_hidden_from_others(self, client):
        admin = get_auth_token(client)
        private = self.create(client, admin)
        shared = self.create(client, admin, name="Общий", is_shared=True)
        viewer = get_auth_token(client, "viewer", "view123")
        visible = [d["id"] for d in client.get("/api/dashboards", headers=auth_header(viewer)).json()]
        assert shared["id"] in visible
        assert private["id"] not in visible

    def test_viewer_cannot_write(self, client):
        token = get_auth_token(client, "viewer", "view123")
        assert client.post("/api/dashboards", json=self.BODY, headers=auth_header(token)).status_code == 403

    def test_non_owner_cannot_edit(self, client):
        admin = get_auth_token(client)
        shared = self.create(client, admin, is_shared=True)
        hr = get_auth_token(client, "hr_head", "hr123")
        r = client.put(f"/api/dashboards/{shared['id']}", json=self.BODY, headers=auth_header(hr))
        assert r.status_code == 403
        assert client.delete(f"/api/dashboards/{shared['id']}", headers=auth_header(hr)).status_code == 403

    def test_requires_auth(self, client):
        assert client.get("/api/dashboards").status_code == 401


class TestPartnerships:
    def test_list(self, client):
        token = get_auth_token(client)
        r = client.get("/api/partnerships", headers=auth_header(token))
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 142
        assert data[0]["partner"]

    def test_list_filters(self, client):
        token = get_auth_token(client)
        r = client.get("/api/partnerships?status=Завершено", headers=auth_header(token))
        assert r.status_code == 200
        assert all(p["status"] == "Завершено" for p in r.json())

        r = client.get("/api/partnerships?type=ПО", headers=auth_header(token))
        assert all(p["type"] == "ПО" for p in r.json())

        r = client.get("/api/partnerships?search=Спайдер", headers=auth_header(token))
        assert len(r.json()) >= 1

    def test_analytics(self, client):
        token = get_auth_token(client)
        r = client.get("/api/partnerships/analytics", headers=auth_header(token))
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 142
        assert sum(data["by_status"].values()) == 142
        assert len(data["by_direction"]) <= 8
        assert data["nda_count"] >= 0
        assert data["agreement_count"] >= 0

    def test_timeline(self, client):
        token = get_auth_token(client)
        r = client.get("/api/partnerships/timeline", headers=auth_header(token))
        assert r.status_code == 200
        dates = [p["last_modified"] or p["cert_date"] for p in r.json()]
        assert dates == sorted(dates, reverse=True)

    def test_crud(self, client):
        token = get_auth_token(client)
        payload = {"partner": "ООО Тест", "product": "Тестовый продукт",
                   "direction": "Тестирование", "almi_product": "АльтерОС",
                   "almi_version": "АльтерОС 7.5", "status": "В работе",
                   "cert_date": None, "nda": True, "agreement": False, "type": "ПО"}
        r = client.post("/api/partnerships", json=payload, headers=auth_header(token))
        assert r.status_code == 200
        pid = r.json()["id"]
        assert r.json()["nda"] is True

        r = client.get(f"/api/partnerships/{pid}", headers=auth_header(token))
        assert r.json()["partner"] == "ООО Тест"

        r = client.put(f"/api/partnerships/{pid}", json={"status": "Завершено"},
                       headers=auth_header(token))
        assert r.status_code == 200
        assert r.json()["status"] == "Завершено"
        assert r.json()["partner"] == "ООО Тест"

        r = client.delete(f"/api/partnerships/{pid}", headers=auth_header(token))
        assert r.status_code == 200
        assert client.get(f"/api/partnerships/{pid}", headers=auth_header(token)).status_code == 404

    def test_viewer_cannot_edit(self, client):
        token = get_auth_token(client, "viewer", "view123")
        r = client.post("/api/partnerships", json={"partner": "X"}, headers=auth_header(token))
        assert r.status_code == 403


class TestPartnershipLightRules:
    """Partnership traffic-light rules are stored separately from the HR thresholds,
    are readable by any signed-in user and editable only by an admin."""

    URL = "/api/partnerships/traffic-light/rules"

    def test_list_seeds_defaults(self, client):
        token = get_auth_token(client)
        r = client.get(self.URL, headers=auth_header(token))
        assert r.status_code == 200
        rules = r.json()
        assert {x["group_key"] for x in rules} == {"status", "nda", "agreement", "cert_age"}
        by_key = {x["key"]: x for x in rules}
        assert by_key["status:Завершено"]["light"] == "green"
        assert by_key["status:Не подписывают"]["light"] == "red"
        # The Russian group name is resolved for the UI, not just the raw key.
        assert by_key["cert_age:fresh"]["group"] == "Срок сертификата"
        assert by_key["cert_age:fresh"]["threshold"] == 2.0

    def test_admin_changes_a_status_colour(self, client):
        token = get_auth_token(client)
        r = client.put(self.URL, json={"rules": [{"key": "status:В работе", "light": "red"}]},
                       headers=auth_header(token))
        assert r.status_code == 200
        assert {x["key"]: x["light"] for x in r.json()}["status:В работе"] == "red"

        # The change is persisted, not just echoed.
        again = client.get(self.URL, headers=auth_header(token)).json()
        assert {x["key"]: x["light"] for x in again}["status:В работе"] == "red"

    def test_colour_change_reaches_the_traffic_light_rows(self, client):
        token = get_auth_token(client)
        rows = client.get("/api/partnerships/traffic-light", headers=auth_header(token)).json()
        assert {r["key"]: r["light"] for r in rows}["status:В работе"] == "yellow"

        client.put(self.URL, json={"rules": [{"key": "status:В работе", "light": "green"}]},
                   headers=auth_header(token))
        rows = client.get("/api/partnerships/traffic-light", headers=auth_header(token)).json()
        assert {r["key"]: r["light"] for r in rows}["status:В работе"] == "green"

    def test_cert_age_threshold_updates(self, client):
        token = get_auth_token(client)
        r = client.put(self.URL, json={"rules": [{"key": "cert_age:fresh", "threshold": 3.0}]},
                       headers=auth_header(token))
        assert r.status_code == 200
        assert {x["key"]: x["threshold"] for x in r.json()}["cert_age:fresh"] == 3.0

    def test_threshold_only_on_cert_age(self, client):
        token = get_auth_token(client)
        r = client.put(self.URL, json={"rules": [{"key": "status:Завершено", "threshold": 5.0}]},
                       headers=auth_header(token))
        assert r.status_code == 400

    def test_non_positive_threshold_rejected(self, client):
        token = get_auth_token(client)
        r = client.put(self.URL, json={"rules": [{"key": "cert_age:fresh", "threshold": 0}]},
                       headers=auth_header(token))
        assert r.status_code == 400

    def test_unknown_rule_and_colour_rejected(self, client):
        token = get_auth_token(client)
        r = client.put(self.URL, json={"rules": [{"key": "status:Ничего", "light": "green"}]},
                       headers=auth_header(token))
        assert r.status_code == 400

        r = client.put(self.URL, json={"rules": [{"key": "status:Завершено", "light": "лиловый"}]},
                       headers=auth_header(token))
        assert r.status_code == 400

    def test_viewer_may_read_but_not_write(self, client):
        token = get_auth_token(client, "viewer", "view123")
        assert client.get(self.URL, headers=auth_header(token)).status_code == 200
        r = client.put(self.URL, json={"rules": [{"key": "status:Завершено", "light": "red"}]},
                       headers=auth_header(token))
        assert r.status_code == 403

    def test_hr_head_cannot_write(self, client):
        token = get_auth_token(client, "hr_head", "hr123")
        r = client.put(self.URL, json={"rules": [{"key": "status:Завершено", "light": "red"}]},
                       headers=auth_header(token))
        assert r.status_code == 403


class TestModules:
    def test_list(self, client):
        token = get_auth_token(client)
        r = client.get("/api/modules", headers=auth_header(token))
        assert r.status_code == 200
        data = r.json()
        # Only the two services that have dashboard content are enabled.
        assert [m["key"] for m in data] == ["hr", "project_product"]
        assert data[1]["title"] == "Проектный и продуктовый офис"
        assert data[1]["route_prefix"] == "/product"

    def test_get_one(self, client):
        token = get_auth_token(client)
        r = client.get("/api/modules/hr", headers=auth_header(token))
        assert r.status_code == 200
        assert r.json()["subtitle"] == "Персонал"

    def test_get_missing(self, client):
        token = get_auth_token(client)
        assert client.get("/api/modules/nope", headers=auth_header(token)).status_code == 404

    def test_disabled_services_seeded(self, client, db):
        from app.models import DashboardModule, SERVICE_KEYS
        keys = {m.key for m in db.query(DashboardModule).all()}
        assert keys == set(SERVICE_KEYS)
        assert db.query(DashboardModule).filter(DashboardModule.key == "finance").first().enabled is False

    def test_list_filtered_by_access(self, client, db):
        """it_viewer is granted hr + it; only hr has an enabled module."""
        token = get_auth_token(client, "it_viewer", "it123")
        r = client.get("/api/modules", headers=auth_header(token))
        assert r.status_code == 200
        assert [m["key"] for m in r.json()] == ["hr"]

    def test_list_empty_without_access(self, client, db):
        from app.models import User, UserServiceAccess
        user = db.query(User).filter(User.username == "viewer").first()
        db.query(UserServiceAccess).filter(UserServiceAccess.user_id == user.id).delete()
        db.commit()
        token = get_auth_token(client, "viewer", "view123")
        r = client.get("/api/modules", headers=auth_header(token))
        assert r.status_code == 200
        assert r.json() == []


class TestServices:
    def test_registry_lists_nine_services(self, client):
        token = get_auth_token(client)
        r = client.get("/api/services", headers=auth_header(token))
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 9
        assert {s["key"] for s in data} == {
            "apparat_gd", "tech", "it", "commercial", "marketing",
            "hr", "project_product", "finance", "legal",
        }
        by_key = {s["key"]: s for s in data}
        assert by_key["hr"]["title"] == "Служба персонала"
        assert by_key["legal"]["title"] == "Юридическая служба"
        assert [s["key"] for s in data if s["has_dashboard"]] == ["hr", "project_product"]

    def test_registry_requires_auth(self, client):
        assert client.get("/api/services").status_code == 401


class TestServiceAccess:
    def test_seeded_access(self, client, db):
        from app.models import User
        token = get_auth_token(client)
        user = db.query(User).filter(User.username == "hr_head").first()
        r = client.get(f"/api/users/{user.id}/access", headers=auth_header(token))
        assert r.status_code == 200
        assert {a["service_key"]: a["access_level"] for a in r.json()} == {
            "hr": "admin", "project_product": "read",
        }

    def test_my_access(self, client):
        token = get_auth_token(client, "viewer", "view123")
        r = client.get("/api/auth/my-access", headers=auth_header(token))
        assert r.status_code == 200
        assert {a["service_key"]: a["access_level"] for a in r.json()} == {
            "hr": "read", "project_product": "read",
        }

    def test_admin_my_access_covers_every_service(self, client):
        from app.models import SERVICE_KEYS
        token = get_auth_token(client)
        r = client.get("/api/auth/my-access", headers=auth_header(token))
        assert {a["service_key"] for a in r.json()} == set(SERVICE_KEYS)
        assert {a["access_level"] for a in r.json()} == {"admin"}

    def test_user_response_includes_access(self, client):
        token = get_auth_token(client)
        r = client.get("/api/auth/me", headers=auth_header(token))
        assert r.status_code == 200
        levels = {a["service_key"]: a["access_level"] for a in r.json()["service_access"]}
        assert levels["hr"] == "admin"

    def test_grant_new_access(self, client, db):
        from app.models import User
        token = get_auth_token(client)
        user = db.query(User).filter(User.username == "viewer").first()
        r = client.put(f"/api/users/{user.id}/access",
                       json={"service_key": "finance", "access_level": "edit"},
                       headers=auth_header(token))
        assert r.status_code == 200
        assert {a["service_key"]: a["access_level"] for a in r.json()}["finance"] == "edit"

    def test_update_existing_access(self, client, db):
        from app.models import User
        token = get_auth_token(client)
        user = db.query(User).filter(User.username == "viewer").first()
        client.put(f"/api/users/{user.id}/access",
                   json={"service_key": "hr", "access_level": "edit_metrics"},
                   headers=auth_header(token))
        r = client.get(f"/api/users/{user.id}/access", headers=auth_header(token))
        levels = {a["service_key"]: a["access_level"] for a in r.json()}
        assert levels["hr"] == "edit_metrics"
        # Updating one service must not duplicate or drop the others.
        assert levels["project_product"] == "read"
        assert len(r.json()) == 2

    def test_empty_level_revokes_access(self, client, db):
        from app.models import User
        token = get_auth_token(client)
        user = db.query(User).filter(User.username == "viewer").first()
        r = client.put(f"/api/users/{user.id}/access",
                       json={"service_key": "hr", "access_level": ""},
                       headers=auth_header(token))
        assert r.status_code == 200
        assert [a["service_key"] for a in r.json()] == ["project_product"]

    def test_null_level_revokes_access(self, client, db):
        from app.models import User
        token = get_auth_token(client)
        user = db.query(User).filter(User.username == "viewer").first()
        r = client.put(f"/api/users/{user.id}/access",
                       json={"service_key": "project_product", "access_level": None},
                       headers=auth_header(token))
        assert r.status_code == 200
        assert [a["service_key"] for a in r.json()] == ["hr"]

    def test_revoking_missing_access_is_noop(self, client, db):
        from app.models import User
        token = get_auth_token(client)
        user = db.query(User).filter(User.username == "viewer").first()
        r = client.put(f"/api/users/{user.id}/access",
                       json={"service_key": "legal", "access_level": None},
                       headers=auth_header(token))
        assert r.status_code == 200
        assert "legal" not in {a["service_key"] for a in r.json()}

    def test_unknown_service_rejected(self, client, db):
        from app.models import User
        token = get_auth_token(client)
        user = db.query(User).filter(User.username == "viewer").first()
        r = client.put(f"/api/users/{user.id}/access",
                       json={"service_key": "nope", "access_level": "read"},
                       headers=auth_header(token))
        assert r.status_code == 400

    def test_unknown_level_rejected(self, client, db):
        from app.models import User
        token = get_auth_token(client)
        user = db.query(User).filter(User.username == "viewer").first()
        r = client.put(f"/api/users/{user.id}/access",
                       json={"service_key": "hr", "access_level": "superuser"},
                       headers=auth_header(token))
        assert r.status_code == 400

    def test_missing_user(self, client):
        token = get_auth_token(client)
        assert client.get("/api/users/9999/access", headers=auth_header(token)).status_code == 404
        r = client.put("/api/users/9999/access", json={"service_key": "hr", "access_level": "read"},
                       headers=auth_header(token))
        assert r.status_code == 404

    def test_non_admin_cannot_read_or_write_access(self, client, db):
        from app.models import User
        token = get_auth_token(client, "hr_head", "hr123")
        user = db.query(User).filter(User.username == "viewer").first()
        assert client.get(f"/api/users/{user.id}/access", headers=auth_header(token)).status_code == 403
        r = client.put(f"/api/users/{user.id}/access",
                       json={"service_key": "hr", "access_level": "admin"},
                       headers=auth_header(token))
        assert r.status_code == 403

    def test_access_deleted_with_user(self, client, db):
        from app.models import User, UserServiceAccess
        token = get_auth_token(client)
        user = db.query(User).filter(User.username == "viewer").first()
        uid = user.id
        assert client.delete(f"/api/users/{uid}", headers=auth_header(token)).status_code == 200
        assert db.query(UserServiceAccess).filter(UserServiceAccess.user_id == uid).count() == 0


class TestUserProfileFields:
    """The admin user form writes contact details, a primary service and a password."""

    NEW = {
        "username": "svc_head", "full_name": "Иванов Иван Иванович",
        "email": "ivanov@almi.ru", "position": "Начальник службы",
        "phone": "+7 495 000-00-00", "avatar": "data:image/png;base64,AAA",
        "role": "hr_head", "password": "start123",
    }

    def test_create_round_trips_every_field(self, client):
        token = get_auth_token(client)
        r = client.post("/api/users", json=self.NEW, headers=auth_header(token))
        assert r.status_code == 200
        out = r.json()
        assert out["position"] == "Начальник службы"
        assert out["email"] == "ivanov@almi.ru"
        assert out["phone"] == "+7 495 000-00-00"
        assert out["avatar"] == "data:image/png;base64,AAA"

        # The list the admin table renders carries the same fields.
        listed = client.get("/api/users", headers=auth_header(token)).json()
        row = next(u for u in listed if u["username"] == "svc_head")
        assert row["position"] == "Начальник службы"
        assert row["email"] == "ivanov@almi.ru"

    def test_update_changes_position(self, client):
        token = get_auth_token(client)
        uid = client.post("/api/users", json=self.NEW, headers=auth_header(token)).json()["id"]
        r = client.put(f"/api/users/{uid}", json={"position": "Заместитель начальника"},
                       headers=auth_header(token))
        assert r.status_code == 200
        assert r.json()["position"] == "Заместитель начальника"
        # An untouched field is not wiped by the partial update.
        assert r.json()["email"] == "ivanov@almi.ru"

    def test_primary_service_grants_edit_metrics(self, client):
        token = get_auth_token(client)
        body = {**self.NEW, "primary_service": "project_product"}
        uid = client.post("/api/users", json=body, headers=auth_header(token)).json()["id"]
        rows = client.get(f"/api/users/{uid}/access", headers=auth_header(token)).json()
        assert {a["service_key"]: a["access_level"] for a in rows} == {
            "project_product": "edit_metrics",
        }

    def test_primary_service_upgrades_an_existing_row(self, client):
        token = get_auth_token(client)
        uid = client.post("/api/users", json=self.NEW, headers=auth_header(token)).json()["id"]
        client.put(f"/api/users/{uid}/access", json={"service_key": "finance", "access_level": "read"},
                   headers=auth_header(token))
        client.put(f"/api/users/{uid}", json={"primary_service": "finance"}, headers=auth_header(token))
        rows = client.get(f"/api/users/{uid}/access", headers=auth_header(token)).json()
        assert {a["service_key"]: a["access_level"] for a in rows}["finance"] == "edit_metrics"

    def test_unknown_primary_service_rejected(self, client):
        token = get_auth_token(client)
        r = client.post("/api/users", json={**self.NEW, "primary_service": "nope"},
                        headers=auth_header(token))
        assert r.status_code == 400

    def test_admin_can_reset_the_password(self, client):
        token = get_auth_token(client)
        uid = client.post("/api/users", json=self.NEW, headers=auth_header(token)).json()["id"]
        r = client.put(f"/api/users/{uid}", json={"password": "reset456"}, headers=auth_header(token))
        assert r.status_code == 200
        # An admin-set password is temporary, so the user is asked to change it.
        assert r.json()["must_change_password"] is True
        assert get_auth_token(client, "svc_head", "reset456")
        assert client.post("/api/auth/login",
                           json={"username": "svc_head", "password": "start123"}).status_code == 401

    def test_blank_password_leaves_it_alone(self, client):
        token = get_auth_token(client)
        uid = client.post("/api/users", json=self.NEW, headers=auth_header(token)).json()["id"]
        r = client.put(f"/api/users/{uid}", json={"position": "Аналитик"}, headers=auth_header(token))
        assert r.status_code == 200
        assert get_auth_token(client, "svc_head", "start123")

    def test_non_admin_cannot_create_users(self, client):
        token = get_auth_token(client, "hr_head", "hr123")
        r = client.post("/api/users", json=self.NEW, headers=auth_header(token))
        assert r.status_code == 403


class TestRBACHelpers:
    """The helpers back the API layer, so they are exercised directly."""

    def _user(self, db, username):
        from app.models import User
        return db.query(User).filter(User.username == username).first()

    def test_admin_is_superadmin_everywhere(self, client, db):
        from app.deps import (can_view_service, can_edit_service, can_edit_metrics,
                              can_admin_service)
        admin = self._user(db, "admin")
        for key in ("hr", "legal", "finance"):
            assert can_view_service(db, admin, key)
            assert can_edit_service(db, admin, key)
            assert can_edit_metrics(db, admin, key)
            assert can_admin_service(db, admin, key)

    def test_service_admin_has_every_capability(self, client, db):
        from app.deps import (can_view_service, can_edit_service, can_edit_metrics,
                              can_admin_service)
        hr_head = self._user(db, "hr_head")
        assert can_view_service(db, hr_head, "hr")
        assert can_edit_service(db, hr_head, "hr")
        assert can_edit_metrics(db, hr_head, "hr")
        assert can_admin_service(db, hr_head, "hr")

    def test_read_only_access(self, client, db):
        from app.deps import (can_view_service, can_edit_service, can_edit_metrics,
                              can_admin_service)
        hr_head = self._user(db, "hr_head")
        assert can_view_service(db, hr_head, "project_product")
        assert not can_edit_service(db, hr_head, "project_product")
        assert not can_edit_metrics(db, hr_head, "project_product")
        assert not can_admin_service(db, hr_head, "project_product")

    def test_no_access_at_all(self, client, db):
        from app.deps import can_view_service, can_edit_service
        viewer = self._user(db, "viewer")
        assert not can_view_service(db, viewer, "legal")
        assert not can_edit_service(db, viewer, "legal")

    def test_edit_and_edit_metrics_are_distinct(self, client, db):
        from app.models import UserServiceAccess
        from app.deps import can_edit_service, can_edit_metrics
        viewer = self._user(db, "viewer")
        row = (db.query(UserServiceAccess)
               .filter(UserServiceAccess.user_id == viewer.id,
                       UserServiceAccess.service_key == "hr").first())
        row.access_level = "edit"
        db.commit()
        assert can_edit_service(db, viewer, "hr")
        assert not can_edit_metrics(db, viewer, "hr")
        row.access_level = "edit_metrics"
        db.commit()
        assert not can_edit_service(db, viewer, "hr")
        assert can_edit_metrics(db, viewer, "hr")

    def test_accessible_service_keys(self, client, db):
        from app.models import SERVICE_KEYS
        from app.deps import accessible_service_keys
        assert accessible_service_keys(db, self._user(db, "admin")) == set(SERVICE_KEYS)
        assert accessible_service_keys(db, self._user(db, "it_viewer")) == {"it", "hr"}

    def test_service_access_level_ignores_global_role(self, client, db):
        from app.deps import service_access_level
        assert service_access_level(db, self._user(db, "hr_head"), "hr") == "admin"
        assert service_access_level(db, self._user(db, "hr_head"), "legal") is None


class TestPalette:
    def test_get_active(self, client):
        token = get_auth_token(client)
        r = client.get("/api/palette", headers=auth_header(token))
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Мягкая"
        assert data["colors"]["traffic_light"]["green"] == "#5a9e68"
        assert len(data["colors"]["charts"]) == 6

    def test_list_all_admin_only(self, client):
        token = get_auth_token(client)
        assert client.get("/api/palette/all", headers=auth_header(token)).status_code == 200
        viewer = get_auth_token(client, "viewer", "view123")
        assert client.get("/api/palette/all", headers=auth_header(viewer)).status_code == 403

    def test_crud_and_activate(self, client):
        token = get_auth_token(client)
        colors = {"traffic_light": {"green": "#0F0", "yellow": "#FF0", "red": "#F00", "neutral": "#CCC"},
                  "charts": ["#111"], "brand": {"primary": "#222", "muted": "#333"}}
        r = client.post("/api/palette", json={"name": "Контрастная", "colors": colors},
                        headers=auth_header(token))
        assert r.status_code == 200
        pid = r.json()["id"]
        assert r.json()["is_active"] is False

        r = client.put(f"/api/palette/{pid}", json={"name": "Контрастная v2", "colors": colors},
                       headers=auth_header(token))
        assert r.json()["name"] == "Контрастная v2"

        r = client.put(f"/api/palette/{pid}/activate", headers=auth_header(token))
        assert r.status_code == 200
        assert r.json()["is_active"] is True
        assert client.get("/api/palette", headers=auth_header(token)).json()["id"] == pid

        assert client.delete(f"/api/palette/{pid}", headers=auth_header(token)).status_code == 200
        # 4 preset palettes (Мягкая, Классическая, Холодная, Контрастная) are always seeded
        assert len(client.get("/api/palette/all", headers=auth_header(token)).json()) == 4

    def test_viewer_cannot_create(self, client):
        token = get_auth_token(client, "viewer", "view123")
        r = client.post("/api/palette", json={"name": "X", "colors": {}}, headers=auth_header(token))
        assert r.status_code == 403


class TestAudit:
    def test_audit_after_update(self, client):
        token = get_auth_token(client)
        # Update traffic light rule (triggers audit)
        client.put("/api/traffic-light/turnover", json={"green_threshold": 4, "yellow_threshold": 6, "enabled": True},
                   headers=auth_header(token))
        # Check audit log
        r = client.get("/api/audit", headers=auth_header(token))
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0
        assert data[0]["entity_type"] == "traffic_light"
        assert data[0]["action"] == "update"
