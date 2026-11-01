"""Наборы входящих данных (ADR-0011): распознавание файла, план и применение через движки загрузки служб.

Набор — подкласс Dataset, зарегистрированный декоратором @register. Он описывает:
- key, label, description, formats — ключ (он же имя подпапки в «Входящих»), подписи для интерфейса;
- patterns — шаблоны имени файла (fnmatch, без учёта регистра), sniff(peek) — оценка по содержимому
  0…100 (peek — первые строки таблицы или разобранный JSON); распознавание берёт лучший набор
  с оценкой не меньше DETECT_THRESHOLD, при равенстве лучших — не распознаёт;
- parse(filename, content, options) → данные для движка; plan(db, data, actor, options) → план
  (словарь со summary и can_apply, без записи в базу); apply(db, data, actor, options, filename,
  request) → (итог, применён ли) — одной транзакцией, commit делает вызывающий;
- service_key — служба, чья ревизия данных растёт при применении (движок пишет журнал с этой
  службой); None — у набора своя ревизия (структура, сквозные отчёты);
- кто применяет: полномочие data.manage — всегда; иначе capability (org.manage, reports.manage)
  или уровень apply_level к службе service_key (и класс данных data_class, если задан); can_view —
  кто видит чужие элементы набора (по умолчанию те же), свои загрузки видны всегда;
- option_fields и normalize_options — параметры загрузки (режим merge/replace и т. п.).

Движки — те же, что у ручной загрузки на страницах служб: app/services/tp.py, naumen.py,
partnerships.py, hr_import.py, report_admin.py, org_transfer.py, employee_transfer.py.

Форматы JSON других систем (например, podelu.org-structure) подключаются register_json_format:
распознавание выбирает набор по полю format, а parse сначала переводит документ в наш формат.
"""
from __future__ import annotations

import fnmatch
import io
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from fastapi import Request
from sqlalchemy.orm import Session

from ..core.errors import ValidationFailed
from ..models import User
from . import access
from .registry import ACCESS_LEVEL_RANK, HR_METRICS

DETECT_THRESHOLD = 50
PATTERN_BONUS = 20
PEEK_ROWS = 8


# ---------------------------------------------------------------- взгляд на содержимое

@dataclass
class Peek:
    """Первые строки таблицы (xlsx — первого листа, csv) или разобранный JSON — для sniff()."""

    filename: str
    kind: str                         # xlsx · csv · json · other
    rows: list[list[str]] = field(default_factory=list)
    data: Any = None                  # JSON
    words: set[str] = field(default_factory=set)

    @property
    def json_format(self) -> str | None:
        return self.data.get("format") if isinstance(self.data, dict) and isinstance(self.data.get("format"), str) \
            else None

    def header(self) -> list[str]:
        """Первая непустая строка (casefold)."""
        for row in self.rows:
            if any(row):
                return [c.casefold() for c in row]
        return []


def _cell(value) -> str:
    from .org_import import cell_text

    return " ".join(cell_text(value).split())


def peek(filename: str, content: bytes) -> Peek:
    name = (filename or "").lower()
    if content[:4] == b"PK\x03\x04" or name.endswith((".xlsx", ".xlsm")):
        try:
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            try:
                rows = [[_cell(v) for v in row] for row in wb.worksheets[0].iter_rows(max_row=PEEK_ROWS,
                                                                                         values_only=True)]
            finally:
                wb.close()
        except Exception:  # noqa: BLE001 — повреждённый файл: распознать нельзя, разбор покажет ошибку
            return Peek(filename, "other")
        return _with_words(Peek(filename, "xlsx", rows))
    from .org_import import decode_text

    text = decode_text(content[:1_000_000]).lstrip("﻿")
    stripped = text.lstrip()
    if name.endswith(".json") or stripped[:1] in ("{", "["):
        try:
            return Peek(filename, "json", data=json.loads(decode_text(content)))
        except ValueError:
            if name.endswith(".json"):
                return Peek(filename, "other")
    if name.endswith((".csv", ".txt")) or not name.endswith((".pdf", ".doc", ".docx", ".zip")):
        import csv

        sample = text[:4096]
        counts = {";": sample.count(";"), ",": sample.count(","), "\t": sample.count("\t")}
        delimiter = max(counts, key=lambda d: (counts[d], d == ";"))
        rows = []
        for values in csv.reader(io.StringIO(text), delimiter=delimiter):
            rows.append([" ".join(v.split()) for v in values])
            if len(rows) >= PEEK_ROWS:
                break
        return _with_words(Peek(filename, "csv", rows))
    return Peek(filename, "other")


