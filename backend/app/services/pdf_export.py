"""PDF export service using reportlab + matplotlib."""
import io
import datetime
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# Register DejaVuSans for Cyrillic support
_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "fonts")
_FONTS_REGISTERED = False

def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    try:
        # Try system DejaVu fonts first
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            os.path.join(_FONT_DIR, "DejaVuSans.ttf"),
            "DejaVuSans.ttf",
        ]
        bold_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf"),
            "DejaVuSans-Bold.ttf",
        ]
        reg = None
        bold = None
        for p in font_paths:
            if os.path.exists(p):
                reg = p
                break
        for p in bold_paths:
            if os.path.exists(p):
                bold = p
                break
        if reg:
            pdfmetrics.registerFont(TTFont("DejaVuSans", reg))
            if bold:
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold))
            else:
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", reg))
            _FONTS_REGISTERED = True
    except Exception:
        pass

_register_fonts()

# Font family for Cyrillic
def _font():
    return "DejaVuSans" if _FONTS_REGISTERED else "Helvetica"

def _font_bold():
    return "DejaVuSans-Bold" if _FONTS_REGISTERED else "Helvetica-Bold"
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from sqlalchemy.orm import Session
from ..models import (
    MonthRecord, MetricDefinition, TrafficLightRule, Benchmark, RoleEnum,
    EmployeeEvent, Partnership, PartnershipLightRule
)
from ..analytics import (
    get_months_sorted, aggregate_months, traffic_light_for_metric, get_benchmarks,
    months_in_period, period_label, benchmark_rows
)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Brand colors
C_RED = colors.HexColor("#c0392b")
C_GREEN = colors.HexColor("#2d6e17")
C_YELLOW = colors.HexColor("#a06010")
C_GRAY = colors.HexColor("#b0afa9")
C_DARK = colors.HexColor("#1e1c17")
C_LIGHT = colors.HexColor("#f5f4f0")

LIGHT_COLORS = {"green": C_GREEN, "yellow": C_YELLOW, "red": C_RED, "gray": C_GRAY}


def _styles():
    ss = getSampleStyleSheet()
    fn = _font()
    fnb = _font_bold()
    ss.add(ParagraphStyle("HRTitle", parent=ss["Title"], fontName=fnb, fontSize=18, textColor=C_RED, spaceAfter=6))
    ss.add(ParagraphStyle("HRSub", parent=ss["Normal"], fontName=fn, fontSize=9, textColor=colors.HexColor("#6b6a65"), spaceAfter=12))
    ss.add(ParagraphStyle("HRH2", parent=ss["Heading2"], fontName=fnb, fontSize=13, textColor=C_DARK, spaceBefore=12, spaceAfter=6))
    ss.add(ParagraphStyle("HRBody", parent=ss["Normal"], fontName=fn, fontSize=9, textColor=C_DARK, leading=13))
    ss.add(ParagraphStyle("HRSrc", parent=ss["Normal"], fontName=fn, fontSize=7, textColor=colors.HexColor("#b0afa9")))
    return ss


