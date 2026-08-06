"""Audit log router (admin only)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from ..database import get_db
from ..models import AuditLog, User
from ..deps import require_admin
from ..schemas import AuditLogOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit(
    entity_type: str | None = None,
    action: str | None = None,
    username: str | None = None,
    limit: int = Query(500, le=2000),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(AuditLog)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if action:
        q = q.filter(AuditLog.action == action)
    if username:
        q = q.filter(AuditLog.username == username)
    return q.order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit).all()