def _with_words(p: Peek) -> Peek:
    p.words = {c.casefold() for row in p.rows for c in row if c}
    return p


# ---------------------------------------------------------------- наборы

@dataclass(frozen=True)
class OptionField:
    key: str
    label: str
    type: str                       # select · bool
    default: Any
    options: tuple[tuple[str, str], ...] = ()
    hint: str = ""

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "type": self.type, "default": self.default, "hint": self.hint,
                "options": [{"value": v, "label": label} for v, label in self.options]}


class Dataset:
    key: ClassVar[str]
    label: ClassVar[str]
    description: ClassVar[str] = ""
    formats: ClassVar[str] = "Excel (.xlsx), CSV"
    service_key: ClassVar[str | None] = None
    apply_level: ClassVar[str | None] = "editor"
    data_class: ClassVar[str | None] = None
    capability: ClassVar[str | None] = None
    patterns: ClassVar[tuple[str, ...]] = ()
    option_fields: ClassVar[tuple[OptionField, ...]] = ()

    # --- распознавание
    def sniff(self, p: Peek) -> int:
        return 0

    def score(self, p: Peek) -> int:
        base = self.sniff(p)
        name = (p.filename or "").casefold()
        if any(fnmatch.fnmatch(name, pattern) for pattern in self.patterns):
            base += PATTERN_BONUS
        return min(base, 100)

    # --- параметры
    def normalize_options(self, options: dict | None) -> dict:
        options = dict(options or {})
        out: dict = {}
        for opt in self.option_fields:
            value = options.pop(opt.key, opt.default)
            if opt.type == "bool":
                value = value if isinstance(value, bool) else str(value).strip().lower() in {"1", "true", "yes", "да"}
            elif opt.type == "select" and value not in {v for v, _ in opt.options}:
                raise ValidationFailed(f"{opt.label}: недопустимое значение «{value}»",
                                       fields={f"options.{opt.key}": "Недопустимое значение"})
            out[opt.key] = value
        if options:
            raise ValidationFailed(f"Неизвестный параметр набора «{self.label}»: {next(iter(options))}",
                                   fields={"options": "Неизвестный параметр"})
        return out

    # --- движок
    def parse(self, filename: str, content: bytes, options: dict) -> Any:  # pragma: no cover - абстрактный
        raise NotImplementedError

    def plan(self, db: Session, data: Any, actor: User, options: dict) -> dict:  # pragma: no cover
        raise NotImplementedError

    def apply(self, db: Session, data: Any, actor: User, options: dict, filename: str,
              request: Request | None) -> tuple[dict, bool]:  # pragma: no cover
        raise NotImplementedError

    # --- доступ
    def can_apply(self, user: User) -> bool:
        if user.can("data.manage"):
            return True
        if self.capability and user.can(self.capability):
            return True
        if self.service_key and self.apply_level:
            if not access.has_level(user, self.service_key, self.apply_level):
                return False
            return self.data_class is None or access.effective(user).allows(self.data_class)
        return False

    def can_view(self, user: User) -> bool:
        """Видеть чужие элементы набора (с планом). Свои загрузки пользователь видит всегда."""
        return self.can_apply(user)

    def meta(self) -> dict:
        return {"key": self.key, "label": self.label, "description": self.description, "formats": self.formats,
                "service_key": self.service_key, "folder": self.key, "patterns": list(self.patterns),
                "options": [o.as_dict() for o in self.option_fields]}


_REGISTRY: dict[str, Dataset] = {}
# format JSON-документа → (набор, перевод в формат набора)
JSON_FORMATS: dict[str, tuple[str, Callable[[Any], Any]]] = {}


def register(cls: type[Dataset]) -> type[Dataset]:
    if cls.key in _REGISTRY:  # pragma: no cover - ошибка программиста
        raise ValueError(f"Набор {cls.key} уже зарегистрирован")
    _REGISTRY[cls.key] = cls()
    return cls


def register_json_format(format_name: str, dataset: str, convert: Callable[[Any], Any]) -> None:
    """Документ {"format": format_name, …} распознаётся как набор dataset; convert(документ) переводит
    его в формат набора (например, podelu.org-structure → dashboards.org-structure)."""
    JSON_FORMATS[format_name] = (dataset, convert)


