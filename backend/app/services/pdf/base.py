"""Оформление PDF-отчётов: шрифты с кириллицей, шапка, таблицы, графики.

Шрифт DejaVu Sans берётся из состава matplotlib — он есть в любом окружении, включая
минимальный Docker-образ (системных шрифтов там нет).
"""
from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4, landscape  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ... import APP_NAME, __version__  # noqa: E402

FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
FONT, FONT_BOLD = "DejaVuSans", "DejaVuSans-Bold"
pdfmetrics.registerFont(TTFont(FONT, str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "DejaVuSans-Bold.ttf")))
plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(FONT_DIR / "DejaVuSans.ttf")).get_name()

INK = colors.HexColor("#1f2430")
MUTED = colors.HexColor("#6b7280")
LINE = colors.HexColor("#e5e7eb")
ZEBRA = colors.HexColor("#f8f9fb")
BRAND = colors.HexColor("#c8302c")

DEFAULT_COLORS = {
    "traffic_light": {"green": "#3f9f6b", "yellow": "#d29a2f", "red": "#d1495b", "neutral": "#a3acb9"},
    "charts": ["#c8302c", "#3f6fb5", "#3f9f6b", "#d29a2f", "#7a5ba6", "#2c9aa6", "#8a8f98"],
}

STYLES = {
    "title": ParagraphStyle("title", fontName=FONT_BOLD, fontSize=17, leading=21, textColor=INK, spaceAfter=2),
    "subtitle": ParagraphStyle("subtitle", fontName=FONT, fontSize=9, leading=12, textColor=MUTED, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName=FONT_BOLD, fontSize=12, leading=15, textColor=INK, spaceBefore=10,
                         spaceAfter=6),
    "body": ParagraphStyle("body", fontName=FONT, fontSize=8.5, leading=11.5, textColor=INK, alignment=TA_LEFT),
    "cell": ParagraphStyle("cell", fontName=FONT, fontSize=7.5, leading=9.5, textColor=INK),
    "cell_bold": ParagraphStyle("cell_bold", fontName=FONT_BOLD, fontSize=7.5, leading=9.5, textColor=INK),
    "kpi_value": ParagraphStyle("kpi_value", fontName=FONT_BOLD, fontSize=15, leading=18, textColor=INK),
    "kpi_label": ParagraphStyle("kpi_label", fontName=FONT, fontSize=7, leading=9, textColor=MUTED),
    "small": ParagraphStyle("small", fontName=FONT, fontSize=7, leading=9, textColor=MUTED),
}