def _chart_hire_fire(months: list[MonthRecord]) -> bytes:
    labels = [m.label for m in months]
    hired = [len([e for e in m.employees if e.event_type == "hired"]) for m in months]
    fired = [len([e for e in m.employees if e.event_type == "fired"]) for m in months]
    fig, ax = plt.subplots(figsize=(5, 2.2))
    x = range(len(labels))
    w = 0.35
    ax.bar([i - w/2 for i in x], hired, w, label="Принято", color="#2d6e17")
    ax.bar([i + w/2 for i in x], fired, w, label="Уволено", color="#c0392b")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=7)
    ax.legend(fontsize=7, loc="upper right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _chart_turnover(months: list[MonthRecord], benchmarks: dict) -> bytes:
    labels = []
    values = []
    for m in months:
        mv = next((x for x in m.metric_values if x.metric_key == "turnover"), None)
        if mv and mv.numeric_value is not None:
            labels.append(m.label)
            values.append(mv.numeric_value)
    if not values:
        return b""
    fig, ax = plt.subplots(figsize=(5, 2.2))
    ax.plot(labels, values, "o-", color="#6b2fa0", linewidth=2, markersize=5)
    # benchmark
    bench = benchmarks.get("turnover", {})
    for year, val in bench.items():
        ax.axhline(y=val, color="#b0afa9", linestyle="--", linewidth=1)
        ax.text(0, val, f" {year}: {val}%", fontsize=6, color="#b0afa9", va="bottom")
    ax.set_xticklabels(labels, fontsize=7, rotation=15)
    ax.set_ylabel("Текучесть, %", fontsize=7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _fmt_val(val, unit):
    if val is None:
        return "—"
    if unit == "%":
        return f"{val:.2f}%".replace(".", ",")
    if unit == "дн.":
        return f"{val:.1f} дн.".replace(".", ",")
    if unit in ("чел.", "шт."):
        return f"{val:.0f} {unit}"
    return f"{val}".replace(".", ",")


# ---------- Shared report scaffolding ----------
#
# Every page-level export shares the same header, table look and source footnote,
# so each builder only has to describe its own content.

SOURCE_NOTE = ("Источник: внутренние данные АЛМИ Партнер. "
               "Сформировано автоматически системой аналитики.")


def _open_doc(buf, landscape_mode=False):
    size = (A4[1], A4[0]) if landscape_mode else A4
    return SimpleDocTemplate(buf, pagesize=size, leftMargin=12*mm, rightMargin=12*mm,
                             topMargin=14*mm, bottomMargin=12*mm)


def _header(ss, title: str, subtitle: str = "") -> list:
    stamp = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    line = f"Отчёт сформирован: {stamp}" + (f" · {subtitle}" if subtitle else "")
    return [Paragraph(title, ss["HRTitle"]), Paragraph(line, ss["HRSub"])]


def _grid_table(rows: list[list[str]], widths, font_size=8, light_col=None,
                light_keys=None) -> Table:
    """A bordered table; `light_col` paints that column with its traffic-light colour.

    The cell text is the Russian status label, so `light_keys` carries the raw
    green/yellow/red key for each data row.
    """
    t = Table(rows, colWidths=widths, repeatRows=1)
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), C_LIGHT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#6b6a65")),
        ("FONTNAME", (0, 0), (-1, -1), _font()),
        ("FONTNAME", (0, 0), (-1, 0), _font_bold()),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbd8d2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]
    if light_col is not None:
        for i, row in enumerate(rows[1:], 1):
            key = light_keys[i - 1] if light_keys else str(row[light_col]).lower()
            clr = LIGHT_COLORS.get(key, C_GRAY)
            cmds += [
                ("BACKGROUND", (light_col, i), (light_col, i), clr),
                ("TEXTCOLOR", (light_col, i), (light_col, i), colors.white),
                ("FONTNAME", (light_col, i), (light_col, i), _font_bold()),
                ("ALIGN", (light_col, i), (light_col, i), "CENTER"),
            ]
    t.setStyle(TableStyle(cmds))
    return t


def _build(story, ss, landscape_mode=False) -> bytes:
    story.append(Spacer(1, 12))
    story.append(Paragraph(SOURCE_NOTE, ss["HRSrc"]))
    buf = io.BytesIO()
    _open_doc(buf, landscape_mode).build(story)
    buf.seek(0)
    return buf.read()


LIGHT_LABELS = {"green": "Норма", "yellow": "Внимание", "red": "Критично", "gray": "—"}