def get(key: str | None) -> Dataset | None:
    return _REGISTRY.get(key or "")


def require(key: str) -> Dataset:
    dataset = get(key)
    if dataset is None:
        raise ValidationFailed(f"Неизвестный набор данных: {key}", fields={"dataset": "Неизвестный набор"})
    return dataset


def all_datasets() -> list[Dataset]:
    return list(_REGISTRY.values())


def detect(filename: str, content: bytes) -> tuple[Dataset | None, dict[str, int]]:
    """Набор по имени и содержимому файла: (лучший или None, оценки всех наборов)."""
    p = peek(filename, content)
    if p.json_format in JSON_FORMATS:
        key = JSON_FORMATS[p.json_format][0]
        return get(key), {key: 100}
    scores = {d.key: d.score(p) for d in _REGISTRY.values()}
    best = max(scores.values(), default=0)
    leaders = [k for k, v in scores.items() if v == best]
    if best < DETECT_THRESHOLD or len(leaders) != 1:
        return None, scores
    return get(leaders[0]), scores


def _json(content: bytes) -> Any:
    from .org_import import decode_text

    try:
        return json.loads(decode_text(content))
    except ValueError as exc:
        raise ValidationFailed("Файл не является JSON") from exc


def _converted(content: bytes, dataset: str) -> Any:
    data = _json(content)
    if isinstance(data, dict) and data.get("format") in JSON_FORMATS:
        target, convert = JSON_FORMATS[data["format"]]
        if target == dataset:
            return convert(data)
    return data


MODE_OPTION = OptionField("mode", "Режим", "select", "merge",
                          (("merge", "Добавить и обновить"), ("replace", "Заменить целиком")),
                          "«Заменить целиком» удаляет данные, которых нет в файле")


# ---------------------------------------------------------------- служба персонала

HR_LABELS = {m.label.casefold() for m in HR_METRICS} | {m.key for m in HR_METRICS}


@register
class HrMonths(Dataset):
    key = "hr-months"
    label = "Метрики месяцев службы персонала"
    description = "Строки — метрики, столбцы — месяцы (ГГГГ-ММ), как в выгрузке; или столбцы «Месяц», «Метрика», " \
                  "«Значение». Месяцы, которых нет, создаются; пустая ячейка не стирает"
    service_key = "hr"
    patterns = ("*hr-month*", "*метрик*персонал*", "*персонал*метрик*", "*hr_month*")

    def sniff(self, p: Peek) -> int:
        from .hr_import import parse_month

        header = p.header()
        if not header or "подразделение" in header or "фио" in header:
            return 0
        known = sum(1 for row in p.rows for c in row[:2] if c.casefold() in HR_LABELS)
        has_metric = bool({"метрика", "ключ"} & set(header)) or ("показатель" in header and "период" not in header)
        months = sum(1 for c in header if parse_month(c))
        if has_metric and months:
            return 90
        if has_metric and "месяц" in header and "значение" in header:
            return 80
        return 60 if known >= 3 else 0

    def parse(self, filename, content, options):
        from .hr_import import parse_months_upload

        return parse_months_upload(filename, content)

    def plan(self, db, data, actor, options):
        from .hr_import import plan_months

        return plan_months(db, data)

    def apply(self, db, data, actor, options, filename, request):
        from .hr_import import apply_months

        return apply_months(db, actor, data, filename, request)


@register
class HrEvents(Dataset):
    key = "hr-events"
    label = "Приёмы и увольнения"
    description = "Реестр в формате выгрузки: Месяц, Событие (Приём / Увольнение), Дата, ФИО, Должность, " \
                  "Подразделение, Тип занятости, Причина"
    service_key = "hr"
    data_class = "personal"
    patterns = ("*hr-event*", "*реестр*при*м*", "*при*мы*увольнен*", "*hr_event*")

    def sniff(self, p: Peek) -> int:
        words = p.words
        if "фио" in words and "событие" in words and "дата" in words:
            return 90
        if "фио" in words and ("причина" in words or "тип занятости" in words) and "дата" in words:
            return 60
        return 0

    def parse(self, filename, content, options):
        from .hr_import import parse_events_upload

        return parse_events_upload(filename, content)

    def plan(self, db, data, actor, options):
        from .hr_import import plan_events

        return plan_events(db, data)

    def apply(self, db, data, actor, options, filename, request):
        from .hr_import import apply_events

        return apply_events(db, actor, data, filename, request)


