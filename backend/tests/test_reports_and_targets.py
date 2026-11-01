"""Цели по годам и оформление PDF-отчётов: исправления по итогам проверки дашбордов."""
import io

import pytest
from matplotlib.colors import to_hex
from pypdf import PdfReader
from reportlab.lib.enums import TA_LEFT, TA_RIGHT

from app.services import hr as hr_service
from app.services.pdf import base as pdf_base
from app.services.pdf import reports


def _pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)


def _target(rows, key, year):
    return next(r for r in rows if r["metric_key"] == key and r["year"] == year)


# ---------------------------------------------------------------- цели

def test_target_is_evaluated_with_data_of_its_own_year(admin):
    # Цель будущего года: данных ещё нет — не «достигнута» по прошлогоднему факту
    created = admin.post("/api/hr/targets", json={"metric_key": "turnover", "year": 2027, "target_value": 4.5})
    assert created.status_code == 201
    future = created.json()
    assert future["current_value"] is None and future["status"] == "gray" and future["current_month"] == ""

    # Появился месяц 2027 года — цель 2027 оценивается по нему, цель 2026 — по-прежнему по данным 2026
    assert admin.post("/api/hr/months", json={"year": 2027, "month": 1}).status_code == 201
    saved = admin.put("/api/hr/months/2027-01/metrics", json=[{"metric_key": "turnover", "value": 6.0}])
    assert saved.status_code == 200
    rows = admin.get("/api/hr/targets").json()
    t2027 = _target(rows, "turnover", 2027)
    assert (t2027["current_value"], t2027["current_month"], t2027["status"]) == (6.0, "Январь 2027", "red")
    t2026 = _target(rows, "turnover", 2026)
    assert (t2026["current_value"], t2026["current_month"], t2026["status"]) == (2.0, "Июль 2026", "green")


def test_reference_row_compares_with_latest_fact(admin):
    rows = admin.get("/api/hr/targets").json()
    reference = _target(rows, "turnover", 2025)
    assert reference["target_value"] is None and reference["reference_value"] == 5.17
    # Справочное значение (факт прошлого года) сравнивается с последним фактом
    assert reference["current_value"] == 2.0 and reference["current_month"] == "Июль 2026"
    assert reference["status"] == "gray"


def test_past_year_target_without_data_is_not_rated(db):
    from app.models import HrTarget

    db.add(HrTarget(metric_key="turnover_company", year=2025, label="Цель 2025", target_value=3.0))
    db.commit()
    row = next(r for r in hr_service.target_rows(db) if r["metric_key"] == "turnover_company" and r["year"] == 2025)
    assert row["current_value"] is None and row["status"] == "gray" and row["diff"] is None


# ---------------------------------------------------------------- PDF

def test_pdf_dashboard_reports_last_month_with_data(admin):
    """Пустой только что добавленный месяц в конце выборки не обнуляет отчёт — как на экране."""
    assert admin.post("/api/hr/months", json={"year": 2026, "month": 8}).status_code == 201
    response = admin.get("/api/pdf/hr/dashboard?months=2026-06,2026-07,2026-08")
    assert response.status_code == 200
    text = _pdf_text(response.content)
    assert "Метрики за Июль 2026" in text
    assert "Метрики за Август 2026" not in text


def test_fmt_matches_interface_number_format():
    # Как в интерфейсе: типографский минус, неразрывные пробелы между разрядами и перед единицей
    assert pdf_base.fmt(-1) == "\u22121"
    assert pdf_base.fmt(-1.87, "п.п.") == "\u22121,87\u00a0п.п."
    assert pdf_base.fmt(1234.5, "ч") == "1\u00a0234,5\u00a0ч"
    assert pdf_base.fmt(12.5, "%") == "12,5%"
    assert pdf_base.fmt(None) == "—"


def test_table_right_aligns_numeric_columns():
    rep = pdf_base.Report("Проверка")
    rep.table(["Показатель", "Значение"], [["Принято", "12"]], align_right_from=1)
    table = rep.story[-1]
    header, row = table._cellvalues
    assert header[0].style.alignment == TA_LEFT and header[1].style.alignment == TA_RIGHT
    assert row[0].style.alignment == TA_LEFT and row[1].style.alignment == TA_RIGHT


@pytest.fixture()
def charts(monkeypatch):
    """Графики отчёта: фигуры matplotlib перехватываются до сохранения в PDF."""
    captured = []
    original = pdf_base.Report.chart

    def chart(self, figure, height_mm=70):
        figure.canvas.draw()
        captured.append({
            "bars": [to_hex(p.get_facecolor()) for ax in figure.axes for p in ax.patches],
            "legend_above": all(
                ax.get_legend() is None
                or ax.get_legend().get_window_extent().y0 >= ax.get_window_extent().y1 - 1
                for ax in figure.axes),
            "title": figure.axes[0].get_title(loc="left"),
        })
        return original(self, figure, height_mm)

    monkeypatch.setattr(pdf_base.Report, "chart", chart)
    return captured