def _bar_png(labels: list[str], series: list[tuple[str, list, str]], ylabel="") -> bytes:
    """Grouped bar chart; `series` is (name, values, colour)."""
    if not labels:
        return b""
    fig, ax = plt.subplots(figsize=(7, 2.6))
    n = len(series)
    w = 0.8 / max(n, 1)
    for i, (name, values, color) in enumerate(series):
        offset = (i - (n - 1) / 2) * w
        ax.bar([x + offset for x in range(len(labels))], values, w, label=name, color=color)
    ax.set_xticks(list(range(len(labels))))
    ax.set_xticklabels(labels, fontsize=7, rotation=15 if len(labels) > 5 else 0)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=7)
    if n > 1:
        ax.legend(fontsize=7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _png_image(data: bytes, width=250*mm, height=90*mm):
    return RLImage(io.BytesIO(data), width=width, height=height)


# ---------- Page-level exports ----------

def generate_summary_pdf(db: Session, period_type: str = "quarter",
                         from_period: str = "", to_period: str = "") -> bytes:
    months = get_months_sorted(db)
    defs = {d.key: d for d in db.query(MetricDefinition).order_by(MetricDefinition.sort_order).all()}
    indices = {"quarter": [1, 2, 3, 4], "half": [1, 2], "year": [1]}.get(period_type, [1, 2, 3, 4])
    periods = []
    for year in sorted({m.year for m in months}):
        for idx in indices:
            ms = months_in_period(months, year, period_type, idx)
            if not ms:
                continue
            agg = aggregate_months(ms)
            periods.append((period_label(year, period_type, idx), agg))

    # Same bounds as /hr/analytics/summary: period labels, either side optional. An
    # unknown bound widens to the full range rather than producing an empty report.
    labels = [p[0] for p in periods]
    lo = labels.index(from_period) if from_period in labels else 0
    hi = labels.index(to_period) if to_period in labels else len(periods) - 1
    if lo > hi:
        lo, hi = hi, lo
    periods = periods[lo:hi + 1]

    scope = {"quarter": "Кварталы", "half": "Полугодия", "year": "Годы"}.get(period_type, "")
    if periods and (from_period or to_period):
        scope += f" · {periods[0][0]} — {periods[-1][0]}"

    ss = _styles()
    story = _header(ss, "Сводка по периодам — АЛМИ Партнер", scope)

    head = ["Период", "Месяцев", "Принято", "Уволено", "Чистый прирост"]
    rows = [head] + [[label, str(a["months_count"]), str(a["hired"]), str(a["fired"]),
                      f"{a['net']:+d}"] for label, a in periods]
    story.append(_grid_table(rows, [60*mm, 25*mm, 25*mm, 25*mm, 35*mm], font_size=9))

    if periods:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Динамика по периодам", ss["HRH2"]))
        png = _bar_png([p[0] for p in periods], [
            ("Принято", [p[1]["hired"] for p in periods], "#2d6e17"),
            ("Уволено", [p[1]["fired"] for p in periods], "#c0392b"),
        ])
        story.append(_png_image(png, width=170*mm, height=64*mm))

    # One row per metric, one column per period.
    metric_keys = []
    for _, agg in periods:
        for key in agg["metrics"]:
            if key not in metric_keys:
                metric_keys.append(key)
    metric_keys.sort(key=lambda k: defs[k].sort_order if k in defs else 9999)
    if metric_keys:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Метрики по периодам", ss["HRH2"]))
        head = ["Метрика"] + [p[0] for p in periods]
        rows = [head]
        for key in metric_keys:
            d = defs.get(key)
            rows.append([d.label if d else key] +
                        [_fmt_val(agg["metrics"].get(key), d.unit if d else "") for _, agg in periods])
        first = 70*mm
        rest = (176*mm - first) / max(len(periods), 1)
        story.append(_grid_table(rows, [first] + [rest] * len(periods), font_size=7))

    return _build(story, ss)


def generate_registry_pdf(db: Session, month_key: str = "", event_type: str = "",
                          department: str = "", search: str = "") -> bytes:
    months = get_months_sorted(db)
    rows_data = []
    for m in months:
        if month_key and m.key != month_key:
            continue
        for e in m.employees:
            if event_type and e.event_type != event_type:
                continue
            if department and (e.department or "") != department:
                continue
            if search and search.lower() not in (e.full_name or "").lower():
                continue
            rows_data.append((m, e))
    rows_data.sort(key=lambda pair: (pair[1].event_date, pair[1].full_name))

    applied = [x for x in [
        f"месяц: {month_key}" if month_key else "",
        "тип: приём" if event_type == "hired" else ("тип: увольнение" if event_type == "fired" else ""),
        f"отдел: {department}" if department else "",
        f"поиск: {search}" if search else "",
    ] if x]

    ss = _styles()
    story = _header(ss, "Реестр сотрудников — АЛМИ Партнер",
                    "Фильтры — " + ", ".join(applied) if applied else "Все записи")
    story.append(Paragraph(f"Записей: {len(rows_data)}", ss["HRBody"]))
    story.append(Spacer(1, 6))

    head = ["Тип", "Дата", "ФИО", "Должность", "Отдел", "Месяц"]
    table_rows = [head] + [[
        "Приём" if e.event_type == "hired" else "Увольнение",
        e.event_date.strftime("%d.%m.%Y"),
        (e.full_name or "")[:45],
        (e.position or "")[:40],
        (e.department or "")[:30],
        m.label,
    ] for m, e in rows_data]
    if len(table_rows) == 1:
        story.append(Paragraph("Нет записей, удовлетворяющих фильтрам.", ss["HRBody"]))
    else:
        story.append(_grid_table(table_rows, [22*mm, 22*mm, 70*mm, 60*mm, 40*mm, 30*mm], font_size=7))
    return _build(story, ss, landscape_mode=True)


def generate_benchmarks_pdf(db: Session) -> bytes:
    rows = benchmark_rows(db)
    ss = _styles()
    story = _header(ss, "Бенчмарки и цели — АЛМИ Партнер", "Служба персонала")

    head = ["Метрика", "Период", "Цель", "Факт", "Отклонение", "Статус"]
    status_labels = {"green": "Цель достигнута", "yellow": "Близко к цели",
                     "red": "Ниже цели", "gray": "Справочно"}
    table_rows = [head]
    light_keys = []
    for b in rows:
        light_keys.append(b["status"])
        table_rows.append([
            b["metric_label"][:45],
            b["label"] or str(b["year"]),
            _fmt_val(b["target_value"], b["unit"]),
            _fmt_val(b["current_value"], b["unit"]) + (f" · {b['current_month']}" if b["current_month"] else ""),
            "—" if b["diff"] is None else f"{b['diff']:+.2f}".replace(".", ","),
            status_labels.get(b["status"], "—"),
        ])
    story.append(_grid_table(table_rows, [50*mm, 20*mm, 22*mm, 38*mm, 24*mm, 32*mm],
                             font_size=8, light_col=5, light_keys=light_keys))

    charted = [b for b in rows if b["target_value"] is not None and b["current_value"] is not None]
    if charted:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Цель и факт", ss["HRH2"]))
        png = _bar_png([b["metric_label"][:18] for b in charted], [
            ("Цель", [b["target_value"] for b in charted], "#6b6a65"),
            ("Факт", [b["current_value"] for b in charted], "#1a4f80"),
        ])
        story.append(_png_image(png, width=170*mm, height=64*mm))
    return _build(story, ss)


PARTNERSHIP_STATUS_LIGHTS = {
    "Завершено": "green", "В работе": "yellow",
    "Отложено": "yellow", "Не подписывают": "red",
}


def _partnership_lights(db: Session) -> dict[str, str]:
    """Admin-edited status rules win; the shipped defaults are the fallback."""
    out = dict(PARTNERSHIP_STATUS_LIGHTS)
    for r in db.query(PartnershipLightRule).filter(PartnershipLightRule.group_key == "status").all():
        out[r.label] = r.light
    return out


def generate_partnerships_pdf(db: Session, status: str = "", almi_product: str = "",
                              direction: str = "", type_: str = "", search: str = "") -> bytes:
    rows = db.query(Partnership).order_by(Partnership.partner).all()
    if status:
        rows = [r for r in rows if r.status == status]
    if almi_product:
        rows = [r for r in rows if r.almi_product == almi_product]
    if direction:
        rows = [r for r in rows if r.direction == direction]
    if type_:
        rows = [r for r in rows if r.type == type_]
    if search:
        q = search.lower()
        rows = [r for r in rows if any(q in (v or "").lower()
                                       for v in (r.partner, r.product, r.direction, r.comment))]

    applied = [x for x in [
        f"статус: {status}" if status else "",
        f"продукт АЛМИ: {almi_product}" if almi_product else "",
        f"направление: {direction}" if direction else "",
        f"тип: {type_}" if type_ else "",
        f"поиск: {search}" if search else "",
    ] if x]

    ss = _styles()
    story = _header(ss, "Реестр технологических партнёрств — АЛМИ Партнер",
                    "Фильтры — " + ", ".join(applied) if applied else "Все записи")
    story.append(Paragraph(f"Записей: {len(rows)}", ss["HRBody"]))
    story.append(Spacer(1, 6))

    lights = _partnership_lights(db)
    light_keys = [lights.get(r.status or "", "gray") for r in rows]
    head = ["Партнёр", "Продукт", "Направление", "Продукт АЛМИ", "Статус",
            "Дата серт.", "NDA", "Соглаш.", "Светофор"]
    table_rows = [head] + [[
        (r.partner or "")[:32], (r.product or "")[:28], (r.direction or "")[:26],
        (r.almi_product or "")[:20], r.status or "",
        r.cert_date.strftime("%d.%m.%Y") if r.cert_date else "—",
        "да" if r.nda else "нет", "да" if r.agreement else "нет",
        LIGHT_LABELS.get(key, "—"),
    ] for r, key in zip(rows, light_keys)]
    if len(table_rows) == 1:
        story.append(Paragraph("Нет записей, удовлетворяющих фильтрам.", ss["HRBody"]))
    else:
        story.append(_grid_table(table_rows,
                                 [40*mm, 34*mm, 32*mm, 26*mm, 24*mm, 20*mm, 12*mm, 15*mm, 24*mm],
                                 font_size=6.5, light_col=8, light_keys=light_keys))
    return _build(story, ss, landscape_mode=True)


def generate_partnerships_summary_pdf(db: Session) -> bytes:
    rows = [r for r in db.query(Partnership).all() if r.cert_date]
    years = sorted({r.cert_date.year for r in rows})
    ss = _styles()
    story = _header(ss, "Сводка технологических партнёрств — АЛМИ Партнер",
                    "Проектный и продуктовый офис")

    head = ["Год", "Всего", "Норма", "Внимание", "Критично", "NDA", "Соглашения"]
    table_rows = [head]
    per_year = []
    status_lights = _partnership_lights(db)
    for year in years:
        group = [r for r in rows if r.cert_date.year == year]
        lights = [status_lights.get(r.status or "", "gray") for r in group]
        stats = {
            "total": len(group),
            "green": lights.count("green"),
            "yellow": lights.count("yellow"),
            "red": lights.count("red"),
            "nda": sum(1 for r in group if r.nda),
            "agr": sum(1 for r in group if r.agreement),
        }
        per_year.append((str(year), stats))
        table_rows.append([str(year), str(stats["total"]), str(stats["green"]),
                           str(stats["yellow"]), str(stats["red"]),
                           str(stats["nda"]), str(stats["agr"])])
    if len(table_rows) == 1:
        story.append(Paragraph("Нет партнёрств с датой сертификата.", ss["HRBody"]))
    else:
        story.append(_grid_table(table_rows, [22*mm, 22*mm, 24*mm, 26*mm, 26*mm, 22*mm, 28*mm],
                                 font_size=9))
        story.append(Spacer(1, 10))
        story.append(Paragraph("Светофор по годам", ss["HRH2"]))
        png = _bar_png([y for y, _ in per_year], [
            ("Норма", [s["green"] for _, s in per_year], "#2d6e17"),
            ("Внимание", [s["yellow"] for _, s in per_year], "#a06010"),
            ("Критично", [s["red"] for _, s in per_year], "#c0392b"),
        ])
        story.append(_png_image(png, width=170*mm, height=64*mm))
    return _build(story, ss)


def generate_dashboard_pdf(db: Session, period_label: str = "", months_filter: list[str] | None = None) -> bytes:
    all_months = get_months_sorted(db)
    if months_filter:
        all_months = [m for m in all_months if m.key in months_filter]
    if not all_months:
        all_months = get_months_sorted(db)
    months = all_months
    benchmarks = get_benchmarks(db)
    defs = {d.key: d for d in db.query(MetricDefinition).order_by(MetricDefinition.sort_order).all()}

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=12*mm)
    ss = _styles()
    story = []

    story.append(Paragraph("Служба персонала — АЛМИ Партнер", ss["HRTitle"]))
    story.append(Paragraph(f"Отчёт сформирован: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}"
                           + (f" · Период: {period_label}" if period_label else ""), ss["HRSub"]))

    # KPI table for each month
    for m in months:
        story.append(Paragraph(m.label, ss["HRH2"]))
        hired = len([e for e in m.employees if e.event_type == "hired"])
        fired = len([e for e in m.employees if e.event_type == "fired"])
        kpi_data = [["Принято", "Уволено", "Чистый прирост"],
                    [str(hired), str(fired), f"{hired - fired:+d}"]]
        t = Table(kpi_data, colWidths=[50*mm, 50*mm, 50*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_LIGHT),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#6b6a65")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (-1, -1), _font()),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 1), (-1, 1), _font_bold()),
            ("FONTSIZE", (0, 1), (-1, 1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dbd8d2")),
        ]))
        story.append(t)
        story.append(Spacer(1, 6))

        # Metrics with traffic light
        metric_rows = [["Метрика", "Значение", "Статус"]]
        metric_lights = []
        for mv in m.metric_values:
            d = defs.get(mv.metric_key)
            if not d:
                continue
            light = traffic_light_for_metric(db, d.key, mv.numeric_value)
            metric_lights.append(light)
            metric_rows.append([d.label, _fmt_val(mv.numeric_value, d.unit),
                                LIGHT_LABELS.get(light, "—")])
        mt = Table(metric_rows, colWidths=[85*mm, 33*mm, 32*mm])
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), C_LIGHT),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, 0), (-1, -1), _font()),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dbd8d2")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
        ]
        for i, light in enumerate(metric_lights, 1):
            clr = LIGHT_COLORS.get(light, C_GRAY)
            style_cmds.append(("BACKGROUND", (2, i), (2, i), clr))
            style_cmds.append(("TEXTCOLOR", (2, i), (2, i), colors.white))
            style_cmds.append(("FONTNAME", (2, i), (2, i), _font_bold()))
        mt.setStyle(TableStyle(style_cmds))
        story.append(mt)

        # Employees table
        emps = sorted(m.employees, key=lambda e: (e.event_date, e.event_type))
        if emps:
            story.append(Spacer(1, 8))
            emp_rows = [["Тип", "Дата", "ФИО", "Должность", "Служба"]]
            for e in emps:
                emp_rows.append(["Приём" if e.event_type == "hired" else "Увольнение",
                                 e.event_date.strftime("%d.%m.%Y"), e.full_name[:35],
                                 e.position[:30], e.department[:25]])
            et = Table(emp_rows, colWidths=[18*mm, 18*mm, 50*mm, 45*mm, 34*mm])
            et.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), C_LIGHT),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("FONTNAME", (0, 0), (-1, -1), _font()),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbd8d2")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(et)

        if m.notes:
            story.append(Spacer(1, 4))
            story.append(Paragraph(f"<i>Заметки:</i> {m.notes}", ss["HRBody"]))
        story.append(Spacer(1, 14))

    # Charts
    if len(months) >= 1:
        story.append(Paragraph("Динамика по месяцам", ss["HRH2"]))
        img1 = _chart_hire_fire(months)
        story.append(RLImage(io.BytesIO(img1), width=160*mm, height=70*mm))
        img2 = _chart_turnover(months, benchmarks)
        if img2:
            story.append(Spacer(1, 6))
            story.append(RLImage(io.BytesIO(img2), width=160*mm, height=70*mm))

    # Source
    story.append(Spacer(1, 12))
    story.append(Paragraph("Источник: внутренние данные службы персонала. "
                           "Сформировано автоматически системой HR-аналитики АЛМИ Партнер.", ss["HRSrc"]))

    doc.build(story)
    buf.seek(0)
    return buf.read()
