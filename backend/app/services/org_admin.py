"""Структура компании: чтение для оргсхемы и изменения с проверками (ADR-0007).

Чтение — из снимка структуры (app/services/org.py) без запросов по строкам; готовые ответы
оргсхемы и списка подразделений хранятся на самом снимке, то есть живут ровно до смены
ревизии структуры. Изменения проверяются по правилам todo-planner (ADR-0044/0046 там)
с исправлениями: признак основного руководителя не теряется, удаление записывается в журнал,
тип уровня проверяется при создании, имена соседей защищены ещё и уникальным индексом.

Функции изменения не фиксируют транзакцию: commit — один раз в обработчике запроса.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from collections import Counter
from typing import Any

from fastapi import Request
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import Conflict, NotFound, ValidationFailed
from ..models import AppSetting, AuditEntry, Department, DepartmentHead, User, name_key
from ..schemas.org import DepartmentCreateIn, DepartmentUpdateIn, HeadsIn, OrgSettingsIn, PersonOrgIn
from . import audit, org
from .registry import ORG_SETTINGS_DEFAULTS, ORG_VIEWS

SETTING_KEYS = {"unit_kinds": "org_unit_kinds", "max_depth": "org_max_depth", "default_view": "org_default_view"}
KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
DEPTH_LIMITS = (2, 30)
ORG_ENTITY_TYPES = ("department", "org_settings", "org_import")
ORG_USER_ACTIONS = ("org_update", "org_import")


# ================================================================ настройки структуры

def _valid_kinds(value: Any) -> list[dict] | None:
    if not isinstance(value, list) or not value:
        return None
    kinds, seen = [], set()
    for item in value:
        if not isinstance(item, dict) or not KIND_PATTERN.match(str(item.get("value") or "")):
            return None
        if item["value"] in seen:
            continue
        seen.add(item["value"])
        kinds.append({"value": item["value"], "label": str(item.get("label") or item["value"]),
                      "color": str(item.get("color") or "#64748b")})
    return kinds


def get_settings(db: Session) -> dict:
    """Настройки структуры: типы уровней, предел вложенности, вид оргсхемы по умолчанию."""
    rows = {row.key: row.value for row in db.scalars(select(AppSetting).where(
        AppSetting.key.in_(SETTING_KEYS.values())))}
    kinds = _valid_kinds(rows.get("org_unit_kinds")) or _valid_kinds(ORG_SETTINGS_DEFAULTS["org_unit_kinds"])
    try:
        depth = int(rows.get("org_max_depth"))
    except (TypeError, ValueError):
        depth = ORG_SETTINGS_DEFAULTS["org_max_depth"]
    depth = max(DEPTH_LIMITS[0], min(DEPTH_LIMITS[1], depth))
    view = rows.get("org_default_view")
    return {"unit_kinds": kinds, "max_depth": depth,
            "default_view": view if view in ORG_VIEWS else ORG_SETTINGS_DEFAULTS["org_default_view"]}


def kind_labels(kinds: list[dict]) -> dict[str, str]:
    return {k["value"]: k["label"] for k in kinds}


def settings_out(db: Session, snap: org.OrgSnapshot | None = None) -> dict:
    snap = snap or org.snapshot(db)
    return {**get_settings(db), "views": list(ORG_VIEWS), "current_depth": snap.depth(),
            "used_kinds": dict(Counter(u.kind for u in snap.units.values()))}


def save_setting(db: Session, key: str, value: Any, actor: User | None) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value, updated_by_id=actor.id if actor else None))
    else:
        row.value = value
        row.updated_by_id = actor.id if actor else None
    # Настройки входят в ответ оргсхемы: новая ревизия сбрасывает готовые ответы во всех процессах
    org.mark_changed(db)


def check_settings(db: Session, snap: org.OrgSnapshot, *, unit_kinds: list[dict] | None = None,
                   max_depth: int | None = None, depth_after: int | None = None) -> None:
    """Типы, которые используются, нельзя убрать; предел вложенности — не меньше текущей глубины."""
    current = get_settings(db)
    if unit_kinds is not None:
        values = [k["value"] for k in unit_kinds]
        duplicates = sorted({v for v in values if values.count(v) > 1})
        if duplicates:
            raise ValidationFailed(f"Тип уровня «{duplicates[0]}» указан дважды", fields={"unit_kinds": "Повтор"})
        used = Counter(u.kind for u in snap.units.values())
        labels = kind_labels(current["unit_kinds"])
        removed = [kind for kind in used if kind not in values]
        if removed:
            kind = sorted(removed)[0]
            raise Conflict(f"Тип «{labels.get(kind, kind)}» используется в {used[kind]} подразделениях — "
                           "сначала смените им тип, затем уберите тип из списка", code="org_kind_in_use",
                           fields={"unit_kinds": f"Используется: {kind}"})
    if max_depth is not None:
        depth = snap.depth() if depth_after is None else depth_after
        if max_depth < depth:
            raise Conflict(f"В структуре уже {depth} уровней вложенности — предел не может быть меньше. "
                           "Сначала перенесите или удалите глубокие уровни", code="org_depth_in_use",
                           fields={"max_depth": f"Не меньше {depth}"})


def update_settings(db: Session, actor: User, body: OrgSettingsIn, request: Request | None = None) -> dict:
    snap = org.build_snapshot(db)
    before = get_settings(db)
    fields = body.model_fields_set
    kinds = [k.model_dump() for k in body.unit_kinds] if "unit_kinds" in fields and body.unit_kinds else None
    depth = body.max_depth if "max_depth" in fields else None
    check_settings(db, snap, unit_kinds=kinds, max_depth=depth)
    after = dict(before)
    if kinds is not None:
        after["unit_kinds"] = kinds
    if depth is not None:
        after["max_depth"] = depth
    if "default_view" in fields and body.default_view:
        after["default_view"] = body.default_view
    b, a = audit.diff(before, after)
    for name in a:
        save_setting(db, SETTING_KEYS[name], after[name], actor)
    if a:
        audit.record(db, actor, entity_type="org_settings", entity_id="org", action="update",
                     summary="Изменены настройки структуры", before=b, after=a, request=request)
    db.flush()
    return after


# ================================================================ чтение: подразделения и оргсхема

def _memo(snap: org.OrgSnapshot, key: tuple, compute):
    """Готовый результат на снимке: снимок живёт до смены ревизии — ровно столько и результат."""
    store = snap.__dict__.setdefault("_serialized", {})
    if key not in store:
        store[key] = compute()
    return store[key]


def unit_stats(snap: org.OrgSnapshot) -> dict[int, tuple[int, int, int, int]]:
    """Подразделение → (штат без руководителей, сотрудников уровня, сотрудников ветки, подразделений в ветке).
    Каждый активный сотрудник считается один раз — в своём основном подразделении."""

    def compute():
        employees: Counter = Counter()
        staff: Counter = Counter()
        for person in snap.people.values():
            if not person.is_active:
                continue
            home = snap.home_unit(person.id)
            if home is None:
                continue
            employees[home] += 1
            if person.id not in snap.heads.get(home, []):
                staff[home] += 1
        branch_people: dict[int, int] = {}
        branch_units: dict[int, int] = {}
        for unit in reversed(snap.ordered_units()):   # дочерние раньше родителей
            kids = snap.children.get(unit, [])
            branch_people[unit] = employees[unit] + sum(branch_people.get(k, 0) for k in kids)
            branch_units[unit] = sum(1 + branch_units.get(k, 0) for k in kids)
        return {u: (staff[u], employees[u], branch_people[u], branch_units[u]) for u in snap.units}

    return _memo(snap, ("unit_stats",), compute)


def _visible(snap: org.OrgSnapshot, user_id: int, privileged: bool) -> bool:
    person = snap.people.get(user_id)
    return person is not None and (privileged or person.is_active)


def department_dict(snap: org.OrgSnapshot, unit_id: int, privileged: bool = True) -> dict:
    unit = snap.units[unit_id]
    stats = unit_stats(snap)[unit_id]
    heads = []
    for uid in snap.heads.get(unit_id, []):
        if not _visible(snap, uid, privileged):
            continue
        person = snap.people[uid]
        heads.append({"user_id": uid, "full_name": person.full_name, "position": person.position,
                      "is_primary": snap.primary.get(unit_id) == uid, "is_active": person.is_active})
    primary = snap.primary.get(unit_id)
    return {
        "id": unit.id, "name": unit.name, "code": unit.code,
        "parent_id": unit.parent_id if unit.parent_id in snap.units else None,
        "kind": unit.kind, "sort_order": unit.sort_order, "level": snap.level(unit_id) + 1,
        "path": snap.path_text(unit_id), "external_id": unit.external_id, "org_source": unit.org_source,
        "child_count": len(snap.children.get(unit_id, [])), "heads": heads,
        "primary_head_id": primary if primary is not None and _visible(snap, primary, privileged) else None,
        "employee_count": stats[1], "branch_employee_count": stats[2],
    }


def list_departments(snap: org.OrgSnapshot, privileged: bool) -> list[dict]:
    return _memo(snap, ("departments", privileged),
                 lambda: [department_dict(snap, u, privileged) for u in snap.ordered_units()])


def _tree_payload(db: Session, snap: org.OrgSnapshot, privileged: bool) -> dict:
    settings = get_settings(db)
    stats = unit_stats(snap)
    reports = snap._reports_index()
    branch = snap.branch_counts()
    units = []
    for unit_id in snap.ordered_units():
        unit = snap.units[unit_id]
        staff, employees, branch_people, branch_units = stats[unit_id]
        active_heads = snap.unit_heads(unit_id)
        units.append({
            "id": unit.id, "name": unit.name, "code": unit.code,
            "parent_id": unit.parent_id if unit.parent_id in snap.units else None,
            "kind": unit.kind, "sort_order": unit.sort_order, "level": snap.level(unit_id) + 1,
            "child_count": len(snap.children.get(unit_id, [])),
            "head_ids": [h for h in snap.heads.get(unit_id, []) if _visible(snap, h, privileged)],
            "primary_head_id": active_heads[0] if active_heads else None,
            "staff_count": staff, "employee_count": employees,
            "branch_employee_count": branch_people, "branch_unit_count": branch_units,
        })
    people = []
    for person in sorted(snap.people.values(), key=lambda p: (p.full_name.casefold(), p.id)):
        if not privileged and not person.is_active:
            continue
        manager, source = snap.direct_manager(person.id)
        item = {
            "id": person.id, "full_name": person.full_name, "position": person.position,
            "department_id": person.department_id if person.department_id in snap.units else None,
            "home_unit_id": snap.home_unit(person.id),
            "manager_id": person.manager_id if person.manager_id and _visible(snap, person.manager_id, privileged)
            else None,
            "direct_manager_id": manager, "manager_source": source, "reports_to_none": person.reports_to_none,
            "is_active": person.is_active, "head_of": list(snap.headed.get(person.id, [])),
            "report_count": len(reports.get(person.id, [])), "branch_count": branch.get(person.id, 0),
            "has_avatar": person.has_avatar,
        }
        if privileged:
            item.update(email=person.email, username=person.username, external_id=person.external_id,
                        org_source=person.org_source)
        people.append(item)
    return {"revision": snap.revision, "settings": settings, "units": units, "people": people}


def tree_body(db: Session, user: User) -> bytes:
    """Ответ GET /api/org/tree (JSON). Общая часть сериализуется один раз на ревизию и вид доступа;
    к ней дописывается только «me»."""
    snap = org.snapshot(db)
    privileged = user.can("org.manage")

    def compute() -> bytes:
        payload = _tree_payload(db, snap, privileged)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()[:-1]   # без «}»

    head = _memo(snap, ("tree", privileged), compute)
    me = {"id": user.id, "home_unit_id": snap.home_unit(user.id)}
    return head + b',"me":' + json.dumps(me, separators=(",", ":")).encode() + b"}"


def _person_ref(snap: org.OrgSnapshot, user_id: int | None) -> dict | None:
    person = snap.people.get(user_id) if user_id is not None else None
    if person is None:
        return None
    return {"id": person.id, "full_name": person.full_name, "position": person.position,
            "is_active": person.is_active}


def _unit_refs(snap: org.OrgSnapshot, unit_id: int | None) -> list[dict]:
    if unit_id not in snap.units:
        return []
    return [{"id": u, "name": snap.units[u].name, "kind": snap.units[u].kind} for u in snap.path(unit_id)]


def person_card(snap: org.OrgSnapshot, person_id: int, privileged: bool) -> dict:
    person = snap.people.get(person_id)
    if person is None or (not person.is_active and not privileged):
        raise NotFound("Сотрудник не найден")
    manager, source = snap.direct_manager(person_id)
    reports = snap._reports_index().get(person_id, [])
    reports = sorted(reports, key=lambda i: snap.people[i].full_name.casefold())
    home = snap.home_unit(person_id)
    explicit = person.manager_id if person.manager_id and _visible(snap, person.manager_id, privileged) else None
    card = {
        "id": person.id, "full_name": person.full_name, "position": person.position,
        "department_id": person.department_id if person.department_id in snap.units else None,
        "home_unit_id": home, "manager_id": explicit, "reports_to_none": person.reports_to_none,
        "is_active": person.is_active, "has_avatar": person.has_avatar,
        "manager": _person_ref(snap, manager), "manager_source": source,
        "structure_manager": _person_ref(snap, snap.structure_manager(person_id)),
        "chain": [_person_ref(snap, uid) for uid in snap.chain(person_id)],
        "direct_reports": [_person_ref(snap, uid) for uid in reports],
        "subordinates_count": len(snap.subordinates(person_id)),
        "department_path": _unit_refs(snap, person.department_id),
        "home_unit_path": _unit_refs(snap, home),
        "head_of": [{"id": u, "name": snap.units[u].name, "kind": snap.units[u].kind,
                     "primary": snap.primary.get(u) == person_id, "path": snap.path_text(u)}
                    for u in snap.headed.get(person_id, [])],
    }
    if privileged:
        card.update(email=person.email, username=person.username, external_id=person.external_id,
                    org_source=person.org_source)
    return card


# ================================================================ фото сотрудника

def image_type(raw: bytes) -> str | None:
    """Тип изображения по содержимому (не по заявленному в data URL)."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode_avatar(data_url: str | None) -> tuple[bytes, str] | None:
    """data:image/…;base64,… → (байты, тип). Только растровые изображения: SVG не отдаём."""
    if not data_url or not data_url.startswith("data:") or "," not in data_url:
        return None
    header, payload = data_url.split(",", 1)
    if ";base64" not in header:
        return None
    try:
        raw = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError):
        return None
    mime = image_type(raw)
    return (raw, mime) if mime else None


