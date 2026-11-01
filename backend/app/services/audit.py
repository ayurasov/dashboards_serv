"""Журнал изменений: кто, когда, что изменил (со значениями «до» и «после»)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from ..models import AuditEntry, User

SECRET_FIELDS = {"password", "password_hash", "avatar", "csrf_token"}


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if k in SECRET_FIELDS else _clean(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict, dict]:
    """Только изменившиеся поля — журнал остаётся читаемым."""
    keys = [k for k in after if before.get(k) != after.get(k)]
    return {k: before.get(k) for k in keys}, {k: after.get(k) for k in keys}


def client_ip(request: Request | None) -> str:
    if request is None:
        return ""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


def record(
    db: Session,
    user: User | None,
    *,
    entity_type: str,
    action: str,
    entity_id: Any = None,
    summary: str = "",
    service_key: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    request: Request | None = None,
) -> AuditEntry:
    entry = AuditEntry(
        user_id=user.id if user else None,
        username=user.username if user else "system",
        service_key=service_key,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        action=action,
        summary=summary[:500],
        before=_clean(before) if before else None,
        after=_clean(after) if after else None,
        ip_address=client_ip(request),
        user_agent=(request.headers.get("user-agent", "") if request else "")[:300],
    )
    db.add(entry)
    return entry
