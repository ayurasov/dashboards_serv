"""Администрирование: пользователи, доступ к службам, подразделения."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...core.db import get_db, utcnow
from ...core.errors import Conflict, NotFound, ValidationFailed
from ...core.security import generate_password, hash_password
from ...models import Department, User
from ...schemas.common import Ok
from ...schemas.users import (
    AccessIn,
    DepartmentIn,
    DepartmentOut,
    PasswordResetOut,
    UserCreatedOut,
    UserCreateIn,
    UserOut,
    UserUpdateIn,
)
from ...services import audit, sessions
from ...services.users import (
    access_snapshot,
    active_admins_count,
    replace_access,
    resolve_departments,
    serialize_user,
    set_departments,
    user_departments,
)
from ..deps import require_admin
from .auth import validate_password

router = APIRouter(prefix="/api/users", tags=["Пользователи"])
departments_router = APIRouter(prefix="/api/departments", tags=["Подразделения"])


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("Пользователь не найден")
    return user


def _email(value) -> str | None:
    return (value or "").strip().lower() or None


def _check_email(db: Session, email: str | None, user_id: int | None = None) -> None:
    if not email:
        return
    stmt = select(User.id).where(func.lower(User.email) == email)
    if user_id:
        stmt = stmt.where(User.id != user_id)
    if db.scalar(stmt):
        raise ValidationFailed("Этот e-mail уже используется", fields={"email": "Уже используется"})


@router.get("", response_model=list[UserOut], summary="Список пользователей")
def list_users(search: str = "", status: str = Query("all", pattern="^(all|active|disabled)$"),
               service: str = "", db: Session = Depends(get_db), _: User = Depends(require_admin)):
    stmt = select(User).order_by(User.full_name)
    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.username).like(like), func.lower(User.full_name).like(like),
                              func.lower(func.coalesce(User.email, "")).like(like)))
    if status == "active":
        stmt = stmt.where(User.is_active.is_(True))
    elif status == "disabled":
        stmt = stmt.where(User.is_active.is_(False))
    users = list(db.scalars(stmt))
    if service:
        users = [u for u in users if u.is_admin or any(a.service_key == service for a in u.access)]
    return [serialize_user(u) for u in users]


@router.post("", response_model=UserCreatedOut, status_code=201, summary="Создать пользователя")
def create_user(body: UserCreateIn, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    if db.scalar(select(User.id).where(func.lower(User.username) == body.username.lower())):
        raise Conflict("Пользователь с таким логином уже существует", fields={"username": "Логин занят"})
    email = _email(body.email)
    _check_email(db, email)
    temporary = None
    if body.password:
        validate_password(body.password, field="password")
        password = body.password
    else:
        password = temporary = generate_password()
    user = User(username=body.username, full_name=body.full_name, email=email, position=body.position or None,
                phone=body.phone or None, role=body.role, password_hash=hash_password(password),
                must_change_password=True, password_changed_at=utcnow())
    set_departments(user, resolve_departments(db, body.department_ids))
    db.add(user)
    db.flush()
    replace_access(db, user, body.access, admin)
    audit.record(db, admin, entity_type="user", entity_id=user.id, action="create",
                 summary=f"Создан пользователь {user.username}",
                 after={"username": user.username, "full_name": user.full_name, "role": user.role,
                        "access": access_snapshot(user)}, request=request)
    db.commit()
    return UserCreatedOut(user=serialize_user(user), temporary_password=temporary)


@router.get("/{user_id}", response_model=UserOut, summary="Карточка пользователя")
def get_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return serialize_user(_get_user(db, user_id))


@router.patch("/{user_id}", response_model=UserOut, summary="Изменить пользователя")
def update_user(user_id: int, body: UserUpdateIn, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = _get_user(db, user_id)
    fields = body.model_dump(exclude_unset=True)
    before = {"full_name": user.full_name, "email": user.email, "position": user.position, "phone": user.phone,
              "role": user.role, "is_active": user.is_active, "departments": [d.name for d in user_departments(user)]}
    demoting = fields.get("role") == "user" and user.is_admin
    disabling = fields.get("is_active") is False and user.is_active
    if user.id == admin.id and (demoting or disabling):
        raise ValidationFailed("Нельзя снять с себя роль администратора или отключить свою учётную запись")
    if (demoting or disabling) and user.is_admin and active_admins_count(db) <= 1:
        raise ValidationFailed("В системе должен остаться хотя бы один активный администратор")
    if "email" in fields:
        email = _email(fields["email"])
        _check_email(db, email, user.id)
        user.email = email
    for key in ("full_name", "position", "phone", "role", "is_active"):
        if key in fields and fields[key] is not None:
            setattr(user, key, fields[key] if key in ("role", "is_active") else (fields[key] or "").strip() or None)
    if user.full_name is None:
        user.full_name = before["full_name"]
    if body.department_ids is not None:
        set_departments(user, resolve_departments(db, body.department_ids))
    if disabling:
        sessions.revoke_all(db, user.id)
    after = {"full_name": user.full_name, "email": user.email, "position": user.position, "phone": user.phone,
             "role": user.role, "is_active": user.is_active, "departments": [d.name for d in user_departments(user)]}
    b, a = audit.diff(before, after)
    if a:
        audit.record(db, admin, entity_type="user", entity_id=user.id, action="update",
                     summary=f"Изменён пользователь {user.username}", before=b, after=a, request=request)
    db.commit()
    return serialize_user(user)


@router.put("/{user_id}/access", response_model=UserOut, summary="Задать доступ к службам")
def set_access(user_id: int, body: list[AccessIn], request: Request, db: Session = Depends(get_db),
               admin: User = Depends(require_admin)):
    user = _get_user(db, user_id)
    before = access_snapshot(user)
    replace_access(db, user, body, admin)
    after = access_snapshot(user)
    if before != after:
        audit.record(db, admin, entity_type="user_access", entity_id=user.id, action="update",
                     summary=f"Изменён доступ пользователя {user.username}", before=before, after=after,
                     request=request)
    db.commit()
    return serialize_user(user)


@router.post("/{user_id}/reset-password", response_model=PasswordResetOut, summary="Выдать временный пароль")
def reset_password(user_id: int, request: Request, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    user = _get_user(db, user_id)
    password = generate_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.password_changed_at = utcnow()
    sessions.revoke_all(db, user.id)
    audit.record(db, admin, entity_type="user", entity_id=user.id, action="password",
                 summary=f"Выдан временный пароль пользователю {user.username}", request=request)
    db.commit()
    return PasswordResetOut(temporary_password=password)


@router.delete("/{user_id}", response_model=Ok, summary="Удалить пользователя")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = _get_user(db, user_id)
    if user.id == admin.id:
        raise ValidationFailed("Нельзя удалить свою учётную запись")
    if user.is_admin and user.is_active and active_admins_count(db) <= 1:
        raise ValidationFailed("Нельзя удалить последнего администратора")
    audit.record(db, admin, entity_type="user", entity_id=user.id, action="delete",
                 summary=f"Удалён пользователь {user.username}",
                 before={"username": user.username, "full_name": user.full_name, "role": user.role},
                 request=request)
    db.delete(user)
    db.commit()
    return Ok(message="Пользователь удалён")


# ---------- Подразделения ----------

@departments_router.get("", response_model=list[DepartmentOut], summary="Подразделения")
def list_departments(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return list(db.scalars(select(Department).order_by(Department.name)))


def _check_department(db: Session, body: DepartmentIn, dept_id: int | None = None) -> None:
    for column, value, label in ((Department.name, body.name, "Название"), (Department.code, body.code, "Код")):
        stmt = select(Department.id).where(func.lower(column) == value.lower())
        if dept_id:
            stmt = stmt.where(Department.id != dept_id)
        if db.scalar(stmt):
            raise Conflict(f"{label} подразделения уже используется")


@departments_router.post("", response_model=DepartmentOut, status_code=201, summary="Создать подразделение")
def create_department(body: DepartmentIn, request: Request, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    _check_department(db, body)
    dept = Department(name=body.name, code=body.code.upper())
    db.add(dept)
    db.flush()
    audit.record(db, admin, entity_type="department", entity_id=dept.id, action="create",
                 summary=f"Создано подразделение {dept.name}", after={"name": dept.name, "code": dept.code},
                 request=request)
    db.commit()
    return dept


@departments_router.put("/{dept_id}", response_model=DepartmentOut, summary="Изменить подразделение")
def update_department(dept_id: int, body: DepartmentIn, request: Request, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    dept = db.get(Department, dept_id)
    if dept is None:
        raise NotFound("Подразделение не найдено")
    _check_department(db, body, dept_id)
    before = {"name": dept.name, "code": dept.code}
    dept.name, dept.code = body.name, body.code.upper()
    b, a = audit.diff(before, {"name": dept.name, "code": dept.code})
    audit.record(db, admin, entity_type="department", entity_id=dept.id, action="update",
                 summary=f"Изменено подразделение {dept.name}", before=b, after=a, request=request)
    db.commit()
    return dept


@departments_router.delete("/{dept_id}", response_model=Ok, summary="Удалить подразделение")
def delete_department(dept_id: int, request: Request, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    dept = db.get(Department, dept_id)
    if dept is None:
        raise NotFound("Подразделение не найдено")
    audit.record(db, admin, entity_type="department", entity_id=dept.id, action="delete",
                 summary=f"Удалено подразделение {dept.name}", before={"name": dept.name, "code": dept.code},
                 request=request)
    db.delete(dept)
    db.commit()
    return Ok(message="Подразделение удалено")