def avatar(db: Session, snap: org.OrgSnapshot, person_id: int, privileged: bool) -> tuple[bytes, str]:
    person = snap.people.get(person_id)
    if person is None or (not person.is_active and not privileged):
        raise NotFound("Сотрудник не найден")
    image = decode_avatar(db.scalar(select(User.avatar).where(User.id == person_id)))
    if image is None:
        raise NotFound("Фото не загружено")
    return image


# ================================================================ подразделения: изменения

def get_department(db: Session, dept_id: int) -> Department:
    dept = db.get(Department, dept_id)
    if dept is None:
        raise NotFound("Подразделение не найдено")
    return dept


def normalize_code(code: str | None) -> str | None:
    code = (code or "").strip().upper()
    return code or None


def check_kind(kind: str, kinds: list[dict]) -> None:
    labels = kind_labels(kinds)
    if kind not in labels:
        raise ValidationFailed(f"Неизвестный тип уровня «{kind}»: выберите один из настроенных "
                               f"({', '.join(labels.values())})", fields={"kind": "Неизвестный тип уровня"})


def default_kind(kinds: list[dict]) -> str:
    values = [k["value"] for k in kinds]
    return "department" if "department" in values else values[0]


def check_parent(snap: org.OrgSnapshot, dept_id: int | None, parent_id: int | None) -> None:
    if parent_id is None:
        return
    if parent_id not in snap.units:
        raise ValidationFailed("Родительское подразделение не найдено", fields={"parent_id": "Не найдено"})
    if dept_id is not None and (parent_id == dept_id or parent_id in snap.descendants([dept_id])):
        raise Conflict("Подразделение нельзя вложить в само себя или в своё вложенное подразделение: "
                       "выберите уровень вне его ветки", code="org_cycle", fields={"parent_id": "Цикл"})


