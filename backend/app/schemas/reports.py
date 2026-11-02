"""Схемы сквозных отчётов (ADR-0010): каталог показателей, ввод значений, заметки, настройки, ответы отчёта."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator

from .common import Input, Schema

DataClass = Literal["operational", "personal", "financial"]
Direction = Literal["higher_is_better", "lower_is_better", "neutral"]
Rollup = Literal["sum", "avg", "none"]
RuleType = Literal["threshold", "target"]
SourceType = Literal["computed", "manual"]
Light = Literal["green", "yellow", "red", "gray"]
PERIOD = r"^\d{4}-(0[1-9]|1[0-2])$"
KEY = r"^[a-z][a-z0-9_.-]{1,79}$"
# Числа ввода: конечные и в разумных пределах (JSON-разбор принимает NaN и Infinity)
Number = Annotated[float, Field(allow_inf_nan=False, ge=-1e15, le=1e15)]


def _clean_name(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    if not value:
        raise ValueError("Название не может быть пустым")
    return value


# ---------------------------------------------------------------- каталог показателей

class _IndicatorFields(Input):
    @field_validator("name", check_fields=False)
    @classmethod
    def _name(cls, v):
        return _clean_name(v)

    @field_validator("expected_kinds", check_fields=False)
    @classmethod
    def _kinds(cls, v):
        return None if v is None else list(dict.fromkeys(v))


class IndicatorCreateIn(_IndicatorFields):
    key: str = Field(pattern=KEY, description="Латиница, цифры, «.», «_», «-»; например fin.revenue")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    unit: str | None = Field(default=None, max_length=30, description="Без значения — из источника (вычисляемые)")
    data_class: DataClass | None = Field(default=None, description="Без значения — из источника или operational")
    direction: Direction | None = None
    rollup: Rollup | None = None
    rule_type: RuleType = "threshold"
    green_threshold: Number | None = None
    yellow_threshold: Number | None = None
    green_deviation: Number | None = Field(default=None, ge=0, le=1000)
    yellow_deviation: Number | None = Field(default=None, ge=0, le=1000)
    default_target: Number | None = None
    source_type: SourceType = "manual"
    source_key: str | None = Field(default=None, max_length=40)
    owner_service: str | None = Field(default=None, max_length=40)
    expected_kinds: list[str] = Field(default_factory=list, max_length=30)
    sort_order: int = Field(default=100, ge=0, le=100000)
    is_active: bool = True


class IndicatorUpdateIn(_IndicatorFields):
    """Изменение показателя: передаются только меняемые поля. Источник (source_type, source_key) не меняется."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    unit: str | None = Field(default=None, max_length=30)
    data_class: DataClass | None = None
    direction: Direction | None = None
    rollup: Rollup | None = None
    rule_type: RuleType | None = None
    green_threshold: Number | None = None
    yellow_threshold: Number | None = None
    green_deviation: Number | None = Field(default=None, ge=0, le=1000)
    yellow_deviation: Number | None = Field(default=None, ge=0, le=1000)
    default_target: Number | None = None
    owner_service: str | None = Field(default=None, max_length=40)
    expected_kinds: list[str] | None = Field(default=None, max_length=30)
    sort_order: int | None = Field(default=None, ge=0, le=100000)
    is_active: bool | None = None


class IndicatorOut(Schema):
    id: int
    key: str
    name: str
    description: str
    unit: str
    data_class: DataClass
    data_class_label: str
    direction: Direction
    direction_label: str
    rollup: Rollup
    rollup_label: str
    rule_type: RuleType
    rule_label: str
    green_threshold: float | None = None
    yellow_threshold: float | None = None
    green_deviation: float | None = None
    yellow_deviation: float | None = None
    default_target: float | None = None
    source_type: SourceType
    source_key: str | None = None
    source_name: str | None = Field(default=None, description="Название источника вычисляемого показателя")
    owner_service: str | None = None
    owner_service_title: str | None = None
    expected_kinds: list[str]
    sort_order: int
    is_active: bool
    values_count: int = Field(default=0, description="Сохранённых значений (для вводимых)")
    created_at: datetime
    updated_at: datetime


class LabelOut(Schema):
    key: str
    label: str


class SourceOut(Schema):
    key: str
    service: str
    service_title: str
    name: str
    unit: str
    attach: Literal["unit", "company", "service"]
    description: str
    direction: Direction
    rollup: Rollup
    data_class: DataClass


class ServiceRefOut(Schema):
    key: str
    title: str


class ReportsMetaOut(Schema):
    sources: list[SourceOut]
    data_classes: list[LabelOut]
    directions: list[LabelOut]
    rollups: list[LabelOut]
    rule_types: list[LabelOut]
    unit_kinds: list[dict[str, Any]]
    services: list[ServiceRefOut]
    statuses: list[LabelOut]


# ---------------------------------------------------------------- ввод значений

class ValueItemIn(Input):
    indicator_id: int
    department_id: int
    value: Number | None = None
    target: Number | None = None
    comment: str = Field(default="", max_length=2000)


