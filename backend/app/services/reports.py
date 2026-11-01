"""Сквозные отчёты: расчёт, статусы, объяснения и фильтр по правам (ADR-0010).

Расчёт за период (CompanyReport) — один проход по снимку структуры, каталогу показателей, введённым
значениям периода и данным служб. Значение подразделения — собственное (введённое или вычисленное),
а без него — свёртка дочерних (сумма или среднее); статус показателя — светофор по правилу; пропуск
ожидаемого значения — «Нет данных» и критичное нарушение полноты (статус не ухудшает); статус
подразделения — худший из статусов его показателей и дочерних подразделений.

Состояние (каталог, данные служб, рассчитанные периоды) хранится в памяти процесса по ключу
(ревизия структуры, ревизии данных служб, ревизия отчётов, текущий месяц), отчёт периода — внутри
него, и дальше только фильтруется под права пользователя без пересчёта:

- вершины области: вся компания — корни структуры; иначе основное, руководимые и дополнительные
  подразделения (у области «своё подразделение» — без детализации ниже них);
- глубина детализации от вершин: глубже подразделения не перечисляются, их значения входят в свёртку
  видимых уровней, у последнего видимого уровня — drill_locked;
- классы данных: показатели недоступного класса не попадают в ответ, статусы и объяснения
  пересчитываются по доступным (вариант на набор классов считается один раз на отчёт).

Готовые ответы — в общем кэше ответов (app/services/cache.py), сжатые один раз, по номеру состояния,
правам просмотра и личным признакам.
"""
from __future__ import annotations

import itertools
import json
import math
import threading
from collections import Counter, OrderedDict, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import Forbidden, NotFound, ValidationFailed
from ..core.timeutil import local_today
from ..models import (
    MONTH_NAMES,
    AppSetting,
    HrEmployeeEvent,
    HrMetricValue,
    HrMonth,
    Indicator,
    IndicatorValue,
    Partnership,
    PartnershipLightRule,
    ReportRevision,
    TpWeeklyReport,
    UnitStatusNote,
    User,
    name_key,
)
from ..models.reports import mark_reports_changed
from . import access, org, org_admin, traffic_light
from . import partnerships as p_service
from .cache import cached_body
from .cache import revisions as data_revisions
from .registry import (
    DATA_CLASSES,
    INDICATOR_SOURCE_BY_KEY,
    ORG_SCOPE_LABELS,
    REPORT_SERVICE_UNIT_DEFAULTS,
    REPORT_SETTING_KEY,
    SERVICE_BY_KEY,
)

# Службы, из данных которых вычисляются показатели: их ревизии входят в ключ отчёта
SOURCE_SERVICES = ("hr", "tech", "project_product")
LIGHT_LABELS = traffic_light.LIGHT_LABELS
MISSING_LABEL = traffic_light.MISSING_LABEL
COLOR_WORDS = {"red": "Красный", "yellow": "Жёлтый", "green": "Зелёный", "gray": "Нет оценки"}
NOTE_LABELS = {"watch": "Под контролем"}
SOURCE_LABELS = {"manual": "введено", "import": "загружено из файла", "computed": "из данных службы"}
# Исходные записи службы: адрес реестра и класс данных, без которого реестр недоступен
RECORDS_LINKS = {"hr": ("/hr/registry", "personal"), "tech": ("/tp/registry", None),
                 "project_product": ("/product/registry", None)}
TREND_MONTHS = 12
SCORECARD_ITEMS = 3      # пунктов объяснения у подразделения в матрице
DETAIL_ITEMS = 20        # в панели подразделения
SUMMARY_ITEMS = 3        # на карточке «Обзора»
MAX_STATES = 4
MAX_PERIODS = 48


# ================================================================ периоды

def parse_period(text: str | None, field_name: str = "period") -> date:
    """«ГГГГ-ММ» → первое число месяца."""
    try:
        year_s, month_s = (text or "").strip().split("-")
        year, month = int(year_s), int(month_s)
        if 2000 <= year <= 2100 and 1 <= month <= 12 and len(month_s) == 2:
            return date(year, month, 1)
    except ValueError:
        pass
    raise ValidationFailed("Период указывается в формате ГГГГ-ММ", fields={field_name: "Формат ГГГГ-ММ"})


def period_key(period: date) -> str:
    return f"{period.year:04d}-{period.month:02d}"


def period_label(period: date) -> str:
    return f"{MONTH_NAMES[period.month]} {period.year}"


def add_months(period: date, months: int) -> date:
    index = period.year * 12 + period.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def month_end(period: date) -> date:
    return add_months(period, 1) - timedelta(days=1)


def current_period() -> date:
    today = local_today()
    return date(today.year, today.month, 1)


# ================================================================ ревизия отчётов

def current_revision(db: Session) -> int:
    return db.scalar(select(ReportRevision.revision).where(ReportRevision.id == 1)) or 0


def revision_key(db: Session) -> tuple:
    """(номер, время изменения): время защищает от совпадения номеров после восстановления базы."""
    row = db.execute(select(ReportRevision.revision, ReportRevision.updated_at).where(ReportRevision.id == 1)).first()
    return (row[0], row[1]) if row else (0, None)


# Ревизия увеличивается событиями сессии (app/models/reports.py) в транзакции любого изменения каталога,
# значений и заметок; остальное (настройка подразделений служб) отмечается явно
mark_changed = mark_reports_changed


# ================================================================ оформление чисел и слов

def fmt_number(value: float | None, unit: str = "") -> str:
    """Как в интерфейсе и PDF: пробел между разрядами, запятая, типографский минус."""
    if value is None:
        return "—"
    if float(value).is_integer():
        text = f"{int(value):,}"
    else:
        text = f"{value:,.2f}".rstrip("0").rstrip(".")
    text = text.replace(",", " ").replace(".", ",").replace("-", "−")
    if unit == "%":
        return f"{text}%"
    return f"{text} {unit}" if unit else text


def units_dative(count: int) -> str:
    return "подразделению" if count % 10 == 1 and count % 100 != 11 else "подразделениям"


def levels_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "уровень"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "уровня"
    return "уровней"


def source_label(source: str | None, count: int, rollup: str) -> str:
    if source == "rollup":
        return f"{'сумма' if rollup == 'sum' else 'среднее'} по {count} {units_dative(count)}"
    return SOURCE_LABELS.get(source or "", "")


