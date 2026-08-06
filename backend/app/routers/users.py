"""User management router (admin only)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Department, RoleEnum, UserServiceAccess, SERVICE_KEYS, ACCESS_LEVELS
from ..security import hash_password
from ..deps import require_admin
from ..schemas import (
    UserCreate, UserUpdate, UserOut, DepartmentOut,
    UserServiceAccessIn, UserServiceAccessOut,
)
from ..audit import log_action

router = APIRouter(prefix="/api/users", tags=["users"])


def _apply_primary_service(db: Session, user_id: int, service_key: str | None):
    """The primary service is the one the user is responsible for, so it gets
    `edit_metrics`. An empty value leaves the access matrix alone."""
    key = (service_key or "").strip()
    if not key:
        return
    if key not in SERVICE_KEYS:
        raise HTTPException(400, f"Неизвестная служба: {key}")
    row = (db.query(UserServiceAccess)
           .filter(UserServiceAccess.user_id == user_id,
                   UserServiceAccess.service_key == key)
           .first())
    if row:
        row.access_level = "edit_metrics"
    else:
        db.add(UserServiceAccess(user_id=user_id, service_key=key, access_level="edit_metrics"))


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(User).order_by(User.username).all()


@router.post("", response_model=UserOut)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(400, "Пользователь с таким логином уже существует")
    try:
        role = RoleEnum(body.role)
    except ValueError:
        raise HTTPException(400, f"Неизвестная роль: {body.role}")
    user = User(username=body.username, full_name=body.full_name, email=body.email,
                position=body.position, phone=body.phone, avatar=body.avatar,
                role=role, hashed_password=hash_password(body.password),
                must_change_password=body.must_change_password)
    for did in body.department_ids:
        d = db.query(Department).get(did)
        if d:
            user.departments.append(d)
    db.add(user)
    db.flush()
    _apply_primary_service(db, user.id, body.primary_service)
    log_action(db, admin, "user", str(user.id), "create", after={"username": user.username, "role": user.role.value})
    db.commit()
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    before = {"full_name": user.full_name, "role": user.role.value, "is_active": user.is_active}
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.email is not None:
        user.email = body.email
    if body.position is not None:
        user.position = body.position
    if body.phone is not None:
        user.phone = body.phone
    if body.avatar is not None:
        user.avatar = body.avatar
    if body.primary_service is not None:
        _apply_primary_service(db, user.id, body.primary_service)
    if body.role is not None:
        try:
            user.role = RoleEnum(body.role)
        except ValueError:
            raise HTTPException(400, f"Неизвестная роль: {body.role}")
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        user.hashed_password = hash_password(body.password)
        user.must_change_password = True
    if body.department_ids is not None:
        user.departments = []
        for did in body.department_ids:
            d = db.query(Department).get(did)
            if d:
                user.departments.append(d)
    log_action(db, admin, "user", str(user.id), "update", before=before, after={"full_name": user.full_name, "role": user.role.value})
    db.commit()
    return user


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if user.id == admin.id:
        raise HTTPException(400, "Нельзя удалить самого себя")
    log_action(db, admin, "user", str(user.id), "delete", before={"username": user.username})
    db.delete(user)
    db.commit()
    return {"ok": True}


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(Department).order_by(Department.name).all()


# ---------- Per-service access ----------

def _access_rows(db: Session, user_id: int) -> list[UserServiceAccess]:
    return (db.query(UserServiceAccess)
            .filter(UserServiceAccess.user_id == user_id)
            .order_by(UserServiceAccess.service_key)
            .all())


@router.get("/{user_id}/access", response_model=list[UserServiceAccessOut])
def get_user_access(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not db.query(User).get(user_id):
        raise HTTPException(404, "Пользователь не найден")
    return _access_rows(db, user_id)


@router.put("/{user_id}/access", response_model=list[UserServiceAccessOut])
def set_user_access(user_id: int, body: UserServiceAccessIn, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    """Grants, changes or (with an empty access_level) revokes access to one service."""
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if body.service_key not in SERVICE_KEYS:
        raise HTTPException(400, f"Неизвестная служба: {body.service_key}")
    level = (body.access_level or "").strip()
    if level and level not in ACCESS_LEVELS:
        raise HTTPException(400, f"Неизвестный уровень доступа: {level}")

    row = (db.query(UserServiceAccess)
           .filter(UserServiceAccess.user_id == user_id,
                   UserServiceAccess.service_key == body.service_key)
           .first())
    before = {"service_key": body.service_key, "access_level": row.access_level if row else None}
    if not level:
        if row:
            db.delete(row)
    elif row:
        row.access_level = level
    else:
        db.add(UserServiceAccess(user_id=user_id, service_key=body.service_key, access_level=level))

    log_action(db, admin, "user_service_access", str(user_id), "update", before=before,
               after={"service_key": body.service_key, "access_level": level or None})
    db.commit()
    return _access_rows(db, user_id)
