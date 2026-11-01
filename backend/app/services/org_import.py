"""Быстрая загрузка структуры списком (CSV, Excel) и общий планировщик для синхронизации с AD.

Оба источника приводятся к строкам «сотрудник → подразделение (путь), руководитель», дальше
работает один планировщик (как в todo-planner, ADR-0044 там):

1. plan_import(rows) — без записи в базу: какие подразделения появятся (по пути «Компания /
   Дирекция / Отдел»), кого создать, кому что поменять, кого отключить, ошибки по строкам и
   циклы подчинения, которые получились бы после загрузки;
2. apply_import(rows) — тот же план одной транзакцией; при ошибках ничего не записывается.

Явный руководитель записывается, только если он отличается от руководителя по структуре:
последующие переводы и смены руководителей подразделений тогда работают сами. Новые
сотрудники создаются без пароля: из списка — «без доступа», из AD — со входом по домену.
Отключаются только сотрудники, пришедшие из AD (org_source = 'ad'); включать загрузка не может.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import ValidationFailed
from ..models import Department, DepartmentHead, User, name_key
from . import audit, org, org_admin, sessions

MAX_ROWS = 5000
PATH_SPLIT = re.compile(r"\s*(?:/|>|\\)\s*")
TRUE_VALUES = {"1", "true", "yes", "да", "y", "+", "руководитель", "head", "основной"}
FALSE_VALUES = {"0", "false", "no", "нет", "n", "-"}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOGIN = re.compile(r"^[A-Za-z0-9._@-]{2,100}$")
SOURCE_LABELS = {"csv": "загрузка списком", "ad": "синхронизация с AD"}

# Заголовки столбцов: русские и английские варианты (без учёта регистра)
COLUMN_ALIASES = {
    "email": ("email", "e-mail", "mail", "почта", "эл. почта", "электронная почта"),
    "name": ("фио", "name", "full_name", "имя", "сотрудник", "displayname"),
    "login": ("логин", "login", "username", "samaccountname", "учётная запись", "учетная запись"),
    "department": ("подразделение", "department", "department_path", "отдел", "путь подразделения"),
    "position": ("должность", "position", "title"),
    "manager_email": ("руководитель", "manager", "manager_email", "руководитель (email)", "email руководителя",
                      "почта руководителя", "руководитель (явно)"),
    "is_head": ("руководит", "is_head", "head", "руководитель подразделения"),
    "external_id": ("внешний id", "external_id", "id", "табельный номер", "табельный", "objectguid"),
}


class ImportFormatError(ValidationFailed):
    """Файл не разобран: нет нужных столбцов, пустой или слишком большой."""


@dataclass
class Row:
    line: int
    email: str = ""
    name: str = ""
    login: str = ""
    department: list[str] = field(default_factory=list)   # путь от верхнего уровня
    position: str | None = None
    manager_email: str = ""
    manager_ref: str = ""                                   # AD: DN руководителя (в нижнем регистре)
    is_head: bool = False
    external_id: str = ""
    disabled: bool = False


# ---------------------------------------------------------------- чтение таблиц (общее с загрузкой сотрудников)

def cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value).strip()


def decode_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1251", errors="replace")


def csv_rows(text: str) -> list[list[str]]:
    text = (text or "").lstrip("﻿")
    if not text.strip():
        raise ImportFormatError("Файл пустой")
    sample = text[:4096]
    counts = {";": sample.count(";"), ",": sample.count(","), "\t": sample.count("\t")}
    delimiter = max(counts, key=lambda d: (counts[d], d == ";"))
    return [[(v or "").strip() for v in values] for values in csv.reader(io.StringIO(text), delimiter=delimiter)]


def xlsx_rows(raw: bytes) -> list[list[str]]:
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — openpyxl бросает разные исключения на повреждённых файлах
        raise ImportFormatError("Не удалось прочитать файл Excel") from exc
    try:
        ws = wb.worksheets[0]
        return [[cell_text(v) for v in row] for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def read_table(filename: str, raw: bytes) -> list[list[str]]:
    """Строки таблицы из .csv или .xlsx (первая непустая — заголовки)."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")) or raw[:4] == b"PK\x03\x04":
        return xlsx_rows(raw)
    if name.endswith((".csv", ".txt")) or not name:
        return csv_rows(decode_text(raw))
    raise ImportFormatError("Поддерживаются файлы .csv и .xlsx")