def check_depth(snap: org.OrgSnapshot, dept_id: int | None, parent_id: int | None, max_depth: int) -> None:
    """Уровней от верхнего до самого глубокого вложенного после создания или переноса — не больше предела."""
    above = len(snap.path(parent_id)) if parent_id is not None else 0
    below = snap.height(dept_id) + 1 if dept_id is not None and dept_id in snap.units else 1
    if above + below > max_depth:
        raise Conflict(f"Структура ограничена {max_depth} уровнями вложенности, а получится {above + below}. "
                       "Выберите уровень выше или увеличьте предел в настройках структуры",
                       code="org_too_deep", fields={"parent_id": "Слишком глубоко"})


def _name_conflict(name: str, parent_path: str) -> Conflict:
    where = f"В подразделении «{parent_path}» уже есть" if parent_path else "На верхнем уровне уже есть"
    return Conflict(f"{where} подразделение «{name}» — выберите другое название",
                    code="department_name_taken", fields={"name": "Название уже используется"})


def check_sibling_name(db: Session, snap: org.OrgSnapshot, name: str, parent_id: int | None,
                       exclude_id: int | None = None) -> None:
    stmt = select(Department.id).where(Department.name_key == name_key(name))
    stmt = stmt.where(Department.parent_id.is_(None) if parent_id is None else Department.parent_id == parent_id)
    if exclude_id is not None:
        stmt = stmt.where(Department.id != exclude_id)
    if db.scalar(stmt.limit(1)) is not None:
        raise _name_conflict(name, snap.path_text(parent_id))


