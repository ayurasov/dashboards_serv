"""Пользователи: сериализация, список с фильтрами и сводкой, операции администрирования и доступ
пользователя (ADR-0008, ADR-0009). Подход todo-planner: полномочие users.manage управляет всеми,
кроме администраторов; роль администратора и полномочия назначает только администратор."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from ..core.config import settings
from ..core.db import utcnow
from ..core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from ..core.security import generate_password, hash_password
from ..models import AccessProfile, Department, ServiceAccess, User
from ..schemas.users import (
    AccessIn,
    AccessOut,
    DepartmentOut,
    ManagerRef,
    ProfileRef,
    UnitRef,
    UserOut,
    UsersSummary,
)
from . import access, audit, ldap_auth, org, sessions
from .registry import CAPABILITIES, ORG_SCOPE_LABELS, SERVICE_BY_KEY, SERVICE_KEYS

PATH_SEPARATOR = " / "
STATUSES = ("active", "disabled", "no_access")


# ---------------------------------------------------------------- сериализация

def _snapshot_for(user: User) -> org.OrgSnapshot | None:
    db = object_session(user)
    return org.snapshot(db) if db is not None else None


def unit_ref(snap: org.OrgSnapshot | None, unit_id: int | None, fallback: Department | None = None) -> UnitRef | None:
    """Подразделение с путём от корня; без снимка структуры — только название."""
    if unit_id is None:
        return None
    unit = snap.units.get(unit_id) if snap is not None else None
    if unit is None:
        return UnitRef(id=fallback.id, name=fallback.name, path=fallback.name) if fallback is not None else None
    return UnitRef(id=unit.id, name=unit.name, path=PATH_SEPARATOR.join(snap.path_names(unit.id)))


def unit_refs(snap: org.OrgSnapshot, unit_ids: Iterable[int]) -> list[UnitRef]:
    refs = [ref for u in unit_ids if (ref := unit_ref(snap, u)) is not None]
    return sorted(refs, key=lambda r: r.path.casefold())


def user_status(user: User) -> str:
    """«Отключён»; «Без доступа» — активная локальная учётная запись без пароля (например, загружена
    списком); иначе «Активен». Учётной записи домена пароль системы не нужен."""
    if not user.is_active:
        return "disabled"
    if user.auth_source != "ldap" and not user.password_hash:
        return "no_access"
    return "active"


def _manager_ref(snap: org.OrgSnapshot | None, user: User) -> ManagerRef | None:
    if snap is None:
        return None
    manager_id, source = snap.direct_manager(user.id)
    person = snap.people.get(manager_id) if manager_id is not None else None
    if person is None:
        return None
    return ManagerRef(id=person.id, username=person.username, full_name=person.full_name, source=source)


def profile_ref(profile: AccessProfile | None) -> ProfileRef | None:
    return ProfileRef(id=profile.id, key=profile.key, name=profile.name) if profile is not None else None


def serialize_user(user: User, snap: org.OrgSnapshot | None = None) -> UserOut:
    snap = snap if snap is not None else _snapshot_for(user)
    return UserOut(
        id=user.id, username=user.username, full_name=user.full_name, email=user.email,
        position=user.position, phone=user.phone, role=user.role, is_active=user.is_active,
        status=user_status(user), must_change_password=user.must_change_password, created_at=user.created_at,
        last_login_at=user.last_login_at,
        department=unit_ref(snap, user.department_id, user.department), manager=_manager_ref(snap, user),
        profile=profile_ref(user.access_profile), capabilities=list(user.capabilities or []),
        auth_source=user.auth_source or "local", has_password=user.has_password, auth_linked_at=user.auth_linked_at,
        departments=[DepartmentOut.model_validate(d) for d in user_departments(user)],
        access=[] if user.is_admin else service_rows(user),
        has_avatar=bool(user.avatar),
    )


def service_rows(user: User) -> list[AccessOut]:
    """Строки доступа к службам в порядке справочника служб."""
    rows = sorted(user.access, key=lambda a: SERVICE_KEYS.index(a.service_key) if a.service_key in SERVICE_KEYS
                  else len(SERVICE_KEYS))
    return [AccessOut.model_validate(a) for a in rows]


def user_departments(user: User) -> list[Department]:
    """Основное подразделение и дополнительные подразделения области доступа."""
    home = [user.department] if user.department is not None else []
    return home + [d for d in user.access_units if d.id != user.department_id]


def set_departments(user: User, departments: list[Department]) -> None:
    """Первое — основное подразделение, остальные — дополнительная область доступа (как в 0.1.0)."""
    user.department_id = departments[0].id if departments else None
    user.department = departments[0] if departments else None
    user.access_units = departments[1:]


def resolve_departments(db: Session, ids: list[int]) -> list[Department]:
    if not ids:
        return []
    found = {d.id: d for d in db.scalars(select(Department).where(Department.id.in_(ids)))}
    missing = set(ids) - set(found)
    if missing:
        raise ValidationFailed(f"Подразделение не найдено: {', '.join(map(str, sorted(missing)))}")
    return [found[i] for i in dict.fromkeys(ids)]


def _department(db: Session, department_id: int | None, field: str = "department_id") -> Department | None:
    if department_id is None:
        return None
    dept = db.get(Department, department_id)
    if dept is None:
        raise ValidationFailed("Подразделение не найдено", fields={field: "Нет такого подразделения"})
    return dept


def _profile(db: Session, profile_id: int | None, field: str = "profile_id") -> AccessProfile | None:
    if profile_id is None:
        return None
    profile = db.get(AccessProfile, profile_id)
    if profile is None:
        raise ValidationFailed("Профиль доступа не найден", fields={field: "Нет такого профиля"})
    return profile


def _capabilities(values: list[str]) -> list[str]:
    unknown = sorted(set(values) - set(CAPABILITIES))
    if unknown:
        raise ValidationFailed(f"Неизвестные полномочия: {', '.join(unknown)}",
                               fields={"capabilities": f"Допустимо: {', '.join(CAPABILITIES)}"})
    return list(dict.fromkeys(values))


def replace_access(db: Session, user: User, rows: list[AccessIn], granted_by: User) -> None:
    seen: set[str] = set()
    for row in rows:
        if row.service_key not in SERVICE_BY_KEY:
            raise ValidationFailed(f"Неизвестная служба: {row.service_key}")
        if row.service_key in seen:
            raise ValidationFailed(f"Служба указана дважды: {SERVICE_BY_KEY[row.service_key].title}")
        seen.add(row.service_key)
    current = {a.service_key: a for a in user.access}
    for key, item in list(current.items()):
        if key not in seen:
            user.access.remove(item)
    for row in rows:
        item = current.get(row.service_key)
        scope = row.org_scope or ("branch" if row.department_scope else None)
        if item is None:
            user.access.append(ServiceAccess(service_key=row.service_key, level=row.level,
                                             org_scope=scope, granted_by_id=granted_by.id))
        elif item.level != row.level or item.org_scope != scope:
            item.level = row.level
            item.org_scope = scope
            item.granted_by_id = granted_by.id
    db.flush()


def access_snapshot(user: User) -> dict[str, str]:
    return {a.service_key: a.level + (f" ({ORG_SCOPE_LABELS[a.org_scope].lower()})" if a.org_scope else "")
            for a in user.access}


def active_admins_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True)))


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("Пользователь не найден")
    return user


def normalize_email(value) -> str | None:
    return (value or "").strip().lower() or None


def email_taken(db: Session, email: str | None, user_id: int | None = None) -> bool:
    if not email:
        return False
    stmt = select(User.id).where(func.lower(User.email) == email.lower())
    if user_id:
        stmt = stmt.where(User.id != user_id)
    return db.scalar(stmt.limit(1)) is not None


def _check_email(db: Session, email: str | None, user_id: int | None = None) -> None:
    if email_taken(db, email, user_id):
        raise ValidationFailed("Этот e-mail уже используется", fields={"email": "Уже используется"})


def find_local(db: Session, login: str) -> User | None:
    """Учётная запись по логину без учёта регистра; если введён email — по email (единственное совпадение)."""
    user = db.scalar(select(User).where(func.lower(User.username) == login.lower()))
    if user is None and "@" in login:
        matches = list(db.scalars(select(User).where(func.lower(User.email) == login.lower()).limit(2)))
        user = matches[0] if len(matches) == 1 else None
    return user


def validate_password(password: str, user: User | None = None, field: str = "new_password") -> None:
    if len(password) < settings.password_min_length:
        raise ValidationFailed(f"Пароль должен быть не короче {settings.password_min_length} символов",
                               fields={field: "Слишком короткий пароль"})
    if len(password.encode("utf-8")) > 72:
        raise ValidationFailed("Пароль слишком длинный", fields={field: "Не больше 72 байт"})
    if password.isdigit() or password.isalpha():
        raise ValidationFailed("Пароль должен содержать и буквы, и цифры или другие символы",
                               fields={field: "Добавьте цифры или символы"})
    if user and password.lower() in (user.username.lower(), (user.email or "").lower()):
        raise ValidationFailed("Пароль не должен совпадать с логином", fields={field: "Совпадает с логином"})


# ---------------------------------------------------------------- список

@dataclass(frozen=True)
class UserFilters:
    search: str = ""
    role: str = ""
    status: str = ""
    department: str = ""        # id, «none» — без подразделения
    profile: str = ""           # id, «none» — индивидуальная настройка
    auth_source: str = ""
    service: str = ""           # совместимость с 0.1.0: есть доступ к службе


def _id_filter(value: str, field: str) -> int | None:
    try:
        return int(value)
    except ValueError as exc:
        raise ValidationFailed("Укажите номер или none", fields={field: "Недопустимое значение"}) from exc


def summary(users: list[User]) -> UsersSummary:
    statuses = [user_status(u) for u in users]
    return UsersSummary(total=len(users), active=sum(1 for u in users if u.is_active),
                        disabled=statuses.count("disabled"), no_access=statuses.count("no_access"),
                        ldap=sum(1 for u in users if u.auth_source == "ldap"),
                        admins=sum(1 for u in users if u.is_admin))


def list_users(db: Session, f: UserFilters) -> tuple[list[UserOut], UsersSummary]:
    """Пользователи по фильтрам и сводка по всем. Поиск без учёта регистра (и для кириллицы) — по ФИО,
    логину, email, должности и пути подразделения; выборка небольшая, фильтры — в Python."""
    users = list(db.scalars(select(User).order_by(User.full_name, User.id)))
    snap = org.snapshot(db)
    head = summary(users)
    department = None if f.department in ("", "none") else _id_filter(f.department, "department_id")
    profile = None if f.profile in ("", "none") else _id_filter(f.profile, "profile_id")
    needle = " ".join(f.search.split()).casefold()

    def path(u: User) -> str:
        ref = unit_ref(snap, u.department_id, u.department)
        return ref.path if ref else ""

    def keep(u: User) -> bool:
        if f.role and u.role != f.role:
            return False
        if f.status and user_status(u) != f.status and not (f.status == "active" and u.is_active):
            return False
        if f.department == "none" and u.department_id is not None:
            return False
        if department is not None and u.department_id != department:
            return False
        if f.profile == "none" and u.access_profile_id is not None:
            return False
        if profile is not None and u.access_profile_id != profile:
            return False
        if f.auth_source and (u.auth_source or "local") != f.auth_source:
            return False
        if f.service and not (u.is_admin or access.effective(u).level(f.service)):
            return False
        if needle:
            haystack = " ".join(filter(None, (u.full_name, u.username, u.email, u.position, path(u)))).casefold()
            return needle in haystack
        return True

    return [serialize_user(u, snap) for u in users if keep(u)], head


# ---------------------------------------------------------------- права администрирования

def ensure_can_manage(actor: User, target: User) -> None:
    """users.manage управляет всеми, кроме администраторов: их меняет только администратор."""
    if target.is_admin and not actor.is_admin:
        raise Forbidden("Изменять администратора может только администратор")


def _ensure_admin_only(actor: User, *, role: str | None = None, capabilities: list[str] | None = None,
                       current: list[str] | None = None) -> None:
    if role == "admin" and not actor.is_admin:
        raise Forbidden("Роль администратора назначает только администратор")
    if capabilities is not None and set(capabilities) != set(current or []) and not actor.is_admin:
        raise Forbidden("Полномочия выдаёт только администратор")


def _ldap_enabled() -> bool:
    return ldap_auth.current_config() is not None


def _can_match_directory(user: User) -> bool:
    """Учётную запись домена каталог узнаёт по objectGUID, идентификатору синхронизации с AD или email."""
    return bool(user.email or user.auth_external_id or (user.org_source == "ad" and user.external_id))


def _set_password(user: User, password: str, *, temporary: bool) -> None:
    user.password_hash = hash_password(password)
    user.must_change_password = temporary
    user.password_changed_at = utcnow()


def _to_local(user: User) -> bool:
    """Учётная запись домена переводится на пароль системы; True — способ входа изменился."""
    if user.auth_source != "ldap":
        return False
    user.auth_source = "local"
    user.auth_linked_at = None
    return True


def _to_ldap(user: User) -> None:
    """Вход по учётной записи домена: пароль системы удаляется (его проверяет каталог)."""
    user.auth_source = "ldap"
    user.password_hash = None
    user.must_change_password = False


def _card(user: User) -> dict:
    return {"full_name": user.full_name, "email": user.email, "position": user.position, "phone": user.phone,
            "role": user.role, "is_active": user.is_active, "capabilities": list(user.capabilities or []),
            "department": user.department.name if user.department else None,
            "departments": [d.name for d in user_departments(user)],
            "profile": user.access_profile.key if user.access_profile else None,
            "auth_source": user.auth_source}


# ---------------------------------------------------------------- создание и изменение

def create_user(db: Session, actor: User, body, request: Request | None = None) -> tuple[User, str | None]:
    """Новая учётная запись; второй элемент — временный пароль (показывается один раз)."""
    _ensure_admin_only(actor, role=body.role, capabilities=body.capabilities)
    if db.scalar(select(User.id).where(func.lower(User.username) == body.username.lower())):
        raise Conflict("Пользователь с таким логином уже существует", fields={"username": "Логин занят"})
    email = normalize_email(body.email)
    _check_email(db, email)
    user = User(username=body.username, full_name=body.full_name, email=email, position=body.position or None,
                phone=body.phone or None, role=body.role, auth_source="local",
                capabilities=_capabilities(body.capabilities))
    temporary = None
    if body.access_method == "password":
        if body.password:
            validate_password(body.password, field="password")
            _set_password(user, body.password, temporary=True)
        else:
            temporary = generate_password()
            _set_password(user, temporary, temporary=True)
    elif body.password:
        raise ValidationFailed("Пароль задаётся только при входе по паролю системы",
                               fields={"password": "Не нужен для выбранного способа входа"})
    elif body.access_method == "ldap":
        if not _ldap_enabled():
            raise ValidationFailed("Вход по домену не включён — выберите вход по паролю системы",
                                   fields={"access_method": "Вход по домену не включён"})
        if not email:
            raise ValidationFailed("Для входа по домену укажите e-mail: по нему учётная запись сопоставляется "
                                   "с каталогом при первом входе", fields={"email": "Нужен для входа по домену"})
        user.auth_source = "ldap"
    set_departments(user, resolve_departments(db, body.department_ids))
    if body.department_id is not None:
        user.department = _department(db, body.department_id)
        user.department_id = user.department.id
    user.access_profile = _profile(db, body.profile_id)
    db.add(user)
    db.flush()
    replace_access(db, user, body.access, actor)
    method = {"password": "пароль системы", "ldap": "учётная запись домена", "none": "без доступа"}
    audit.record(db, actor, entity_type="user", entity_id=user.id, action="create",
                 summary=f"Создан пользователь {user.username} ({method[body.access_method]})",
                 after={"username": user.username, **_card(user), "access": access_snapshot(user)}, request=request)
    return user, temporary


def update_user(db: Session, actor: User, user: User, fields: dict, request: Request | None = None) -> User:
    """Изменение карточки. Защиты: себя не отключить и не лишить роли; администратора меняет только
    администратор; роль администратора и полномочия — только администратор; последний активный
    администратор остаётся."""
    ensure_can_manage(actor, user)
    _ensure_admin_only(actor, role=fields.get("role"), capabilities=fields.get("capabilities"),
                       current=user.capabilities)
    before = _card(user)
    demoting = fields.get("role") == "user" and user.is_admin
    disabling = fields.get("is_active") is False and user.is_active
    if user.id == actor.id and (demoting or disabling):
        raise ValidationFailed("Нельзя снять с себя роль администратора или отключить свою учётную запись")
    if (demoting or disabling) and user.is_admin and active_admins_count(db) <= 1:
        raise ValidationFailed("В системе должен остаться хотя бы один активный администратор")
    if "email" in fields:
        email = normalize_email(fields["email"])
        _check_email(db, email, user.id)
        user.email = email
    if fields.get("full_name") is not None:
        user.full_name = fields["full_name"].strip() or user.full_name
    for key in ("position", "phone"):
        if key in fields:
            setattr(user, key, (fields[key] or "").strip() or None)
    for key in ("role", "is_active"):
        if fields.get(key) is not None:
            setattr(user, key, fields[key])
    if fields.get("capabilities") is not None:
        user.capabilities = _capabilities(fields["capabilities"])
    if fields.get("department_ids") is not None:
        set_departments(user, resolve_departments(db, fields["department_ids"]))
    if "department_id" in fields:
        user.department = _department(db, fields["department_id"])
        user.department_id = user.department.id if user.department else None
    if "profile_id" in fields:
        user.access_profile = _profile(db, fields["profile_id"])
    if disabling:
        sessions.revoke_all(db, user.id)
    b, a = audit.diff(before, _card(user))
    if a:
        audit.record(db, actor, entity_type="user", entity_id=user.id, action="update",
                     summary=f"Изменён пользователь {user.username}", before=b, after=a, request=request)
    db.flush()
    return user


def grant_access(db: Session, actor: User, user: User, method: str, request: Request | None = None) -> str | None:
    """«Выдать доступ» (ADR-0008): включить учётную запись и выбрать способ входа. password — пароль
    системы (временный, если пароля нет или сотрудник входил по домену); ldap — вход по домену.
    Возвращает временный пароль, если он создан."""
    ensure_can_manage(actor, user)
    before = {"is_active": user.is_active, "auth_source": user.auth_source, "has_password": user.has_password}
    temporary = None
    if method == "ldap":
        if not _ldap_enabled():
            raise ValidationFailed("Вход по домену не включён — выдайте пароль системы",
                                   fields={"method": "Вход по домену не включён"})
        if not _can_match_directory(user):
            raise ValidationFailed("Для входа по домену укажите сотруднику e-mail: по нему учётная запись "
                                   "сопоставляется с каталогом", fields={"email": "Нужен для входа по домену"})
        _to_ldap(user)
    elif user.auth_source == "ldap" or not user.password_hash:
        _to_local(user)
        temporary = generate_password()
        _set_password(user, temporary, temporary=True)
    user.is_active = True
    after = {"is_active": user.is_active, "auth_source": user.auth_source, "has_password": user.has_password}
    b, a = audit.diff(before, after)
    if a or temporary:
        how = "вход по домену" if method == "ldap" else "временный пароль" if temporary else "пароль системы"
        audit.record(db, actor, entity_type="user", entity_id=user.id, action="grant",
                     summary=f"Выдан доступ пользователю {user.username}: {how}", before=b, after=a, request=request)
    db.flush()
    return temporary


def reset_password(db: Session, actor: User, user: User, request: Request | None = None) -> str:
    """Временный пароль системы; сотрудник, входивший по домену, переводится на пароль системы."""
    ensure_can_manage(actor, user)
    switched = _to_local(user)
    password = generate_password()
    _set_password(user, password, temporary=True)
    sessions.revoke_all(db, user.id)
    summary_text = f"Выдан временный пароль пользователю {user.username}"
    if switched:
        summary_text += " (вход по домену заменён паролем системы)"
    audit.record(db, actor, entity_type="user", entity_id=user.id, action="password", summary=summary_text,
                 before={"auth_source": "ldap"} if switched else None,
                 after={"auth_source": "local"} if switched else None, request=request)
    db.flush()
    return password


def delete_user(db: Session, actor: User, user: User, request: Request | None = None) -> None:
    if user.id == actor.id:
        raise ValidationFailed("Нельзя удалить свою учётную запись")
    if user.is_admin and not actor.is_admin:
        raise Forbidden("Удалять администратора может только администратор")
    if user.is_admin and user.is_active and active_admins_count(db) <= 1:
        raise ValidationFailed("Нельзя удалить последнего администратора")
    audit.record(db, actor, entity_type="user", entity_id=user.id, action="delete",
                 summary=f"Удалён пользователь {user.username}",
                 before={"username": user.username, "full_name": user.full_name, "role": user.role},
                 request=request)
    db.delete(user)
    db.flush()


# ---------------------------------------------------------------- доступ пользователя (ADR-0009)

def access_policy(db: Session, user: User) -> dict:
    """Профиль, личные настройки, строки служб, дополнительные подразделения и действующий доступ."""
    snap = org.snapshot(db)
    access.invalidate(user)
    eff = access.effective(user)
    scope = access.scope_units(db, user)
    return {
        "user_id": user.id, "is_admin": user.is_admin, "profile": profile_ref(user.access_profile),
        "overrides": dict(user.access_overrides or {}),
        "services": service_rows(user),
        "extra_units": unit_refs(snap, [d.id for d in user.access_units]),
        "effective": eff.as_dict(),
        "scope_units": None if scope is None else unit_refs(snap, scope),
    }


def _policy_snapshot(user: User) -> dict:
    return {"profile": user.access_profile.key if user.access_profile else None,
            "overrides": dict(user.access_overrides or {}), "services": access_snapshot(user),
            "extra_units": sorted(d.name for d in user.access_units)}


def set_access_policy(db: Session, actor: User, user: User, fields: dict, request: Request | None = None) -> None:
    """Меняет только переданные части доступа: profile_id, overrides, services, extra_unit_ids."""
    ensure_can_manage(actor, user)
    before = _policy_snapshot(user)
    if "profile_id" in fields:
        user.access_profile = _profile(db, fields["profile_id"])
    if fields.get("overrides") is not None:
        user.access_overrides = access.normalize_overrides(fields["overrides"])
    if fields.get("services") is not None:
        rows = [row if isinstance(row, AccessIn) else AccessIn.model_validate(row) for row in fields["services"]]
        replace_access(db, user, rows, actor)
    if fields.get("extra_unit_ids") is not None:
        user.access_units = resolve_departments(db, fields["extra_unit_ids"])
    db.flush()
    after = _policy_snapshot(user)
    b, a = audit.diff(before, after)
    if a:
        audit.record(db, actor, entity_type="user_access", entity_id=user.id, action="update",
                     summary=f"Изменён доступ пользователя {user.username}", before=b, after=a, request=request)
    access.invalidate(user)