# ================================================================ каталог показателей

@dataclass(frozen=True)
class IndicatorDef:
    """Показатель каталога, отделённый от сессии базы (живёт в памяти вместе с отчётом)."""

    id: int
    key: str
    name: str
    description: str
    unit: str
    data_class: str
    direction: str
    rollup: str
    rule_type: str
    green_threshold: float | None
    yellow_threshold: float | None
    green_deviation: float | None
    yellow_deviation: float | None
    default_target: float | None
    source_type: str
    source_key: str | None
    owner_service: str | None
    expected_kinds: tuple[str, ...]
    sort_order: int
    is_active: bool
    created: date                     # месяц создания показателя
    since: date | None = None         # с какого периода значение ожидается (первое значение или создание)

    enabled = True                    # для traffic_light.evaluate: правило порогов всегда включено

    @property
    def computed(self) -> bool:
        return self.source_type == "computed"

    @classmethod
    def from_row(cls, row: Indicator, since: date | None = None) -> IndicatorDef:
        created = row.created_at.date().replace(day=1) if row.created_at else current_period()
        return cls(
            id=row.id, key=row.key, name=row.name, description=row.description or "", unit=row.unit or "",
            data_class=row.data_class, direction=row.direction, rollup=row.rollup, rule_type=row.rule_type,
            green_threshold=row.green_threshold, yellow_threshold=row.yellow_threshold,
            green_deviation=row.green_deviation, yellow_deviation=row.yellow_deviation,
            default_target=row.default_target, source_type=row.source_type, source_key=row.source_key,
            owner_service=row.owner_service, expected_kinds=tuple(row.expected_kinds or ()),
            sort_order=row.sort_order, is_active=row.is_active, created=created, since=since,
        )


def evaluate(ind: IndicatorDef, value: float | None, target: float | None) -> tuple[str, float | None]:
    """Статус показателя по правилу и отклонение от цели в % (для правила «target»)."""
    if value is None or ind.direction == "neutral":
        return "gray", None
    if ind.rule_type == "threshold":
        return traffic_light.evaluate(value, ind), None
    if target is None or ind.green_deviation is None or ind.yellow_deviation is None:
        return "gray", None
    higher = ind.direction == "higher_is_better"
    if target == 0:
        short = value < 0 if higher else value > 0
        deviation = math.inf if short else 0.0
    else:
        deviation = max(0.0, round(((target - value) if higher else (value - target)) / abs(target) * 100, 6))
    if deviation <= ind.green_deviation:
        status = "green"
    elif deviation <= ind.yellow_deviation:
        status = "yellow"
    else:
        status = "red"
    return status, (round(deviation, 1) if math.isfinite(deviation) else None)


def expected(ind: IndicatorDef, kind: str, period: date) -> bool:
    """Значение ожидается: тип уровня из «где ожидается» и период не раньше начала показателя."""
    return bool(ind.expected_kinds) and kind in ind.expected_kinds and (ind.since is None or period >= ind.since)


# ================================================================ данные служб

def resolve_service_units(db: Session, snap: org.OrgSnapshot) -> dict[str, int | None]:
    """Подразделение службы: из настройки report_service_units, иначе по коду (HR, TECH, PROJ)."""
    row = db.get(AppSetting, REPORT_SETTING_KEY)
    configured = row.value if row is not None and isinstance(row.value, dict) else {}
    by_code = {u.code.casefold(): u.id for u in snap.units.values() if u.code}
    result: dict[str, int | None] = {}
    for service, code in REPORT_SERVICE_UNIT_DEFAULTS.items():
        value = configured.get(service)
        if isinstance(value, int) and not isinstance(value, bool) and value in snap.units:
            result[service] = value
        else:
            result[service] = by_code.get(code.casefold())
    return result


def unit_matcher(snap: org.OrgSnapshot) -> Callable[[str | None], int | None]:
    """Подразделение структуры по тексту записи службы: код, затем название (только однозначное)."""
    by_code = {u.code.casefold(): u.id for u in snap.units.values() if u.code}
    by_name: dict[str, list[int]] = defaultdict(list)
    for unit in snap.units.values():
        by_name[name_key(unit.name)].append(unit.id)
    cache: dict[str, int | None] = {}

    def match(text: str | None) -> int | None:
        raw = (text or "").strip()
        if raw not in cache:
            found = by_code.get(raw.casefold())
            if found is None:
                candidates = by_name.get(name_key(raw), [])
                found = candidates[0] if len(candidates) == 1 else None
            cache[raw] = found
        return cache[raw]

    return match


@dataclass
class ServiceData:
    """Вычисляемые значения по периодам: источник → подразделение → значение."""

    by_period: dict[date, dict[str, dict[int, float]]] = field(default_factory=dict)
    first: dict[str, date] = field(default_factory=dict)
    pp_rows: list = field(default_factory=list)
    pp_rules: dict = field(default_factory=dict)
    pp_unit: int | None = None
    current: date = field(default_factory=current_period)
    _pp: dict[date, float | None] = field(default_factory=dict)

    def put(self, period: date, source_key: str, values: dict[int, float]) -> None:
        if not values:
            return
        self.by_period.setdefault(period, {})[source_key] = values
        if source_key not in self.first or period < self.first[source_key]:
            self.first[source_key] = period

    def periods(self, source_key: str) -> set[date]:
        return {p for p, sources in self.by_period.items() if source_key in sources}

    def pp_share(self, period: date) -> float | None:
        if period > self.current or not self.pp_rows or self.pp_unit is None:
            return None
        if period not in self._pp:
            end = month_end(period)
            try:
                green = sum(1 for p in self.pp_rows
                            if p_service.record_light(p, self.pp_rules, end)["light"] == "green")
                self._pp[period] = round(green * 100 / len(self.pp_rows), 1)
            except KeyError:   # правила светофора партнёрств неполные — оценить нельзя
                self._pp[period] = None
        return self._pp[period]

    def values(self, period: date, sources: set[str]) -> dict[str, dict[int, float]]:
        result = {k: v for k, v in self.by_period.get(period, {}).items() if k in sources}
        if "pp.green_share" in sources:
            share = self.pp_share(period)
            if share is not None:
                result["pp.green_share"] = {self.pp_unit: share}
        return result