def check_code(db: Session, snap: org.OrgSnapshot, code: str | None, exclude_id: int | None = None) -> None:
    if not code:
        return
    stmt = select(Department.id).where(Department.code == code)
    if exclude_id is not None:
        stmt = stmt.where(Department.id != exclude_id)
    other = db.scalar(stmt.limit(1))
    if other is not None:
        raise Conflict(f"Код «{code}» уже у подразделения «{snap.path_text(other)}»",
                       code="department_code_taken", fields={"code": "Код уже используется"})


def flush_department(db: Session, snap: org.OrgSnapshot, name: str, parent_id: int | None,
                     code: str | None) -> None:
    """Запись с защитой от гонки: параллельный запрос мог занять имя или код после проверки —
    уникальный индекс это поймает, и ответ будет тем же понятным 409."""
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        message = str(exc.orig).lower()
        # SQLite: «UNIQUE constraint failed: departments.code»; PostgreSQL: имя индекса uq_departments_code
        if code and ("departments.code" in message or "uq_departments_code" in message):
            raise Conflict(f"Код «{code}» уже используется", code="department_code_taken",
                           fields={"code": "Код уже используется"}) from None
        raise _name_conflict(name, snap.path_text(parent_id)) from None


def department_state(dept: Department, snap: org.OrgSnapshot) -> dict:
    return {"name": dept.name, "code": dept.code, "parent": snap.path_text(dept.parent_id) or None,
            "kind": dept.kind, "sort_order": dept.sort_order}


