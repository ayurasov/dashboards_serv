"""Сквозные отчёты: каталог показателей, ввод и загрузка значений, заметки о статусе, настройки (ADR-0010).

Функции изменения не фиксируют транзакцию: commit — один раз в обработчике запроса. Каждое изменение
записывается в журнал; ревизия отчётов увеличивается в той же транзакции (события сессии в app/models/reports.py).

Вводить значения вводимого показателя могут:
- пользователь с полномочием reports.manage (и администратор) — во всех подразделениях;
- пользователь с уровнем «Ввод данных» к службе-владельцу — в своей области структуры для этой службы
  (scope_units: вся компания, своя ветка или свои подразделения).
Показатель недоступного класса данных не вводится и в ответах не упоминается («не найден»).
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from ..models import AppSetting, Indicator, IndicatorValue, UnitStatusNote, User, name_key
from ..schemas.reports import IndicatorCreateIn, IndicatorUpdateIn, NoteIn, ServiceUnitsIn, ValueItemIn
from . import access, audit, org, org_admin, org_import, reports
from .registry import (
    ACCESS_LEVEL_LABELS,
    DATA_CLASSES,
    INDICATOR_DIRECTION_LABELS,
    INDICATOR_ROLLUP_LABELS,
    INDICATOR_RULE_LABELS,
    INDICATOR_SOURCE_BY_KEY,
    INDICATOR_SOURCES,
    REPORT_SERVICE_UNIT_DEFAULTS,
    REPORT_SETTING_KEY,
    SERVICE_BY_KEY,
    SERVICES,
)

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,79}$")
NUMBER_SPACES = re.compile(r"[\s  ]")
MAX_IMPORT_ROWS = 5000
IMPORT_ALIASES = {
    "department": ("подразделение", "department", "код подразделения", "путь подразделения", "unit"),
    "indicator": ("показатель", "indicator", "ключ показателя", "key"),
    "period": ("период", "period", "месяц", "month"),
    "value": ("значение", "value", "факт"),
    "target": ("цель", "target", "план"),
    "comment": ("комментарий", "comment", "примечание"),
}
NOT_FOUND = "Показатель не найден"


# ================================================================ справочник

def meta(db: Session) -> dict:
    kinds = org_admin.get_settings(db)["unit_kinds"]
    return {
        "sources": [{"key": s.key, "service": s.service_key, "service_title": SERVICE_BY_KEY[s.service_key].title,
                     "name": s.name, "unit": s.unit, "attach": s.attach, "description": s.description,
                     "direction": s.direction, "rollup": s.rollup, "data_class": s.data_class}
                    for s in INDICATOR_SOURCES],
        "data_classes": [{"key": k, "label": v} for k, v in DATA_CLASSES.items()],
        "directions": [{"key": k, "label": v} for k, v in INDICATOR_DIRECTION_LABELS.items()],
        "rollups": [{"key": k, "label": v} for k, v in INDICATOR_ROLLUP_LABELS.items()],
        "rule_types": [{"key": k, "label": v} for k, v in INDICATOR_RULE_LABELS.items()],
        "unit_kinds": kinds,
        "services": [{"key": s.key, "title": s.title} for s in SERVICES],
        "statuses": [{"key": k, "label": v} for k, v in reports.LIGHT_LABELS.items()]
        + [{"key": "missing", "label": reports.MISSING_LABEL}],
    }


# ================================================================ каталог

def indicator_out(row: Indicator, values_count: int = 0) -> dict:
    service = SERVICE_BY_KEY.get(row.owner_service or "")
    source = INDICATOR_SOURCE_BY_KEY.get(row.source_key or "")
    return {
        "id": row.id, "key": row.key, "name": row.name, "description": row.description or "", "unit": row.unit or "",
        "data_class": row.data_class, "data_class_label": DATA_CLASSES.get(row.data_class, row.data_class),
        "direction": row.direction, "direction_label": INDICATOR_DIRECTION_LABELS.get(row.direction, row.direction),
        "rollup": row.rollup, "rollup_label": INDICATOR_ROLLUP_LABELS.get(row.rollup, row.rollup),
        "rule_type": row.rule_type, "rule_label": INDICATOR_RULE_LABELS.get(row.rule_type, row.rule_type),
        "green_threshold": row.green_threshold, "yellow_threshold": row.yellow_threshold,
        "green_deviation": row.green_deviation, "yellow_deviation": row.yellow_deviation,
        "default_target": row.default_target, "source_type": row.source_type, "source_key": row.source_key,
        "source_name": source.name if source else None, "owner_service": row.owner_service,
        "owner_service_title": service.title if service else None, "expected_kinds": list(row.expected_kinds or []),
        "sort_order": row.sort_order, "is_active": row.is_active, "values_count": values_count,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


def values_counts(db: Session) -> dict[int, int]:
    return dict(db.execute(select(IndicatorValue.indicator_id, func.count())
                           .group_by(IndicatorValue.indicator_id)).all())


def list_indicators(db: Session, user: User) -> list[dict]:
    """Каталог: с полномочием reports.manage — весь (в том числе выключенные), иначе — активные показатели
    доступных классов данных."""
    eff = access.effective(user)
    manage = user.can("reports.manage")
    counts = values_counts(db) if manage else {}
    rows = db.scalars(select(Indicator).order_by(Indicator.sort_order, Indicator.id))
    return [indicator_out(r, counts.get(r.id, 0)) for r in rows
            if manage or (r.is_active and eff.allows(r.data_class))]


def get_indicator(db: Session, indicator_id: int) -> Indicator:
    row = db.get(Indicator, indicator_id)
    if row is None:
        raise NotFound(NOT_FOUND)
    return row


def _snapshot(row: Indicator) -> dict:
    return {k: v for k, v in indicator_out(row).items()
            if k not in ("id", "created_at", "updated_at", "values_count") and not k.endswith(("_label", "_title"))
            and k != "source_name"}


def _check_unique(db: Session, key: str | None, name: str | None, indicator_id: int | None = None) -> None:
    for other in db.scalars(select(Indicator)):
        if other.id == indicator_id:
            continue
        if key is not None and other.key == key:
            raise Conflict(f"Показатель с ключом «{key}» уже есть", fields={"key": "Ключ занят"})
        if name is not None and name_key(other.name) == name_key(name):
            raise Conflict(f"Показатель «{other.name}» уже есть", fields={"name": "Название занято"})


def _validate(db: Session, data: dict) -> None:
    """Согласованность полей показателя (после применения изменений)."""
    if data["source_type"] == "computed":
        if data["source_key"] not in INDICATOR_SOURCE_BY_KEY:
            raise ValidationFailed("Выберите источник вычисляемого показателя",
                                   fields={"source_key": f"Допустимо: {', '.join(INDICATOR_SOURCE_BY_KEY)}"})
    else:
        if data["source_key"]:
            raise ValidationFailed("У вводимого показателя нет источника данных службы",
                                   fields={"source_key": "Только для вычисляемых"})
        if data["owner_service"] not in SERVICE_BY_KEY:
            raise ValidationFailed("Укажите службу-владельца: её сотрудники с уровнем «Ввод данных» вводят значения",
                                   fields={"owner_service": "Обязательное поле"})
    direction = data["direction"]
    if data["rule_type"] == "threshold":
        green, yellow = data["green_threshold"], data["yellow_threshold"]
        if (green is None) != (yellow is None):
            raise ValidationFailed("Задайте обе границы светофора или ни одной",
                                   fields={"green_threshold" if green is None else "yellow_threshold": "Нужна граница"})
        if green is not None:
            if direction == "lower_is_better" and green > yellow:
                raise ValidationFailed("«Меньше — лучше»: граница зелёного должна быть не больше границы жёлтого",
                                       fields={"green_threshold": "Больше границы жёлтого"})
            if direction == "higher_is_better" and green < yellow:
                raise ValidationFailed("«Больше — лучше»: граница зелёного должна быть не меньше границы жёлтого",
                                       fields={"green_threshold": "Меньше границы жёлтого"})
    else:
        green, yellow = data["green_deviation"], data["yellow_deviation"]
        if direction != "neutral" and (green is None or yellow is None):
            raise ValidationFailed("Для правила «Отклонение от цели» задайте допустимые отклонения зелёного и жёлтого",
                                   fields={"green_deviation" if green is None else "yellow_deviation": "Нужно, %"})
        if green is not None and yellow is not None and green > yellow:
            raise ValidationFailed("Отклонение зелёного должно быть не больше отклонения жёлтого",
                                   fields={"green_deviation": "Больше отклонения жёлтого"})
    kinds = {k["value"] for k in org_admin.get_settings(db)["unit_kinds"]}
    unknown = [k for k in data["expected_kinds"] if k not in kinds]
    if unknown:
        raise ValidationFailed(f"Неизвестный тип уровня структуры: {unknown[0]}",
                               fields={"expected_kinds": f"Допустимо: {', '.join(sorted(kinds))}"})


def create_indicator(db: Session, actor: User, body: IndicatorCreateIn, request: Request | None = None) -> Indicator:
    fields = body.model_dump()
    source = INDICATOR_SOURCE_BY_KEY.get(fields["source_key"] or "") if fields["source_type"] == "computed" else None
    if fields["source_type"] == "computed" and source is None:
        raise ValidationFailed("Выберите источник вычисляемого показателя",
                               fields={"source_key": f"Допустимо: {', '.join(INDICATOR_SOURCE_BY_KEY)}"})
    data = {
        **fields,
        "unit": fields["unit"] if fields["unit"] is not None else (source.unit if source else ""),
        "data_class": fields["data_class"] or (source.data_class if source else "operational"),
        "direction": fields["direction"] or (source.direction if source else "higher_is_better"),
        "rollup": fields["rollup"] or (source.rollup if source else "sum"),
        # Владелец вычисляемого показателя — служба источника
        "owner_service": source.service_key if source else fields["owner_service"],
    }
    _validate(db, data)
    _check_unique(db, data["key"], data["name"])
    row = Indicator(**data)
    db.add(row)
    db.flush()
    audit.record(db, actor, entity_type="indicator", entity_id=row.id, action="create",
                 summary=f"Создан показатель «{row.name}»", after=_snapshot(row), request=request)
    return row


def update_indicator(db: Session, actor: User, row: Indicator, body: IndicatorUpdateIn,
                     request: Request | None = None) -> Indicator:
    fields = body.model_dump(exclude_unset=True)
    before = _snapshot(row)
    data = {k: getattr(row, k) for k in before}
    data["expected_kinds"] = list(row.expected_kinds or [])
    nullable = {"green_threshold", "yellow_threshold", "green_deviation", "yellow_deviation", "default_target"}
    for key, value in fields.items():
        if value is None and key not in nullable:
            continue
        data[key] = value
    if row.source_type == "computed":
        data["owner_service"] = INDICATOR_SOURCE_BY_KEY[row.source_key].service_key \
            if row.source_key in INDICATOR_SOURCE_BY_KEY else row.owner_service
    _validate(db, data)
    if data["name"] != row.name:
        _check_unique(db, None, data["name"], row.id)
    for key, value in data.items():
        if key not in ("key", "source_type", "source_key"):
            setattr(row, key, value)
    db.flush()
    b, a = audit.diff(before, _snapshot(row))
    if a:
        audit.record(db, actor, entity_type="indicator", entity_id=row.id, action="update",
                     summary=f"Изменён показатель «{row.name}»", before=b, after=a, request=request)
    return row


def delete_indicator(db: Session, actor: User, row: Indicator, *, force: bool = False,
                     request: Request | None = None) -> int:
    count = db.scalar(select(func.count()).select_from(IndicatorValue)
                      .where(IndicatorValue.indicator_id == row.id)) or 0
    if count and not force:
        raise Conflict(f"У показателя «{row.name}» {count} сохранённых значений — выключите его (он перестанет "
                       "попадать в отчёты, значения сохранятся) или удалите вместе со значениями",
                       code="indicator_has_values")
    audit.record(db, actor, entity_type="indicator", entity_id=row.id, action="delete",
                 summary=f"Удалён показатель «{row.name}»" + (f" и {count} значений" if count else ""),
                 before={**_snapshot(row), "values_count": count}, request=request)
    db.delete(row)
    db.flush()
    return count


# ================================================================ права на ввод

@dataclass
class EntryRight:
    allowed: bool
    units: set[int] | None = None        # None — все подразделения
    reason: str = ""
    status: int = 403


def entry_right(db: Session, user: User, ind: reports.IndicatorDef) -> EntryRight:
    eff = access.effective(user)
    if not eff.allows(ind.data_class):
        return EntryRight(False, reason=NOT_FOUND, status=404)
    if ind.computed:
        return EntryRight(False, reason=f"«{ind.name}» вычисляется из данных службы — вводить значения не нужно",
                          status=422)
    if not ind.is_active:
        return EntryRight(False, reason=f"Показатель «{ind.name}» выключен", status=422)
    if user.can("reports.manage"):
        return EntryRight(True)
    service = SERVICE_BY_KEY.get(ind.owner_service or "")
    if service is None or not eff.has_level(service.key, "editor"):
        title = service.title if service else "служба-владелец"
        return EntryRight(False, reason=f"Вводить «{ind.name}» может уровень доступа «{ACCESS_LEVEL_LABELS['editor']}» "
                                        f"к службе «{title}»")
    return EntryRight(True, access.scope_units(db, user, service.key))


def _right_error(right: EntryRight, field: str | None = None):
    fields = {field: right.reason} if field else None
    if right.status == 404:
        return NotFound(right.reason, fields=fields)
    if right.status == 422:
        return ValidationFailed(right.reason, fields=fields)
    return Forbidden(right.reason, code="entry_forbidden", fields=fields)


def _out_of_scope(snap: org.OrgSnapshot, ind: reports.IndicatorDef, unit_id: int) -> str:
    service = SERVICE_BY_KEY.get(ind.owner_service or "")
    title = f" для службы «{service.title}»" if service else ""
    return f"«{snap.units[unit_id].name}» вне вашей области структуры{title} — вводить «{ind.name}» там нельзя"


# ================================================================ значения

def _value_out(row: IndicatorValue, ind: reports.IndicatorDef, snap: org.OrgSnapshot) -> dict:
    person = snap.people.get(row.updated_by_id) if row.updated_by_id else None
    return {"indicator_id": row.indicator_id, "indicator_key": ind.key, "department_id": row.department_id,
            "period": reports.period_key(row.period), "value": row.value, "target": row.target,
            "comment": row.comment or "", "source": row.source, "source_label": reports.SOURCE_LABELS[row.source],
            "updated_at": row.updated_at,
            "updated_by": {"id": person.id, "full_name": person.full_name} if person else None}


def _find_indicator(st: reports.ReportState, ref: str) -> reports.IndicatorDef | None:
    ref = (ref or "").strip()
    by_key = {i.key: i for i in st.catalog}
    if ref in by_key:
        return by_key[ref]
    if ref.isdigit():
        found = next((i for i in st.catalog if i.id == int(ref)), None)
        if found is not None:
            return found
    key = name_key(ref)
    return next((i for i in st.catalog if name_key(i.name) == key), None)


def values_listing(db: Session, user: User, period_text: str, indicator: str | None = None,
                   unit: int | None = None) -> dict:
    """Форма ввода за месяц: вводимые показатели, которые пользователь может вводить, подразделения
    его области и сохранённые значения."""
    period = reports.parse_period(period_text)
    st = reports.state(db)
    snap = st.snap
    rights: list[tuple[reports.IndicatorDef, EntryRight]] = []
    for ind in st.active:
        if ind.computed:
            continue
        right = entry_right(db, user, ind)
        if right.allowed and (right.units is None or right.units):
            rights.append((ind, right))
    if indicator:
        found = _find_indicator(st, indicator)
        if found is None or not access.effective(user).allows(found.data_class):
            raise NotFound(NOT_FOUND)
        rights = [(i, r) for i, r in rights if i.id == found.id]
        if not rights:
            raise _right_error(entry_right(db, user, found))
    if not rights:
        raise Forbidden("Ввод показателей вам недоступен: нужен уровень «Ввод данных» к службе-владельцу "
                        "показателя или полномочие «Сквозные отчёты»", code="entry_forbidden")
    if unit is not None and unit not in snap.units:
        raise NotFound("Подразделение не найдено")
    every = any(r.units is None for _, r in rights)
    allowed_units: set[int] = set(snap.units) if every else set().union(*(r.units for _, r in rights))
    if unit is not None:
        if unit not in allowed_units:
            raise Forbidden("Подразделение вне вашей области ввода", code="entry_forbidden")
        allowed_units = {unit}
    order = [u for u in st.order if u in allowed_units]
    ids = [i.id for i, _ in rights]
    rows = list(db.scalars(select(IndicatorValue).where(IndicatorValue.period == period,
                                                        IndicatorValue.indicator_id.in_(ids))))
    by_id = {i.id: (i, r) for i, r in rights}
    values = [_value_out(r, by_id[r.indicator_id][0], snap) for r in rows
              if r.department_id in allowed_units and
              (by_id[r.indicator_id][1].units is None or r.department_id in by_id[r.indicator_id][1].units)]
    position = {u: i for i, u in enumerate(order)}
    rank = {ind_id: i for i, ind_id in enumerate(ids)}
    values.sort(key=lambda v: (position.get(v["department_id"], 0), rank[v["indicator_id"]]))
    return {
        "period": reports.period_key(period), "period_label": reports.period_label(period),
        "indicators": [{
            "id": i.id, "key": i.key, "name": i.name, "unit": i.unit, "data_class": i.data_class,
            "data_class_label": DATA_CLASSES[i.data_class], "owner_service": i.owner_service,
            "owner_service_title": SERVICE_BY_KEY[i.owner_service].title if i.owner_service in SERVICE_BY_KEY
            else None, "direction": i.direction, "rule_type": i.rule_type, "default_target": i.default_target,
            "expected_kinds": list(i.expected_kinds),
            "unit_ids": None if r.units is None else [u for u in order if u in r.units],
        } for i, r in rights],
        "units": [{"id": u, "name": snap.units[u].name, "code": snap.units[u].code, "kind": snap.units[u].kind,
                   "kind_label": st.kind_labels.get(snap.units[u].kind, snap.units[u].kind),
                   "path": snap.path_text(u), "level": snap.level(u) + 1,
                   "parent_id": snap.units[u].parent_id if snap.units[u].parent_id in snap.units else None}
                  for u in order],
        "values": values,
    }


def _cell_state(row: IndicatorValue | None) -> dict | None:
    if row is None:
        return None
    return {"value": row.value, "target": row.target, "comment": row.comment or ""}


def _write_cells(db: Session, actor: User, period: date, cells: list[dict], source: str) -> dict:
    """cells: indicator, unit, value, target, comment, row (существующая или None). Пустая ячейка удаляет запись."""
    created = updated = deleted = unchanged = 0
    touched: list[IndicatorValue] = []
    changes: list[dict] = []
    for cell in cells:
        row: IndicatorValue | None = cell["row"]
        after = {"value": cell["value"], "target": cell["target"], "comment": cell["comment"] or ""}
        empty = after["value"] is None and after["target"] is None and not after["comment"]
        before = _cell_state(row)
        label = f"{cell['indicator'].key} / {cell['unit_name']}"
        if row is None:
            if empty:
                unchanged += 1
                continue
            row = IndicatorValue(indicator_id=cell["indicator"].id, department_id=cell["unit"], period=period,
                                 source=source, updated_by_id=actor.id, **after)
            db.add(row)
            created += 1
        elif empty:
            db.delete(row)
            deleted += 1
            changes.append({"cell": label, "before": before, "after": None})
            continue
        elif before == after:
            unchanged += 1
            touched.append(row)
            continue
        else:
            row.value, row.target, row.comment = after["value"], after["target"], after["comment"]
            row.source, row.updated_by_id, row.updated_at = source, actor.id, utcnow()
            updated += 1
        touched.append(row)
        changes.append({"cell": label, "before": before, "after": after})
    db.flush()
    return {"created": created, "updated": updated, "deleted": deleted, "unchanged": unchanged,
            "touched": touched, "changes": changes}


def save_values(db: Session, actor: User, period_text: str, items: list[ValueItemIn],
                request: Request | None = None) -> dict:
    period = reports.parse_period(period_text)
    st = reports.state(db)
    snap = st.snap
    by_id = {i.id: i for i in st.catalog}
    rights: dict[int, EntryRight] = {}
    seen: set[tuple[int, int]] = set()
    for index, item in enumerate(items):
        ind = by_id.get(item.indicator_id)
        if ind is None:
            raise NotFound(NOT_FOUND, fields={f"items.{index}.indicator_id": NOT_FOUND})
        if ind.id not in rights:
            rights[ind.id] = entry_right(db, actor, ind)
        right = rights[ind.id]
        if not right.allowed:
            raise _right_error(right, f"items.{index}.indicator_id")
        if item.department_id not in snap.units:
            raise NotFound("Подразделение не найдено", fields={f"items.{index}.department_id": "Нет такого"})
        if right.units is not None and item.department_id not in right.units:
            raise Forbidden(_out_of_scope(snap, ind, item.department_id), code="entry_forbidden",
                            fields={f"items.{index}.department_id": "Вне области ввода"})
        if (ind.id, item.department_id) in seen:
            raise ValidationFailed("Одна и та же ячейка указана дважды",
                                   fields={f"items.{index}": "Повтор показателя и подразделения"})
        seen.add((ind.id, item.department_id))
    existing = {(r.indicator_id, r.department_id): r for r in db.scalars(
        select(IndicatorValue).where(IndicatorValue.period == period,
                                     IndicatorValue.indicator_id.in_({i.indicator_id for i in items}),
                                     IndicatorValue.department_id.in_({i.department_id for i in items})))}
    cells = [{"indicator": by_id[i.indicator_id], "unit": i.department_id,
              "unit_name": snap.units[i.department_id].name, "value": i.value, "target": i.target,
              "comment": i.comment.strip(), "row": existing.get((i.indicator_id, i.department_id))} for i in items]
    result = _write_cells(db, actor, period, cells, "manual")
    if result["changes"]:
        label = reports.period_label(period)
        audit.record(db, actor, entity_type="indicator_value", entity_id=reports.period_key(period), action="update",
                     summary=f"Значения показателей за {label.lower()}: новых {result['created']}, "
                             f"изменено {result['updated']}, удалено {result['deleted']}",
                     before={"cells": [c for c in result["changes"] if c["before"]][:200]},
                     after={"cells": [c for c in result["changes"] if c["after"]][:200]}, request=request)
    return {"period": reports.period_key(period), "created": result["created"], "updated": result["updated"],
            "deleted": result["deleted"], "unchanged": result["unchanged"],
            "values": [_value_out(r, by_id[r.indicator_id], snap) for r in result["touched"]]}


# ================================================================ загрузка значений (Excel, CSV)

def parse_number(text: str) -> float:
    raw = NUMBER_SPACES.sub("", text or "").replace(",", ".").rstrip("%").replace("−", "-")
    number = float(raw)
    if not math.isfinite(number) or abs(number) >= 1e15:
        raise ValueError(text)
    return number


def parse_import_period(text: str) -> date:
    raw = (text or "").strip()
    match = re.match(r"^(\d{4})-(\d{1,2})(?:-\d{1,2}(?:[T ].*)?)?$", raw) or None
    if match:
        year, month = int(match.group(1)), int(match.group(2))
    else:
        match = re.match(r"^(\d{1,2})[./](\d{4})$", raw)
        if not match:
            raise ValueError(raw)
        month, year = int(match.group(1)), int(match.group(2))
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        raise ValueError(raw)
    return date(year, month, 1)


def parse_table(table: list[list[str]]) -> list[dict]:
    while table and not any(table[0]):
        table = table[1:]
    if not table:
        raise org_import.ImportFormatError("Файл пустой")
    mapping = org_import.header_map(table[0], IMPORT_ALIASES)
    missing = [title for column, title in (("department", "Подразделение"), ("indicator", "Показатель"),
                                          ("period", "Период")) if column not in mapping]
    if missing:
        raise org_import.ImportFormatError(f"Нужен столбец «{missing[0]}» (столбцы: Подразделение, Показатель, "
                                           "Период, Значение, Цель, Комментарий)")
    if not {"value", "target", "comment"} & set(mapping):
        raise org_import.ImportFormatError("Нужен хотя бы один из столбцов «Значение», «Цель», «Комментарий»")
    rows = []
    for line, values in enumerate(table[1:], start=2):
        if not any((v or "").strip() for v in values):
            continue
        if len(rows) >= MAX_IMPORT_ROWS:
            raise org_import.ImportFormatError(f"Не больше {MAX_IMPORT_ROWS} строк за одну загрузку")

        def cell(column: str, vals=values) -> str | None:
            index = mapping.get(column)
            if index is None:
                return None
            return (vals[index] if index < len(vals) else "").strip()

        rows.append({"line": line, **{column: cell(column) for column in IMPORT_ALIASES}})
    if not rows:
        raise org_import.ImportFormatError("В файле нет ни одной строки со значениями")
    return rows


def parse_upload(filename: str, raw: bytes) -> list[dict]:
    return parse_table(org_import.read_table(filename, raw))


def parse_content(content: str) -> list[dict]:
    return parse_table(org_import.csv_rows(content))


def _unit_resolver(snap: org.OrgSnapshot):
    by_code = {u.code.casefold(): u.id for u in snap.units.values() if u.code}
    by_path: dict[tuple, int] = {}
    by_name: dict[str, list[int]] = defaultdict(list)
    for unit_id in snap.units:
        by_path[tuple(name_key(n) for n in snap.path_names(unit_id))] = unit_id
        by_name[name_key(snap.units[unit_id].name)].append(unit_id)

    def resolve(text: str) -> tuple[int | None, str]:
        raw = (text or "").strip()
        if not raw:
            return None, "Не указано подразделение"
        if raw.casefold() in by_code:
            return by_code[raw.casefold()], ""
        parts = tuple(name_key(p) for p in org_import.split_path(raw))
        if parts in by_path:
            return by_path[parts], ""
        if len(parts) == 1 and len(by_name.get(parts[0], [])) == 1:
            return by_name[parts[0]][0], ""
        if len(parts) == 1 and len(by_name.get(parts[0], [])) > 1:
            return None, f"Несколько подразделений «{raw}» — укажите путь через «/» или код"
        return None, f"Подразделение «{raw}» не найдено — укажите путь через «/» или код"

    return resolve


def plan_import(db: Session, user: User, rows: list[dict]) -> tuple[dict, list[dict]]:
    """План загрузки без записи в базу и ячейки для записи (если ошибок нет). Пустая ячейка файла
    не стирает сохранённое значение."""
    st = reports.state(db)
    snap = st.snap
    resolve_unit = _unit_resolver(snap)
    eff = access.effective(user)
    rights: dict[int, EntryRight] = {}
    parsed: list[dict] = []
    for row in rows:
        errors: list[str] = []
        out = {"line": row["line"], "department": row["department"] or "", "department_id": None,
               "department_path": "", "indicator": row["indicator"] or "", "indicator_id": None,
               "indicator_key": None, "indicator_name": "", "period": row["period"] or "", "value": None,
               "target": None, "comment": row["comment"], "action": "error", "before": None, "after": None,
               "errors": errors}
        unit_id, unit_error = resolve_unit(row["department"] or "")
        if unit_error:
            errors.append(unit_error)
        else:
            out["department_id"], out["department_path"] = unit_id, snap.path_text(unit_id)
        ind = _find_indicator(st, row["indicator"] or "")
        if ind is None or not eff.allows(ind.data_class):
            errors.append(f"Показатель «{row['indicator'] or ''}» не найден — укажите ключ или название")
            ind = None
        else:
            out["indicator_id"], out["indicator_key"], out["indicator_name"] = ind.id, ind.key, ind.name
            if ind.id not in rights:
                rights[ind.id] = entry_right(db, user, ind)
            right = rights[ind.id]
            if not right.allowed:
                errors.append(right.reason)
            elif unit_id is not None and right.units is not None and unit_id not in right.units:
                errors.append(_out_of_scope(snap, ind, unit_id))
        period = None
        try:
            period = parse_import_period(row["period"] or "")
            out["period"] = reports.period_key(period)
        except ValueError:
            errors.append("Период — в формате ГГГГ-ММ")
        numbers: dict[str, float | None] = {}
        for column, title in (("value", "Значение"), ("target", "Цель")):
            text = row[column]
            if not text:
                numbers[column] = None
                continue
            try:
                numbers[column] = parse_number(text)
                out[column] = numbers[column]
            except ValueError:
                errors.append(f"«{title}» — не число: {text}")
        if not errors and numbers["value"] is None and numbers["target"] is None and not row["comment"]:
            errors.append("Нет значения, цели и комментария")
        parsed.append({"out": out, "indicator": ind, "unit": unit_id, "period": period, "numbers": numbers,
                       "comment": row["comment"]})
    # Повтор ячейки в файле — ошибка у второй строки
    first_line: dict[tuple, int] = {}
    for item in parsed:
        if item["indicator"] is None or item["unit"] is None or item["period"] is None:
            continue
        key = (item["indicator"].id, item["unit"], item["period"])
        if key in first_line:
            item["out"]["errors"].append(f"Повтор: это значение уже задано в строке {first_line[key]}")
        else:
            first_line[key] = item["out"]["line"]
    keys = list(first_line)
    existing: dict[tuple, IndicatorValue] = {}
    if keys:
        periods = {k[2] for k in keys}
        for r in db.scalars(select(IndicatorValue).where(IndicatorValue.period.in_(periods),
                                                         IndicatorValue.indicator_id.in_({k[0] for k in keys}))):
            existing[(r.indicator_id, r.department_id, r.period)] = r
    cells: list[dict] = []
    for item in parsed:
        out = item["out"]
        if out["errors"]:
            continue
        key = (item["indicator"].id, item["unit"], item["period"])
        row = existing.get(key)
        before = _cell_state(row)
        after = dict(before or {"value": None, "target": None, "comment": ""})
        for column in ("value", "target"):
            if item["numbers"][column] is not None:
                after[column] = item["numbers"][column]
        if item["comment"]:
            after["comment"] = item["comment"]
        out["before"], out["after"] = before, after
        out["action"] = "create" if row is None else ("unchanged" if before == after else "update")
        cells.append({"indicator": item["indicator"], "unit": item["unit"], "unit_name": snap.units[item["unit"]].name,
                      "period": item["period"], "row": row, **after})
    plan_rows = [item["out"] for item in parsed]
    actions = [r["action"] for r in plan_rows]
    errors = sum(1 for r in plan_rows if r["errors"])
    summary = {"rows": len(plan_rows), "create": actions.count("create"), "update": actions.count("update"),
               "unchanged": actions.count("unchanged"), "errors": errors}
    return {"summary": summary, "rows": plan_rows, "can_apply": errors == 0}, cells


def apply_import(db: Session, user: User, rows: list[dict], filename: str = "",
                 request: Request | None = None) -> tuple[dict, bool]:
    plan, cells = plan_import(db, user, rows)
    if not plan["can_apply"]:
        return {**plan, "applied": False}, False
    totals = {"created": 0, "updated": 0}
    by_period: dict[date, list[dict]] = defaultdict(list)
    for cell in cells:
        if cell["row"] is None or (cell["row"].value, cell["row"].target, cell["row"].comment or "") != \
                (cell["value"], cell["target"], cell["comment"]):
            by_period[cell["period"]].append(cell)
    for period, period_cells in sorted(by_period.items()):
        result = _write_cells(db, user, period, period_cells, "import")
        totals["created"] += result["created"]
        totals["updated"] += result["updated"]
    name = f"«{filename}»" if filename else "из файла"
    audit.record(db, user, entity_type="indicator_value", action="import",
                 summary=f"Загружены значения показателей {name}: новых {totals['created']}, "
                         f"обновлено {totals['updated']}",
                 after={"filename": filename, **plan["summary"],
                        "periods": [reports.period_key(p) for p in sorted(by_period)]}, request=request)
    return {**plan, "applied": True}, True


# ================================================================ заметки о статусе

def save_note(db: Session, actor: User, unit_id: int, body: NoteIn, request: Request | None = None) -> dict | None:
    snap = org.snapshot(db)
    if unit_id not in snap.units:
        raise NotFound("Подразделение не найдено")
    if not actor.can("reports.manage") and actor.id not in snap.heads.get(unit_id, []):
        raise Forbidden("Заметку о статусе оставляет руководитель подразделения", code="note_forbidden")
    period = reports.parse_period(body.period)
    comment = body.comment.strip()
    if body.status and not comment:
        raise ValidationFailed("Напишите, что делается: заметка «под контролем» — с комментарием",
                               fields={"comment": "Обязательное поле"})
    row = db.scalar(select(UnitStatusNote).where(UnitStatusNote.department_id == unit_id,
                                                 UnitStatusNote.period == period))
    unit_name = snap.units[unit_id].name
    label = reports.period_label(period).lower()
    before = {"status": row.status, "comment": row.comment} if row else None
    if body.status is None:
        if row is not None:
            db.delete(row)
            audit.record(db, actor, entity_type="unit_status_note", entity_id=unit_id, action="delete",
                         summary=f"Снята заметка о статусе «{unit_name}» за {label}", before=before, request=request)
        db.flush()
        return None
    if row is None:
        row = UnitStatusNote(department_id=unit_id, period=period)
        db.add(row)
    row.status, row.comment, row.author_id, row.created_at = body.status, comment, actor.id, utcnow()
    db.flush()
    audit.record(db, actor, entity_type="unit_status_note", entity_id=unit_id,
                 action="update" if before else "create",
                 summary=f"Заметка о статусе «{unit_name}» за {label}: {reports.NOTE_LABELS[row.status].lower()}",
                 before=before, after={"status": row.status, "comment": row.comment}, request=request)
    return note_out(row, actor)


def note_out(row: UnitStatusNote, author: User | None) -> dict:
    return {"department_id": row.department_id, "period": reports.period_key(row.period), "status": row.status,
            "status_label": reports.NOTE_LABELS.get(row.status, row.status), "comment": row.comment,
            "author": {"id": author.id, "full_name": author.full_name} if author else None,
            "created_at": row.created_at}


# ================================================================ настройка подразделений служб

def settings_out(db: Session) -> dict:
    snap = org.snapshot(db)
    row = db.get(AppSetting, REPORT_SETTING_KEY)
    configured = row.value if row is not None and isinstance(row.value, dict) else {}
    resolved = reports.resolve_service_units(db, snap)
    services = []
    for key, code in REPORT_SERVICE_UNIT_DEFAULTS.items():
        unit = resolved.get(key)
        value = configured.get(key)
        services.append({
            "key": key, "title": SERVICE_BY_KEY[key].title, "default_code": code,
            "configured": value if isinstance(value, int) and value in snap.units else None,
            "unit": {"id": unit, "name": snap.units[unit].name, "path": snap.path_text(unit)} if unit else None,
            "sources": [s.key for s in INDICATOR_SOURCES if s.service_key == key],
        })
    return {"report_service_units": {s["key"]: s["configured"] for s in services}, "services": services}


def save_settings(db: Session, actor: User, body: ServiceUnitsIn, request: Request | None = None) -> dict:
    snap = org.snapshot(db)
    for key, unit_id in body.report_service_units.items():
        if key not in REPORT_SERVICE_UNIT_DEFAULTS:
            raise ValidationFailed(f"У службы «{key}» нет вычисляемых показателей",
                                   fields={f"report_service_units.{key}": "Неизвестная служба"})
        if unit_id is not None and unit_id not in snap.units:
            raise ValidationFailed("Подразделение не найдено", fields={f"report_service_units.{key}": "Нет такого"})
    row = db.get(AppSetting, REPORT_SETTING_KEY)
    before = dict(row.value) if row is not None and isinstance(row.value, dict) else {}
    after = {**before, **body.report_service_units}
    after = {k: after.get(k) for k in REPORT_SERVICE_UNIT_DEFAULTS}
    b, a = audit.diff({k: before.get(k) for k in after}, after)
    if a:
        if row is None:
            db.add(AppSetting(key=REPORT_SETTING_KEY, value=after, updated_by_id=actor.id))
        else:
            row.value, row.updated_by_id = after, actor.id
        reports.mark_changed(db)
        audit.record(db, actor, entity_type="report_settings", entity_id=REPORT_SETTING_KEY, action="update",
                     summary="Изменены подразделения служб сквозных отчётов", before=b, after=a, request=request)
    db.flush()
    return settings_out(db)
