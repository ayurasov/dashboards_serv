"""Техническая поддержка: метаданные показателей, импорт и экспорт недельного отчёта."""
from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from ..core.errors import ValidationFailed
from ..models import TP_METRIC_COLUMNS, TpWeeklyReport

TP_GROUPS = {
    "load": "Нагрузка",
    "client_hours": "Трудозатраты по клиентам",
    "tickets": "Поток заявок",
    "altos_channels": "AlterOS: каналы",
    "altoffice_channels": "AlterOffice: каналы",
    "projserver": "Project Server",
    "altos_sla": "AlterOS: решение",
    "altoffice_sla": "AlterOffice: решение",
    "altos_avail": "AlterOS: доступность",
    "altoffice_avail": "AlterOffice: доступность",
}

# key, подпись, группа, единица
COLUMN_META: tuple[tuple[str, str, str, str], ...] = (
    ("total_in_work", "Итого в работе заявок", "load", "шт."),
    ("avail_total", "Трудозатраты всего доступно", "load", "ч"),
    ("rushydro_hours", "РусГидро", "client_hours", "ч"),
    ("transneft_hours", "Транснефть", "client_hours", "ч"),
    ("roscosmos_hours", "Роскосмос", "client_hours", "ч"),
    ("bryansk_hours", "Брянск", "client_hours", "ч"),
    ("mchs_hours", "МЧС", "client_hours", "ч"),
    ("internal_sales_hours", "Внутренние задачи и продажи", "client_hours", "ч"),
    ("new_received", "Принято новых заявок", "tickets", "шт."),
    ("renewed", "Возобновлено", "tickets", "шт."),
    ("ratio_solved_received", "Отношение решено / получено", "tickets", ""),
    ("total_solved_week", "Решено за неделю", "tickets", "шт."),
    ("altos_rusg_email", "AlterOS · РусГидро · e-mail", "altos_channels", "шт."),
    ("altos_rusg_tf", "AlterOS · РусГидро · телефон", "altos_channels", "шт."),
    ("altos_other_email", "AlterOS · прочие · e-mail", "altos_channels", "шт."),
    ("altos_other_tf", "AlterOS · прочие · телефон", "altos_channels", "шт."),
    ("altoffice_rusg_email", "AlterOffice · РусГидро · e-mail", "altoffice_channels", "шт."),
    ("altoffice_rusg_tf", "AlterOffice · РусГидро · телефон", "altoffice_channels", "шт."),
    ("altoffice_other_email", "AlterOffice · прочие · e-mail", "altoffice_channels", "шт."),
    ("altoffice_other_tf", "AlterOffice · прочие · телефон", "altoffice_channels", "шт."),
    ("projserver_taken", "Project Server · принято", "projserver", "шт."),
    ("projserver_solved", "Project Server · решено", "projserver", "шт."),
    ("projserver_avail", "Project Server · доступно", "projserver", "ч"),
    ("altos_avg_time", "AlterOS · среднее время решения", "altos_sla", "ч"),
    ("altos_total", "AlterOS · решено всего", "altos_sla", "шт."),
    ("altos_1_2line", "AlterOS · 1–2 линия", "altos_sla", "шт."),
    ("altos_3line", "AlterOS · 3 линия", "altos_sla", "шт."),
    ("altoffice_avg_time", "AlterOffice · среднее время решения", "altoffice_sla", "ч"),
    ("altoffice_total", "AlterOffice · решено всего", "altoffice_sla", "шт."),
    ("altoffice_1_2line", "AlterOffice · 1–2 линия", "altoffice_sla", "шт."),
    ("altoffice_3line", "AlterOffice · 3 линия", "altoffice_sla", "шт."),
    ("altos_avail_total", "AlterOS · доступно всего", "altos_avail", "ч"),
    ("altos_avail_1_3", "AlterOS · сложность 1–3", "altos_avail", "ч"),
    ("altos_avail_4_7", "AlterOS · сложность 4–7", "altos_avail", "ч"),
    ("altos_avail_8_10", "AlterOS · сложность 8–10", "altos_avail", "ч"),
    ("altoffice_avail_total", "AlterOffice · доступно всего", "altoffice_avail", "ч"),
    ("altoffice_avail_1_3", "AlterOffice · сложность 1–3", "altoffice_avail", "ч"),
    ("altoffice_avail_4_7", "AlterOffice · сложность 4–7", "altoffice_avail", "ч"),
    ("altoffice_avail_8_10", "AlterOffice · сложность 8–10", "altoffice_avail", "ч"),
)
META_BY_KEY = {key: {"key": key, "label": label, "group": group, "unit": unit}
               for key, label, group, unit in COLUMN_META}
