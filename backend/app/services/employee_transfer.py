"""Выгрузка и загрузка сотрудников (ADR-0007; подход todo-planner, ADR-0051 там).

Форматы: Excel, CSV (UTF-8 с BOM, «;», строки через CRLF — открывается в Excel без вопросов)
и JSON dashboards.employees версии 1. Пароли не выгружаются и не загружаются никогда.

Загрузка в два шага: план без записи в базу, затем то же самое с решениями администратора
одной транзакцией. Сотрудник файла сопоставляется с системой по email (без учёта регистра).
Коллизия — поле, у которого и в системе, и в файле есть разные значения: администратор выбирает
значение системы, файла или вводит своё; по умолчанию остаётся значение системы. Пустое
в системе заполняется из файла без вопросов, пустое в файле ничего не стирает. Если email
не найден, а логин занят другим сотрудником, администратор решает, тот же это человек или новый.

Роль и профиль доступа (и активность) применяются, только если у загружающего есть полномочие
users.manage; роль администратора и изменения администраторов — только администратором.
Подразделения из путей, которых ещё нет, создаются (план их показывает).
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import __version__
from ..core.config import settings
from ..core.errors import ValidationFailed
from ..models import AccessProfile, DepartmentHead, User, name_key
from . import audit, org, org_admin, sessions
from .org_import import (
    EMAIL,
    FALSE_VALUES,
    LOGIN,
    TRUE_VALUES,
    Paths,
    decode_text,
    header_map,
    normalize_single_heads,
    read_table,
    split_path,
    unique_login,
)

FORMAT = "dashboards.employees"
VERSION = 1
MAX_RECORDS = 10000
INDIVIDUAL = "Индивидуальная настройка"
PRIMARY_MARK = "(основной)"
OWN = "__own__"        # «Руководит: да» — своим подразделением
ROLE_LABELS = {"admin": "Администратор", "user": "Пользователь"}
ROLE_ALIASES = {"admin": "admin", "администратор": "admin", "user": "user", "пользователь": "user",
                "сотрудник": "user"}
AUTH_LABELS = {"local": "Пароль", "ldap": "Домен"}
NEW_USER_MODES = ("active", "inactive", "no_access")

# Столбцы выгрузки — в этом порядке и с этими заголовками
COLUMNS = (
    ("email", "Email"), ("login", "Логин"), ("full_name", "ФИО"), ("position", "Должность"), ("phone", "Телефон"),
    ("department", "Подразделение"), ("manager", "Руководитель (явно)"), ("reports_to_none", "Первое лицо"),
    ("heads", "Руководит"), ("role", "Роль"), ("access_profile", "Профиль доступа"), ("is_active", "Активен"),
    ("auth_source", "Способ входа"), ("external_id", "Внешний ID"),
)
FIELD_LABELS = dict(COLUMNS)
ALIASES = {
    "email": ("email", "e-mail", "mail", "почта", "эл. почта", "электронная почта"),
    "login": ("логин", "login", "username", "samaccountname", "учётная запись", "учетная запись"),
    "full_name": ("фио", "full_name", "name", "имя", "сотрудник", "displayname"),
    "position": ("должность", "position", "title"),
    "phone": ("телефон", "phone", "тел."),
    "department": ("подразделение", "department", "department_path", "отдел", "путь подразделения"),
    "manager": ("руководитель (явно)", "руководитель", "manager", "manager_email", "email руководителя"),
    "reports_to_none": ("первое лицо", "reports_to_none", "никому не подчиняется"),
    "heads": ("руководит", "heads", "is_head", "руководит подразделениями"),
    "role": ("роль", "role"),
    "access_profile": ("профиль доступа", "access_profile", "профиль"),
    "is_active": ("активен", "is_active", "active"),
    "auth_source": ("способ входа", "auth_source", "вход"),
    "external_id": ("внешний id", "external_id", "табельный номер", "objectguid"),
}
FIELD_KINDS = {"department": "path", "manager": "email", "reports_to_none": "bool", "heads": "list",
               "role": "role", "access_profile": "profile", "is_active": "bool"}
COMPARED = ("full_name", "email", "login", "position", "phone", "department", "manager", "reports_to_none",
            "heads", "role", "access_profile", "is_active")
ACCESS_FIELDS = ("role", "access_profile", "is_active")
BOOL_FIELDS = ("reports_to_none", "is_active")


class EmployeeFormatError(ValidationFailed):
    """Файл не разобран: не тот формат, нет нужных столбцов, слишком большой."""


@dataclass
class Record:
    line: int
    email: str = ""
    login: str = ""
    full_name: str = ""
    position: str | None = None
    phone: str | None = None
    department: tuple | None = None
    manager: str | None = None
    reports_to_none: bool | None = None
    heads: tuple | None = None            # ((путь, основной), …); путь может быть OWN
    role: str | None = None
    access_profile: str | None = None
    is_active: bool | None = None
    external_id: str | None = None
    notes: list = field(default_factory=list)


# ---------------------------------------------------------------- разбор значений

def _clean(value) -> str:
    return " ".join(str(value if value is not None else "").split())


def _bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _clean(value).lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return None


def _path(value) -> tuple | None:
    parts = tuple(split_path(value))
    return parts or None


def path_text(path) -> str:
    return " / ".join(path or ())


def parse_heads(value) -> tuple | None:
    """«Руководит»: «да» — своим подразделением; иначе пути через «|», «(основной)» — основной."""
    if isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, dict):
                path = _path(item.get("department") or item.get("path"))
                if path:
                    items.append((path, bool(item.get("primary"))))
            else:
                items.extend(parse_heads(str(item)) or ())
        return tuple(items) or None
    text = _clean(value)
    if not text:
        return None
    if text.lower() in TRUE_VALUES:
        return ((OWN, True),)
    if text.lower() in FALSE_VALUES:
        return None
    items = []
    for part in text.split("|"):
        primary = PRIMARY_MARK in part.lower()
        path = _path(re.sub(re.escape(PRIMARY_MARK), "", part, flags=re.IGNORECASE))
        if path:
            items.append((path, primary))
    return tuple(items) or None


def make_record(line: int, raw: dict) -> Record:
    """Словарь (строка таблицы или объект JSON) → Record; непонятные значения — в notes."""
    record = Record(line=line)
    record.email = _clean(raw.get("email")).lower()
    record.login = _clean(raw.get("login"))
    record.full_name = _clean(raw.get("full_name") or raw.get("name"))[:200]
    record.position = _clean(raw.get("position"))[:200] or None
    record.phone = _clean(raw.get("phone"))[:50] or None
    record.department = _path(raw.get("department"))
    record.manager = _clean(raw.get("manager")).lower() or None
    for name in BOOL_FIELDS:
        value = raw.get(name)
        if value not in (None, ""):
            parsed = _bool(value)
            if parsed is None:
                record.notes.append(f"{FIELD_LABELS[name]}: «{value}» не распознано (да или нет) — не применяется")
            setattr(record, name, parsed)
    record.heads = parse_heads(raw.get("heads"))
    role = _clean(raw.get("role")).lower()
    if role:
        record.role = ROLE_ALIASES.get(role)
        if record.role is None:
            record.notes.append(f"роль «{raw.get('role')}» не распознана — не применяется")
    record.access_profile = _clean(raw.get("access_profile")) or None
    record.external_id = _clean(raw.get("external_id"))[:200] or None
    return record


def parse_table(table: list[list[str]]) -> list[Record]:
    while table and not any(table[0]):
        table = table[1:]
    if not table:
        raise EmployeeFormatError("Файл пустой")
    mapping = header_map(table[0], ALIASES)
    if "email" not in mapping:
        raise EmployeeFormatError("Нужен столбец Email")
    records = []
    for line, values in enumerate(table[1:], start=2):
        if not any(values):
            continue
        if len(records) >= MAX_RECORDS:
            raise EmployeeFormatError(f"Не больше {MAX_RECORDS} сотрудников за одну загрузку")
        raw = {column: (values[index] if index < len(values) else "") for column, index in mapping.items()}
        records.append(make_record(line, raw))
    return records


def parse_json(content: Any) -> list[Record]:
    if isinstance(content, (str, bytes)):
        try:
            content = json.loads(content)
        except ValueError as exc:
            raise EmployeeFormatError("Файл не является JSON") from exc
    if isinstance(content, dict):
        if content.get("format") != FORMAT:
            raise EmployeeFormatError(f"Это не файл сотрудников «Дашбордов компании» (нужен format: {FORMAT})")
        if content.get("version") != VERSION:
            raise EmployeeFormatError(f"Версия файла {content.get('version')} не поддерживается — нужна {VERSION}")
        items = content.get("employees")
    else:
        items = content
    if not isinstance(items, list):
        raise EmployeeFormatError("В файле нет списка сотрудников")
    if len(items) > MAX_RECORDS:
        raise EmployeeFormatError(f"Не больше {MAX_RECORDS} сотрудников за одну загрузку")
    return [make_record(index, item) for index, item in enumerate(items, start=1) if isinstance(item, dict)]


def parse_upload(filename: str, raw: bytes) -> list[Record]:
    name = (filename or "").lower()
    if name.endswith(".json"):
        return parse_json(decode_text(raw))
    if name.endswith((".csv", ".txt", ".xlsx", ".xlsm")):
        return parse_table(read_table(filename, raw))
    raise EmployeeFormatError("Поддерживаются файлы .xlsx, .csv и .json")


def parse_content(fmt: str, content: Any) -> list[Record]:
    if fmt == "csv":
        if not isinstance(content, str):
            raise EmployeeFormatError("Для формата csv content — текст файла")
        from .org_import import csv_rows

        return parse_table(csv_rows(content))
    return parse_json(content)


# ---------------------------------------------------------------- выгрузка

def export_records(db: Session, *, include_inactive: bool = True) -> list[dict]:
    snap = org.build_snapshot(db)
    emails = {p.id: (p.email or "").lower() for p in snap.people.values()}
    users = sorted(db.scalars(select(User)), key=lambda u: (u.full_name.casefold(), u.id))
    records = []
    for user in users:
        if not include_inactive and not user.is_active:
            continue
        heads = [{"department": list(snap.path_names(u)), "primary": snap.primary.get(u) == user.id}
                 for u in snap.headed.get(user.id, [])]
        heads.sort(key=lambda h: (not h["primary"], path_text(h["department"]).casefold()))
        records.append({
            "email": (user.email or "").lower(), "login": user.username, "full_name": user.full_name,
            "position": user.position or "", "phone": user.phone or "",
            "department": list(snap.path_names(user.department_id)) if user.department_id in snap.units else [],
            "manager": emails.get(user.manager_id, "") if user.manager_id else "",
            "reports_to_none": bool(user.reports_to_none), "heads": heads, "role": user.role,
            "access_profile": user.access_profile.name if user.access_profile else INDIVIDUAL,
            "is_active": bool(user.is_active), "auth_source": user.auth_source or "local",
            "external_id": user.external_id or "",
        })
    return records


def export_document(records: list[dict]) -> dict:
    return {"format": FORMAT, "version": VERSION,
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "app": __version__, "employees": records}


def cell_value(key: str, value) -> str:
    if key == "department":
        return path_text(value)
    if key == "heads":
        return " | ".join(path_text(h["department"]) + (f" {PRIMARY_MARK}" if h["primary"] else "") for h in value)
    if key == "role":
        return ROLE_LABELS.get(value, value)
    if key in BOOL_FIELDS:
        return "да" if value else "нет"
    if key == "auth_source":
        return AUTH_LABELS.get(value, value)
    return "" if value is None else str(value)


def export_csv(records: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow([title for _key, title in COLUMNS])
    for record in records:
        writer.writerow([cell_value(key, record.get(key)) for key, _title in COLUMNS])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def export_xlsx(records: list[dict]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Сотрудники"
    ws.append([title for _key, title in COLUMNS])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for record in records:
        ws.append([cell_value(key, record.get(key)) for key, _title in COLUMNS])
    widths = {"email": 30, "full_name": 34, "position": 30, "department": 48, "heads": 40, "manager": 28,
              "access_profile": 28}
    for index, (key, _title) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(index)].width = widths.get(key, 16)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_json(records: list[dict]) -> bytes:
    return json.dumps(export_document(records), ensure_ascii=False, indent=2).encode("utf-8")


# ---------------------------------------------------------------- сравнение и решения

def _empty(value) -> bool:
    return value is None or value == "" or value == () or value == []


def _same(name: str, left, right) -> bool:
    if name == "department":
        return tuple(name_key(p) for p in left or ()) == tuple(name_key(p) for p in right or ())
    if name == "heads":
        return ({(tuple(name_key(p) for p in path), primary) for path, primary in left or ()}
                == {(tuple(name_key(p) for p in path), primary) for path, primary in right or ()})
    if name in ("email", "manager", "login", "access_profile"):
        return (left or "").casefold() == (right or "").casefold()
    return (None if left == "" else left) == (None if right == "" else right)


def _text(name: str, value):
    """Значение для показа администратору."""
    if _empty(value):
        return ""
    if name == "department":
        return path_text(value)
    if name == "heads":
        return [path_text(path) + (f" {PRIMARY_MARK}" if primary else "") for path, primary in value]
    if name == "role":
        return ROLE_LABELS.get(value, value)
    if name in BOOL_FIELDS:
        return "да" if value else "нет"
    return value


def _merge_heads(current, incoming) -> tuple:
    merged: dict = {}
    for path, primary in (*(current or ()), *(incoming or ())):
        key = tuple(name_key(p) for p in path)
        previous = merged.get(key)
        merged[key] = (path, primary or (previous[1] if previous else False))
    return tuple(merged.values())


def _own(heads, own_department) -> tuple | None:
    if not heads:
        return heads
    items = tuple(((own_department or ()) if path == OWN else path, primary) for path, primary in heads)
    return tuple(item for item in items if item[0]) or None


class Profiles:
    def __init__(self, db: Session):
        self.items = list(db.scalars(select(AccessProfile).order_by(AccessProfile.sort_order)))
        self.by_name = {}
        for profile in self.items:
            self.by_name[profile.name.casefold()] = profile
            self.by_name.setdefault(profile.key.casefold(), profile)

    def resolve(self, value: str | None) -> tuple[str | None, str | None]:
        """Название профиля из файла → (каноническое название или INDIVIDUAL, ошибка)."""
        text = _clean(value)
        if not text:
            return None, None
        if text.casefold() == INDIVIDUAL.casefold():
            return INDIVIDUAL, None
        profile = self.by_name.get(text.casefold())
        if profile is None:
            return None, f"профиль доступа «{text}» не найден"
        return profile.name, None

    def id_of(self, name: str | None) -> int | None:
        if not name or name == INDIVIDUAL:
            return None
        profile = self.by_name.get(name.casefold())
        return profile.id if profile else None


def _custom(name: str, value, profiles: Profiles):
    """Своё значение администратора → (значение, ошибка)."""
    if name in ("full_name", "position", "phone", "email", "login", "manager"):
        text = _clean(value)
        if name == "full_name" and not text:
            return None, "ФИО не может быть пустым"
        if name == "email" and not EMAIL.match(text):
            return None, "некорректный email"
        if name == "login" and not LOGIN.match(text):
            return None, "логин: латиница, цифры, «._-@», 2–100 символов"
        if name == "manager" and text and not EMAIL.match(text):
            return None, "руководитель — email сотрудника"
        limit = {"full_name": 200, "position": 200, "phone": 50}.get(name)
        if limit and len(text) > limit:
            return None, f"не длиннее {limit} символов"
        return (text.lower() if name in ("email", "manager") else text) or None, None
    if name == "department":
        return _path(value), None
    if name in BOOL_FIELDS:
        result = _bool(value)
        return (result, None) if result is not None else (None, "ожидается да или нет")
    if name == "heads":
        return parse_heads(value) or (), None
    if name == "role":
        role = ROLE_ALIASES.get(_clean(value).lower())
        return (role, None) if role else (None, "роль: Пользователь или Администратор")
    if name == "access_profile":
        resolved, error = profiles.resolve(value)
        if resolved is None and error is None:
            return INDIVIDUAL, None
        return resolved, error
    return None, "это поле нельзя ввести вручную"


# ---------------------------------------------------------------- план

@dataclass
class Entry:
    record: Record
    user: User | None
    key: str
    action: str = "create"
    final: dict = field(default_factory=dict)
    changes: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    identity: dict | None = None
    unresolved: bool = False
    touched: set = field(default_factory=set)

    @property
    def active(self) -> bool:
        return bool(self.final) and not self.errors and self.action in ("create", "update")


@dataclass
class EmployeePlan:
    entries: list = field(default_factory=list)
    paths: Paths | None = None
    notes: list = field(default_factory=list)
    new_users: str = "no_access"

    def as_dict(self) -> dict:
        actions = [e.action for e in self.entries]
        errors = sum(1 for e in self.entries if e.errors)
        unresolved = sum(1 for e in self.entries if e.unresolved)
        created = self.paths.created if self.paths else []
        return {
            "summary": {
                "records": len(self.entries), "create": actions.count("create"), "update": actions.count("update"),
                "unchanged": actions.count("unchanged"), "skip": actions.count("skip"),
                "conflicts": sum(len(e.conflicts) for e in self.entries), "unresolved": unresolved,
                "errors": errors, "create_departments": len(created),
            },
            "departments": [{"key": d["key"], "path": d["path"], "name": d["name"], "kind": d["kind"]}
                            for d in created],
            "records": [{
                "key": e.key, "line": e.record.line, "action": e.action,
                "user_id": e.user.id if e.user is not None and e.user.id else None,
                "name": e.final.get("full_name") or e.record.full_name or (e.user.full_name if e.user else ""),
                "email": e.final.get("email") or e.record.email, "identity": e.identity, "unresolved": e.unresolved,
                "changes": e.changes, "conflicts": e.conflicts, "errors": e.errors, "warnings": e.warnings,
            } for e in self.entries],
            "notes": self.notes,
            "can_apply": not errors and not unresolved,
        }


@dataclass
class Context:
    actor: User | None
    actor_admin: bool
    access_allowed: bool
    snap: org.OrgSnapshot
    profiles: Profiles
    emails: dict
    by_login: dict
    new_users: str


def _current(user: User, ctx: Context) -> dict:
    snap = ctx.snap
    heads = tuple((tuple(snap.path_names(u)), snap.primary.get(u) == user.id) for u in snap.headed.get(user.id, []))
    return {
        "full_name": user.full_name, "email": (user.email or "").lower() or None, "login": user.username,
        "position": user.position or None, "phone": user.phone or None,
        "department": tuple(snap.path_names(user.department_id)) or None if user.department_id in snap.units
        else None,
        "manager": ctx.emails.get(user.manager_id) or None if user.manager_id else None,
        "reports_to_none": bool(user.reports_to_none), "heads": heads or None, "role": user.role,
        "access_profile": user.access_profile.name if user.access_profile else INDIVIDUAL,
        "is_active": bool(user.is_active),
    }


def _incoming(record: Record, name: str, own_department, ctx: Context, entry: Entry):
    if name == "access_profile":
        resolved, error = ctx.profiles.resolve(record.access_profile)
        if error and error not in entry.warnings:
            entry.warnings.append(f"{error} — не применяется")
        return resolved
    value = {
        "full_name": record.full_name or None, "email": record.email or None, "login": record.login or None,
        "position": record.position, "phone": record.phone, "department": record.department,
        "manager": record.manager, "reports_to_none": record.reports_to_none, "heads": record.heads,
        "role": record.role, "is_active": record.is_active,
    }[name]
    if name == "heads":
        value = _own(value, own_department)
    return value


def plan_employees(db: Session, records: list[Record], *, actor: User | None, new_users: str = "no_access",
                   decisions: dict | None = None) -> EmployeePlan:
    """План загрузки. decisions — {email: {"identity": "same"|"new", "fields": {поле: {"choice":
    "current"|"incoming"|"merge"|"custom", "value": …}}}}."""
    decisions = {str(k).lower(): v for k, v in (decisions or {}).items()}
    snap = org.build_snapshot(db)
    users = list(db.scalars(select(User)))
    by_email: dict[str, list[User]] = {}
    by_login: dict[str, User] = {}
    for user in users:
        if user.email:
            by_email.setdefault(user.email.lower(), []).append(user)
        by_login.setdefault(user.username.lower(), user)
    access_allowed = bool(actor and actor.can("users.manage"))
    plan = EmployeePlan(new_users=new_users)
    if new_users == "active" and not access_allowed:
        # Вход по домену — это выдача доступа: её делает ведущий пользователей
        plan.new_users = new_users = "no_access"
        plan.notes.append("Новые сотрудники будут без доступа: входить по домену разрешает ведущий пользователей "
                          "(полномочие users.manage)")
    ctx = Context(actor=actor, actor_admin=bool(actor and actor.is_admin), access_allowed=access_allowed,
                  snap=snap, profiles=Profiles(db), emails={u.id: (u.email or "").lower() for u in users},
                  by_login=by_login, new_users=new_users)
    plan.paths = Paths(snap, org_admin.get_settings(db)["unit_kinds"])
    if not ctx.access_allowed and any(r.role or r.access_profile or r.is_active is not None for r in records):
        plan.notes.append("Роль, профиль доступа и активность загружает ведущий пользователей (полномочие "
                          "users.manage) — эти столбцы не применяются")
    if new_users == "active" and not settings.auth_ldap_enabled:
        plan.notes.append("Вход по домену не включён: новые сотрудники со входом по домену смогут войти, когда "
                          "его настроят, или после «Выдать доступ»")

    seen: dict[str, int] = {}
    for record in records:
        key = record.email or f"line:{record.line}"
        entry = Entry(record=record, user=None, key=key)
        entry.warnings.extend(record.notes)
        plan.entries.append(entry)
        if not record.email or not EMAIL.match(record.email):
            entry.errors.append("нет email или он некорректный")
            continue
        if record.email in seen:
            entry.errors.append(f"email повторяется (строка {seen[record.email]})")
            continue
        seen[record.email] = record.line
        matches = by_email.get(record.email, [])
        if len(matches) > 1:
            entry.errors.append("в системе несколько сотрудников с таким email (отличаются регистром) — "
                                "исправьте в системе")
            continue
        user = matches[0] if matches else None
        decision = decisions.get(key) or {}
        if hasattr(decision, "model_dump"):
            decision = decision.model_dump()
        if user is None and record.login and record.login.lower() in by_login:
            other = by_login[record.login.lower()]
            entry.identity = {"user_id": other.id, "name": other.full_name, "email": other.email,
                              "login": other.username}
            choice = decision.get("identity")
            if choice == "same":
                user = other
            elif choice != "new":
                entry.unresolved = True
        entry.user = user
        if user is not None and user.is_admin and not ctx.actor_admin:
            entry.action = "skip"
            entry.warnings.append("администратора изменяет только администратор — запись пропущена")
            continue
        if user is None:
            _plan_new(entry, decision, ctx)
        else:
            _plan_existing(entry, decision, ctx)
    _check_logins(plan, by_login)
    _check_admins(plan, users)
    _resolve(plan, ctx, by_email, org_admin.get_settings(db)["max_depth"])
    return plan


def _plan_new(entry: Entry, decision: dict, ctx: Context) -> None:
    record = entry.record
    fields = decision.get("fields") or {}
    if not record.full_name:
        entry.errors.append("для нового сотрудника нужно ФИО")
    role = "user"
    if record.role and ctx.access_allowed:
        role = record.role
    if role == "admin" and not ctx.actor_admin:
        entry.errors.append("роль администратора назначает только администратор")
    profile = None
    if record.access_profile and ctx.access_allowed:
        profile, error = ctx.profiles.resolve(record.access_profile)
        if error:
            entry.warnings.append(f"{error} — не применяется")
    login = record.login or None
    if login and not LOGIN.match(login):
        entry.errors.append(f"логин «{login}»: латиница, цифры, «._-@», 2–100 символов")
    if entry.identity is not None and decision.get("identity") == "new":
        chosen = fields.get("login") or {}
        custom, error = (_custom("login", chosen.get("value"), ctx.profiles) if chosen.get("choice") == "custom"
                         else (None, None))
        entry.conflicts.append({
            "field": "login", "label": FIELD_LABELS["login"], "kind": "text", "current": "",
            "incoming": record.login, "merged": None, "choices": ["custom"], "choice": "custom",
            "value": chosen.get("value") or "", "note": f"логин «{record.login}» занят сотрудником "
                                                        f"{entry.identity['name']}",
        })
        if error or not custom:
            entry.errors.append(error or f"логин «{record.login}» занят — укажите другой")
        login = custom
    entry.final = {
        "full_name": record.full_name, "email": record.email, "login": login, "position": record.position,
        "phone": record.phone, "department": record.department, "manager": record.manager,
        "reports_to_none": bool(record.reports_to_none), "heads": _own(record.heads, record.department) or (),
        "role": role, "access_profile": profile, "is_active": ctx.new_users != "inactive",
        "external_id": record.external_id,
    }
    entry.touched = set(entry.final)
    entry.action = "create"


def _plan_existing(entry: Entry, decision: dict, ctx: Context) -> None:
    record, user = entry.record, entry.user
    fields = decision.get("fields") or {}
    current = _current(user, ctx)
    final = dict(current)
    own = record.department or current["department"]
    for name in COMPARED:
        incoming = _incoming(record, name, own, ctx, entry)
        if _empty(incoming):
            continue
        if name in ACCESS_FIELDS and not ctx.access_allowed:
            continue
        if name == "email" and entry.identity is None:
            continue   # сопоставлен по email — совпадает
        if _same(name, current[name], incoming):
            continue
        if name in ("role", "is_active") and ctx.actor is not None and user.id == ctx.actor.id:
            entry.warnings.append(f"{FIELD_LABELS[name]}: свою учётную запись так изменить нельзя — не применяется")
            continue
        if name == "role" and incoming == "admin" and not ctx.actor_admin:
            entry.warnings.append("роль администратора назначает только администратор — не применяется")
            continue
        empty_now = _empty(current[name]) or (name == "access_profile" and current[name] == INDIVIDUAL)
        if empty_now and name not in BOOL_FIELDS:
            # В системе пусто — берём из файла без вопросов
            final[name] = incoming
            entry.touched.add(name)
            entry.changes.append({"field": name, "label": FIELD_LABELS[name], "old": _text(name, current[name]),
                                  "new": _text(name, incoming)})
            continue
        choices = ["current", "incoming", "custom"]
        if name == "heads":
            choices.insert(2, "merge")
        note = None
        if name == "login":
            holder = ctx.by_login.get(incoming.lower())
            if holder is not None and holder.id != user.id:
                choices = ["current", "custom"]
                note = f"логин «{incoming}» занят сотрудником {holder.full_name}"
        chosen = fields.get(name) or {}
        if hasattr(chosen, "model_dump"):
            chosen = chosen.model_dump()
        choice = chosen.get("choice") if chosen.get("choice") in choices else "current"
        value = current[name]
        if choice == "incoming":
            value = incoming
        elif choice == "merge":
            value = _merge_heads(current[name], incoming)
        elif choice == "custom":
            value, error = _custom(name, chosen.get("value"), ctx.profiles)
            if error:
                entry.errors.append(f"{FIELD_LABELS[name]}: {error}")
                value = current[name]
            elif name == "heads":
                value = _own(value, own) or ()
            elif name == "role" and value == "admin" and not ctx.actor_admin:
                entry.errors.append("роль администратора назначает только администратор")
                value = current[name]
        if choice != "current" and not _same(name, current[name], value):
            final[name] = value
            entry.touched.add(name)
        entry.conflicts.append({
            "field": name, "label": FIELD_LABELS[name], "kind": FIELD_KINDS.get(name, "text"),
            "current": _text(name, current[name]), "incoming": _text(name, incoming),
            "merged": _text(name, _merge_heads(current[name], incoming)) if name == "heads" else None,
            "choices": choices, "choice": choice, "value": _text(name, value) if choice == "custom" else None,
            "note": note,
        })
    if record.external_id and not user.external_id:
        final["external_id"] = record.external_id
        entry.touched.add("external_id")
        entry.changes.append({"field": "external_id", "label": FIELD_LABELS["external_id"], "old": "",
                              "new": record.external_id})
    entry.final = final
    entry.action = "update" if entry.touched else "unchanged"


def _check_logins(plan: EmployeePlan, by_login: dict) -> None:
    """Логины после загрузки не повторяются."""
    taken: dict[str, int] = {}
    for entry in plan.entries:
        if entry.errors or entry.action == "skip" or not entry.final:
            continue
        login = entry.final.get("login")
        if not login:
            continue
        holder = by_login.get(login.lower())
        if holder is not None and (entry.user is None or holder.id != entry.user.id):
            if entry.user is None and entry.identity is None:
                entry.errors.append(f"логин «{login}» занят сотрудником {holder.full_name} — уберите логин из "
                                    "файла или измените")
            elif entry.user is not None:
                entry.errors.append(f"логин «{login}» занят сотрудником {holder.full_name}")
        if login.lower() in taken:
            entry.errors.append(f"логин «{login}» повторяется (строка {taken[login.lower()]})")
        taken.setdefault(login.lower(), entry.record.line)


def _check_admins(plan: EmployeePlan, users: list[User]) -> None:
    """После загрузки остаётся хотя бы один активный администратор."""
    final = {u.id: (u.is_admin, u.is_active) for u in users}
    reducing = []
    for entry in plan.entries:
        if entry.user is None or not entry.active:
            continue
        role = entry.final.get("role", entry.user.role)
        active = entry.final.get("is_active", entry.user.is_active)
        final[entry.user.id] = (role == "admin", bool(active))
        if entry.user.is_admin and entry.user.is_active and not (role == "admin" and active):
            reducing.append(entry)
    if reducing and not any(is_admin and active for is_admin, active in final.values()):
        for entry in reducing:
            entry.errors.append("в системе должен остаться хотя бы один активный администратор")


def _resolve(plan: EmployeePlan, ctx: Context, by_email: dict, max_depth: int) -> None:
    """Подразделения, руководители и проверка циклов подчинения по итоговым значениям."""
    snap = ctx.snap
    keys: dict[str, object] = {}
    for entry in plan.entries:
        if entry.active:
            keys[entry.final["email"]] = entry.user.id if entry.user is not None else f"new-user:{entry.final['email']}"
    for email, users in by_email.items():
        if len(users) == 1:
            keys.setdefault(email, users[0].id)
    active = [e for e in plan.entries if e.active]
    for entry in active:
        final = entry.final
        for path in [final.get("department"), *[p for p, _ in final.get("heads") or ()]]:
            if path and len(path) > max_depth:
                entry.errors.append(f"путь «{path_text(path)}» глубже предела вложенности ({max_depth} уровней)")
    active = [e for e in active if not e.errors]
    for entry in active:
        final = entry.final
        final["_department"] = plan.paths.resolve(final.get("department")) if final.get("department") else None
        final["_heads"] = [(plan.paths.resolve(path), primary) for path, primary in final.get("heads") or () if path]
        manager = final.get("manager")
        final["_manager"] = None
        if manager:
            final["_manager"] = keys.get(manager.lower())
            if final["_manager"] is None:
                entry.warnings.append(f"руководитель {manager} не найден ни в системе, ни в файле — не назначается")
                final["manager"] = None
                entry.touched.discard("manager")
    future = snap.copy()
    plan.paths.add_to(future)
    for entry in active:
        final = entry.final
        key = entry.user.id if entry.user is not None else f"new-user:{final['email']}"
        final["_key"] = key
        base = future.people.get(key) or org.Person(key, final.get("login") or "", final.get("full_name") or "",
                                                     final["email"], None, None, None, False, True, False)
        # Активность не влияет на расчёт подчинения
        future.people[key] = replace(base, full_name=final.get("full_name") or base.full_name,
                                     department_id=final["_department"], manager_id=None, is_active=True,
                                     reports_to_none=bool(final.get("reports_to_none")))
    for entry in active:
        final = entry.final
        key = final["_key"]
        if "heads" in entry.touched or entry.user is None:
            wanted = {unit: primary for unit, primary in final["_heads"]}
            for unit in set(future.headed.get(key, [])) - set(wanted):
                ids = [h for h in future.heads.get(unit, []) if h != key]
                primary = future.primary.get(unit) if future.primary.get(unit) != key else None
                future.set_heads(unit, ids, org_admin.choose_primary(ids, primary, None))
            for unit, primary in wanted.items():
                if key in future.heads.get(unit, []):
                    continue
                ids = [*future.heads.get(unit, []), key]
                current = future.primary.get(unit) or (key if primary else None)
                future.set_heads(unit, ids, org_admin.choose_primary(ids, current, None))
    future.forget()
    # Явный руководитель — только если он отличается от руководителя по структуре
    for entry in active:
        final = entry.final
        key = final["_key"]
        if "manager" in entry.touched or entry.user is None:
            manager = final["_manager"]
            if manager is not None and future.structure_manager(key) == manager:
                manager = None
            final["_explicit"] = manager
        else:
            final["_explicit"] = entry.user.manager_id
        if final.get("reports_to_none"):
            final["_explicit"] = None
        future.people[key] = replace(future.people[key], manager_id=final["_explicit"])
    future.forget()
    cyclic = future.cycles()
    for entry in active:
        if entry.final["_key"] in cyclic:
            entry.errors.append("цикл подчинения: руководитель подчиняется сотруднику")


# ---------------------------------------------------------------- применение

def apply_employees(db: Session, actor: User | None, records: list[Record], *, new_users: str = "no_access",
                    decisions: dict | None = None, request: Request | None = None) -> tuple[dict, bool]:
    """(план, применён ли). При ошибках или нерешённых вопросах ничего не записывается."""
    plan = plan_employees(db, records, actor=actor, new_users=new_users, decisions=decisions)
    result = plan.as_dict()
    if not result["can_apply"]:
        return result, False
    before_snap = org.build_snapshot(db)
    comment = "загрузка сотрудников"
    ids = plan.paths.create(db, actor, "import", comment, request)
    profiles = Profiles(db)

    def real(key):
        return ids.get(key, key) if key is not None else None

    taken = {u.lower() for u in db.scalars(select(User.username))}
    active = [e for e in plan.entries if e.active]
    for entry in active:
        if entry.user is not None:
            continue
        final = entry.final
        login = final.get("login")
        login = login if login and login.lower() not in taken else unique_login(final["email"].split("@")[0], taken)
        taken.add(login.lower())
        user = User(username=login, full_name=final["full_name"], email=final["email"], password_hash=None,
                    role=final.get("role") or "user", is_active=bool(final.get("is_active", True)),
                    position=final.get("position"), phone=final.get("phone"),
                    reports_to_none=bool(final.get("reports_to_none")), org_source="import",
                    external_id=final.get("external_id"), must_change_password=False,
                    auth_source="ldap" if plan.new_users == "active" else "local",
                    access_profile_id=profiles.id_of(final.get("access_profile")))
        db.add(user)
        db.flush()
        entry.user = user
        ids[final["_key"]] = user.id
    db.flush()

    primaries = set(db.scalars(select(DepartmentHead.department_id).where(DepartmentHead.is_primary.is_(True))))
    touched_units: set[int] = set()
    for entry in active:
        user, final, created = entry.user, entry.final, entry.action == "create"
        touched = entry.touched
        before = {"full_name": user.full_name, "email": user.email, "username": user.username,
                  "position": user.position, "phone": user.phone, "role": user.role,
                  "access_profile": user.access_profile.name if user.access_profile else None,
                  "is_active": user.is_active, "reports_to_none": user.reports_to_none,
                  "department": before_snap.path_text(user.department_id) or None, "manager_id": user.manager_id}
        if not created:
            for name, attr in (("full_name", "full_name"), ("email", "email"), ("login", "username"),
                               ("position", "position"), ("phone", "phone"), ("role", "role"),
                               ("is_active", "is_active"), ("reports_to_none", "reports_to_none")):
                if name in touched:
                    value = final.get(name)
                    setattr(user, attr, bool(value) if name in BOOL_FIELDS else value)
            if "access_profile" in touched:
                user.access_profile_id = profiles.id_of(final.get("access_profile"))
                user.access_profile = None if user.access_profile_id is None else db.get(AccessProfile,
                                                                                         user.access_profile_id)
            if "external_id" in touched and not user.external_id:
                user.external_id = final.get("external_id")
        if "department" in touched or created:
            user.department_id = real(final.get("_department"))
        if "manager" in touched or created:
            user.manager_id = real(final.get("_explicit"))
            if user.manager_id and "reports_to_none" not in touched:
                user.reports_to_none = False    # явный руководитель снимает «первое лицо»
        if user.reports_to_none:
            user.manager_id = None
        if not created and before["is_active"] and not user.is_active:
            sessions.revoke_all(db, user.id)    # отключённый сотрудник выходит из системы
        if "heads" in touched or created:
            wanted = {real(unit): primary for unit, primary in final.get("_heads") or []}
            links = {link.department_id: link for link in db.scalars(
                select(DepartmentHead).where(DepartmentHead.user_id == user.id))}
            for unit, link in links.items():
                if unit not in wanted:
                    if link.is_primary:
                        primaries.discard(unit)
                    db.delete(link)
                    touched_units.add(unit)
            db.flush()
            for unit, primary in wanted.items():
                link = links.get(unit)
                if link is None:
                    # Новый руководитель — основной, только если основного у подразделения нет
                    is_primary = bool(primary) and unit not in primaries
                    db.add(DepartmentHead(department_id=unit, user_id=user.id, is_primary=is_primary))
                    if is_primary:
                        primaries.add(unit)
                elif bool(primary) != link.is_primary:
                    # Отметка «(основной)» из файла по решению администратора
                    if primary:
                        db.execute(update(DepartmentHead).where(DepartmentHead.department_id == unit,
                                                                DepartmentHead.is_primary.is_(True))
                                   .values(is_primary=False), execution_options={"synchronize_session": "fetch"})
                        primaries.add(unit)
                    else:
                        primaries.discard(unit)
                    link.is_primary = bool(primary)
                touched_units.add(unit)
                db.flush()
        after_snap_department = before_snap.path_text(user.department_id) if user.department_id in before_snap.units \
            else (path_text(final.get("department")) or None)
        after = {"full_name": user.full_name, "email": user.email, "username": user.username,
                 "position": user.position, "phone": user.phone, "role": user.role,
                 "access_profile": final.get("access_profile") if "access_profile" in touched or created
                 else before["access_profile"],
                 "is_active": user.is_active, "reports_to_none": user.reports_to_none,
                 "department": after_snap_department or None, "manager_id": user.manager_id}
        if created:
            audit.record(db, actor, entity_type="user", entity_id=user.id, action="org_import",
                         summary=f"Создан сотрудник {user.full_name} ({comment})",
                         after={k: v for k, v in after.items() if v not in (None, "")}, request=request)
        else:
            b, a = audit.diff(before, after)
            if a or "heads" in touched:
                audit.record(db, actor, entity_type="user", entity_id=user.id, action="org_import",
                             summary=f"Изменён сотрудник {user.full_name} ({comment})", before=b or None,
                             after=a or {"heads": _text("heads", final.get("heads"))}, request=request)
    normalize_single_heads(db, touched_units, primaries)
    org_admin.check_reporting_cycles(db, before_snap)
    summary = result["summary"]
    audit.record(db, actor, entity_type="org_import", action="employees",
                 summary=f"Загружены сотрудники: создано {summary['create']}, изменено {summary['update']}, "
                         f"подразделений создано {summary['create_departments']}", after=summary, request=request)
    db.flush()
    mapping = {e.final["email"]: e.user.id for e in plan.entries if e.user is not None and e.final.get("email")}
    return {**result, "applied": True, "user_ids": mapping}, True