def _load_hr(db: Session, snap: org.OrgSnapshot, data: ServiceData, company_root: int | None,
             sources: set[str]) -> None:
    months = {mid: date(year, month, 1) for mid, year, month in db.execute(
        select(HrMonth.id, HrMonth.year, HrMonth.month))}
    if not months:
        return
    metric_keys = {"hr.turnover": "turnover", "hr.time_to_fill": "avg_time_to_fill"}
    metrics: dict[int, dict[str, float]] = defaultdict(dict)
    for mid, key, value in db.execute(select(HrMetricValue.month_id, HrMetricValue.metric_key, HrMetricValue.value)
                                      .where(HrMetricValue.value.is_not(None),
                                             HrMetricValue.metric_key.in_(list(metric_keys.values())))):
        metrics[mid][key] = value
    match = unit_matcher(snap)
    contrib: dict[tuple[int, str], Counter] = defaultdict(Counter)
    unmatched: dict[tuple[int, str], int] = defaultdict(int)
    with_events: set[int] = set()
    tracked: set[int] = {company_root} if company_root is not None else set()
    if sources & {"hr.hired", "hr.fired"}:
        for mid, event_type, department in db.execute(select(HrEmployeeEvent.month_id, HrEmployeeEvent.event_type,
                                                             HrEmployeeEvent.department)):
            with_events.add(mid)
            unit = match(department)
            if unit is None:
                unmatched[(mid, event_type)] += 1
            else:
                contrib[(mid, event_type)][unit] += 1
                tracked.update(snap.path(unit))
    for mid, period in months.items():
        for source_key, metric in metric_keys.items():
            if source_key in sources and company_root is not None and metric in metrics.get(mid, {}):
                data.put(period, source_key, {company_root: metrics[mid][metric]})
        # Месяц без приёмов, увольнений и метрик не заполнен: нули ему не приписываются
        if mid not in with_events and mid not in metrics:
            continue
        for event_type, source_key in (("hired", "hr.hired"), ("fired", "hr.fired")):
            if source_key not in sources:
                continue
            branch: Counter = Counter()
            for unit, count in contrib[(mid, event_type)].items():
                for ancestor in snap.path(unit):
                    branch[ancestor] += count
            if company_root is not None:
                branch[company_root] += unmatched[(mid, event_type)]
            data.put(period, source_key, {u: float(branch.get(u, 0)) for u in tracked})


def _load_tech(db: Session, data: ServiceData, unit: int | None, sources: set[str]) -> None:
    if unit is None:
        return
    by_month: dict[date, list[tuple]] = defaultdict(list)
    for year, week, in_work, solved, received in db.execute(
            select(TpWeeklyReport.year, TpWeeklyReport.week, TpWeeklyReport.total_in_work,
                   TpWeeklyReport.total_solved_week, TpWeeklyReport.new_received)
            .order_by(TpWeeklyReport.year, TpWeeklyReport.week)):
        try:
            monday = date.fromisocalendar(year, week, 1)
        except ValueError:
            continue
        by_month[monday.replace(day=1)].append((in_work, solved, received))
    for period, weeks in by_month.items():
        in_work = next((w[0] for w in reversed(weeks) if w[0] is not None), None)
        solved_values = [w[1] for w in weeks if w[1] is not None]
        received_values = [w[2] for w in weeks if w[2] is not None]
        solved = sum(solved_values) if solved_values else None
        received = sum(received_values) if received_values else None
        ratio = round(solved / received, 2) if solved is not None and received else None
        for source_key, value in (("tech.in_work", in_work), ("tech.solved", solved), ("tech.ratio", ratio)):
            if source_key in sources and value is not None:
                data.put(period, source_key, {unit: float(value)})


def _load_pp(db: Session, data: ServiceData, unit: int | None) -> None:
    if unit is None:
        return
    data.pp_unit = unit
    data.pp_rows = [SimpleNamespace(status=s, nda=bool(n), agreement=bool(a), cert_date=c) for s, n, a, c in db.execute(
        select(Partnership.status, Partnership.nda, Partnership.agreement, Partnership.cert_date))]
    data.pp_rules = {r.key: SimpleNamespace(key=r.key, light=r.light, threshold=r.threshold)
                     for r in db.scalars(select(PartnershipLightRule))}


def load_service_data(db: Session, snap: org.OrgSnapshot, units: dict[str, int | None],
                      sources: set[str]) -> ServiceData:
    data = ServiceData()
    hr_unit = units.get("hr")
    roots = snap.roots()
    company_root = snap.path(hr_unit)[0] if hr_unit in snap.units else (roots[0] if roots else None)
    if sources & {"hr.hired", "hr.fired", "hr.turnover", "hr.time_to_fill"}:
        _load_hr(db, snap, data, company_root, sources)
    if sources & {"tech.in_work", "tech.solved", "tech.ratio"}:
        _load_tech(db, data, units.get("tech"), sources)
    if "pp.green_share" in sources:
        _load_pp(db, data, units.get("project_product"))
    return data


# ================================================================ значения периода и свёртка

@dataclass
class Layer:
    """Значения периода: показатель → подразделение → (значение, источник, N свёрнутых, цель, комментарий)."""

    period: date
    cells: dict[int, dict[int, tuple]]