def check_reporting_cycles(db: Session, before: org.OrgSnapshot) -> org.OrgSnapshot:
    """После изменения (уже записанного в транзакцию) не должно появиться новых циклов подчинения.
    Возвращает снимок структуры после изменения."""
    db.flush()
    after = org.build_snapshot(db, before.revision)
    new = after.cycles() - before.cycles()
    if new:
        names = ", ".join(sorted(after.people[u].full_name for u in new if u in after.people))
        db.rollback()
        raise Conflict(f"Получится цикл подчинения: {names}. Руководитель не может подчиняться своему "
                       "сотруднику — проверьте руководителей подразделений и явных руководителей",
                       code="org_reporting_cycle")
    return after


def create_department(db: Session, actor: User, body: DepartmentCreateIn, request: Request | None = None) -> int:
    snap = org.build_snapshot(db)
    settings = get_settings(db)
    kind = body.kind or default_kind(settings["unit_kinds"])
    check_kind(kind, settings["unit_kinds"])
    check_parent(snap, None, body.parent_id)
    check_depth(snap, None, body.parent_id, settings["max_depth"])
    check_sibling_name(db, snap, body.name, body.parent_id)
    code = normalize_code(body.code)
    check_code(db, snap, code)
    dept = Department(name=body.name, code=code, parent_id=body.parent_id, kind=kind, sort_order=body.sort_order,
                      org_source="manual")
    db.add(dept)
    flush_department(db, snap, body.name, body.parent_id, code)
    audit.record(db, actor, entity_type="department", entity_id=dept.id, action="create",
                 summary=f"Создано подразделение {snap.path_text(body.parent_id) + ' / ' if body.parent_id else ''}"
                         f"{dept.name}", after=department_state(dept, snap), request=request)
    db.flush()
    return dept.id


