"""Местное время компании и фильтры PDF-отчётов (найдено функциональной проверкой)."""
from datetime import date, datetime

from sqlalchemy import select

from app.core import timeutil
from app.models import AuditEntry


def test_local_day_bounds_are_converted_to_utc(monkeypatch):
    monkeypatch.setattr(timeutil.settings, "timezone", "Europe/Moscow")
    assert timeutil.day_start_utc(date(2026, 11, 1)) == datetime(2026, 10, 31, 21, 0)
    assert timeutil.day_end_utc(date(2026, 11, 1)) == datetime(2026, 11, 1, 21, 0)


def test_unknown_timezone_falls_back_to_utc(monkeypatch):
    monkeypatch.setattr(timeutil.settings, "timezone", "Нет/Такой")
    timeutil._zone.cache_clear()
    assert timeutil.day_start_utc(date(2026, 11, 1)) == datetime(2026, 11, 1, 0, 0)
    timeutil._zone.cache_clear()


def test_audit_filter_uses_local_day(admin, db):
    # запись в 22:30 UTC 31 октября — это уже 1 ноября по Москве
    db.add(AuditEntry(occurred_at=datetime(2026, 10, 31, 22, 30), username="admin", entity_type="test",
                      action="create", summary="поздняя запись"))
    db.commit()
    nov = admin.get("/api/audit", params={"entity_type": "test", "date_from": "2026-11-01",
                                          "date_to": "2026-11-01"}).json()
    oct_ = admin.get("/api/audit", params={"entity_type": "test", "date_from": "2026-10-31",
                                           "date_to": "2026-10-31"}).json()
    assert nov["total"] == 1 and oct_["total"] == 0


def test_hr_summary_pdf_respects_range():
    from app.services.pdf.reports import _period_range

    periods = [{"key": k} for k in ("2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4")]
    assert [p["key"] for p in _period_range(periods, "2026-Q2", "2026-Q3")] == ["2026-Q2", "2026-Q3"]
    assert [p["key"] for p in _period_range(periods, "", "")] == ["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"]
    assert [p["key"] for p in _period_range(periods, "2026-Q3", "2026-Q2")] == ["2026-Q2", "2026-Q3"]


def test_pdf_endpoints_accept_page_filters(admin):
    for url, params in (("/api/pdf/hr/summary", {"period_type": "quarter", "from_key": "2026-Q1", "to_key": "2026-Q2"}),
                        ("/api/pdf/tp/dashboard", {"years": "2025,2026"}),
                        ("/api/pdf/partnerships/summary", {"status": "Завершено"})):
        response = admin.get(url, params=params)
        assert response.status_code == 200, (url, response.text)
        assert response.content.startswith(b"%PDF")


def test_tp_rows_for_several_years(db):
    from app.models import TpWeeklyReport
    from app.services.pdf.reports import _tp_rows

    years = sorted(set(db.scalars(select(TpWeeklyReport.year))))
    rows = _tp_rows(db, None, None, years=years[-2:])
    assert {r.year for r in rows} == set(years[-2:])


def test_overview_tp_period_is_human_readable(admin):
    tech = next(s for s in admin.get("/api/overview").json()["services"] if s["key"] == "tech")
    assert "-я неделя " in tech["period"]
