"""Per-user dashboard layout preferences (widget order, size, visibility)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, UserDashboardPreference, SERVICE_KEYS
from ..deps import get_current_user
from ..schemas import DashboardPreferenceIn, DashboardPreferenceOut

router = APIRouter(prefix="/api/dashboard/preferences", tags=["dashboard-preferences"])

WIDGET_SIZES = ("small", "medium", "wide", "large")


def _check_service(service_key: str):
    if service_key not in SERVICE_KEYS:
        raise HTTPException(404, "Служба не найдена")


@router.get("/{service_key}", response_model=DashboardPreferenceOut)
def get_preferences(service_key: str, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    _check_service(service_key)
    row = (db.query(UserDashboardPreference)
           .filter(UserDashboardPreference.user_id == user.id,
                   UserDashboardPreference.service_key == service_key)
           .first())
    # No saved layout is a normal state: the frontend then uses its own defaults.
    widgets = (row.preferences_json or {}).get("widgets", []) if row else []
    return DashboardPreferenceOut(service_key=service_key, widgets=widgets)


@router.put("/{service_key}", response_model=DashboardPreferenceOut)
def set_preferences(service_key: str, body: DashboardPreferenceIn,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _check_service(service_key)
    keys = set()
    for w in body.widgets:
        if w.size not in WIDGET_SIZES:
            raise HTTPException(400, f"Неизвестный размер виджета: {w.size}")
        if w.key in keys:
            raise HTTPException(400, f"Виджет повторяется: {w.key}")
        keys.add(w.key)
    payload = {"widgets": [w.model_dump() for w in body.widgets]}
    row = (db.query(UserDashboardPreference)
           .filter(UserDashboardPreference.user_id == user.id,
                   UserDashboardPreference.service_key == service_key)
           .first())
    if row:
        row.preferences_json = payload
    else:
        db.add(UserDashboardPreference(user_id=user.id, service_key=service_key,
                                       preferences_json=payload))
    db.commit()
    return DashboardPreferenceOut(service_key=service_key, widgets=payload["widgets"])


@router.delete("/{service_key}")
def reset_preferences(service_key: str, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    _check_service(service_key)
    row = (db.query(UserDashboardPreference)
           .filter(UserDashboardPreference.user_id == user.id,
                   UserDashboardPreference.service_key == service_key)
           .first())
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}