def build_layer(period: date, indicators: Iterable[IndicatorDef], snap: org.OrgSnapshot, order: list[int],
                rows: Iterable, computed: dict[str, dict[int, float]]) -> Layer:
    by_indicator: dict[int, dict[int, tuple]] = defaultdict(dict)
    for ind_id, unit_id, value, target, comment, source in rows:
        by_indicator[ind_id][unit_id] = (value, target, comment or "", source)
    bottom_up = list(reversed(order))
    result: dict[int, dict[int, tuple]] = {}
    for ind in indicators:
        own_rows = by_indicator.get(ind.id, {})
        own_computed = computed.get(ind.source_key or "", {}) if ind.computed else {}
        cells: dict[int, tuple] = {}
        explicit: dict[int, float] = {}
        for unit_id in bottom_up:
            row = own_rows.get(unit_id)
            value = source = None
            count = 0
            contributors: list[int] = []
            if row is not None and row[0] is not None and not ind.computed:
                value, source = row[0], row[3]
            elif unit_id in own_computed:
                value, source = own_computed[unit_id], "computed"
            elif ind.rollup != "none":
                contributors = [c for c in snap.children.get(unit_id, ()) if c in cells and cells[c][0] is not None]
                if contributors:
                    total = sum(cells[c][0] for c in contributors)
                    count = len(contributors)
                    value = round(total, 6) if ind.rollup == "sum" else round(total / count, 4)
                    source = "rollup"
            target = row[1] if row is not None else None
            if target is None and contributors:
                # Цель свёрнутого значения — свёртка целей, если они заданы у всех свёрнутых подразделений
                kid_targets = [explicit.get(c) for c in contributors]
                if all(t is not None for t in kid_targets):
                    target = round(sum(kid_targets) if ind.rollup == "sum" else sum(kid_targets) / count, 6)
            if target is not None:
                explicit[unit_id] = target
            comment = row[2] if row is not None else ""
            if value is not None or row is not None:
                cells[unit_id] = (value, source, count, target if target is not None else ind.default_target, comment)
        result[ind.id] = cells
    return Layer(period, result)


# ================================================================ отчёт периода

@dataclass
class View:
    """Статусы по набору доступных классов данных (на весь отчёт)."""

    indicators: list[IndicatorDef]
    status: dict[int, str]
    counts: dict[str, dict[int, int]]           # red / yellow → ячеек с этим статусом в ветке
    subtree: dict[str, dict[int, frozenset]]    # red / yellow → показатели с этим статусом в ветке
    missing_total: dict[int, int]
    valued: dict[int, int]
    rated: dict[int, int]


@dataclass
class CompanyReport:
    period: date
    state: ReportState
    cells: dict[int, dict[int, dict]]           # подразделение → показатель → ячейка (готова для JSON)
    notes: dict[int, dict]
    _views: dict[frozenset, View] = field(default_factory=dict)

    def view(self, classes: frozenset[str]) -> View:
        cached = self._views.get(classes)
        if cached is None:
            cached = self._views[classes] = self._build_view(classes)
        return cached

    def _build_view(self, classes: frozenset[str]) -> View:
        snap = self.state.snap
        indicators = [i for i in self.state.active if i.data_class in classes]
        status: dict[int, str] = {}
        counts = {"red": {}, "yellow": {}}
        subtree: dict[str, dict[int, frozenset]] = {"red": {}, "yellow": {}}
        missing_total: dict[int, int] = {}
        valued: dict[int, int] = {}
        rated: dict[int, int] = {}
        empty: frozenset = frozenset()
        for unit_id in reversed(self.state.order):
            own = self.cells.get(unit_id, {})
            lights: list[str] = []
            n_red = n_yellow = n_missing = n_valued = n_rated = 0
            red_set: set[int] = set()
            yellow_set: set[int] = set()
            for ind in indicators:
                cell = own.get(ind.id)
                if cell is None:
                    continue
                light = cell["status"]
                if cell["value"] is not None:
                    n_valued += 1
                if cell["missing"]:
                    n_missing += 1
                if light != "gray":
                    n_rated += 1
                    lights.append(light)
                if light == "red":
                    n_red += 1
                    red_set.add(ind.id)
                elif light == "yellow":
                    n_yellow += 1
                    yellow_set.add(ind.id)
            for child in snap.children.get(unit_id, ()):
                lights.append(status[child])
                n_red += counts["red"][child]
                n_yellow += counts["yellow"][child]
                n_missing += missing_total[child]
                red_set |= subtree["red"][child]
                yellow_set |= subtree["yellow"][child]
            status[unit_id] = traffic_light.worst(lights)
            counts["red"][unit_id], counts["yellow"][unit_id] = n_red, n_yellow
            subtree["red"][unit_id] = frozenset(red_set) if red_set else empty
            subtree["yellow"][unit_id] = frozenset(yellow_set) if yellow_set else empty
            missing_total[unit_id], valued[unit_id], rated[unit_id] = n_missing, n_valued, n_rated
        return View(indicators, status, counts, subtree, missing_total, valued, rated)


_serials = itertools.count(1)