# ---------------------------------------------------------------- техническая поддержка

@register
class TpWeekly(Dataset):
    key = "tp-weekly"
    label = "Недельный отчёт техподдержки"
    description = "«Итоговый отчёт ТП по неделям» (Excel, 4 строки шапки) или выгрузка CSV страницы службы"
    service_key = "tech"
    apply_level = "manager"
    patterns = ("*tp-weekly*", "*отч*т*тп*", "*тп*недел*")
    option_fields = (MODE_OPTION,)

    def sniff(self, p: Peek) -> int:
        words = p.words
        if "итого в работе заявок" in words and "год" in words and ("№ недели" in words or "неделя" in words):
            return 90
        return 0

    def parse(self, filename, content, options):
        from .tp import parse_upload

        return parse_upload(filename, content)

    def plan(self, db, data, actor, options):
        from .tp import plan_import

        records, skipped = data
        return plan_import(db, records, skipped, options.get("mode", "merge"))

    def apply(self, db, data, actor, options, filename, request):
        from .tp import apply_import

        records, skipped = data
        return apply_import(db, actor, records, skipped, options.get("mode", "merge"), filename, request)


@register
class Naumen(Dataset):
    key = "naumen"
    label = "Заявки Naumen SD"
    description = "Выгрузка заявок Naumen (Excel): Номер, Дата регистрации, Статус, Организация…; " \
                  "заявки сопоставляются по номеру"
    formats = "Excel (.xlsx)"
    service_key = "tech"
    apply_level = "manager"
    patterns = ("*naumen*", "*наумен*", "*заявк*")
    option_fields = (MODE_OPTION,)

    def sniff(self, p: Peek) -> int:
        if p.kind != "xlsx":
            return 0
        header = set(p.header())
        if "дата регистрации" in header and ({"номер", "статус"} & header):
            return 90
        return 0

    def parse(self, filename, content, options):
        from .naumen import parse_xlsx

        if content[:4] != b"PK\x03\x04":
            raise ValidationFailed("Выгрузка Naumen — файл Excel (.xlsx)")
        return parse_xlsx(content)

    def plan(self, db, data, actor, options):
        from .naumen import plan_import

        records, skipped = data
        return plan_import(db, records, skipped, options.get("mode", "merge"))

    def apply(self, db, data, actor, options, filename, request):
        from .naumen import apply_import

        records, skipped = data
        return apply_import(db, actor, records, skipped, options.get("mode", "merge"), filename, request)


# ---------------------------------------------------------------- партнёрства

@register
class Partnerships(Dataset):
    key = "partnerships"
    label = "Реестр партнёрств"
    description = "Реестр в формате выгрузки: №, Партнёр, Продукт партнёра, Направление, Продукт АЛМИ, Версия, " \
                  "Тип, Статус, Дата сертификата, NDA, Соглашение…"
    service_key = "project_product"
    patterns = ("*partnership*", "*партн*рств*")

    def sniff(self, p: Peek) -> int:
        header = set(p.header())
        if ({"партнёр", "партнер"} & header) and ({"продукт алми", "продукт партнёра", "продукт партнера"} & header):
            return 90
        return 0

    def parse(self, filename, content, options):
        from .partnerships import parse_upload

        return parse_upload(filename, content)

    def plan(self, db, data, actor, options):
        from .partnerships import plan_import

        return plan_import(db, data)

    def apply(self, db, data, actor, options, filename, request):
        from .partnerships import apply_import

        return apply_import(db, actor, data, filename, request)


# ---------------------------------------------------------------- сквозные отчёты

