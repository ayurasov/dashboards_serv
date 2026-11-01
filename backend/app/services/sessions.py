"""Сессии входа: создание, проверка, продление, отзыв."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.db import utcnow
from ..core.security import new_token, token_digest
from ..models import User, UserSession

# Как часто обновлять last_seen_at (чтобы не писать в базу на каждый запрос)
TOUCH_INTERVAL = timedelta(minutes=2)


def create_session(db: Session, user: User, ip: str, user_agent: str) -> tuple[str, UserSession]:
    token = new_token()
    now = utcnow()
    session = UserSession(
        id=token_digest(token), user_id=user.id, csrf_token=new_token(24),
        created_at=now, last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_lifetime_hours),
        ip_address=ip[:64], user_agent=user_agent[:300],
    )
    db.add(session)
    return token, session


def resolve_session(db: Session, token: str | None) -> UserSession | None:
    """Действующая сессия по токену из cookie или None (истёкшая сессия удаляется)."""
    if not token:
        return None
    session = db.get(UserSession, token_digest(token))
    if session is None:
        return None
    now = utcnow()
    idle = timedelta(minutes=settings.session_idle_minutes)
    if session.expires_at <= now or session.last_seen_at + idle <= now:
        db.delete(session)
        db.commit()
        return None
    if now - session.last_seen_at >= TOUCH_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return session


def revoke(db: Session, session_id: str) -> None:
    db.execute(delete(UserSession).where(UserSession.id == session_id))


def revoke_all(db: Session, user_id: int, except_id: str | None = None) -> int:
    stmt = delete(UserSession).where(UserSession.user_id == user_id)
    if except_id:
        stmt = stmt.where(UserSession.id != except_id)
    return db.execute(stmt).rowcount or 0


def list_sessions(db: Session, user_id: int) -> list[UserSession]:
    return list(db.scalars(select(UserSession).where(UserSession.user_id == user_id)
                           .order_by(UserSession.last_seen_at.desc())))


def purge_expired(db: Session) -> int:
    now = utcnow()
    idle_border = now - timedelta(minutes=settings.session_idle_minutes)
    result = db.execute(delete(UserSession).where(
        (UserSession.expires_at <= now) | (UserSession.last_seen_at <= idle_border)))
    return result.rowcount or 0