@dataclass
class ReportState:
    """Каталог, данные служб и рассчитанные периоды при одном наборе ревизий."""

    key: tuple
    snap: org.OrgSnapshot
    order: list[int]
    catalog: tuple[IndicatorDef, ...]
    active: list[IndicatorDef]
    data: ServiceData
    service_units: dict[str, int | None]
    kind_labels: dict[str, str]
    units_by_kind: dict[str, list[int]]
    sources: set[str]
    _layers: OrderedDict = field(default_factory=OrderedDict)
    _reports: OrderedDict = field(default_factory=OrderedDict)
    _periods: dict | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    # Номер состояния в процессе — в ключе готовых ответов: при пересчёте состояния прежние ответы не
    # совпадут с новыми, даже если номера ревизий повторились (копия или восстановленная база)
    serial: int = field(default_factory=lambda: next(_serials))

    def _remember(self, store: OrderedDict, key, value) -> None:
        with self._lock:
            store[key] = value
            store.move_to_end(key)
            while len(store) > MAX_PERIODS:
                store.popitem(last=False)

    def layer(self, db: Session, period: date) -> Layer:
        cached = self._layers.get(period)
        if cached is not None:
            return cached
        rows = db.execute(select(IndicatorValue.indicator_id, IndicatorValue.department_id, IndicatorValue.value,
                                 IndicatorValue.target, IndicatorValue.comment, IndicatorValue.source)
                          .where(IndicatorValue.period == period)).all()
        rows = [r for r in rows if r[1] in self.snap.units]
        layer = build_layer(period, self.active, self.snap, self.order, rows, self.data.values(period, self.sources))
        self._remember(self._layers, period, layer)
        return layer

    def report(self, db: Session, period: date) -> CompanyReport:
        cached = self._reports.get(period)
        if cached is not None:
            return cached
        current = self.layer(db, period)
        previous = self.layer(db, add_months(period, -1))
        cells: dict[int, dict[int, dict]] = defaultdict(dict)
        for ind in self.active:
            now_cells = current.cells.get(ind.id, {})
            prev_cells = previous.cells.get(ind.id, {})
            for unit_id, (value, source, count, target, comment) in now_cells.items():
                prev = prev_cells.get(unit_id)
                prev_value = prev[0] if prev else None
                light, deviation = evaluate(ind, value, target)
                missing = value is None and expected(ind, self.snap.units[unit_id].kind, period)
                cells[unit_id][ind.id] = self._cell(ind, value, target, prev_value, light, deviation, missing,
                                                    source, count, comment)
            if ind.expected_kinds:
                for kind in ind.expected_kinds:
                    for unit_id in self.units_by_kind.get(kind, ()):
                        if unit_id not in now_cells and expected(ind, kind, period):
                            prev = prev_cells.get(unit_id)
                            cells[unit_id][ind.id] = self._cell(ind, None, ind.default_target,
                                                                prev[0] if prev else None, "gray", None, True,
                                                                None, 0, "")
        notes = self._notes(db, period)
        report = CompanyReport(period, self, dict(cells), notes)
        self._remember(self._reports, period, report)
        return report

    @staticmethod
    def _cell(ind: IndicatorDef, value, target, previous, light, deviation, missing, source, count, comment) -> dict:
        return {
            "value": value, "target": target, "previous": previous,
            "delta": round(value - previous, 6) if value is not None and previous is not None else None,
            "status": light, "status_label": MISSING_LABEL if missing else LIGHT_LABELS[light],
            "missing": missing, "deviation": deviation, "source": source,
            "source_label": source_label(source, count, ind.rollup), "rollup_count": count, "comment": comment,
        }

    def _notes(self, db: Session, period: date) -> dict[int, dict]:
        notes = {}
        for unit_id, status, comment, author_id, created_at in db.execute(
                select(UnitStatusNote.department_id, UnitStatusNote.status, UnitStatusNote.comment,
                       UnitStatusNote.author_id, UnitStatusNote.created_at).where(UnitStatusNote.period == period)):
            author = self.snap.people.get(author_id) if author_id else None
            notes[unit_id] = {"status": status, "status_label": NOTE_LABELS.get(status, status), "comment": comment,
                              "author": {"id": author.id, "full_name": author.full_name} if author else None,
                              "created_at": created_at.isoformat() if created_at else None}
        return notes

    def periods_by_class(self, db: Session) -> dict[str, set[date]]:
        """Периоды с данными по классам данных (введённые значения и данные служб; без партнёрств —
        их доля считается за любой месяц)."""
        if self._periods is None:
            by_id = {i.id: i for i in self.active}
            result: dict[str, set[date]] = defaultdict(set)
            for ind_id, period in db.execute(select(IndicatorValue.indicator_id, IndicatorValue.period)
                                             .where(IndicatorValue.value.is_not(None)).distinct()):
                if ind_id in by_id:
                    result[by_id[ind_id].data_class].add(period)
            for ind in self.active:
                if ind.computed and ind.source_key and ind.source_key != "pp.green_share":
                    result[ind.data_class] |= self.data.periods(ind.source_key)
            self._periods = dict(result)
        return self._periods


_states: OrderedDict[tuple, ReportState] = OrderedDict()
_states_lock = threading.Lock()


def _build_state(db: Session, snap: org.OrgSnapshot, key: tuple) -> ReportState:
    rows = list(db.scalars(select(Indicator).order_by(Indicator.sort_order, Indicator.id)))
    first_values = dict(db.execute(select(IndicatorValue.indicator_id, func.min(IndicatorValue.period))
                                   .where(IndicatorValue.value.is_not(None))
                                   .group_by(IndicatorValue.indicator_id)).all())
    sources = {r.source_key for r in rows if r.is_active and r.source_type == "computed" and r.source_key}
    units = resolve_service_units(db, snap)
    data = load_service_data(db, snap, units, sources)
    catalog = []
    for row in rows:
        created = IndicatorDef.from_row(row).created
        first = data.first.get(row.source_key or "") if row.source_type == "computed" else first_values.get(row.id)
        catalog.append(IndicatorDef.from_row(row, min(created, first) if first else created))
    units_by_kind: dict[str, list[int]] = defaultdict(list)
    order = snap.ordered_units()
    for unit_id in order:
        units_by_kind[snap.units[unit_id].kind].append(unit_id)
    kinds = org_admin.kind_labels(org_admin.get_settings(db)["unit_kinds"])
    return ReportState(key=key, snap=snap, order=order, catalog=tuple(catalog),
                       active=[i for i in catalog if i.is_active], data=data, service_units=units,
                       kind_labels=kinds, units_by_kind=dict(units_by_kind), sources=sources)


def state(db: Session) -> ReportState:
    """Состояние отчётов при текущих ревизиях (из памяти процесса или заново)."""
    snap = org.snapshot(db)
    key = (snap.revision, data_revisions(db, SOURCE_SERVICES), revision_key(db), current_period())
    with _states_lock:
        cached = _states.get(key)
        if cached is not None and cached.snap is snap:
            _states.move_to_end(key)
            return cached
    fresh = _build_state(db, snap, key)
    with _states_lock:
        _states[key] = fresh
        while len(_states) > MAX_STATES:
            _states.popitem(last=False)
    return fresh


def invalidate() -> None:
    with _states_lock:
        _states.clear()


# ================================================================ права просмотра

@dataclass(frozen=True)
class Viewer:
    user_id: int
    scope: str
    roots: tuple[int, ...]
    depth: int | None                      # действующая глубина (у области «своё подразделение» — 0)
    classes: frozenset[str]
    services: tuple[tuple[str, str], ...]
    can_records: bool
    can_export: bool
    can_manage: bool

    @property
    def key(self) -> tuple:
        """Всё, от чего зависит общий для пользователей ответ (без личных признаков)."""
        return (self.scope, self.roots, self.depth, tuple(sorted(self.classes)), self.services, self.can_records)


def viewer_for(user: User, snap: org.OrgSnapshot) -> Viewer:
    eff = access.effective(user)
    scope = "company" if eff.is_admin else eff.org_scope
    if scope == "company":
        roots = tuple(snap.roots())
    else:
        base = access.base_units(user, snap)
        roots = tuple(u for u in snap.ordered_units() if u in base)
    depth = 0 if scope == "unit" else eff.drill_depth
    classes = frozenset(c for c in DATA_CLASSES if eff.allows(c))
    return Viewer(user.id, scope, roots, depth, classes, tuple(sorted(eff.services.items())),
                  eff.can_view_records, eff.can_export, user.can("reports.manage"))