class ValuesIn(Input):
    """Значения за месяц. Каждая ячейка заменяется целиком (значение, цель, комментарий);
    пустые значение, цель и комментарий удаляют запись."""

    period: str = Field(pattern=PERIOD, description="ГГГГ-ММ")
    items: list[ValueItemIn] = Field(min_length=1, max_length=5000)


class PersonRefOut(Schema):
    id: int
    full_name: str


class ValueOut(Schema):
    indicator_id: int
    indicator_key: str
    department_id: int
    period: str
    value: float | None = None
    target: float | None = None
    comment: str = ""
    source: Literal["manual", "import"]
    source_label: str
    updated_at: datetime | None = None
    updated_by: PersonRefOut | None = None


class EntryIndicatorOut(Schema):
    id: int
    key: str
    name: str
    unit: str
    data_class: DataClass
    data_class_label: str
    owner_service: str | None = None
    owner_service_title: str | None = None
    direction: Direction
    rule_type: RuleType
    default_target: float | None = None
    expected_kinds: list[str]
    unit_ids: list[int] | None = Field(description="Подразделения, где можно вводить; null — все из units")


class EntryUnitOut(Schema):
    id: int
    name: str
    code: str | None = None
    kind: str
    kind_label: str
    path: str
    level: int
    parent_id: int | None = None


class ValuesListOut(Schema):
    period: str
    period_label: str
    indicators: list[EntryIndicatorOut]
    units: list[EntryUnitOut]
    values: list[ValueOut]


class ValuesSaveOut(Schema):
    period: str
    created: int
    updated: int
    deleted: int
    unchanged: int
    values: list[ValueOut]


class ValuesImportIn(Input):
    """Загрузка телом JSON: content — текст CSV (разделитель «;» или «,»)."""

    content: str = Field(max_length=10_000_000)
    apply: bool = False


class CellStateOut(Schema):
    value: float | None = None
    target: float | None = None
    comment: str = ""


class ImportRowOut(Schema):
    line: int
    department: str
    department_id: int | None = None
    department_path: str = ""
    indicator: str
    indicator_id: int | None = None
    indicator_key: str | None = None
    indicator_name: str = ""
    period: str
    value: float | None = None
    target: float | None = None
    comment: str | None = None
    clear: bool = Field(default=False, description="Строка «очистить»: удалить сохранённое значение")
    action: Literal["create", "update", "clear", "unchanged", "error"]
    before: CellStateOut | None = None
    after: CellStateOut | None = None
    errors: list[str] = []


class ImportSummaryOut(Schema):
    rows: int
    create: int
    update: int
    cleared: int = 0
    unchanged: int
    errors: int


class ValuesImportOut(Schema):
    summary: ImportSummaryOut
    rows: list[ImportRowOut]
    can_apply: bool
    applied: bool = False


# ---------------------------------------------------------------- заметки и настройки

class NoteIn(Input):
    period: str = Field(pattern=PERIOD)
    status: Literal["watch"] | None = Field(default="watch", description="null — снять заметку")
    comment: str = Field(default="", max_length=2000)


class NoteOut(Schema):
    department_id: int
    period: str
    status: Literal["watch"]
    status_label: str
    comment: str
    author: PersonRefOut | None = None
    created_at: datetime


class NoteResultOut(Schema):
    note: NoteOut | None = None


class ServiceUnitsIn(Input):
    report_service_units: dict[str, int | None] = Field(
        description="Служба → id подразделения структуры; null — по коду по умолчанию (HR, TECH, PROJ)")


class UnitRefOut(Schema):
    id: int
    name: str
    path: str


class ServiceUnitOut(Schema):
    key: str
    title: str
    default_code: str
    configured: int | None = Field(default=None, description="Заданное подразделение; null — по коду")
    unit: UnitRefOut | None = Field(default=None, description="Действующее подразделение службы")
    sources: list[str]


class ReportSettingsOut(Schema):
    report_service_units: dict[str, int | None]
    services: list[ServiceUnitOut]


# ---------------------------------------------------------------- ответы отчёта (для документации API)

class CellOut(Schema):
    value: float | None = None
    target: float | None = None
    previous: float | None = None
    delta: float | None = None
    status: Light
    status_label: str
    missing: bool = Field(description="Значение ожидается, но не заполнено — критичное нарушение полноты")
    deviation: float | None = Field(default=None, description="Отклонение от цели, %, для правила «target»")
    source: Literal["manual", "import", "computed", "rollup"] | None = None
    source_label: str
    rollup_count: int = 0
    comment: str = ""


class ExplanationItemOut(Schema):
    indicator: str
    indicator_name: str
    unit_id: int
    unit_name: str
    status: Light
    value: float | None = None
    target: float | None = None
    measure: str
    detail_locked: bool = Field(description="Причина во вложенных подразделениях за пределом детализации")
    text: str


class ExplanationOut(Schema):
    status: Light
    text: str
    items: list[ExplanationItemOut]
    more: int


class ReportNoteOut(Schema):
    status: Literal["watch"]
    status_label: str
    comment: str
    author: PersonRefOut | None = None
    created_at: str | None = None


class MissingOut(Schema):
    indicator: str
    name: str