assert set(META_BY_KEY) == set(TP_METRIC_COLUMNS), "COLUMN_META и TP_METRIC_COLUMNS разошлись"

# Столбец исходного xlsx «Итоговый отчёт ТП по неделям» → показатель (4 строки шапки, данные с 5-й).
XLSX_COLUMNS: dict[int, str] = {
    0: "year", 1: "week", 2: "total_in_work", 3: "avail_total",
    4: "rushydro_hours", 5: "transneft_hours", 6: "roscosmos_hours",
    7: "bryansk_hours", 8: "mchs_hours", 9: "internal_sales_hours",
    10: "new_received", 11: "renewed", 12: "ratio_solved_received",
    13: "altos_rusg_email", 14: "altos_rusg_tf", 15: "altos_other_email", 16: "altos_other_tf",
    17: "altoffice_rusg_email", 18: "altoffice_rusg_tf", 19: "altoffice_other_email", 20: "altoffice_other_tf",
    21: "projserver_taken", 22: "total_solved_week",
    23: "altos_avg_time", 24: "altos_total", 25: "altos_1_2line", 26: "altos_3line",
    27: "altoffice_avg_time", 28: "altoffice_total", 29: "altoffice_1_2line", 30: "altoffice_3line",
    31: "projserver_solved",
    32: "altos_avail_total", 33: "altos_avail_1_3", 34: "altos_avail_4_7", 35: "altos_avail_8_10",
    36: "altoffice_avail_total", 37: "altoffice_avail_1_3", 38: "altoffice_avail_4_7", 39: "altoffice_avail_8_10",
    40: "projserver_avail",
}
XLSX_HEADERS = [
    ["Год", "№ недели", "Итого в работе заявок", "Трудозатраты чел./часов", "", "", "", "", "", "",
     "Принято новых заявок", "", "", "", "", "", "", "", "", "", "", "", "Решено заявок"] + [""] * 19,
    ["", "", "", "Всего доступно", "ТП РусГидро", "ТП Транснефть", "ТП Роскосмос", "ТП Брянск", "ТП МЧС",
     "Внутренние задачи + SALES", "Итого получено за неделю", "Возобновлено за неделю",
     "Отношение решённых к полученным", "Поддержка AlterOS", "", "", "", "Поддержка AlterOffice", "", "", "",
     "Project Server", "", "", "", "", "", "", "", "", "", "", "Поддержка AlterOS", "", "", "",
     "Поддержка AlterOffice", "", "", "", "Поддержка Project Server", ""],
    ["", "", "", "", "", "", "", "", "", "", "", "", "", "РусГидро", "", "Остальные клиенты", "", "РусГидро", "",
     "Остальные клиенты", "", "", "Итого решено за неделю", "Поддержка AlterOS", "", "", "",
     "Поддержка AlterOffice", "", "", "", "Project Server", "", "из них 1–2 линия", "", "3 линия", "",
     "из них 1–2 линия", "", "3 линия", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", "", "", "Получено по e-mail", "Принято по телефону",
     "Получено по e-mail", "Принято по телефону", "Получено по e-mail", "Принято по телефону",
     "Получено по e-mail", "Принято по телефону", "Принято в работу", "", "Среднее время решения", "Итого",
     "из них 1–2 линия", "3 линия", "Среднее время решения", "Итого", "из них 1–2 линия", "3 линия", "",
     "Итого", "Сложность 1–3", "Сложность 4–7", "Сложность 8–10", "Итого", "Сложность 1–3",
     "Сложность 4–7", "Сложность 8–10", "", ""],
]