def update_department(db: Session, actor: User, dept_id: int, body: DepartmentUpdateIn,
                      request: Request | None = None) -> None:
    dept = get_department(db, dept_id)
    snap = org.build_snapshot(db)
    settings = get_settings(db)
    fields = body.model_fields_set
    before = department_state(dept, snap)
    parent_id = body.parent_id if "parent_id" in fields else dept.parent_id
    name = body.name if "name" in fields and body.name is not None else dept.name
    if "kind" in fields and body.kind is not None and body.kind != dept.kind:
        check_kind(body.kind, settings["unit_kinds"])
    moved = parent_id != dept.parent_id
    if moved:
        check_parent(snap, dept.id, parent_id)
        check_depth(snap, dept.id, parent_id, settings["max_depth"])
    if moved or name_key(name) != dept.name_key:
        check_sibling_name(db, snap, name, parent_id, exclude_id=dept.id)
    code = normalize_code(body.code) if "code" in fields else dept.code
    if code != dept.code:
        check_code(db, snap, code, exclude_id=dept.id)
    dept.name, dept.parent_id, dept.code = name, parent_id, code
    if "kind" in fields and body.kind is not None:
        dept.kind = body.kind
    if "sort_order" in fields and body.sort_order is not None:
        dept.sort_order = body.sort_order
    flush_department(db, snap, name, parent_id, code)
    if moved:
        check_reporting_cycles(db, snap)
    after = {"name": dept.name, "code": dept.code, "parent": snap.path_text(parent_id) or None, "kind": dept.kind,
             "sort_order": dept.sort_order}
    b, a = audit.diff(before, after)
    if a:
        audit.record(db, actor, entity_type="department", entity_id=dept.id, action="update",
                     summary=f"Изменено подразделение {dept.name}", before=b, after=a, request=request)
    db.flush()


def delete_department(db: Session, actor: User, dept_id: int, request: Request | None = None) -> str:
    dept = get_department(db, dept_id)
    snap = org.build_snapshot(db)
    children = snap.children.get(dept.id, [])
    if children:
        names = ", ".join(f"«{snap.units[c].name}»" for c in children[:5]) + (" и др." if len(children) > 5 else "")
        raise Conflict(f"У подразделения есть вложенные ({len(children)}): {names}. Перенесите их в другое "
                       "подразделение или удалите, затем повторите удаление", code="department_has_children")
    people = [p for p in snap.people.values() if p.department_id == dept.id]
    before = {**department_state(dept, snap), "path": snap.path_text(dept.id),
              "heads": [snap.people[h].full_name for h in snap.heads.get(dept.id, []) if h in snap.people],
              "employees": sorted(p.full_name for p in people)}
    # Сотрудники остаются без подразделения (как ON DELETE SET NULL, но и в объектах этой сессии)
    db.execute(update(User).where(User.department_id == dept.id).values(department_id=None),
               execution_options={"synchronize_session": "fetch"})
    org.mark_changed(db)
    db.delete(dept)
    db.flush()
    check_reporting_cycles(db, snap)
    audit.record(db, actor, entity_type="department", entity_id=dept_id, action="delete",
                 summary=f"Удалено подразделение {before['path']}"
                         + (f"; без подразделения остались: {len(people)}" if people else ""),
                 before=before, request=request)
    db.flush()
    return before["name"]


