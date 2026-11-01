"""Зависимости FastAPI: текущий пользователь, CSRF, проверки прав."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..core.config import settings
from ..core.db import get_db
from ..core.errors import Forbidden, Unauthorized
from ..core.security import constant_time_equals
from ..models import User, UserSession
from ..services import access
from ..services.registry import ACCESS_LEVEL_LABELS, SERVICE_BY_KEY
from ..services.sessions import resolve_session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def current_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    token = request.cookies.get(settings.session_cookie_name)
    session = resolve_session(db, token)
    if session is None:
        raise Unauthorized("Войдите в систему", code="not_authenticated")
    if request.method not in SAFE_METHODS:
        header = request.headers.get("x-csrf-token", "")
        if not header or not constant_time_equals(header, session.csrf_token):
            raise Forbidden("Сессия устарела: обновите страницу", code="csrf_failed")
    return session


def current_user(session: UserSession = Depends(current_session), db: Session = Depends(get_db)) -> User:
    # Пользователь вместе с доступом и подразделениями — одним запросом (это каждый запрос API)
    user = db.scalars(select(User).options(joinedload(User.access), joinedload(User.departments))
                      .where(User.id == session.user_id)).unique().first()
    if user is None or not user.is_active:
        raise Unauthorized("Учётная запись недоступна", code="not_authenticated")
    return user


def active_user(user: User = Depends(current_user)) -> User:
    """Пользователь, которому не нужно сначала сменить временный пароль."""
    if user.must_change_password:
        raise Forbidden("Смените временный пароль, чтобы продолжить", code="password_change_required")
    return user


def require_admin(user: User = Depends(active_user)) -> User:
    if not user.is_admin:
        raise Forbidden("Действие доступно только администратору")
    return user


def require_service(service_key: str, minimum: str = "viewer") -> Callable[..., User]:
    """Фабрика зависимостей: доступ к службе не ниже уровня minimum."""
    if service_key not in SERVICE_BY_KEY:  # pragma: no cover - ошибка программиста
        raise ValueError(service_key)

    def checker(user: User = Depends(active_user)) -> User:
        if not access.has_level(user, service_key, minimum):
            service = SERVICE_BY_KEY[service_key].title
            if access.access_level(user, service_key) is None:
                raise Forbidden(f"Нет доступа к службе «{service}»")
            raise Forbidden(f"Нужен уровень доступа «{ACCESS_LEVEL_LABELS[minimum]}» к службе «{service}»")
        return user

    checker.__name__ = f"require_{service_key}_{minimum}"
    return checker