_UNSET = object()


def window(snap: org.OrgSnapshot, order: list[int], roots: Iterable[int], depth: int | None) -> dict[int, int | None]:
    """Видимые подразделения → сколько уровней ниже ещё видно (None — без ограничения, 0 — последний
    видимый уровень). Окна нескольких вершин объединяются."""
    root_set = set(roots)
    budget: dict[int, int | None] = {}
    for unit_id in order:
        value = _UNSET
        parent = snap.units[unit_id].parent_id
        if parent in budget:
            parent_budget = budget[parent]
            if parent_budget is None:
                value = None
            elif parent_budget > 0:
                value = parent_budget - 1
        if unit_id in root_set and (value is _UNSET or depth is None or (value is not None and depth > value)):
            value = depth
        if value is not _UNSET:
            budget[unit_id] = value
    return budget


def access_info(st: ReportState, viewer: Viewer) -> dict:
    hidden = [label for key, label in DATA_CLASSES.items() if key not in viewer.classes]
    scope_text = {"company": "вся компания", "branch": "своя ветка структуры", "unit": "своё подразделение"}
    if viewer.depth is None:
        depth_text = "детализация без ограничения"
    elif viewer.depth == 0:
        depth_text = "без детализации"
    else:
        depth_text = f"детализация на {viewer.depth} {levels_word(viewer.depth)}"
    parts = [scope_text[viewer.scope], depth_text]
    if hidden:
        parts.append("скрыты: " + ", ".join(h.lower() for h in hidden))
    return {
        "scope": viewer.scope, "scope_label": ORG_SCOPE_LABELS[viewer.scope],
        "roots": [{"id": u, "name": st.snap.units[u].name, "path": st.snap.path_text(u)} for u in viewer.roots],
        "drill_depth": viewer.depth, "classes": [c for c in DATA_CLASSES if c in viewer.classes],
        "hidden_classes": hidden, "text": "Ваш доступ: " + " · ".join(parts),
    }


def indicator_entry(ind: IndicatorDef, viewer: Viewer) -> dict:
    service = SERVICE_BY_KEY.get(ind.owner_service or "")
    levels = dict(viewer.services)
    dashboard = records = None
    if service is not None and service.has_dashboard and service.key in levels:
        dashboard = service.route_prefix
        link = RECORDS_LINKS.get(service.key)
        if link and viewer.can_records and (link[1] is None or link[1] in viewer.classes):
            records = link[0]
    source = INDICATOR_SOURCE_BY_KEY.get(ind.source_key or "")
    if ind.computed:
        origin = f"из данных службы «{service.title}»" if service else "из данных службы"
    else:
        origin = f"вводит {service.title}" if service else "вводится"
    return {
        "id": ind.id, "key": ind.key, "name": ind.name, "description": ind.description or
        (source.description if source else ""), "unit": ind.unit, "data_class": ind.data_class,
        "data_class_label": DATA_CLASSES[ind.data_class], "direction": ind.direction, "rollup": ind.rollup,
        "rule_type": ind.rule_type, "green_threshold": ind.green_threshold, "yellow_threshold": ind.yellow_threshold,
        "green_deviation": ind.green_deviation, "yellow_deviation": ind.yellow_deviation,
        "default_target": ind.default_target, "source_type": ind.source_type, "source_key": ind.source_key,
        "origin": origin, "owner_service": ind.owner_service, "owner_service_title": service.title if service else None,
        "dashboard_url": dashboard, "records_url": records,
    }


# ================================================================ объяснение статуса

def _item_text(light: str, ind: IndicatorDef, unit_name: str, cell: dict) -> str:
    head = f"{COLOR_WORDS[light]}: {ind.name} в «{unit_name}» — {fmt_number(cell['value'], ind.unit)}"
    if ind.rule_type == "target":
        if cell["target"] is None:
            return head
        tail = f" при цели {fmt_number(cell['target'], ind.unit)}"
        if cell["deviation"] is not None:
            tail += f" (отклонение {fmt_number(cell['deviation'], '%')})"
        return head + tail
    border = ind.yellow_threshold if light == "red" else ind.green_threshold
    if border is None:
        return head
    return head + f" при границе {'жёлтого' if light == 'red' else 'нормы'} {fmt_number(border, ind.unit)}"


def explain(rep: CompanyReport, view: View, unit_id: int, budget: dict[int, int | None], limit: int) -> dict:
    """Показатели и подразделения ветки, которые определили статус, — там, где причина возникла:
    свёрнутое значение не называется, если тот же цвет у этого показателя есть у дочернего подразделения
    (причина — ниже). Подразделения глубже доступной детализации не называются: у последнего видимого
    уровня — «во вложенных подразделениях … (детализация недоступна)»."""
    snap = rep.state.snap
    light = view.status[unit_id]
    if light not in ("red", "yellow"):
        if light == "green":
            text = "Зелёный: все оценённые показатели в норме"
        else:
            text = "Нет оценки: нет показателей со светофором"
        if view.missing_total[unit_id]:
            text += f"; не заполнено: {view.missing_total[unit_id]}"
        return {"status": light, "text": text, "items": [], "more": 0}
    counts = view.counts[light]
    found: list[tuple] = []          # (подразделение, показатель, ячейка или None — причина глубже детализации)
    stack = [unit_id]
    while stack:
        current = stack.pop()
        own = rep.cells.get(current, {})
        locked = budget.get(current) == 0
        kids = snap.children.get(current, ())
        own_lights = set()
        for ind in view.indicators:
            cell = own.get(ind.id)
            if cell is not None and cell["status"] == light:
                own_lights.add(ind.id)
                if cell["source"] == "rollup" and not locked and any(
                        (kid := rep.cells.get(c, {}).get(ind.id)) is not None and kid["status"] == light for c in kids):
                    continue
                found.append((current, ind, cell))
        children = [c for c in kids if counts.get(c)]
        if locked:
            hidden: set[int] = set()
            for child in children:
                hidden |= view.subtree[light][child]
            found.extend((current, ind, None) for ind in view.indicators
                         if ind.id in hidden and ind.id not in own_lights)
            continue
        stack.extend(reversed(children))
    items = [_item(light, snap.units[u].name, u, ind, cell) for u, ind, cell in found[:limit]]
    text = items[0]["text"] if items else COLOR_WORDS[light]
    if len(found) > 1:
        text += f"; ещё {len(found) - 1}"
    return {"status": light, "text": text, "items": items, "more": max(0, len(found) - limit)}


