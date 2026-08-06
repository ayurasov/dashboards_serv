"""Custom dashboards router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import CustomDashboard, DashboardWidget, User, WIDGET_TYPES
from ..deps import get_current_user, require_edit
from ..schemas import CustomDashboardCreate, CustomDashboardOut
from ..audit import log_action

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


def _replace_widgets(db: Session, dash: CustomDashboard, widgets) -> None:
    for w in widgets:
        if w.widget_type not in WIDGET_TYPES:
            raise HTTPException(400, f"Неизвестный тип виджета: {w.widget_type}")
    for w in list(dash.widgets):
        db.delete(w)
    db.flush()
    for i, w in enumerate(widgets):
        db.add(DashboardWidget(dashboard_id=dash.id, widget_type=w.widget_type, title=w.title,
                               config=w.config or {}, sort_order=w.sort_order or i))


@router.get("", response_model=list[CustomDashboardOut])
def list_dashboards(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(CustomDashboard)
    # show own + shared
    from sqlalchemy import or_
    q = q.filter(or_(CustomDashboard.owner_id == user.id, CustomDashboard.is_shared == True))
    return q.order_by(CustomDashboard.created_at.desc()).all()


@router.post("", response_model=CustomDashboardOut)
def create_dashboard(body: CustomDashboardCreate, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    if not body.name.strip():
        raise HTTPException(400, "Название дашборда обязательно")
    dash = CustomDashboard(name=body.name.strip(), owner_id=user.id, is_shared=body.is_shared)
    db.add(dash)
    db.flush()
    _replace_widgets(db, dash, body.widgets)
    log_action(db, user, "dashboard", str(dash.id), "create", after={"name": dash.name})
    db.commit()
    db.refresh(dash)
    return dash


@router.put("/{dash_id}", response_model=CustomDashboardOut)
def update_dashboard(dash_id: int, body: CustomDashboardCreate, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    dash = db.query(CustomDashboard).get(dash_id)
    if not dash:
        raise HTTPException(404, "Дашборд не найден")
    if dash.owner_id != user.id and user.role.value != "admin":
        raise HTTPException(403, "Нет прав на редактирование")
    if not body.name.strip():
        raise HTTPException(400, "Название дашборда обязательно")
    before = {"name": dash.name, "is_shared": dash.is_shared}
    dash.name = body.name.strip()
    dash.is_shared = body.is_shared
    _replace_widgets(db, dash, body.widgets)
    log_action(db, user, "dashboard", str(dash.id), "update", before=before)
    db.commit()
    db.refresh(dash)
    return dash


@router.delete("/{dash_id}")
def delete_dashboard(dash_id: int, db: Session = Depends(get_db), user: User = Depends(require_edit)):
    dash = db.query(CustomDashboard).get(dash_id)
    if not dash:
        raise HTTPException(404, "Дашборд не найден")
    if dash.owner_id != user.id and user.role.value != "admin":
        raise HTTPException(403, "Нет прав на удаление")
    log_action(db, user, "dashboard", str(dash.id), "delete", before={"name": dash.name})
    db.delete(dash)
    db.commit()
    return {"ok": True}
