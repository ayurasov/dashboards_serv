"""FastAPI dependencies for auth and RBAC."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, RoleEnum, Department, UserServiceAccess, SERVICE_KEYS
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")
    user = db.query(User).filter(User.username == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден или неактивен")
    return user


def require_role(*roles: RoleEnum):
    """Dependency factory: require one of the given roles."""
    def checker(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return user
    return checker


def require_admin(user: User = Depends(get_current_user)):
    if user.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права администратора")
    return user


def require_edit(user: User = Depends(get_current_user)):
    """Admin or HR head can edit data."""
    if user.role not in (RoleEnum.ADMIN, RoleEnum.HR_HEAD):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права на редактирование")
    return user


# ---------- Per-service access ----------
#
# `User.role == ADMIN` is a superadmin: it grants every level on every service
# regardless of the UserServiceAccess rows.

def service_access_level(db: Session, user: User, service_key: str) -> str | None:
    """The user's own access level for a service, ignoring the global admin role."""
    row = (db.query(UserServiceAccess)
           .filter(UserServiceAccess.user_id == user.id,
                   UserServiceAccess.service_key == service_key)
           .first())
    return row.access_level if row else None


def _has_level(db: Session, user: User, service_key: str, *levels: str) -> bool:
    if user.role == RoleEnum.ADMIN:
        return True
    return service_access_level(db, user, service_key) in levels


def can_view_service(db: Session, user: User, service_key: str) -> bool:
    """Any access level is enough to view a service."""
    if user.role == RoleEnum.ADMIN:
        return True
    return service_access_level(db, user, service_key) is not None


def can_edit_service(db: Session, user: User, service_key: str) -> bool:
    return _has_level(db, user, service_key, "edit", "admin")


def can_edit_metrics(db: Session, user: User, service_key: str) -> bool:
    return _has_level(db, user, service_key, "edit_metrics", "admin")


def can_admin_service(db: Session, user: User, service_key: str) -> bool:
    return _has_level(db, user, service_key, "admin")


def require_metrics_edit(service_key: str):
    """Editing metric values needs the global edit role or `edit_metrics` on the service."""
    def checker(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
        if user.role in (RoleEnum.ADMIN, RoleEnum.HR_HEAD) or can_edit_metrics(db, user, service_key):
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Требуются права на заполнение метрик")
    return checker


def accessible_service_keys(db: Session, user: User) -> set[str]:
    """Every service the user may view; a global admin may view all of them."""
    if user.role == RoleEnum.ADMIN:
        return set(SERVICE_KEYS)
    return {a.service_key for a in
            db.query(UserServiceAccess).filter(UserServiceAccess.user_id == user.id).all()}


def can_view_department(user: User, department_name: str) -> bool:
    """Department-scoped viewers can only see their departments."""
    if user.role in (RoleEnum.ADMIN, RoleEnum.HR_HEAD, RoleEnum.VIEWER):
        return True
    # department_viewer
    dept_names = {d.name for d in user.departments}
    dept_codes = {d.code for d in user.departments}
    return department_name in dept_names or department_name in dept_codes or department_name == ""