def _item(light: str, name: str, unit_id: int, ind: IndicatorDef, cell: dict | None) -> dict:
    if cell is None:
        return {"indicator": ind.key, "indicator_name": ind.name, "unit_id": unit_id, "unit_name": name,
                "status": light, "value": None, "target": None, "measure": ind.unit, "detail_locked": True,
                "text": f"{COLOR_WORDS[light]}: {ind.name} — во вложенных подразделениях «{name}» "
                        "(детализация недоступна)"}
    return {"indicator": ind.key, "indicator_name": ind.name, "unit_id": unit_id, "unit_name": name, "status": light,
            "value": cell["value"], "target": cell["target"], "measure": ind.unit, "detail_locked": False,
            "text": _item_text(light, ind, name, cell)}


# ================================================================ ответы API

def _dumps(data) -> bytes:
    def default(value):
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        raise TypeError(type(value))

    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=default).encode()


def _respond(key: tuple, me: dict, build: Callable[[], dict]) -> Response:
    """Ответ из кэша ответов: ключ — состояние отчётов, права просмотра и личные признаки («me» —
    у пользователей с одинаковыми правами он одинаковый, поэтому ответ общий)."""
    return cached_body((*key, tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in me.items()))),
                       lambda: _dumps({**build(), "me": me}))


def resolve_period(db: Session, st: ReportState, viewer: Viewer, text: str | None) -> date:
    if text:
        return parse_period(text)
    periods = available_periods(db, st, viewer)
    return periods[0] if periods else current_period()


def available_periods(db: Session, st: ReportState, viewer: Viewer) -> list[date]:
    by_class = st.periods_by_class(db)
    found: set[date] = set()
    for data_class in viewer.classes:
        found |= by_class.get(data_class, set())
    return sorted(found, reverse=True)


def can_enter(user: User, st: ReportState) -> bool:
    eff = access.effective(user)
    manage = user.can("reports.manage")
    return any(not i.computed and eff.allows(i.data_class) and
               (manage or (i.owner_service is not None and eff.has_level(i.owner_service, "editor")))
               for i in st.active)


def me_block(user: User, st: ReportState, viewer: Viewer) -> dict:
    """Личные признаки: что пользователь может сделать с отчётом (кнопки интерфейса)."""
    return {"can_manage": viewer.can_manage, "can_export": viewer.can_export, "can_enter": can_enter(user, st),
            "can_note_all": viewer.can_manage,
            "note_units": sorted(u for u in st.snap.headed.get(user.id, []) if u in st.snap.units)}


def _unit_base(st: ReportState, rep: CompanyReport, view: View, unit_id: int, budget: dict) -> dict:
    snap = st.snap
    unit = snap.units[unit_id]
    parent = unit.parent_id
    light = view.status[unit_id]
    own = rep.cells.get(unit_id, {})
    missing = [{"indicator": i.key, "name": i.name} for i in view.indicators
               if (c := own.get(i.id)) is not None and c["missing"]]
    return {
        "id": unit_id, "name": unit.name, "code": unit.code, "kind": unit.kind,
        "kind_label": st.kind_labels.get(unit.kind, unit.kind),
        "parent_id": parent if parent in budget else None, "level": snap.level(unit_id) + 1,
        "path": snap.path_text(unit_id),
        "drill_locked": budget.get(unit_id) == 0 and bool(snap.children.get(unit_id)),
        "status": light, "status_label": LIGHT_LABELS[light],
        "indicator_count": view.valued[unit_id], "rated_count": view.rated[unit_id],
        "missing": missing, "missing_total": view.missing_total[unit_id], "note": rep.notes.get(unit_id),
    }


def scorecard_data(db: Session, st: ReportState, viewer: Viewer, period: date, root: int | None = None) -> dict:
    snap = st.snap
    rep = st.report(db, period)
    view = rep.view(viewer.classes)
    budget = window(snap, st.order, viewer.roots, viewer.depth)
    if root is not None:
        if root not in snap.units:
            raise NotFound("Подразделение не найдено")
        if root not in budget:
            raise Forbidden("Подразделение вне вашей области отчёта или глубже доступной детализации",
                            code="unit_out_of_scope")
        tops = [root]
    else:
        tops = [u for u in st.order if u in budget and snap.units[u].parent_id not in budget]
    listed: list[int] = []
    depth_of: dict[int, int] = {}
    for top in tops:
        stack = [(top, 0)]
        while stack:
            unit_id, rel = stack.pop()
            listed.append(unit_id)
            depth_of[unit_id] = rel
            if budget.get(unit_id) != 0:
                stack.extend((c, rel + 1) for c in reversed(snap.children.get(unit_id, ())) if c in budget)
    units = []
    violations = []
    for unit_id in listed:
        entry = _unit_base(st, rep, view, unit_id, budget)
        own = rep.cells.get(unit_id, {})
        if entry["parent_id"] not in depth_of:
            entry["parent_id"] = None       # вершина ответа: родителя в ответе нет
        entry["depth"] = depth_of[unit_id]
        entry["child_ids"] = [c for c in snap.children.get(unit_id, ()) if c in budget and budget[unit_id] != 0]
        entry["cells"] = {i.key: own[i.id] for i in view.indicators if i.id in own}
        entry["explanation"] = explain(rep, view, unit_id, budget, SCORECARD_ITEMS)
        units.append(entry)
        violations.extend({"unit_id": unit_id, "unit_name": entry["name"], "path": entry["path"],
                           "indicator": m["indicator"], "indicator_name": m["name"]} for m in entry["missing"])
    top_lights = [view.status[t] for t in tops]
    missing_total = sum(view.missing_total[t] for t in tops)
    light = traffic_light.worst(top_lights)
    return {
        "period": period_key(period), "period_label": period_label(period),
        "previous_period": period_key(add_months(period, -1)),
        "access": access_info(st, viewer),
        "indicators": [indicator_entry(i, viewer) for i in view.indicators],
        "roots": tops,
        "summary": {"status": light, "status_label": LIGHT_LABELS[light],
                    "units": traffic_light.counts(view.status[u] for u in listed),
                    "missing_total": missing_total, "violations": violations,
                    "hidden_violations": missing_total - len(violations)},
        "units": units,
    }


