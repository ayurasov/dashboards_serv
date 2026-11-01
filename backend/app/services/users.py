"""Пользователи: сериализация и операции администратора."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import ValidationFailed
from ..models import Department, ServiceAccess, User
from ..schemas.users import AccessIn, AccessOut, DepartmentOut, UserOut
from .registry import SERVICE_BY_KEY


def serialize_user(user: User) -> UserOut:
    return UserOut(
        id=user.id, username=user.username, full_name=user.full_name, email=user.email,
        position=user.position, phone=user.phone, role=user.role, is_active=user.is_active,
        must_change_password=user.must_change_password, created_at=user.created_at,
        last_login_at=user.last_login_at,
        departments=[DepartmentOut.model_validate(d) for d in user.departments],
        access=[] if user.is_admin else [AccessOut.model_validate(a) for a in user.access],
        has_avatar=bool(user.avatar),
    )


def resolve_departments(db: Session, ids: list[int]) -> list[Department]:
    if not ids:
        return []
    found = list(db.scalars(select(Department).where(Department.id.in_(ids))))
    missing = set(ids) - {d.id for d in found}
    if missing:
        raise ValidationFailed(f"Подразделение не найдено: {', '.join(map(str, sorted(missing)))}")
    return found


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
        scope = row.department_scope and row.level == "viewer"
        if item is None:
            user.access.append(ServiceAccess(service_key=row.service_key, level=row.level,
                                             department_scope=scope, granted_by_id=granted_by.id))
        elif item.level != row.level or item.department_scope != scope:
            item.level = row.level
            item.department_scope = scope
            item.granted_by_id = granted_by.id
    db.flush()


def access_snapshot(user: User) -> dict[str, str]:
    return {a.service_key: a.level + (" (свои подразделения)" if a.department_scope else "") for a in user.access}


def active_admins_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True)))