def _heads_state(db: Session, dept_id: int) -> dict:
    rows = db.execute(select(User.full_name, DepartmentHead.is_primary).join(User, User.id == DepartmentHead.user_id)
                      .where(DepartmentHead.department_id == dept_id)).all()
    return {"heads": sorted(r.full_name for r in rows), "primary": next((r.full_name for r in rows if r.is_primary),
                                                                        None)}


def replace_heads(db: Session, dept_id: int, user_ids: list[int], primary_id: int | None) -> None:
    """Состав руководителей целиком; основной не больше одного (порядок записи — без нарушения индекса)."""
    links = {h.user_id: h for h in db.scalars(select(DepartmentHead).where(DepartmentHead.department_id == dept_id))}
    for uid, link in links.items():
        if uid not in user_ids:
            db.delete(link)
        elif link.is_primary and uid != primary_id:
            link.is_primary = False
    db.flush()
    for uid in user_ids:
        if uid not in links:
            links[uid] = DepartmentHead(department_id=dept_id, user_id=uid, is_primary=False)
            db.add(links[uid])
    db.flush()
    if primary_id is not None and not links[primary_id].is_primary:
        links[primary_id].is_primary = True
        db.flush()


def choose_primary(user_ids: list[int], requested: int | None, current: int | None) -> int | None:
    """Основной: указанный; иначе прежний, если остался; единственный руководитель — основной сам."""
    if requested is not None:
        return requested
    if current in user_ids:
        return current
    return user_ids[0] if len(user_ids) == 1 else None


def set_heads(db: Session, actor: User, dept_id: int, body: HeadsIn, request: Request | None = None) -> None:
    dept = get_department(db, dept_id)
    snap = org.build_snapshot(db)
    ids = list(dict.fromkeys(body.user_ids))
    if body.primary_id is not None and body.primary_id not in ids:
        raise ValidationFailed("Основной руководитель должен быть среди руководителей",
                               fields={"primary_id": "Не среди руководителей"})
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    missing = [i for i in ids if i not in users]
    if missing:
        raise ValidationFailed(f"Сотрудник не найден: {', '.join(map(str, missing))}",
                               fields={"user_ids": "Сотрудник не найден"})
    current = set(snap.heads.get(dept.id, []))
    inactive = [users[i].full_name for i in ids if not users[i].is_active and i not in current]
    if inactive:
        raise ValidationFailed(f"Руководителем можно назначить только активного сотрудника: {', '.join(inactive)}",
                               fields={"user_ids": "Сотрудник отключён"})
    primary = choose_primary(ids, body.primary_id, snap.primary.get(dept.id))
    before = _heads_state(db, dept.id)
    replace_heads(db, dept.id, ids, primary)
    check_reporting_cycles(db, snap)
    after = _heads_state(db, dept.id)
    b, a = audit.diff(before, after)
    if a:
        audit.record(db, actor, entity_type="department", entity_id=dept.id, action="heads",
                     summary=f"Руководители подразделения {dept.name}: "
                             + (", ".join(after["heads"]) if after["heads"] else "не назначены"),
                     before=b, after=a, request=request)
    db.flush()


# ================================================================ сотрудник: поля подчинения

def _person_state(user: User, snap: org.OrgSnapshot) -> dict:
    manager = snap.people.get(user.manager_id) if user.manager_id else None
    return {
        "department": snap.path_text(user.department_id) or None,
        "manager": manager.full_name if manager else None,
        "reports_to_none": bool(user.reports_to_none), "position": user.position,
        "head_of": sorted(snap.path_text(u) + (" (основной)" if snap.primary.get(u) == user.id else "")
                          for u in snap.headed.get(user.id, [])),
    }


def check_manager(db: Session, snap: org.OrgSnapshot, user: User, manager_id: int) -> None:
    if manager_id == user.id:
        raise ValidationFailed("Сотрудник не может быть руководителем самому себе",
                               fields={"manager_id": "Сам себе руководитель"})
    manager = db.get(User, manager_id)
    if manager is None:
        raise ValidationFailed("Руководитель не найден", fields={"manager_id": "Не найден"})
    if not manager.is_active:
        raise ValidationFailed(f"Руководителем может быть только активный сотрудник: {manager.full_name} отключён",
                               fields={"manager_id": "Сотрудник отключён"})
    if manager_id in snap.subordinates(user.id):
        raise Conflict(f"{manager.full_name} подчиняется сотруднику {user.full_name}: получится цикл подчинения. "
                       "Сначала измените руководителя у подчинённого", code="org_reporting_cycle",
                       fields={"manager_id": "Цикл подчинения"})


