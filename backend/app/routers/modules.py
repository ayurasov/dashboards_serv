"""Dashboard modules and the service registry."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import DashboardModule, User, RoleEnum, SERVICES
from ..deps import get_current_user, accessible_service_keys
from ..schemas import DashboardModuleOut, ServiceOut

router = APIRouter(prefix="/api/modules", tags=["modules"])
services_router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("", response_model=list[DashboardModuleOut])
def list_modules(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Only the modules the user may view; a global admin sees every enabled module."""
    q = db.query(DashboardModule).filter(DashboardModule.enabled.is_(True))
    if user.role != RoleEnum.ADMIN:
        q = q.filter(DashboardModule.key.in_(accessible_service_keys(db, user)))
    return q.order_by(DashboardModule.sort_order).all()


@router.get("/{key}", response_model=DashboardModuleOut)
def get_module(key: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    module = db.query(DashboardModule).filter(DashboardModule.key == key).first()
    if not module:
        raise HTTPException(status_code=404, detail="Модуль не найден")
    return module


@services_router.get("", response_model=list[ServiceOut])
def list_services(_: User = Depends(get_current_user)):
    """The full nine-service registry, used to grant access before content exists."""
    return [ServiceOut(key=key, title=title, subtitle=subtitle, has_dashboard=has_dashboard)
            for key, title, subtitle, _icon, _prefix, has_dashboard in SERVICES]