@register
class Indicators(Dataset):
    key = "indicators"
    label = "Значения показателей"
    description = "Столбцы: Подразделение (путь или код), Показатель (ключ или название), Период (ГГГГ-ММ), " \
                  "Значение, Цель, Комментарий"
    capability = "reports.manage"
    apply_level = None
    patterns = ("*indicator*", "*показател*")

    def sniff(self, p: Peek) -> int:
        header = set(p.header())
        if {"подразделение", "показатель", "период"} <= header:
            return 90
        return 0

    def can_apply(self, user: User) -> bool:
        # Права ввода — по строкам (служба-владелец и область структуры): план покажет недоступное
        if super().can_apply(user):
            return True
        eff = access.effective(user)
        return any(ACCESS_LEVEL_RANK[level] >= ACCESS_LEVEL_RANK["editor"] for level in eff.services.values())

    def can_view(self, user: User) -> bool:
        # План файла от источника строится со всеми классами данных (финансовые значения) — чужие элементы
        # видят только ведущие отчётов; редактор служб видит и применяет свои загрузки (план — с его правами)
        return Dataset.can_apply(self, user)

    def parse(self, filename, content, options):
        from .report_admin import parse_upload

        return parse_upload(filename, content)

    def plan(self, db, data, actor, options):
        from .report_admin import plan_import

        return plan_import(db, actor, data)[0]

    def apply(self, db, data, actor, options, filename, request):
        from .report_admin import apply_import

        return apply_import(db, actor, data, filename, request)


# ---------------------------------------------------------------- структура и сотрудники

@register
class Structure(Dataset):
    key = "structure"
    label = "Структура компании"
    description = "Файл структуры dashboards.org-structure (JSON, выгрузка «Структура → Перенос»); подразделения " \
                  "сопоставляются по пути, отсутствующие в файле не удаляются"
    formats = "JSON"
    capability = "org.manage"
    apply_level = None
    patterns = ("*structure*.json", "*структур*.json")
    option_fields = (OptionField("apply_settings", "Применить настройки структуры", "bool", False,
                                 hint="Типы уровней, предел вложенности и вид оргсхемы из файла"),)

    def sniff(self, p: Peek) -> int:
        from .org_transfer import FORMAT

        return 95 if p.json_format == FORMAT else 0

    def parse(self, filename, content, options):
        from .org_transfer import parse_bundle

        bundle = _converted(content, self.key)
        parse_bundle(bundle)  # формат проверяется сразу: понятная ошибка вместо плана
        return bundle

    def plan(self, db, data, actor, options):
        from .org_transfer import plan_structure

        return plan_structure(db, data, apply_settings=bool(options.get("apply_settings"))).as_dict()

    def apply(self, db, data, actor, options, filename, request):
        from .org_transfer import apply_structure

        return apply_structure(db, actor, data, apply_settings=bool(options.get("apply_settings")), request=request)


@register
class Employees(Dataset):
    key = "employees"
    label = "Сотрудники"
    description = "Сотрудники: Excel или CSV со столбцом Email (как выгрузка «Структура → Перенос»), или JSON " \
                  "dashboards.employees; сопоставление по email"
    formats = "Excel (.xlsx), CSV, JSON"
    capability = "org.manage"
    apply_level = None
    patterns = ("*employee*", "*сотрудник*")
    option_fields = (OptionField("new_users", "Новые сотрудники", "select", "no_access",
                                 (("no_access", "Без доступа"), ("inactive", "Отключены"),
                                  ("active", "Вход по домену")),
                                 "Вход по домену выдаёт только ведущий пользователей (users.manage)"),)

    def sniff(self, p: Peek) -> int:
        from .employee_transfer import FORMAT

        if p.json_format == FORMAT:
            return 95
        header = set(p.header())
        if ({"email", "e-mail", "почта"} & header) and ({"фио", "подразделение", "должность", "логин"} & header) \
                and "событие" not in header and "показатель" not in header:
            return 70
        return 0

    def normalize_options(self, options):
        options = dict(options or {})
        decisions = options.pop("decisions", {}) or {}
        if not isinstance(decisions, dict):
            raise ValidationFailed("decisions: ожидается объект", fields={"options.decisions": "Ожидается объект"})
        return {**super().normalize_options(options), "decisions": decisions}

    def parse(self, filename, content, options):
        from .employee_transfer import parse_json, parse_upload

        if (filename or "").lower().endswith(".json") or content.lstrip()[:1] in (b"{", b"["):
            return parse_json(_converted(content, self.key))
        return parse_upload(filename, content)

    def plan(self, db, data, actor, options):
        from .employee_transfer import plan_employees

        return plan_employees(db, data, actor=actor, new_users=options.get("new_users", "no_access"),
                              decisions=options.get("decisions")).as_dict()

    def apply(self, db, data, actor, options, filename, request):
        from .employee_transfer import apply_employees

        return apply_employees(db, actor, data, new_users=options.get("new_users", "no_access"),
                               decisions=options.get("decisions"), request=request)