class ReportUnitOut(Schema):
    id: int
    name: str
    code: str | None = None
    kind: str
    kind_label: str
    parent_id: int | None = Field(default=None, description="Родитель, если он есть в ответе")
    level: int = Field(description="Уровень в структуре, 1 — верхний")
    depth: int = Field(description="Уровень в ответе от вершины, 0 — вершина")
    path: str
    child_ids: list[int]
    drill_locked: bool = Field(description="Есть вложенные подразделения за пределом детализации")
    status: Light
    status_label: str
    indicator_count: int = Field(description="Доступных показателей со значением у подразделения")
    rated_count: int = Field(description="Из них оценённых светофором")
    missing: list[MissingOut]
    missing_total: int = Field(description="Нарушений полноты во всей ветке")
    note: ReportNoteOut | None = None
    cells: dict[str, CellOut] = Field(description="Ключ показателя → ячейка; нет ключа — нет значения")
    explanation: ExplanationOut


class AccessInfoOut(Schema):
    scope: Literal["company", "branch", "unit"]
    scope_label: str
    roots: list[UnitRefOut]
    drill_depth: int | None
    classes: list[DataClass]
    hidden_classes: list[str] = Field(description="Названия недоступных классов данных")
    text: str


class ReportIndicatorOut(Schema):
    id: int
    key: str
    name: str
    description: str
    unit: str
    data_class: DataClass
    data_class_label: str
    direction: Direction
    rollup: Rollup
    rule_type: RuleType
    green_threshold: float | None = None
    yellow_threshold: float | None = None
    green_deviation: float | None = None
    yellow_deviation: float | None = None
    default_target: float | None = None
    source_type: SourceType
    source_key: str | None = None
    origin: str
    owner_service: str | None = None
    owner_service_title: str | None = None
    dashboard_url: str | None = None
    records_url: str | None = None


class ViolationOut(Schema):
    unit_id: int
    unit_name: str
    path: str
    indicator: str
    indicator_name: str


class ScorecardSummaryOut(Schema):
    status: Light
    status_label: str
    units: dict[str, int]
    missing_total: int
    violations: list[ViolationOut]
    hidden_violations: int


class MeOut(Schema):
    """Личные признаки: что пользователь может сделать с отчётом (кнопки интерфейса)."""

    can_manage: bool
    can_export: bool
    can_enter: bool
    can_note_all: bool
    note_units: list[int]
    can_note: bool | None = None


class ScorecardOut(Schema):
    period: str
    period_label: str
    previous_period: str
    access: AccessInfoOut
    indicators: list[ReportIndicatorOut]
    roots: list[int]
    summary: ScorecardSummaryOut
    units: list[ReportUnitOut]
    me: MeOut


class TrendPointOut(Schema):
    period: str
    label: str
    value: float | None = None
    target: float | None = None
    status: Light
    missing: bool


class UnitIndicatorOut(ReportIndicatorOut):
    cell: CellOut | None = None
    trend: list[TrendPointOut]


class UnitChildOut(Schema):
    id: int
    name: str
    code: str | None = None
    kind: str
    kind_label: str
    status: Light
    status_label: str
    drill_locked: bool
    has_children: bool
    missing_total: int
    indicator_count: int
    note: ReportNoteOut | None = None


class BreadcrumbOut(Schema):
    id: int
    name: str


class ServiceLinkOut(Schema):
    service: str
    title: str
    dashboard_url: str
    records_url: str | None = None


class UnitDetailUnitOut(Schema):
    id: int
    name: str
    code: str | None = None
    kind: str
    kind_label: str
    parent_id: int | None = None
    level: int
    path: str
    drill_locked: bool
    status: Light
    status_label: str
    indicator_count: int
    rated_count: int
    missing: list[MissingOut]
    missing_total: int
    note: ReportNoteOut | None = None
    explanation: ExplanationOut


class UnitReportOut(Schema):
    period: str
    period_label: str
    access: AccessInfoOut
    unit: UnitDetailUnitOut
    breadcrumbs: list[BreadcrumbOut]
    indicators: list[UnitIndicatorOut]
    children: list[UnitChildOut]
    links: list[ServiceLinkOut]
    me: MeOut


class PeriodOut(Schema):
    period: str
    label: str


class PeriodsOut(Schema):
    periods: list[PeriodOut] = Field(description="Периоды с данными, от новых к старым")
    latest: str | None = None
    current: str


class SummaryRootOut(Schema):
    id: int
    name: str
    kind_label: str
    status: Light
    status_label: str
    missing_total: int
    indicator_count: int
    note: ReportNoteOut | None = None
    explanation: ExplanationOut


class ReportSummaryOut(Schema):
    period: str
    period_label: str
    status: Light
    status_label: str
    access: AccessInfoOut
    roots: list[SummaryRootOut]
    counts: dict[str, int] = Field(description="Видимые подразделения по статусам: green, yellow, red, gray")
    missing_total: int
    indicators: int = Field(description="Доступных показателей в каталоге")
    top: list[ExplanationItemOut] = Field(description="Три главные причины статуса")
    empty: bool
    me: MeOut
