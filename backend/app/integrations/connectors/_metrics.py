"""Общее для коннекторов показателей (Jira, Bitrix24, 1С): окно месяцев, шаблоны с подстановками,
описание показателя (ключ из каталога или создание подключением — ctx.plans.ensure_indicator), сопоставление
подразделений и запись значений через ctx.plans.indicator_values — тот же движок, что у загрузки значений
из файла.

Запись: сначала план без записи; применяется, только если есть новые или изменённые значения (повторный
запуск с теми же данными ничего не пишет и не засоряет журнал изменений). Ошибка в плане — ничего
не записывается.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ...core.errors import AppError, ValidationFailed
from ...models import name_key
from ...services import org, reports
from ...services.registry import INDICATOR_DIRECTION_LABELS, SERVICES
from ..base import Field, Option, RunContext
from ..http import IntegrationError

MAX_MONTHS = 24
KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,79}$")
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
MONTH_VARS = ("month", "month_start", "month_end", "next_month_start")
DIRECTIONS = tuple(INDICATOR_DIRECTION_LABELS)
RULE_TYPES = ("threshold", "target")
ROLLUPS = ("sum", "avg", "none")
DATA_CLASSES = ("operational", "personal", "financial")
SAMPLE_ROWS = 50


def months_field(default: int = 2) -> Field:
    return Field("months", "Месяцев к пересчёту", "int", default=default, min=1, max=MAX_MONTHS,
                 hint="Сколько месяцев пересчитывать при каждом запуске: 1 — только текущий, 2 — текущий и прошлый "
                      "(по умолчанию: поздние правки прошлого месяца тоже попадут в отчёт)")


def owner_field(default: str) -> Field:
    return Field("owner_service", "Служба-владелец новых показателей", "select", default=default,
                 options=tuple(Option(s.key, s.title) for s in SERVICES),
                 hint="Если показателя из настроек ещё нет в каталоге, подключение создаёт его с этой службой-"
                      "владельцем: её сотрудники с уровнем «Ввод данных» смогут поправить значение вручную")


# ---------------------------------------------------------------- месяцы и подстановки

@dataclass(frozen=True)
class Month:
    start: date

    @property
    def key(self) -> str:
        return reports.period_key(self.start)

    @property
    def end(self) -> date:
        return reports.month_end(self.start)

    @property
    def next_start(self) -> date:
        return reports.add_months(self.start, 1)

    @property
    def label(self) -> str:
        return reports.period_label(self.start)

    def values(self) -> dict[str, str]:
        """Подстановки шаблонов: {month} — ГГГГ-ММ, {month_start} / {month_end} — первый и последний день,
        {next_month_start} — первый день следующего месяца (для условий «меньше»)."""
        return {"month": self.key, "month_start": self.start.isoformat(), "month_end": self.end.isoformat(),
                "next_month_start": self.next_start.isoformat()}


def window(months: int, today: date | None = None) -> list[Month]:
    """Месяцы к пересчёту, от раннего к текущему (текущий — последний)."""
    current = reports.current_period() if today is None else date(today.year, today.month, 1)
    count = max(1, min(int(months or 1), MAX_MONTHS))
    return [Month(reports.add_months(current, -offset)) for offset in range(count - 1, -1, -1)]


def placeholders(text: str | None) -> set[str]:
    return set(PLACEHOLDER.findall(text or ""))


def check_template(text: str, allowed: Iterable[str], where: str, place: str) -> None:
    allowed = tuple(allowed)
    unknown = sorted(placeholders(text) - set(allowed))
    if unknown:
        names = ", ".join("{" + a + "}" for a in allowed)
        raise ValidationFailed(f"{where}: неизвестная подстановка {{{unknown[0]}}} — допустимо: {names}",
                               fields={place: f"Неизвестная подстановка {{{unknown[0]}}}"})


def render(text: str, values: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text or "")


def monthly(*texts: str | None) -> bool:
    """Есть ли в шаблонах подстановка месяца: без неё запрос — снимок «на сейчас» (только текущий месяц)."""
    return any(placeholders(t) & set(MONTH_VARS) for t in texts)


# ---------------------------------------------------------------- настройки JSON и списки соответствий

def load_list(data: Any, place: str, label: str, *, limit: int = 50) -> list[dict]:
    """Список правил из настройки типа json: разобранный список (или один объект) либо JSON-текст."""
    if isinstance(data, str):
        if not data.strip():
            return []
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValidationFailed(f"{label}: ошибка JSON в строке {exc.lineno}, позиция {exc.colno} — проверьте "
                                   "кавычки (только двойные), запятые и скобки",
                                   fields={place: "Ошибка JSON"}) from None
    if data is None:
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
        raise ValidationFailed(f"{label}: нужен список объектов JSON [{{…}}, {{…}}]", fields={place: "Нужен список"})
    if len(data) > limit:
        raise ValidationFailed(f"{label}: не больше {limit}", fields={place: f"Не больше {limit}"})
    return data


def pretty(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def parse_pairs(items: Iterable[str], place: str, label: str) -> dict[str, str]:
    """Строки «ключ = код подразделения» → {ключ без регистра: код}."""
    out: dict[str, str] = {}
    for item in items or ():
        left, sep, right = str(item).rpartition("=")
        left, right = left.strip(), right.strip()
        if not sep or not left or not right:
            raise ValidationFailed(f"{label}: «{item}» — нужно «значение = код подразделения»",
                                   fields={place: "Формат «значение = код подразделения»"})
        out[left.casefold()] = right
    return out


def text(raw: dict, key: str, default: str = "") -> str:
    value = raw.get(key, default)
    return default if value is None else str(value).strip()


def number(raw: dict, key: str, where: str, place: str) -> float | None:
    value = raw.get(key)
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValidationFailed(f"{where}: «{key}» — число", fields={place: f"{key}: нужно число"})
    try:
        result = float(str(value).replace(",", ".").replace(" ", ""))
    except ValueError:
        raise ValidationFailed(f"{where}: «{key}» — число", fields={place: f"{key}: нужно число"}) from None
    if result != result or abs(result) >= 1e15:  # NaN и бесконечность
        raise ValidationFailed(f"{where}: «{key}» — число", fields={place: f"{key}: нужно число"})
    return result


def choice(raw: dict, key: str, options: tuple[str, ...], default: str, where: str, place: str) -> str:
    value = text(raw, key, default) or default
    if value not in options:
        raise ValidationFailed(f"{where}: «{key}» — одно из: {', '.join(options)}",
                               fields={place: f"{key}: одно из {', '.join(options)}"})
    return value


# ---------------------------------------------------------------- показатель

INDICATOR_KEYS = ("indicator", "name", "unit", "direction", "rule", "green", "yellow", "rollup", "description",
                  "data_class")


@dataclass(frozen=True)
class IndicatorSpec:
    """Показатель, в который пишет подключение: ключ каталога и (необязательно) описание для создания."""

    key: str
    name: str = ""
    unit: str = ""
    data_class: str = "operational"
    direction: str = "higher_is_better"
    rule_type: str = "threshold"
    green: float | None = None
    yellow: float | None = None
    rollup: str = "sum"
    description: str = ""

    def create_body(self, owner_service: str, origin: str) -> dict:
        body = {"key": self.key, "name": self.name, "unit": self.unit, "data_class": self.data_class,
                "direction": self.direction, "rollup": self.rollup, "rule_type": self.rule_type,
                "description": self.description or f"Значения загружает {origin}", "source_type": "manual",
                "owner_service": owner_service}
        if self.rule_type == "threshold":
            body.update(green_threshold=self.green, yellow_threshold=self.yellow)
        else:
            green = 5.0 if self.green is None else self.green
            yellow = 15.0 if self.yellow is None else self.yellow
            body.update(green_deviation=green, yellow_deviation=max(green, yellow))
        return body


def indicator_spec(raw: dict, where: str, place: str, *, unit: str = "", data_class: str = "operational",
                   rollup: str = "sum", allow_class: bool = False, key: str | None = None) -> IndicatorSpec:
    """Показатель правила: indicator (ключ) и для создания — name, unit, direction, rule (threshold | target),
    green, yellow, rollup, description (у 1С ещё data_class)."""
    key = (key if key is not None else text(raw, "indicator")).strip()
    if not KEY_PATTERN.match(key):
        raise ValidationFailed(f"{where}: ключ показателя «{key}» — латиница в нижнем регистре, цифры, «.», «_», «-» "
                               "(например, jira.resolved)", fields={place: "Некорректный ключ показателя"})
    name = " ".join(text(raw, "name").split())
    if len(name) > 200:
        raise ValidationFailed(f"{where}: название показателя — до 200 символов", fields={place: "Длинное название"})
    unit_text = text(raw, "unit", unit)
    if len(unit_text) > 30:
        raise ValidationFailed(f"{where}: единица измерения — до 30 символов", fields={place: "Длинная единица"})
    cls = choice(raw, "data_class", DATA_CLASSES, data_class, where, place) if allow_class else data_class
    if not allow_class and text(raw, "data_class") not in ("", data_class):
        raise ValidationFailed(f"{where}: класс данных показателей этого подключения — {data_class}",
                               fields={place: f"data_class: только {data_class}"})
    return IndicatorSpec(
        key=key, name=name, unit=unit_text, data_class=cls,
        direction=choice(raw, "direction", DIRECTIONS, "higher_is_better", where, place),
        rule_type=choice(raw, "rule", RULE_TYPES, "threshold", where, place),
        green=number(raw, "green", where, place), yellow=number(raw, "yellow", where, place),
        rollup=choice(raw, "rollup", ROLLUPS, rollup, where, place), description=text(raw, "description")[:2000])


@dataclass
class Targets:
    """Показатели запуска: найденные (ключ → IndicatorDef), созданные, будущие (создадутся при записи) и
    проблемы (ключ → текст: показателя нет, он вычисляемый или выключен)."""

    found: dict[str, reports.IndicatorDef] = field(default_factory=dict)
    created: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    problems: dict[str, str] = field(default_factory=dict)

    def usable(self, key: str) -> bool:
        return key in self.found or key in self.pending


def ensure_indicators(ctx: RunContext, specs: Iterable[IndicatorSpec], owner_service: str, origin: str, *,
                      create: bool = True) -> Targets:
    """Показатели из каталога; отсутствующие с названием создаются каркасом — ctx.plans.ensure_indicator
    (create=False — только отмечаются, создаются позже create_pending)."""
    targets = Targets()
    by_key = {i.key: i for i in reports.state(ctx.db).catalog}
    for spec in {s.key: s for s in specs}.values():
        ind = by_key.get(spec.key)
        if ind is None and spec.name and create:
            try:
                ind = ctx.plans.ensure_indicator(spec.create_body(owner_service, origin))
            except AppError as exc:
                detail = exc.detail.removeprefix(f"Показатель «{spec.key}» не создан: ")
                targets.problems[spec.key] = f"Показатель «{spec.key}» не создан: {detail}"
                continue
            targets.created.append(spec.key)
            targets.found[spec.key] = ind
            continue
        if ind is not None:
            if ind.computed:
                targets.problems[spec.key] = (f"«{ind.name}» вычисляется из данных службы — значения подключения "
                                              "в него не записываются")
            elif not ind.is_active:
                targets.problems[spec.key] = f"Показатель «{ind.name}» выключен — включите его в разделе «Показатели»"
            else:
                targets.found[spec.key] = ind
            continue
        if not spec.name:
            targets.problems[spec.key] = (f"Показатель «{spec.key}» не найден в каталоге — создайте его в разделе "
                                          "«Показатели» или задайте name, и подключение создаст его само")
            continue
        targets.pending.append(spec.key)
    return targets


def create_pending(ctx: RunContext, targets: Targets, specs: Iterable[IndicatorSpec], owner_service: str,
                   origin: str, needed: Iterable[str]) -> None:
    """Создать отложенные показатели, для которых получены значения (needed), — после обращения к внешней
    системе: неудачный запуск или запрос не оставляют в каталоге пустых показателей."""
    needed = set(needed)
    wanted = [s for s in specs if s.key in targets.pending and s.key in needed]
    if not wanted:
        return
    made = ensure_indicators(ctx, wanted, owner_service, origin, create=True)
    targets.pending = [k for k in targets.pending if k not in needed]
    targets.found.update(made.found)
    targets.created += made.created
    targets.problems.update(made.problems)


# ---------------------------------------------------------------- подразделения

class Units:
    """Подразделения структуры по коду, пути через «/» или однозначному названию — как в загрузке значений."""

    def __init__(self, snap: org.OrgSnapshot):
        from ...services import org_import

        self.snap = snap
        self._split = org_import.split_path
        self.by_code = {u.code.casefold(): u.id for u in snap.units.values() if u.code}
        self.by_path: dict[tuple, int] = {}
        self.by_name: dict[str, list[int]] = {}
        for unit_id in snap.units:
            self.by_path[tuple(name_key(n) for n in snap.path_names(unit_id))] = unit_id
            self.by_name.setdefault(name_key(snap.units[unit_id].name), []).append(unit_id)

    @classmethod
    def load(cls, db) -> Units:
        return cls(org.snapshot(db))

    def find(self, ref: str | None) -> tuple[int | None, str]:
        raw = (ref or "").strip()
        if not raw:
            return None, "не указано подразделение"
        if raw.casefold() in self.by_code:
            return self.by_code[raw.casefold()], ""
        parts = tuple(name_key(p) for p in self._split(raw))
        if parts in self.by_path:
            return self.by_path[parts], ""
        if len(parts) == 1:
            found = self.by_name.get(parts[0], [])
            if len(found) == 1:
                return found[0], ""
            if found:
                return None, f"несколько подразделений «{raw}» — укажите код или путь через «/»"
        return None, f"подразделение «{raw}» не найдено в структуре — укажите код или путь через «/»"

    def by_name_or_code(self, value: str | None) -> int | None:
        """Подразделение по коду или однозначному названию (сопоставление чужих справочников)."""
        raw = (value or "").strip()
        if not raw:
            return None
        if raw.casefold() in self.by_code:
            return self.by_code[raw.casefold()]
        found = self.by_name.get(name_key(raw), [])
        return found[0] if len(found) == 1 else None

    def ref(self, unit_id: int) -> str:
        unit = self.snap.units[unit_id]
        return unit.code or self.snap.path_text(unit_id)

    def name(self, unit_id: int) -> str:
        return self.snap.units[unit_id].name

    def path(self, unit_id: int) -> str:
        return self.snap.path_text(unit_id)


# ---------------------------------------------------------------- запись значений

@dataclass
class Cell:
    indicator: str
    unit: int
    month: Month
    value: float
    comment: str = ""


@dataclass
class WriteResult:
    rows: int = 0
    create: int = 0
    update: int = 0
    unchanged: int = 0
    cleared: int = 0
    applied: bool = False
    errors: list[str] = field(default_factory=list)
    sample: list[dict] = field(default_factory=list)

    def counters(self) -> dict[str, int]:
        return {"values": self.rows, "created": self.create, "updated": self.update, "unchanged": self.unchanged}

    def text(self, preview: bool) -> str:
        head = "План без записи — значений" if preview else "Значений"
        return f"{head}: {self.rows} (новых {self.create}, изменено {self.update}, без изменений {self.unchanged})"


@dataclass
class Pending:
    """Показатели, которых ещё нет в каталоге (создаются при записи, если для них получены значения).

    План без записи (preview) не может построить для них план загрузки — показателя нет, — поэтому их значения
    считаются отдельно: «показатель «jira.resolved» будет создан при запуске: значений 6» и образцы строк с
    действием create. После записи в pending остаются только показатели без значений — они не создаются."""

    parts: list[str] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    sample: list[dict] = field(default_factory=list)

    @classmethod
    def of(cls, cells: list[Cell], targets: Targets, units: Units, *, preview: bool,
           room: int = SAMPLE_ROWS) -> Pending:
        out = cls()
        if not targets.pending:
            return out
        if not preview:
            out.parts.append("не созданы показатели без значений: " + ", ".join(f"«{k}»" for k in targets.pending))
            return out
        waiting = sorted((c for c in cells if c.indicator in targets.pending),
                         key=lambda c: (c.indicator, c.month.key, units.path(c.unit)))
        for key in targets.pending:
            count = sum(1 for c in waiting if c.indicator == key)
            out.parts.append(f"показатель «{key}» будет создан при запуске: значений {count}" if count else
                             f"показатель «{key}»: значений нет — при запуске он не будет создан")
        out.counters["values_pending"] = len(waiting)
        out.sample = [{"unit": units.path(c.unit), "indicator": c.indicator, "period": c.month.key,
                       "value": number_text(c.value), "action": "create", "pending": True}
                      for c in waiting[:max(0, room)]]
        return out


def number_text(value: float) -> str:
    text_value = f"{round(float(value), 6):.6f}".rstrip("0").rstrip(".")
    return "0" if text_value in ("-0", "") else text_value


def zero_fill(ctx: RunContext, cells: list[Cell], months: list[Month], zeroable: set[str], units: Units,
              note: str) -> list[Cell]:
    """Суммы и количества: подразделение, у которого прошлый запуск записал значение, а теперь данных нет
    (сделку перенесли, документ отменили), получает 0 — иначе в отчёте осталось бы старое значение."""
    previous = ctx.state.get("written") or {}
    have = {(c.indicator, c.unit, c.month.key) for c in cells}
    extra = []
    for month in months:
        for indicator in zeroable:
            for unit_id in previous.get(f"{indicator}|{month.key}", []):
                if unit_id in units.snap.units and (indicator, unit_id, month.key) not in have:
                    extra.append(Cell(indicator, unit_id, month, 0.0, f"{note} — за месяц данных нет"))
    return cells + extra


def branch_totals(cells: list[Cell], snap: org.OrgSnapshot, summable: set[str]) -> list[Cell]:
    """Суммы и количества из чужой системы, разнесённые по подразделениям: если данные есть и у подразделения,
    и у вложенных (сделки директора и его отделов), подразделение получает итог ветки — своё и вложенные.
    В сквозном отчёте собственное значение заменяет свёртку дочерних, иначе итог ветки был бы занижен."""
    own: dict[tuple[str, str], dict[int, float]] = {}
    for cell in cells:
        if cell.indicator in summable:
            own.setdefault((cell.indicator, cell.month.key), {})[cell.unit] = cell.value
    out = []
    for cell in cells:
        values = own.get((cell.indicator, cell.month.key))
        if values is None or not snap.children.get(cell.unit):
            out.append(cell)
            continue
        nested = [values[d] for d in snap.descendants([cell.unit]) if d != cell.unit and d in values]
        if not any(nested):
            out.append(cell)
            continue
        out.append(Cell(cell.indicator, cell.unit, cell.month, round(cell.value + sum(nested), 6),
                        f"{cell.comment} (вместе с вложенными подразделениями)"))
    return out


def remember(ctx: RunContext, cells: list[Cell], months: list[Month], keep: Iterable[str] = ()) -> None:
    """Какие ячейки подключение заполнило ненулевым значением (для zero_fill следующего запуска): только
    месяцы окна. keep — показатели, которые в этом запуске не посчитались (ошибка): их отметки остаются."""
    keys, keep = {m.key for m in months}, set(keep)
    written: dict[str, list[int]] = {k: list(v) for k, v in (ctx.state.get("written") or {}).items()
                                     if k.rsplit("|", 1)[-1] in keys and k.rsplit("|", 1)[0] in keep}
    for cell in cells:
        if cell.value:
            written.setdefault(f"{cell.indicator}|{cell.month.key}", []).append(cell.unit)
    ctx.state["written"] = {k: sorted(set(v)) for k, v in sorted(written.items())}


def write(ctx: RunContext, cells: list[Cell], units: Units, *, apply: bool, label: str) -> WriteResult:
    """План и (если apply и есть изменения) применение значений одной транзакцией."""
    result = WriteResult()
    if not cells:
        return result
    cells = sorted(cells, key=lambda c: (c.indicator, c.month.key, units.path(c.unit)))
    rows = [{"line": n, "department": units.ref(c.unit), "indicator": c.indicator, "period": c.month.key,
             "value": number_text(c.value), "target": None, "comment": c.comment[:1000]}
            for n, c in enumerate(cells, start=1)]
    plan = ctx.plans.indicator_values(rows, apply=False, filename=label)
    summary = plan["summary"]
    result.rows, result.create = summary["rows"], summary["create"]
    result.update, result.unchanged = summary["update"], summary["unchanged"]
    result.cleared = summary.get("cleared", 0)
    for row in plan["rows"]:
        if row["errors"]:
            result.errors.append(f"{row['department_path'] or row['department']} · {row['indicator']} · "
                                 f"{row['period']}: {'; '.join(row['errors'])}")
    result.sample = [{"unit": r["department_path"], "indicator": r["indicator_key"], "period": r["period"],
                      "value": r["value"], "action": r["action"]} for r in plan["rows"][:SAMPLE_ROWS]]
    if result.errors:
        raise IntegrationError("Значения не записаны — в плане ошибки: " + " | ".join(result.errors[:5]),
                               code="plan_errors", short="Значения не записаны: в плане загрузки ошибки")
    if apply and (result.create or result.update or result.cleared):
        applied = ctx.plans.indicator_values(rows, apply=True, filename=label)
        if not applied.get("applied"):  # pragma: no cover - план только что был без ошибок
            raise IntegrationError("Значения не записаны: план изменился во время записи — повторите запуск",
                                   code="plan_errors")
        result.applied = True
    return result


def diagnose(indicators: Iterable[str], unit_refs: Iterable[str]) -> list[str]:
    """Для проверки подключения: какие показатели будут созданы или не годятся и какие подразделения
    не найдены (без записи; ошибки базы не мешают проверке)."""
    from sqlalchemy import select

    from ...core import db as core_db
    from ...models import Indicator

    notes: list[str] = []
    try:
        with core_db.SessionLocal() as db:
            catalog = {k: (s, a) for k, s, a in db.execute(select(Indicator.key, Indicator.source_type,
                                                                   Indicator.is_active))}
            units = Units.load(db)
    except Exception:  # pragma: no cover - проверка подключения не зависит от базы
        return notes
    for key in dict.fromkeys(indicators):
        if key not in catalog:
            notes.append(f"показателя «{key}» нет в каталоге — он будет создан при первом запуске (если задано name)")
        elif catalog[key][0] == "computed":
            notes.append(f"«{key}» — вычисляемый показатель, значения в него не записываются")
        elif not catalog[key][1]:
            notes.append(f"показатель «{key}» выключен")
    for ref in dict.fromkeys(unit_refs):
        unit_id, error = units.find(ref)
        if unit_id is None:
            notes.append(error)
    return notes