def scorecard_response(db: Session, user: User, period_text: str | None = None, root: int | None = None) -> Response:
    st = state(db)
    viewer = viewer_for(user, st.snap)
    period = resolve_period(db, st, viewer, period_text)
    return _respond(("reports.scorecard", st.serial, period, root, viewer.key), me_block(user, st, viewer),
                    lambda: scorecard_data(db, st, viewer, period, root))


def unit_data(db: Session, st: ReportState, viewer: Viewer, unit_id: int, period: date) -> dict:
    snap = st.snap
    if unit_id not in snap.units:
        raise NotFound("Подразделение не найдено")
    budget = window(snap, st.order, viewer.roots, viewer.depth)
    if unit_id not in budget:
        raise Forbidden("Подразделение вне вашей области отчёта или глубже доступной детализации",
                        code="unit_out_of_scope")
    rep = st.report(db, period)
    view = rep.view(viewer.classes)
    entry = _unit_base(st, rep, view, unit_id, budget)
    entry["explanation"] = explain(rep, view, unit_id, budget, DETAIL_ITEMS)
    periods = [add_months(period, -offset) for offset in range(TREND_MONTHS - 1, -1, -1)]
    layers = [st.layer(db, p) for p in periods]
    kind = snap.units[unit_id].kind
    own = rep.cells.get(unit_id, {})
    indicators = []
    for ind in view.indicators:
        trend = []
        for p, layer in zip(periods, layers, strict=True):
            cell = layer.cells.get(ind.id, {}).get(unit_id)
            value, target = (cell[0], cell[3]) if cell else (None, ind.default_target)
            light, _ = evaluate(ind, value, target)
            trend.append({"period": period_key(p), "label": period_label(p), "value": value, "target": target,
                          "status": light, "missing": value is None and expected(ind, kind, p)})
        # Показатели, которых у подразделения нет ни в одном из 12 месяцев, в панель не попадают
        if own.get(ind.id) is not None or any(t["value"] is not None or t["missing"] for t in trend):
            indicators.append({**indicator_entry(ind, viewer), "cell": own.get(ind.id), "trend": trend})
    children = []
    if budget.get(unit_id) != 0:
        for child in snap.children.get(unit_id, ()):
            if child in budget:
                base = _unit_base(st, rep, view, child, budget)
                children.append({k: base[k] for k in ("id", "name", "code", "kind", "kind_label", "status",
                                                      "status_label", "drill_locked", "missing_total",
                                                      "indicator_count", "note")}
                                | {"has_children": bool(snap.children.get(child))})
    breadcrumbs = [{"id": u, "name": snap.units[u].name} for u in snap.path(unit_id)[:-1] if u in budget]
    links, seen = [], set()
    for item in indicators:
        if item["dashboard_url"] and item["owner_service"] not in seen:
            seen.add(item["owner_service"])
            links.append({"service": item["owner_service"], "title": item["owner_service_title"],
                          "dashboard_url": item["dashboard_url"], "records_url": item["records_url"]})
    return {"period": period_key(period), "period_label": period_label(period), "access": access_info(st, viewer),
            "unit": entry, "breadcrumbs": breadcrumbs, "indicators": indicators, "children": children,
            "links": links}


def unit_response(db: Session, user: User, unit_id: int, period_text: str | None = None) -> Response:
    st = state(db)
    viewer = viewer_for(user, st.snap)
    period = resolve_period(db, st, viewer, period_text)
    me = me_block(user, st, viewer)
    me["can_note"] = viewer.can_manage or unit_id in me["note_units"]
    return _respond(("reports.unit", st.serial, period, unit_id, viewer.key), me,
                    lambda: unit_data(db, st, viewer, unit_id, period))


def summary_data(db: Session, st: ReportState, viewer: Viewer, period: date) -> dict:
    """Карточка «Обзора»: статус вершин области, подразделения по статусам, пропуски, главные причины."""
    snap = st.snap
    rep = st.report(db, period)
    view = rep.view(viewer.classes)
    budget = window(snap, st.order, viewer.roots, viewer.depth)
    tops = [u for u in st.order if u in budget and snap.units[u].parent_id not in budget]
    roots, top_items = [], []
    for unit_id in tops:
        base = _unit_base(st, rep, view, unit_id, budget)
        explanation = explain(rep, view, unit_id, budget, SUMMARY_ITEMS)
        roots.append({k: base[k] for k in ("id", "name", "kind_label", "status", "status_label", "missing_total",
                                           "indicator_count", "note")} | {"explanation": explanation})
        top_items.extend(explanation["items"])
    light = traffic_light.worst(view.status[u] for u in tops)
    return {"period": period_key(period), "period_label": period_label(period), "status": light,
            "status_label": LIGHT_LABELS[light], "access": access_info(st, viewer), "roots": roots,
            "counts": traffic_light.counts(view.status[u] for u in budget),
            "missing_total": sum(view.missing_total[u] for u in tops),
            "indicators": len(view.indicators),
            "top": sorted(top_items, key=lambda i: i["status"] != "red")[:SUMMARY_ITEMS],
            "empty": not view.indicators or not tops}


def summary_response(db: Session, user: User, period_text: str | None = None) -> Response:
    st = state(db)
    viewer = viewer_for(user, st.snap)
    period = resolve_period(db, st, viewer, period_text)
    return _respond(("reports.summary", st.serial, period, viewer.key), me_block(user, st, viewer),
                    lambda: summary_data(db, st, viewer, period))


def periods_data(db: Session, user: User) -> dict:
    st = state(db)
    viewer = viewer_for(user, st.snap)
    periods = available_periods(db, st, viewer)
    return {"periods": [{"period": period_key(p), "label": period_label(p)} for p in periods],
            "latest": period_key(periods[0]) if periods else None, "current": period_key(current_period())}


def scorecard(db: Session, user: User, period_text: str | None = None, root: int | None = None) -> dict:
    """Отчёт пользователя словарём (для PDF и проверок)."""
    st = state(db)
    viewer = viewer_for(user, st.snap)
    return scorecard_data(db, st, viewer, resolve_period(db, st, viewer, period_text), root)
