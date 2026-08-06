"""Audit log helper service."""
import datetime
from sqlalchemy.orm import Session
from .models import AuditLog, User


def log_action(
    db: Session,
    user: User | None,
    entity_type: str,
    entity_id: str | None,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
    ip: str = "",
):
    entry = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else "system",
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        action=action,
        before_json=before,
        after_json=after,
        ip_address=ip,
    )
    db.add(entry)
    db.flush()
    return entry