def header_map(header: list[str], aliases: dict[str, tuple[str, ...]]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, title in enumerate(header):
        key = (title or "").strip().lower().lstrip("﻿")
        for column, names in aliases.items():
            if key in names and column not in mapping:
                mapping[column] = index
    return mapping


def split_path(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        parts = [str(p) for p in value]
    else:
        parts = PATH_SPLIT.split(str(value or "").strip())
    return [" ".join(p.split())[:200] for p in parts if p and p.strip()]


def parse_rows(table: list[list[str]]) -> list[Row]:
    """Таблица быстрой загрузки → строки импорта."""
    while table and not any(table[0]):
        table = table[1:]
    if not table:
        raise ImportFormatError("Файл пустой")
    mapping = header_map(table[0], COLUMN_ALIASES)
    if "email" not in mapping and "login" not in mapping:
        raise ImportFormatError("Нужен столбец email или «Логин»")
    if "department" not in mapping:
        raise ImportFormatError("Нужен столбец «Подразделение» (путь через «/»)")
    rows: list[Row] = []
    for line, values in enumerate(table[1:], start=2):
        if not any(values):
            continue
        if len(rows) >= MAX_ROWS:
            raise ImportFormatError(f"Не больше {MAX_ROWS} строк за одну загрузку")

        def cell(column: str, vals=values) -> str:
            index = mapping.get(column)
            return vals[index].strip() if index is not None and index < len(vals) else ""

        rows.append(Row(
            line=line, email=cell("email").lower(), name=" ".join(cell("name").split()), login=cell("login"),
            department=split_path(cell("department")), position=cell("position") or None,
            manager_email=cell("manager_email").lower(), is_head=cell("is_head").lower() in TRUE_VALUES,
            external_id=cell("external_id"),
        ))
    if not rows:
        raise ImportFormatError("В файле нет ни одной строки с сотрудниками")
    return rows


def parse_upload(filename: str, raw: bytes) -> list[Row]:
    return parse_rows(read_table(filename, raw))


# ---------------------------------------------------------------- подразделения по путям (общее)

class Paths:
    """Пути подразделений → id существующего или ключ нового («new:1»)."""

    def __init__(self, snap: org.OrgSnapshot, kinds: list[dict]):
        self.children: dict[tuple, object] = {}
        for unit in snap.units.values():
            parent = unit.parent_id if unit.parent_id in snap.units else None
            self.children.setdefault((parent, name_key(unit.name)), unit.id)
        values = {k["value"] for k in kinds}
        self.has_roots = bool(snap.roots())
        self.root_kind = "company" if "company" in values else org_admin.default_kind(kinds)
        self.kind = org_admin.default_kind(kinds)
        self.created: list[dict] = []
        self.by_key: dict[str, dict] = {}

    def resolve(self, path: list[str] | tuple | None):
        if not path:
            return None
        parent, walked = None, []
        for depth, name in enumerate(path):
            walked.append(name)
            key = (parent, name_key(name))
            if key not in self.children:
                new_key = f"new:{len(self.created) + 1}"
                kind = self.root_kind if depth == 0 and not self.has_roots else self.kind
                item = {"key": new_key, "path": " / ".join(walked), "name": name, "parent_key": parent,
                        "kind": kind}
                self.created.append(item)
                self.by_key[new_key] = item
                self.children[key] = new_key
            parent = self.children[key]
        return parent

    def add_to(self, future: org.OrgSnapshot) -> None:
        for item in self.created:
            if item["key"] not in future.units:
                future.add_unit(org.Unit(item["key"], item["name"], item["parent_key"], item["kind"], 0, None, None))

    def create(self, db: Session, actor: User | None, source: str, comment: str,
               request: Request | None = None) -> dict:
        """Новые подразделения (родители раньше детей) → {ключ: id}."""
        ids: dict = {}
        for item in self.created:
            parent = ids.get(item["parent_key"], item["parent_key"])
            dept = Department(name=item["name"], parent_id=parent, kind=item["kind"], sort_order=0,
                              org_source=source)
            db.add(dept)
            db.flush()
            ids[item["key"]] = dept.id
            audit.record(db, actor, entity_type="department", entity_id=dept.id, action="create",
                         summary=f"Создано подразделение {item['path']} ({comment})",
                         after={"name": dept.name, "kind": dept.kind}, request=request)
        return ids


def label(snap: org.OrgSnapshot, paths: Paths, unit) -> str:
    if unit is None:
        return ""
    if isinstance(unit, str):
        return paths.by_key[unit]["path"] if unit in paths.by_key else ""
    return snap.path_text(unit)


def unique_login(base: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9._@-]", "", (base or "user").lower())[:90] or "user"
    if len(base) < 2:
        base = f"{base}1"
    login, counter = base, 1
    while login in taken:
        counter += 1
        login = f"{base}{counter}"
    taken.add(login)
    return login


def add_head_link(db: Session, dept_id: int, user_id: int, primary: bool, primaries: set[int]) -> bool:
    """Добавить руководителя; основным — только если основного у подразделения ещё нет."""
    exists = db.scalar(select(DepartmentHead).where(DepartmentHead.department_id == dept_id,
                                                    DepartmentHead.user_id == user_id))
    if exists is not None:
        return False
    is_primary = primary and dept_id not in primaries
    db.add(DepartmentHead(department_id=dept_id, user_id=user_id, is_primary=is_primary))
    if is_primary:
        primaries.add(dept_id)
    db.flush()
    return True


def normalize_single_heads(db: Session, dept_ids: set[int], primaries: set[int]) -> None:
    """Единственный руководитель подразделения — основной (как в «Руководители подразделения»)."""
    for dept_id in dept_ids - primaries:
        links = list(db.scalars(select(DepartmentHead).where(DepartmentHead.department_id == dept_id)))
        if len(links) == 1 and not links[0].is_primary:
            links[0].is_primary = True
            primaries.add(dept_id)
    db.flush()


# ---------------------------------------------------------------- план

@dataclass
class ImportPlan:
    source: str
    departments: list = field(default_factory=list)
    users: list = field(default_factory=list)
    deactivate: list = field(default_factory=list)
    cycles: list = field(default_factory=list)
    errors: int = 0
    targets: dict = field(default_factory=dict)       # ключ → что записать
    paths: Paths | None = None
    admins_left: int = 0

    def as_dict(self) -> dict:
        actions = [u["action"] for u in self.users]
        return {
            "source": self.source,
            "summary": {
                "rows": len(self.users), "create_departments": len(self.departments),
                "create_users": actions.count("create"), "update_users": actions.count("update"),
                "unchanged": actions.count("unchanged"), "deactivate_users": len(self.deactivate),
                "errors": self.errors, "warnings": sum(len(u["warnings"]) for u in self.users),
            },
            "departments": [{k: v for k, v in d.items() if k != "parent_key"} for d in self.departments],
            "users": self.users, "deactivate": self.deactivate, "cycles": self.cycles,
            "can_apply": self.errors == 0,
        }


def _match(rows: list[Row], snap: org.OrgSnapshot, source: str) -> dict[int, int | None]:
    """Сопоставление: внешний ID того же источника, затем email; логин — только для загрузки списком
    (в каталоге одинаковый логин может принадлежать другому человеку, ADR-0008)."""
    by_external = {p.external_id: p.id for p in snap.people.values() if p.external_id and p.org_source == source}
    by_email: dict[str, list[int]] = {}
    by_login: dict[str, int] = {}
    for p in snap.people.values():
        if p.email:
            by_email.setdefault(p.email.lower(), []).append(p.id)
        by_login.setdefault(p.username.lower(), p.id)
    matched = {}
    for row in rows:
        user = by_external.get(row.external_id) if row.external_id else None
        if user is None and row.email and len(by_email.get(row.email, [])) == 1:
            user = by_email[row.email][0]
        if user is None and row.login and source == "csv":
            user = by_login.get(row.login.lower())
        matched[row.line] = user
    return matched


def plan_import(db: Session, rows: list[Row], *, source: str = "csv", create_missing: bool = False,
                deactivate_missing: bool = False, manager_refs: dict[str, str] | None = None,
                actor_id: int | None = None) -> ImportPlan:
    plan = ImportPlan(source=source)
    snap = org.build_snapshot(db)
    settings = org_admin.get_settings(db)
    paths = plan.paths = Paths(snap, settings["unit_kinds"])
    matched = _match(rows, snap, source)
    emails_in_system = {p.email.lower(): p.id for p in snap.people.values() if p.email}

    entries = []
    seen_emails: dict[str, int] = {}
    seen_users: dict[int, int] = {}
    email_to_key: dict[str, object] = {}
    ref_to_key: dict[str, object] = {}
    for row in rows:
        user_id = matched[row.line]
        person = snap.people.get(user_id) if user_id is not None else None
        errors: list[str] = []
        warnings: list[str] = []
        if not row.email and not row.login:
            errors.append("нет email и логина")
        if row.email and not EMAIL.match(row.email):
            errors.append(f"некорректный email «{row.email}»")
        if row.email and row.email in seen_emails:
            errors.append(f"email повторяется (строка {seen_emails[row.email]})")
        if user_id is not None and user_id in seen_users:
            errors.append(f"сотрудник уже указан в строке {seen_users[user_id]}")
        if not row.department:
            if source == "ad":
                warnings.append("в каталоге не указано подразделение — подразделение не меняется")
            else:
                errors.append("не указано подразделение")
        elif len(row.department) > settings["max_depth"]:
            errors.append(f"путь подразделения глубже предела вложенности ({settings['max_depth']} уровней)")
        if user_id is None and not create_missing:
            errors.append("сотрудник не найден (включите «Создавать новых»)")
        if user_id is None and create_missing and not row.name:
            errors.append("для нового сотрудника нужно ФИО")
        if user_id is None and row.email and row.email in emails_in_system:
            errors.append(f"email {row.email} в системе у нескольких сотрудников (отличаются регистром)")
        if row.email:
            seen_emails.setdefault(row.email, row.line)
        key = user_id if user_id is not None else f"new-user:{row.line}"
        if user_id is not None:
            seen_users.setdefault(user_id, row.line)
        if row.email:
            email_to_key.setdefault(row.email, key)
        if row.external_id:
            ref_to_key.setdefault(row.external_id, key)
        department = paths.resolve(row.department) if row.department and not errors else (
            person.department_id if person is not None else None)
        entries.append((row, person, key, errors, warnings, department))

    refs = manager_refs or {}
    future = snap.copy()
    paths.add_to(future)
    wanted: dict = {}
    kept: dict = {}
    for row, person, key, errors, warnings, department in entries:
        manager = None
        if row.manager_email:
            manager = email_to_key.get(row.manager_email) or emails_in_system.get(row.manager_email)
            if manager is None:
                errors.append(f"руководитель {row.manager_email} не найден ни в файле, ни в системе")
        elif row.manager_ref:
            manager = ref_to_key.get(refs.get(row.manager_ref, row.manager_ref))
            if manager is None:
                warnings.append("руководитель из каталога не входит в выборку синхронизации — не меняется")
                if person is not None and person.manager_id:
                    kept[key] = person.manager_id
        elif person is not None and person.manager_id:
            kept[key] = person.manager_id      # руководитель не указан — явное подчинение остаётся
        if manager == key:
            errors.append("сотрудник указан своим руководителем")
            manager = None
        if manager is not None and person is not None and person.reports_to_none:
            warnings.append("отмечен как «первое лицо» — руководитель из файла не учитывается")
        wanted[key] = manager
        base = future.people.get(key)
        if base is None:
            base = org.Person(key, row.login, row.name or row.email, row.email or None, row.position, None, None,
                              False, True, False)
        # Активность не влияет на расчёт подчинения: руководитель по структуре — как для активных
        future.people[key] = replace(base, full_name=row.name or base.full_name, department_id=department,
                                     manager_id=None, is_active=True)
        if row.is_head and department is not None and key not in future.heads.get(department, []):
            ids = [*future.heads.get(department, []), key]
            future.set_heads(department, ids, future.primary.get(department) or key)
    future.forget()
    explicit: dict = {}
    for key, manager in wanted.items():
        if manager is not None and future.structure_manager(key) != manager:
            explicit[key] = manager
    explicit.update(kept)
    for key, manager in explicit.items():
        future.people[key] = replace(future.people[key], manager_id=manager)
    future.forget()
    cyclic = future.cycles()
    plan.cycles = sorted(future.people[k].full_name for k in cyclic if k in future.people)
    plan.departments = paths.created

    admins_left = sum(1 for p in snap.people.values() if p.is_admin and p.is_active)
    for row, person, key, errors, warnings, department in entries:
        if key in cyclic:
            errors.append("цикл подчинения: руководитель подчиняется сотруднику")
        disable = False
        if row.disabled:
            if person is None:
                disable = True
            elif person.org_source == "ad":
                disable = person.is_active and person.id != actor_id and not (person.is_admin and admins_left <= 1)
                if person.is_active and not disable:
                    warnings.append("отключён в каталоге, но это ваша учётная запись или последний администратор — "
                                    "не отключается")
                admins_left -= 1 if disable and person.is_admin else 0
            else:
                warnings.append("отключён в каталоге, но учётная запись создана не синхронизацией с AD — "
                                "не отключается")
        head = bool(row.is_head and department is not None)
        target = {"department": department, "position": row.position, "manager": explicit.get(key),
                  "head": head, "name": row.name or None, "email": row.email or None, "login": row.login,
                  "external_id": row.external_id or None, "disabled": disable, "row_disabled": row.disabled,
                  "adopt": person is not None and source != "csv" and not (row.disabled and person.org_source != "ad")}
        changes = []
        if person is not None:
            if department != person.department_id:
                changes.append({"field": "department", "old": label(snap, paths, person.department_id),
                                "new": label(snap, paths, department)})
            if row.position is not None and (person.position or None) != row.position:
                changes.append({"field": "position", "old": person.position or "", "new": row.position})
            if row.name and person.full_name != row.name:
                changes.append({"field": "full_name", "old": person.full_name, "new": row.name})
            if (person.manager_id or None) != target["manager"]:
                changes.append({"field": "manager", "old": _name(snap, person.manager_id),
                                "new": _name(future, target["manager"])})
            if head and department not in snap.headed.get(person.id, []):
                changes.append({"field": "head", "old": "", "new": label(snap, paths, department)})
            if disable:
                changes.append({"field": "is_active", "old": "активен", "new": "отключён"})
            if row.email and not person.email and row.email not in emails_in_system:
                changes.append({"field": "email", "old": "", "new": row.email})
            if row.external_id and not person.external_id:
                changes.append({"field": "external_id", "old": "", "new": row.external_id})
        plan.targets[key] = target
        action = "error" if errors else "create" if person is None else "update" if changes else "unchanged"
        plan.errors += 1 if errors else 0
        plan.users.append({
            "line": row.line, "user_id": person.id if person is not None else None,
            "name": row.name or (person.full_name if person else ""),
            "email": row.email or (person.email if person else "") or "",
            "department": " / ".join(row.department),
            "manager": _name(future, wanted.get(key)) if wanted.get(key) is not None else "",
            "manager_explicit": key in explicit and wanted.get(key) is not None,
            "action": action, "changes": changes, "errors": errors, "warnings": warnings,
        })

    plan.admins_left = admins_left
    if deactivate_missing and source == "ad":
        present = {person.id for _row, person, *_ in entries if person is not None}
        candidates = [p for p in snap.people.values()
                      if p.org_source == "ad" and p.is_active and p.id not in present and p.id != actor_id]
        for person in sorted(candidates, key=lambda p: p.full_name.casefold()):
            if person.is_admin and plan.admins_left <= 1:
                continue    # последний активный администратор не отключается
            if person.is_admin:
                plan.admins_left -= 1
            plan.deactivate.append({"user_id": person.id, "name": person.full_name, "email": person.email})
    return plan


def _name(snap: org.OrgSnapshot, key) -> str:
    person = snap.people.get(key) if key is not None else None
    return person.full_name if person else ""


# ---------------------------------------------------------------- применение

def apply_import(db: Session, actor: User | None, rows: list[Row], *, source: str = "csv",
                 create_missing: bool = False, deactivate_missing: bool = False,
                 manager_refs: dict[str, str] | None = None, request: Request | None = None) -> tuple[dict, bool]:
    """(план, применён ли). При ошибках ничего не записывается."""
    plan = plan_import(db, rows, source=source, create_missing=create_missing,
                       deactivate_missing=deactivate_missing, manager_refs=manager_refs,
                       actor_id=actor.id if actor else None)
    result = plan.as_dict()
    if plan.errors:
        return result, False
    comment = SOURCE_LABELS.get(source, source)
    snap = org.build_snapshot(db)
    ids = plan.paths.create(db, actor, source, comment, request)

    def real(key):
        return ids.get(key, key) if key is not None else None

    taken = {u.lower() for u in db.scalars(select(User.username))}
    emails_taken = {e.lower() for e in db.scalars(select(User.email).where(User.email.isnot(None)))}
    for key, target in plan.targets.items():
        if not isinstance(key, str):
            continue
        login = target["login"] if target["login"] and LOGIN.match(target["login"]) and \
            target["login"].lower() not in taken else None
        login = login.lower() if login else unique_login(target["login"] or (target["email"] or "").split("@")[0],
                                                          taken)
        taken.add(login)
        email = target["email"] if target["email"] and target["email"] not in emails_taken else None
        user = User(username=login, full_name=target["name"], email=email, password_hash=None, role="user",
                    is_active=not target["row_disabled"], position=target["position"], org_source=source,
                    external_id=target["external_id"], auth_source="ldap" if source == "ad" else "local",
                    must_change_password=False)
        db.add(user)
        db.flush()
        ids[key] = user.id
        audit.record(db, actor, entity_type="user", entity_id=user.id, action="org_import",
                     summary=f"Создан сотрудник {user.full_name} ({comment})",
                     after={"username": user.username, "full_name": user.full_name, "email": user.email,
                            "department": label(snap, plan.paths, target["department"]) or None,
                            "is_active": user.is_active}, request=request)
    db.flush()
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_([real(k) for k in plan.targets])))}
    primaries = set(db.scalars(select(DepartmentHead.department_id).where(DepartmentHead.is_primary.is_(True))))
    touched_units: set[int] = set()
    for key, target in plan.targets.items():
        user = users[real(key)]
        created = isinstance(key, str)
        department_id = real(target["department"])
        before = {"department": snap.path_text(user.department_id) or None, "manager_id": user.manager_id,
                  "position": user.position, "full_name": user.full_name, "is_active": user.is_active,
                  "email": user.email, "external_id": user.external_id}
        user.department_id = department_id
        user.manager_id = real(target["manager"])
        if target["position"] is not None:
            user.position = target["position"]
        if target["name"]:
            user.full_name = target["name"]
        if target["email"] and not user.email and target["email"] not in emails_taken:
            user.email = target["email"]
            emails_taken.add(target["email"])
        if target["external_id"] and not user.external_id:
            user.external_id = target["external_id"]
        if target["adopt"]:
            user.org_source = source
        if target["disabled"] and user.is_active:
            user.is_active = False
            sessions.revoke_all(db, user.id)
        if target["head"] and department_id is not None and add_head_link(db, department_id, user.id, True,
                                                                           primaries):
            touched_units.add(department_id)
            audit.record(db, actor, entity_type="department", entity_id=department_id, action="heads",
                         summary=f"Назначен руководитель {user.full_name} ({comment})",
                         after={"added": [user.full_name]}, request=request)
        if not created:
            after = {"department": label(snap, plan.paths, target["department"]) or None,
                     "manager_id": user.manager_id, "position": user.position, "full_name": user.full_name,
                     "is_active": user.is_active, "email": user.email, "external_id": user.external_id}
            b, a = audit.diff(before, after)
            if a:
                audit.record(db, actor, entity_type="user", entity_id=user.id, action="org_import",
                             summary=f"Изменён сотрудник {user.full_name} ({comment})", before=b, after=a,
                             request=request)
    for item in plan.deactivate:
        user = db.get(User, item["user_id"])
        if user is not None and user.is_active:
            user.is_active = False
            sessions.revoke_all(db, user.id)
            audit.record(db, actor, entity_type="user", entity_id=user.id, action="org_import",
                         summary=f"Отключён сотрудник {user.full_name}: нет в каталоге ({comment})",
                         before={"is_active": True}, after={"is_active": False}, request=request)
    normalize_single_heads(db, touched_units, primaries)
    summary = result["summary"]
    audit.record(db, actor, entity_type="org_import", action=source,
                 summary=f"{comment.capitalize()}: создано сотрудников {summary['create_users']}, изменено "
                         f"{summary['update_users']}, отключено {summary['deactivate_users']}, подразделений "
                         f"создано {summary['create_departments']}", after=summary, request=request)
    db.flush()
    return {**result, "applied": True}, True