def to_number(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if text in ("", "-", "—"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _valid_week(rec: dict) -> bool:
    year, week = rec.get("year"), rec.get("week")
    return year is not None and week is not None and 2000 <= year <= 2100 and 1 <= week <= 53


def parse_xlsx(raw: bytes) -> tuple[list[dict], int]:
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:
        raise ValidationFailed("Не удалось прочитать файл Excel") from exc
    ws = wb["Лист1"] if "Лист1" in wb.sheetnames else wb.worksheets[0]
    records, skipped = [], 0
    for row in ws.iter_rows(min_row=5, values_only=True):
        if not row or all(v is None for v in row):
            continue
        rec = {key: to_number(row[idx]) if idx < len(row) else None for idx, key in XLSX_COLUMNS.items()}
        if not _valid_week(rec):
            skipped += 1
            continue
        rec["year"], rec["week"] = int(rec["year"]), int(rec["week"])
        records.append(rec)
    return records, skipped


def _header_map() -> dict[str, str]:
    mapping = {"year": "year", "год": "year", "week": "week", "неделя": "week", "№ недели": "week",
               "note": "note", "примечание": "note", "extra": "note"}
    for key, meta in META_BY_KEY.items():
        mapping[key] = key
        mapping[meta["label"].lower()] = key
    return mapping


def parse_csv(raw: bytes) -> tuple[list[dict], int]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1251")
    sample = text[:2000]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = next(reader, None)
    if not header:
        return [], 0
    mapping = _header_map()
    keys = [mapping.get(h.strip().lower()) for h in header]
    records, skipped = [], 0
    for values in reader:
        if not values or not any(v.strip() for v in values):
            continue
        rec: dict = {}
        for key, value in zip(keys, values, strict=False):
            if not key:
                continue
            rec[key] = value.strip() if key == "note" else to_number(value)
        if not _valid_week(rec):
            skipped += 1
            continue
        rec["year"], rec["week"] = int(rec["year"]), int(rec["week"])
        records.append(rec)
    return records, skipped


def parse_upload(filename: str, raw: bytes) -> tuple[list[dict], int]:
    name = filename.lower()
    if name.endswith(".csv"):
        records, skipped = parse_csv(raw)
    elif name.endswith((".xlsx", ".xlsm")):
        records, skipped = parse_xlsx(raw)
    else:
        raise ValidationFailed("Поддерживаются файлы .xlsx и .csv")
    if not records:
        raise ValidationFailed("В файле нет ни одной строки с годом и неделей")
    # Повтор недели внутри файла: побеждает последняя строка
    unique = {(r["year"], r["week"]): r for r in records}
    return sorted(unique.values(), key=lambda r: (r["year"], r["week"])), skipped + len(records) - len(unique)


def row_to_dict(row: TpWeeklyReport) -> dict:
    data = {"id": row.id, "year": row.year, "week": row.week, "period": row.period, "note": row.note or "",
            "updated_at": row.updated_at}
    data.update({c: getattr(row, c) for c in TP_METRIC_COLUMNS})
    return data


def _csv_number(value) -> str:
    """Число для CSV в русском Excel: запятая, целые — без «,0» («274», а не «274,0»)."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).replace(".", ",")


def export_csv(rows: Iterable[TpWeeklyReport]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    keys = list(TP_METRIC_COLUMNS)
    writer.writerow(["Год", "Неделя", *[META_BY_KEY[k]["label"] for k in keys], "Примечание"])
    for row in rows:
        values = [getattr(row, k) for k in keys]
        writer.writerow([row.year, row.week, *[_csv_number(v) for v in values], row.note or ""])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def export_xlsx(rows: Iterable[TpWeeklyReport]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Лист1"
    for header in XLSX_HEADERS:
        ws.append(header)
    for cell in ws[1] + ws[2] + ws[3] + ws[4]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    index_by_key = {key: idx for idx, key in XLSX_COLUMNS.items()}
    for row in rows:
        out: list = [None] * 42
        out[0], out[1] = row.year, row.week
        for key in TP_METRIC_COLUMNS:
            out[index_by_key[key]] = getattr(row, key)
        ws.append(out)
    ws.freeze_panes = "C5"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
