"""Администрирование пользователей и их доступа (ADR-0008, ADR-0009).

Полномочие users.manage (или роль администратора): все пользователи, кроме администраторов —
их, роль администратора и полномочия меняет только администратор."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...models import User
from ...schemas.access import AccessPolicyIn, AccessPolicyOut
from ...schemas.common import Ok
from ...schemas.users import (
    AccessIn,
    GrantAccessIn,
    PasswordResetOut,
    UserCreatedOut,
    UserCreateIn,
    UserListOut,
    UserOut,
    UserUpdateIn,
)
from ...services import users as users_service
from ...services.users import UserFilters, get_user, serialize_user
from ..deps import require_capability

router = APIRouter(prefix="/api/users", tags=["Пользователи"])
manage = require_capability("users.manage")


@router.get("", response_model=UserListOut, summary="Пользователи: поиск, фильтры и сводка")
def list_users(search: str = "", role: str = Query("", pattern="^(|admin|user)$"),
               status: str = Query("", pattern="^(|all|active|disabled|no_access)$"),
               department_id: str = "", profile_id: str = "",
               auth_source: str = Query("", pattern="^(|local|ldap)$"), service: str = "",
               db: Session = Depends(get_db), _: User = Depends(manage)):
    """status: active · disabled · no_access (активная локальная учётная запись без пароля);
    department_id и profile_id: номер или none (без подразделения · индивидуальная настройка).
    Сводка — по всем пользователям, без фильтров."""
    filters = UserFilters(search=search, role=role, status="" if status == "all" else status,
                          department=department_id.strip(), profile=profile_id.strip(), auth_source=auth_source,
                          service=service)
    items, summary = users_service.list_users(db, filters)
    return UserListOut(items=items, total=len(items), summary=summary)


@router.post("", response_model=UserCreatedOut, status_code=201, summary="Создать пользователя")
def create_user(body: UserCreateIn, request: Request, db: Session = Depends(get_db), actor: User = Depends(manage)):
    """access_method: password — пароль системы (без пароля — временный, возвращается один раз);
    ldap — вход по учётной записи домена (нужны включённый вход по домену и e-mail); none — без доступа."""
    user, temporary = users_service.create_user(db, actor, body, request)
    db.commit()
    return UserCreatedOut(user=serialize_user(user), temporary_password=temporary)


@router.get("/{user_id}", response_model=UserOut, summary="Карточка пользователя")
def get_one(user_id: int, db: Session = Depends(get_db), _: User = Depends(manage)):
    return serialize_user(get_user(db, user_id))


@router.patch("/{user_id}", response_model=UserOut, summary="Изменить пользователя")
def update_user(user_id: int, body: UserUpdateIn, request: Request, db: Session = Depends(get_db),
                actor: User = Depends(manage)):
    user = users_service.update_user(db, actor, get_user(db, user_id), body.model_dump(exclude_unset=True), request)
    db.commit()
    return serialize_user(user)


@router.get("/{user_id}/access", response_model=AccessPolicyOut, summary="Доступ пользователя")
def get_access(user_id: int, db: Session = Depends(get_db), _: User = Depends(manage)):
    return users_service.access_policy(db, get_user(db, user_id))


@router.put("/{user_id}/access", response_model=AccessPolicyOut, summary="Задать доступ пользователя")
def set_access(user_id: int, request: Request, body: AccessPolicyIn | list[AccessIn] = Body(...),
               db: Session = Depends(get_db), actor: User = Depends(manage)):
    """Меняются только переданные части: profile_id, overrides, services, extra_unit_ids.
    Совместимость с 0.1.0: список строк доступа к службам заменяет только строки служб."""
    fields = {"services": body} if isinstance(body, list) else body.model_dump(exclude_unset=True)
    user = get_user(db, user_id)
    users_service.set_access_policy(db, actor, user, fields, request)
    db.commit()
    return users_service.access_policy(db, user)


@router.post("/{user_id}/grant-access", response_model=UserCreatedOut, summary="Выдать доступ")
def grant_access(user_id: int, request: Request, body: GrantAccessIn | None = None, db: Session = Depends(get_db),
                 actor: User = Depends(manage)):
    """Включает учётную запись. method: password — пароль системы (временный, если пароля не было
    или сотрудник входил по домену); ldap — вход по учётной записи домена."""
    user = get_user(db, user_id)
    temporary = users_service.grant_access(db, actor, user, (body or GrantAccessIn()).method, request)
    db.commit()
    return UserCreatedOut(user=serialize_user(user), temporary_password=temporary)


@router.post("/{user_id}/reset-password", response_model=PasswordResetOut, summary="Выдать временный пароль")
def reset_password(user_id: int, request: Request, db: Session = Depends(get_db), actor: User = Depends(manage)):
    """Сотрудник, входивший по домену, переводится на пароль системы. Сессии пользователя завершаются."""
    user = get_user(db, user_id)
    password = users_service.reset_password(db, actor, user, request)
    db.commit()
    return PasswordResetOut(temporary_password=password, user=serialize_user(user))


@router.delete("/{user_id}", response_model=Ok, summary="Удалить пользователя")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db), actor: User = Depends(manage)):
    users_service.delete_user(db, actor, get_user(db, user_id), request)
    db.commit()
    return Ok(message="Пользователь удалён")