def test_summary_lights_chart_uses_traffic_light_colors(db, charts):
    reports.hr_summary(db, "quarter", None)
    lights = next(c for c in charts if c["title"].startswith("Светофор"))
    palette = pdf_base.DEFAULT_COLORS["traffic_light"]
    assert set(lights["bars"]) <= {palette["green"], palette["yellow"], palette["red"]}
    assert palette["green"] in lights["bars"]
    assert lights["legend_above"]


def test_dashboard_flow_chart_colors_and_legend(db, charts):
    reports.hr_dashboard(db, [], None)
    flow = next(c for c in charts if c["title"] == "Приём и увольнение")
    palette = pdf_base.DEFAULT_COLORS["traffic_light"]
    assert set(flow["bars"]) == {palette["green"], palette["red"]}
    # Легенда над областью графика — не закрывает столбцы
    assert all(c["legend_above"] for c in charts)


def test_light_hex_follows_active_palette():
    rep = pdf_base.Report("x", palette={"traffic_light": {"green": "#00ff00"}, "charts": ["#123456"]})
    assert rep.light_hex("green") == "#00ff00"
    assert rep.light_hex("red") == pdf_base.DEFAULT_COLORS["traffic_light"]["red"]
    assert rep.light_hex("gray") == pdf_base.DEFAULT_COLORS["traffic_light"]["neutral"]


# ---------------------------------------------------------------- Naumen: ось месяцев

def test_month_span_fills_gaps_across_years():
    from app.services.naumen import month_span

    assert month_span("2023-11", "2024-02") == ["2023-11", "2023-12", "2024-01", "2024-02"]
    assert month_span("2024-05", "2024-05") == ["2024-05"]


def test_naumen_year_axis_is_limited_to_registration_months(login):
    """Заявки 2023 года, решённые позже, не растягивают помесячные графики года на следующие годы."""
    c = login("viewer")
    data = c.get("/api/tp/naumen/summary", params={"year": 2023}).json()
    months = [m["month"] for m in data["months"]]
    assert all(m.startswith("2023") for m in months)
    assert months == sorted(months) and len(months) == len(set(months))
    # Без пропусков между первым и последним месяцем
    from app.services.naumen import month_span

    assert months == month_span(months[0], months[-1])
    assert sum(m["registered"] for m in data["months"]) == data["total"]


def test_naumen_summary_keeps_empty_months_inside_period():
    from datetime import datetime

    from app.models import NaumenTicket
    from app.services.naumen import summary

    def ticket(reg, solved=None):
        return NaumenTicket(number=1, name="", registered_at=reg, solved_at=solved,
                            status="Закрыта" if solved else "Новая", org="", responsible="", team="", first_line="",
                            channel="", is_overdue=False, is_reopened=False, processing_hours=1.0)

    data = summary([ticket(datetime(2024, 1, 10), datetime(2025, 6, 1)), ticket(datetime(2024, 3, 5))])
    assert [m["month"] for m in data["months"]] == ["2024-01", "2024-02", "2024-03"]
    assert [m["registered"] for m in data["months"]] == [1, 0, 1]
    assert data["closed"] == 1 and sum(m["solved"] for m in data["months"]) == 0


def test_section_heading_is_kept_with_its_table(db):
    """Заголовок «Детализация по неделям» не остаётся последней строкой страницы без таблицы."""
    content = reports.tp_dashboard(db, None, 26)
    pages = PdfReader(io.BytesIO(content)).pages
    for page in pages:
        lines = [line for line in page.extract_text().splitlines() if line.strip()]
        body = [line for line in lines if not line.startswith("Дашборды компании") and not line.startswith("стр.")]
        assert body and body[-1] != "Детализация по неделям"
    assert pdf_base.STYLES["h2"].keepWithNext == 1


# ---------------------------------------------------------------- CSV недельного отчёта

def test_tp_csv_numbers_and_round_trip(db):
    from sqlalchemy import select

    from app.models import TpWeeklyReport
    from app.services import tp

    rows = list(db.scalars(select(TpWeeklyReport).order_by(TpWeeklyReport.year, TpWeeklyReport.week)))
    raw = tp.export_csv(rows)
    lines = raw.decode("utf-8-sig").splitlines()
    first = lines[1].split(";")
    value = rows[0].total_in_work
    expected = str(int(value)) if float(value).is_integer() else str(value).replace(".", ",")
    assert first[2] == expected
    assert ",0;" not in raw.decode("utf-8-sig")
    records, skipped = tp.parse_upload("report.csv", raw)
    assert skipped == 0 and len(records) == len(rows)
    for row, rec in zip(rows, records, strict=True):
        assert all(getattr(row, k) == rec.get(k) for k in tp.META_BY_KEY)