def replace_head_links(db: Session, snap: org.OrgSnapshot, user: User, items: list) -> None:
    """Руководимые подразделения сотрудника целиком (с отметкой основного в каждом)."""
    wanted: dict[int, bool] = {}
    for item in items:
        wanted[item.department_id] = wanted.get(item.department_id, False) or item.primary
    missing = [d for d in wanted if d not in snap.units]
    if missing:
        raise ValidationFailed(f"Подразделение не найдено: {', '.join(map(str, missing))}",
                               fields={"head_of": "Подразделение не найдено"})
    for unit_id in set(snap.headed.get(user.id, [])) | set(wanted):
        heads = [h for h in snap.heads.get(unit_id, []) if h != user.id]
        current_primary = snap.primary.get(unit_id)
        if unit_id in wanted:
            heads.append(user.id)
            if wanted[unit_id]:
                primary = user.id
            elif current_primary == user.id:
                primary = None
            else:
                primary = current_primary
        else:
            primary = current_primary if current_primary != user.id else None
        if primary is None and len(heads) == 1:
            primary = heads[0]
        replace_heads(db, unit_id, heads, primary)


def update_person(db: Session, actor: User, person_id: int, body: PersonOrgIn, request: Request | None = None) -> None:
    user = db.get(User, person_id)
    if user is None:
        raise NotFound("Сотрудник не найден")
    snap = org.build_snapshot(db)
    fields = body.model_fields_set
    before = _person_state(user, snap)
    if "manager_id" in fields and body.manager_id is not None and body.reports_to_none:
        raise ValidationFailed("Выберите одно: явный руководитель или «первое лицо»",
                               fields={"reports_to_none": "Взаимоисключающие поля"})
    if "department_id" in fields:
        if body.department_id is not None and body.department_id not in snap.units:
            raise ValidationFailed("Подразделение не найдено", fields={"department_id": "Не найдено"})
        user.department_id = body.department_id
    if "manager_id" in fields:
        if body.manager_id is not None:
            check_manager(db, snap, user, body.manager_id)
            user.reports_to_none = False      # явный руководитель снимает «первое лицо»
        user.manager_id = body.manager_id
    if "reports_to_none" in fields and body.reports_to_none is not None:
        user.reports_to_none = body.reports_to_none
        if body.reports_to_none:
            user.manager_id = None            # «первое лицо» никому не подчиняется
    if "position" in fields:
        user.position = (body.position or "").strip() or None
    if "head_of" in fields and body.head_of is not None:
        replace_head_links(db, snap, user, body.head_of)
    after_snap = check_reporting_cycles(db, snap)
    b, a = audit.diff(before, _person_state(user, after_snap))
    if a:
        audit.record(db, actor, entity_type="user", entity_id=user.id, action="org_update",
                     summary=f"Изменено подчинение: {user.full_name}", before=b, after=a, request=request)
    db.flush()


# ================================================================ история

def history(db: Session, entity_type: str | None, entity_id: str | None, limit: int) -> list[AuditEntry]:
    """Журнал изменений структуры: подразделения, настройки, загрузки и подчинение сотрудников
    (прочие правки учётных записей — в общем журнале администратора)."""
    org_user = and_(AuditEntry.entity_type == "user", AuditEntry.action.in_(ORG_USER_ACTIONS))
    if entity_type == "user":
        stmt = select(AuditEntry).where(org_user)
    elif entity_type:
        stmt = select(AuditEntry).where(AuditEntry.entity_type == entity_type)
    else:
        stmt = select(AuditEntry).where(or_(AuditEntry.entity_type.in_(ORG_ENTITY_TYPES), org_user))
    if entity_id:
        stmt = stmt.where(AuditEntry.entity_id == str(entity_id))
    return list(db.scalars(stmt.order_by(AuditEntry.occurred_at.desc(), AuditEntry.id.desc()).limit(limit)))
