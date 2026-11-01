"""Пользовательские дашборды службы персонала: личные и общие подборки виджетов."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.errors import Forbidden, NotFound, ValidationFailed
from ...models import CustomDashboard, CustomDashboardWidget, User
from ...schemas.common import Ok
from ...schemas.settings import CustomDashboardIn, CustomDashboardOut, WidgetOut
from ...services import access, audit
from ...services import hr as hr_service
from ..deps import require_service

router = APIRouter(prefix="/api/dashboards", tags=["Пользовательские дашборды"])
SERVICE = "hr"
read = require_service(SERVICE, "viewer")


def _can_edit(user: User, dash: CustomDashboard) -> bool:
    return user.is_admin or dash.owner_id == user.id


def _out(user: User, dash: CustomDashboard) -> CustomDashboardOut:
    return CustomDashboardOut(
        id=dash.id, name=dash.name, is_shared=dash.is_shared, owner_id=dash.owner_id,
        owner_name=dash.owner.full_name if dash.owner else "", can_edit=_can_edit(user, dash),
        created_at=dash.created_at, updated_at=dash.updated_at,
        widgets=[WidgetOut.model_validate(w) for w in dash.widgets])


def _validate(db: Session, user: User, body: CustomDashboardIn) -> None:
    if body.is_shared and not access.has_level(user, SERVICE, "editor"):
        raise Forbidden("Общие дашборды создаёт уровень доступа «Ввод данных» или выше")
    if len(body.widgets) > 40:
        raise ValidationFailed("Не больше 40 виджетов на дашборде")
    known = {d.key for d in hr_service.definitions(db)}
    for w in body.widgets:
        keys = [w.config.get("metric_key")] if w.widget_type == "metric_card" else w.config.get("metric_keys", [])
        if w.widget_type == "note":
            continue
        if not keys or not all(k in known for k in keys if k):
            raise ValidationFailed(f"Виджет «{w.title or w.widget_type}»: выберите метрики")


def _get(db: Session, dash_id: int) -> CustomDashboard:
    dash = db.get(CustomDashboard, dash_id)
    if dash is None:
        raise NotFound("Дашборд не найден")
    return dash


@router.get("", response_model=list[CustomDashboardOut], summary="Мои и общие дашборды")
def list_dashboards(db: Session = Depends(get_db), user: User = Depends(read)):
    stmt = select(CustomDashboard).where(or_(CustomDashboard.owner_id == user.id, CustomDashboard.is_shared.is_(True)))
    return [_out(user, d) for d in db.scalars(stmt.order_by(CustomDashboard.name))]


@router.post("", response_model=CustomDashboardOut, status_code=201, summary="Создать дашборд")
def create_dashboard(body: CustomDashboardIn, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(read)):
    _validate(db, user, body)
    dash = CustomDashboard(name=body.name, is_shared=body.is_shared, owner_id=user.id)
    dash.widgets = [CustomDashboardWidget(widget_type=w.widget_type, title=w.title, config=w.config, sort_order=i)
                    for i, w in enumerate(body.widgets)]
    db.add(dash)
    db.flush()
    audit.record(db, user, service_key=SERVICE, entity_type="custom_dashboard", entity_id=dash.id, action="create",
                 summary=f"Создан дашборд «{dash.name}»", request=request)
    db.commit()
    return _out(user, dash)


@router.put("/{dash_id}", response_model=CustomDashboardOut, summary="Изменить дашборд")
def update_dashboard(dash_id: int, body: CustomDashboardIn, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(read)):
    dash = _get(db, dash_id)
    if not _can_edit(user, dash):
        raise Forbidden("Изменять дашборд может только его автор")
    _validate(db, user, body)
    dash.name, dash.is_shared = body.name, body.is_shared
    dash.widgets.clear()
    db.flush()
    dash.widgets.extend(CustomDashboardWidget(widget_type=w.widget_type, title=w.title, config=w.config,
                                              sort_order=i) for i, w in enumerate(body.widgets))
    audit.record(db, user, service_key=SERVICE, entity_type="custom_dashboard", entity_id=dash.id, action="update",
                 summary=f"Изменён дашборд «{dash.name}»", request=request)
    db.commit()
    return _out(user, dash)


@router.delete("/{dash_id}", response_model=Ok, summary="Удалить дашборд")
def delete_dashboard(dash_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(read)):
    dash = _get(db, dash_id)
    if not _can_edit(user, dash):
        raise Forbidden("Удалить дашборд может только его автор")
    audit.record(db, user, service_key=SERVICE, entity_type="custom_dashboard", entity_id=dash.id, action="delete",
                 summary=f"Удалён дашборд «{dash.name}»", request=request)
    db.delete(dash)
    db.commit()
    return Ok(message="Дашборд удалён")