def fmt(value, unit: str = "", digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        text = f"{value:,.{digits}f}".rstrip("0").rstrip(".") if not value.is_integer() else f"{int(value):,}"
    elif isinstance(value, int):
        text = f"{value:,}"
    else:
        return str(value)
    text = text.replace(",", " ").replace(".", ",")
    if unit == "%":
        return f"{text}%"
    return f"{text} {unit}" if unit else text


class Report:
    def __init__(self, title: str, subtitle: str = "", *, wide: bool = False, palette: dict | None = None):
        self.title = title
        self.subtitle = subtitle
        self.pagesize = landscape(A4) if wide else A4
        self.story: list = []
        self.colors = palette or DEFAULT_COLORS
        self.width = self.pagesize[0] - 30 * mm

    # --- цвета
    def light_color(self, light: str):
        tl = self.colors.get("traffic_light", DEFAULT_COLORS["traffic_light"])
        return colors.HexColor(tl.get("neutral" if light == "gray" else light, "#a3acb9"))

    def series_colors(self) -> list[str]:
        return list(self.colors.get("charts") or DEFAULT_COLORS["charts"])

    # --- элементы
    def h2(self, text: str) -> None:
        self.story.append(Paragraph(text, STYLES["h2"]))

    def text(self, text: str, style: str = "body") -> None:
        self.story.append(Paragraph(text, STYLES[style]))

    def spacer(self, height_mm: float = 4) -> None:
        self.story.append(Spacer(1, height_mm * mm))

    def kpis(self, items: Sequence[tuple[str, str, str | None]]) -> None:
        """Плитки показателей: (подпись, значение, цвет светофора или None)."""
        if not items:
            return
        per_row = 4 if self.pagesize == A4 else 6
        cell_w = self.width / per_row
        rows, row = [], []
        for label, value, light in items:
            inner = Table([[Paragraph(value, STYLES["kpi_value"])], [Paragraph(label, STYLES["kpi_label"])]],
                          colWidths=[cell_w - 8])
            style = [("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 2),
                     ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
            if light:
                style.append(("LINEBEFORE", (0, 0), (0, -1), 2.5, self.light_color(light)))
            inner.setStyle(TableStyle(style))
            row.append(inner)
            if len(row) == per_row:
                rows.append(row)
                row = []
        if row:
            rows.append(row + [""] * (per_row - len(row)))
        table = Table(rows, colWidths=[cell_w] * per_row)
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        self.story.append(table)

    def table(self, header: Sequence[str], rows: Sequence[Sequence], widths: Sequence[float] | None = None,
              lights: Sequence[str | None] | None = None, align_right_from: int | None = None,
              bold_last: bool = False) -> None:
        """Таблица с шапкой, «зеброй» и необязательной цветной меткой светофора в первой колонке."""
        data = [[Paragraph(str(h), STYLES["cell_bold"]) for h in header]]
        for r in rows:
            data.append([Paragraph("" if v is None else str(v), STYLES["cell"]) for v in r])
        if widths is None:
            widths = [self.width / len(header)] * len(header)
        else:
            total = sum(widths)
            widths = [w * self.width / total for w in widths]
        table = Table(data, colWidths=widths, repeatRows=1)
        style = [
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(data)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
        if lights:
            for i, light in enumerate(lights, start=1):
                if light:
                    style.append(("LINEBEFORE", (0, i), (0, i), 3, self.light_color(light)))
        if align_right_from is not None:
            style.append(("ALIGN", (align_right_from, 1), (-1, -1), "RIGHT"))
        if bold_last and len(data) > 1:
            style.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, INK))
        table.setStyle(TableStyle(style))
        self.story.append(table)

    def chart(self, figure, height_mm: float = 70) -> None:
        buf = io.BytesIO()
        figure.savefig(buf, format="png", dpi=160, bbox_inches="tight")
        plt.close(figure)
        buf.seek(0)
        ratio = figure.get_figheight() / figure.get_figwidth()
        width = self.width
        height = min(height_mm * mm, width * ratio)
        self.story.append(KeepTogether([Image(buf, width=height / ratio, height=height)]))

    def figure(self, width: float = 10, height: float = 3.6):
        fig, ax = plt.subplots(figsize=(width, height))
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#d1d5db")
        ax.tick_params(colors="#4b5563", labelsize=8)
        ax.grid(axis="y", color="#eef0f3", linewidth=0.8)
        ax.set_axisbelow(True)
        return fig, ax

    # --- сборка
    def _decorate(self, canvas, doc) -> None:
        canvas.saveState()
        w, h = self.pagesize
        canvas.setFillColor(BRAND)
        canvas.rect(15 * mm, h - 12 * mm, 14 * mm, 1.6 * mm, stroke=0, fill=1)
        canvas.setFont(FONT, 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(15 * mm, 9 * mm, f"{APP_NAME} {__version__} · сформировано "
                                           f"{datetime.now().strftime('%d.%m.%Y %H:%M')}")
        canvas.drawRightString(w - 15 * mm, 9 * mm, f"стр. {doc.page}")
        canvas.restoreState()

    def build(self) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=self.pagesize, leftMargin=15 * mm, rightMargin=15 * mm,
                                topMargin=17 * mm, bottomMargin=16 * mm, title=self.title, author=APP_NAME)
        story = [Paragraph(self.title, STYLES["title"])]
        if self.subtitle:
            story.append(Paragraph(self.subtitle, STYLES["subtitle"]))
        story.extend(self.story or [Paragraph("Нет данных для отчёта", STYLES["body"])])
        doc.build(story, onFirstPage=self._decorate, onLaterPages=self._decorate)
        return buf.getvalue()
