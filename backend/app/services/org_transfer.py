"""Перенос структуры компании между установками: файл dashboards.org-structure версии 1 (ADR-0007).

В файле — настройки структуры (типы уровней, предел вложенности, вид оргсхемы) и подразделения
в порядке «родители раньше детей»: путь, тип, порядок, код, внешний ключ, руководители по email.

Загрузка в два шага: план без записи в базу, затем то же самое одной транзакцией. Подразделения
сопоставляются по пути от верхнего уровня (названия без учёта регистра и лишних пробелов);
подразделения, которых нет в файле, не удаляются; руководители только добавляются (кого нет
в системе — назначит загрузка сотрудников). Типы уровней из файла объединяются с типами,
которые уже используются в структуре.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import __version__
from ..core.errors import ValidationFailed
from ..models import Department, DepartmentHead, User, name_key
from . import audit, org, org_admin
from .registry import ORG_VIEWS

FORMAT = "dashboards.org-structure"
VERSION = 1
MAX_DEPARTMENTS = 5000
SETTING_LABELS = {
    "org_unit_kinds": "Типы уровней",
    "org_max_depth": "Предел вложенности",
    "org_default_view": "Вид оргсхемы по умолчанию",
}
VIEW_LABELS = {"chart": "Оргсхема", "people": "Люди", "tree": "Дерево", "table": "Таблица"}


class StructureFormatError(ValidationFailed):
    """Файл не похож на выгрузку структуры или повреждён."""


# ---------------------------------------------------------------- выгрузка

def export_structure(db: Session) -> dict:
    snap = org.build_snapshot(db)
    settings = org_admin.get_settings(db)
    emails = {p.id: p.email for p in snap.people.values()}
    departments = []
    for unit_id in snap.ordered_units():
        unit = snap.units[unit_id]
        heads = [{"email": (emails.get(uid) or "").lower() or None, "name": snap.people[uid].full_name,
                  "primary": snap.primary.get(unit_id) == uid}
                 for uid in snap.heads.get(unit_id, []) if uid in snap.people]
        departments.append({
            "key": str(unit.id), "name": unit.name,
            "parent": str(unit.parent_id) if unit.parent_id in snap.units else None,
            "path": snap.path_text(unit_id), "kind": unit.kind, "sort_order": unit.sort_order,
            "code": unit.code, "external_id": unit.external_id,
            "heads": sorted(heads, key=lambda h: (not h["primary"], h["email"] or "", h["name"])),
        })
    return {
        "format": FORMAT, "version": VERSION,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "app": __version__,
        "settings": {"org_unit_kinds": settings["unit_kinds"], "org_max_depth": settings["max_depth"],
                     "org_default_view": settings["default_view"]},
        "departments": departments,
    }


def export_filename() -> str:
    return f"dashboards-structure-{datetime.now(UTC).date().isoformat()}.json"


# ---------------------------------------------------------------- разбор файла

@dataclass
class Item:
    key: str
    name: str
    parent: str | None
    kind: str
    sort_order: int
    code: str | None
    external_id: str | None
    heads: list[dict]


def parse_bundle(bundle: Any) -> tuple[dict, list[Item]]:
    """Проверка формата → (настройки, подразделения в порядке «родители раньше детей»)."""
    if isinstance(bundle, (str, bytes)):
        try:
            bundle = json.loads(bundle)
        except ValueError as exc:
            raise StructureFormatError("Файл не является JSON") from exc
    if not isinstance(bundle, dict) or bundle.get("format") != FORMAT:
        raise StructureFormatError(f"Это не файл структуры «Дашбордов компании» (нужен format: {FORMAT})")
    if bundle.get("version") != VERSION:
        raise StructureFormatError(f"Версия файла {bundle.get('version')} не поддерживается — нужна {VERSION}")
    raw_items = bundle.get("departments")
    if not isinstance(raw_items, list):
        raise StructureFormatError("В файле нет списка подразделений")
    if len(raw_items) > MAX_DEPARTMENTS:
        raise StructureFormatError(f"Не больше {MAX_DEPARTMENTS} подразделений в одном файле")
    items: list[Item] = []
    keys: set[str] = set()
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise StructureFormatError(f"Подразделение №{index}: ожидается объект")
        key = str(raw.get("key") or "").strip()
        name = " ".join(str(raw.get("name") or "").split())[:200]
        if not key or not name:
            raise StructureFormatError(f"Подразделение №{index}: нужны key и name")
        if key in keys:
            raise StructureFormatError(f"Подразделение №{index}: key «{key}» повторяется")
        parent = raw.get("parent")
        parent = None if parent in (None, "") else str(parent)
        if parent is not None and parent not in keys:
            raise StructureFormatError(f"Подразделение «{name}»: родитель «{parent}» должен идти в файле раньше")
        heads = []
        for head in raw.get("heads") or []:
            if isinstance(head, dict):
                heads.append({"email": str(head.get("email") or "").strip().lower(),
                              "name": str(head.get("name") or "").strip(), "primary": bool(head.get("primary"))})
        try:
            sort_order = int(raw.get("sort_order") or 0)
        except (TypeError, ValueError):
            sort_order = 0
        keys.add(key)
        items.append(Item(key, name, parent, str(raw.get("kind") or "department"), sort_order,
                          org_admin.normalize_code(str(raw["code"])) if raw.get("code") else None,
                          str(raw["external_id"])[:200] if raw.get("external_id") else None, heads))
    settings = bundle.get("settings") if isinstance(bundle.get("settings"), dict) else {}
    return {k: settings[k] for k in SETTING_LABELS if k in settings}, items


def _display(key: str, value: Any) -> str:
    if key == "org_unit_kinds":
        return ", ".join(f"{k.get('label')} ({k.get('value')})" for k in value or [] if isinstance(k, dict))
    if key == "org_default_view":
        return VIEW_LABELS.get(value, str(value))
    return str(value)


# ---------------------------------------------------------------- план

@dataclass
class StructurePlan:
    settings: list = field(default_factory=list)
    departments: list = field(default_factory=list)
    heads: list = field(default_factory=list)
    missing_in_file: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    settings_patch: dict = field(default_factory=dict)
    items: list = field(default_factory=list)
    targets: dict = field(default_factory=dict)     # ключ файла → id существующего или None (создать)
    paths: dict = field(default_factory=dict)       # ключ файла → путь « / »

    def as_dict(self) -> dict:
        actions = [d["action"] for d in self.departments]
        heads = [h["action"] for h in self.heads]
        return {
            "summary": {
                "departments": len(self.departments), "create": actions.count("create"),
                "update": actions.count("update"), "unchanged": actions.count("unchanged"),
                "settings": len(self.settings), "add_heads": heads.count("add"),
                "existing_heads": heads.count("exists"), "pending_heads": heads.count("pending"),
                "missing_in_file": len(self.missing_in_file), "errors": len(self.errors),
            },
            "settings": self.settings, "departments": self.departments, "heads": self.heads,
            "missing_in_file": self.missing_in_file, "errors": self.errors, "can_apply": not self.errors,
        }


def _plan_settings(db: Session, plan: StructurePlan, snap: org.OrgSnapshot, incoming: dict) -> tuple[list, int]:
    current = org_admin.get_settings(db)
    kinds, max_depth = current["unit_kinds"], current["max_depth"]
    patch: dict = {}
    if "org_unit_kinds" in incoming:
        parsed = org_admin._valid_kinds(incoming["org_unit_kinds"])
        if parsed is None or len(parsed) > 30:
            plan.errors.append("Типы уровней в файле: нужен список из 1–30 типов с ключом латиницей "
                               "(a–z, цифры, «_», «-»), названием и цветом")
        else:
            values = {k["value"] for k in parsed}
            used = {u.kind for u in snap.units.values()}
            known = {k["value"]: k for k in kinds}
            merged = parsed + [known.get(kind, {"value": kind, "label": kind, "color": "#64748b"})
                               for kind in sorted(used - values)]
            patch["org_unit_kinds"] = merged
            kinds = merged
    if "org_max_depth" in incoming:
        try:
            value = int(incoming["org_max_depth"])
        except (TypeError, ValueError):
            value = None
        if value is None or not org_admin.DEPTH_LIMITS[0] <= value <= org_admin.DEPTH_LIMITS[1]:
            plan.errors.append("Предел вложенности в файле: целое число от 2 до 30")
        else:
            patch["org_max_depth"] = max_depth = value
    if "org_default_view" in incoming:
        if incoming["org_default_view"] in ORG_VIEWS:
            patch["org_default_view"] = incoming["org_default_view"]
        else:
            plan.errors.append(f"Вид оргсхемы в файле: одно из {', '.join(ORG_VIEWS)}")
    names = {"org_unit_kinds": "unit_kinds", "org_max_depth": "max_depth", "org_default_view": "default_view"}
    for key, value in patch.items():
        old = current[names[key]]
        if _display(key, old) != _display(key, value) or (key == "org_unit_kinds" and old != value):
            plan.settings.append({"key": key, "label": SETTING_LABELS[key], "current": _display(key, old),
                                  "incoming": _display(key, value)})
    plan.settings_patch = {k: v for k, v in patch.items()
                           if any(s["key"] == k for s in plan.settings)}
    return kinds, max_depth


def plan_structure(db: Session, bundle: Any, *, apply_settings: bool = True) -> StructurePlan:
    plan = StructurePlan()
    incoming, items = parse_bundle(bundle)
    plan.items = items
    snap = org.build_snapshot(db)
    current = org_admin.get_settings(db)
    kinds, max_depth = current["unit_kinds"], current["max_depth"]
    if apply_settings and incoming:
        kinds, max_depth = _plan_settings(db, plan, snap, incoming)
    kind_values = {k["value"] for k in kinds}

    by_path = {(u.parent_id if u.parent_id in snap.units else None, name_key(u.name)): u.id
               for u in snap.units.values()}
    codes = {u.code: u.id for u in snap.units.values() if u.code}
    paths: dict[str, list[str]] = {}
    depth_of: dict[str, int] = {}
    seen_paths: dict[tuple, str] = {}
    file_codes: dict[str, str] = {}
    matched: set[int] = set()
    future = snap.copy()
    for item in items:
        parent_target = plan.targets.get(item.parent) if item.parent else None
        path = [*paths.get(item.parent, []), item.name]
        paths[item.key] = path
        depth_of[item.key] = depth_of.get(item.parent, 0) + 1
        label = plan.paths[item.key] = " / ".join(path)
        path_key = (item.parent, name_key(item.name))
        if path_key in seen_paths:
            plan.errors.append(f"{label}: подразделение повторяется в файле (ключи «{seen_paths[path_key]}» "
                               f"и «{item.key}»)")
        seen_paths.setdefault(path_key, item.key)
        if item.kind not in kind_values:
            plan.errors.append(f"{label}: тип «{item.kind}» не задан в настройках структуры")
        target = by_path.get((parent_target, name_key(item.name))) if item.parent is None or parent_target else None
        if item.code:
            if item.code in file_codes:
                plan.errors.append(f"{label}: код «{item.code}» повторяется в файле ({file_codes[item.code]})")
            file_codes.setdefault(item.code, label)
            holder = codes.get(item.code)
            if holder is not None and holder != target:
                plan.errors.append(f"{label}: код «{item.code}» уже у подразделения «{snap.path_text(holder)}»")
        plan.targets[item.key] = target
        if target is None:
            plan.departments.append({"key": item.key, "path": label, "action": "create", "changes": []})
            future.add_unit(org.Unit(f"new:{item.key}", item.name, plan.targets.get(item.parent) or
                                     (f"new:{item.parent}" if item.parent else None), item.kind, item.sort_order,
                                     item.code, item.external_id))
            continue
        matched.add(target)
        unit = snap.units[target]
        changes = []
        if unit.kind != item.kind:
            changes.append({"field": "kind", "old": unit.kind, "new": item.kind})
        if unit.sort_order != item.sort_order:
            changes.append({"field": "sort_order", "old": unit.sort_order, "new": item.sort_order})
        if item.code and unit.code != item.code:
            changes.append({"field": "code", "old": unit.code, "new": item.code})
        plan.departments.append({"key": item.key, "path": label, "action": "update" if changes else "unchanged",
                                 "changes": changes})
    depth = max(max(depth_of.values(), default=0), snap.depth())
    if depth > max_depth:
        plan.errors.append(f"Вложенность после загрузки — {depth} уровней, а предел — {max_depth}: увеличьте "
                           "«Предел вложенности» в файле или в настройках структуры")
    plan.missing_in_file = sorted(snap.path_text(u) for u in snap.units if u not in matched)

    # Руководители — по email; кого нет в системе, назначит загрузка сотрудников
    emails = {h["email"] for item in items for h in item.heads if h["email"]}
    users = {}
    if emails:
        for user in db.scalars(select(User).where(func.lower(User.email).in_(emails))):
            users[(user.email or "").lower()] = user
    for item in items:
        target = plan.targets.get(item.key)
        unit_key = target if target is not None else f"new:{item.key}"
        added = []
        for head in item.heads:
            user = users.get(head["email"]) if head["email"] else None
            if user is None:
                action = "pending"
            elif target is not None and user.id in snap.heads.get(target, []):
                action = "exists"
            else:
                action = "add"
                added.append((user.id, head["primary"]))
            plan.heads.append({"department_key": item.key, "path": " / ".join(paths[item.key]),
                               "email": head["email"], "name": user.full_name if user else head["name"],
                               "primary": head["primary"], "action": action,
                               "user_id": user.id if user else None})
        if added:
            ids = list(future.heads.get(unit_key, [])) + [uid for uid, _ in added]
            primary = future.primary.get(unit_key) or next((uid for uid, p in added if p), None)
            future.set_heads(unit_key, ids, org_admin.choose_primary(ids, primary, None))
    cyclic = future.cycles() - snap.cycles()
    if cyclic:
        names = ", ".join(sorted(future.people[u].full_name for u in cyclic if u in future.people))
        plan.errors.append(f"Получится цикл подчинения: {names} — проверьте руководителей в файле")
    return plan


# ---------------------------------------------------------------- применение

def apply_structure(db: Session, actor: User | None, bundle: Any, *, apply_settings: bool = True,
                    request: Request | None = None) -> tuple[dict, bool]:
    """(план, применён ли). При ошибках ничего не записывается."""
    plan = plan_structure(db, bundle, apply_settings=apply_settings)
    result = plan.as_dict()
    if plan.errors:
        return result, False
    ids: dict[str, int] = {}
    for item in plan.items:
        target = plan.targets.get(item.key)
        parent_id = ids.get(item.parent) if item.parent else None
        if target is None:
            dept = Department(name=item.name, parent_id=parent_id, kind=item.kind, sort_order=item.sort_order,
                              code=item.code, external_id=item.external_id, org_source="import")
            db.add(dept)
            db.flush()
            ids[item.key] = dept.id
            audit.record(db, actor, entity_type="department", entity_id=dept.id, action="create",
                         summary=f"Создано подразделение {plan.paths[item.key]} (загрузка структуры)",
                         after={"name": dept.name, "kind": dept.kind, "code": dept.code}, request=request)
            continue
        ids[item.key] = target
        dept = db.get(Department, target)
        before = {"kind": dept.kind, "sort_order": dept.sort_order, "code": dept.code}
        dept.kind, dept.sort_order = item.kind, item.sort_order
        if item.code:
            dept.code = item.code
        if item.external_id and not dept.external_id:
            dept.external_id = item.external_id
        b, a = audit.diff(before, {"kind": dept.kind, "sort_order": dept.sort_order, "code": dept.code})
        if a:
            audit.record(db, actor, entity_type="department", entity_id=dept.id, action="update",
                         summary=f"Изменено подразделение {dept.name} (загрузка структуры)", before=b, after=a,
                         request=request)
    db.flush()
    by_department: dict[int, list[tuple[int, bool, str]]] = {}
    for head in plan.heads:
        if head["action"] == "add":
            by_department.setdefault(ids[head["department_key"]], []).append(
                (head["user_id"], head["primary"], head["name"]))
    for dept_id, added in by_department.items():
        links = list(db.scalars(select(DepartmentHead).where(DepartmentHead.department_id == dept_id)))
        current_primary = next((link.user_id for link in links if link.is_primary), None)
        user_ids = [link.user_id for link in links] + [uid for uid, _, _ in added if uid not in
                                                       {link.user_id for link in links}]
        wanted = current_primary or next((uid for uid, primary, _ in added if primary), None)
        org_admin.replace_heads(db, dept_id, user_ids, org_admin.choose_primary(user_ids, wanted, None))
        audit.record(db, actor, entity_type="department", entity_id=dept_id, action="heads",
                     summary="Назначены руководители (загрузка структуры): " + ", ".join(n for _, _, n in added),
                     after={"added": [n for _, _, n in added]}, request=request)
    if apply_settings and plan.settings_patch:
        for key, value in plan.settings_patch.items():
            org_admin.save_setting(db, key, value, actor)
        audit.record(db, actor, entity_type="org_settings", entity_id="org", action="update",
                     summary="Изменены настройки структуры (загрузка структуры)",
                     before={s["key"]: s["current"] for s in plan.settings},
                     after={s["key"]: s["incoming"] for s in plan.settings}, request=request)
    summary = result["summary"]
    audit.record(db, actor, entity_type="org_import", action="structure",
                 summary=f"Загружена структура: создано {summary['create']}, изменено {summary['update']}, "
                         f"руководителей назначено {summary['add_heads']}", after=summary, request=request)
    db.flush()
    return {**result, "applied": True}, True
