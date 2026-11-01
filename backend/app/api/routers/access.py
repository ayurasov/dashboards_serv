"""Модель доступа 2.0 (ADR-0009): справочник измерений и профили доступа."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...models import AccessProfile, User
from ...schemas.access import AccessMetaOut, ProfileCreateIn, ProfileOut, ProfilePatchIn
from ...schemas.common import Ok
from ...services import access
from ..deps import active_user, require_capability

router = APIRouter(prefix="/api/access", tags=["Доступ"])
manage = require_capability("users.manage")


def _out(profile: AccessProfile, users_count: int) -> ProfileOut:
    out = ProfileOut.model_validate(profile)
    out.users_count = users_count
    return out


@router.get("/meta", response_model=AccessMetaOut, summary="Справочник измерений доступа")
def meta(_: User = Depends(active_user)):
    """Классы данных с пояснениями, области структуры, измерения, уровни доступа, полномочия, службы."""
    return access.meta()


@router.get("/profiles", response_model=list[ProfileOut], summary="Профили доступа")
def list_profiles(db: Session = Depends(get_db), _: User = Depends(manage)):
    return [_out(p, count) for p, count in access.list_profiles(db)]


@router.post("/profiles", response_model=ProfileOut, status_code=201, summary="Создать профиль доступа")
def create_profile(body: ProfileCreateIn, request: Request, db: Session = Depends(get_db),
                   actor: User = Depends(manage)):
    profile = access.create_profile(db, actor, body.model_dump(), request)
    db.commit()
    return _out(profile, 0)


@router.get("/profiles/{profile_id}", response_model=ProfileOut, summary="Профиль доступа")
def get_profile(profile_id: int, db: Session = Depends(get_db), _: User = Depends(manage)):
    profile = access.get_profile(db, profile_id)
    return _out(profile, access.profile_users_count(db).get(profile.id, 0))


@router.patch("/profiles/{profile_id}", response_model=ProfileOut, summary="Изменить профиль доступа")
def update_profile(profile_id: int, body: ProfilePatchIn, request: Request, db: Session = Depends(get_db),
                   actor: User = Depends(manage)):
    """Встроенные профили тоже изменяются; ключ профиля не меняется. Изменение действует на всех
    пользователей с этим профилем сразу."""
    profile = access.update_profile(db, actor, access.get_profile(db, profile_id),
                                    body.model_dump(exclude_unset=True), request)
    db.commit()
    return _out(profile, access.profile_users_count(db).get(profile.id, 0))


@router.delete("/profiles/{profile_id}", response_model=Ok, summary="Удалить профиль доступа")
def delete_profile(profile_id: int, request: Request, db: Session = Depends(get_db), actor: User = Depends(manage)):
    """Встроенный профиль не удаляется; назначенный пользователям — 409 с их числом."""
    profile = access.get_profile(db, profile_id)
    access.delete_profile(db, actor, profile, request)
    db.commit()
    return Ok(message=f"Профиль «{profile.name}» удалён")
