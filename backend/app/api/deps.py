"""Зависимости FastAPI: текущий пользователь, CSRF, проверки прав."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..core.config import settings
from ..core.db import get_db
from ..core.errors import Forbidden, Unauthorized
from ..core.security import constant_time_equals
from ..models import User, UserSession
from ..services import access
from ..services.registry import ACCESS_LEVEL_LABELS, CAPABILITIES, DATA_CLASSES, SERVICE_BY_KEY
from ..services.sessions import resolve_session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class AuthContext:
    session: UserSession
    user: User


def auth_context(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    """Сессия и пользователь (с доступом и подразделениями) — в одном потоке и за одну транзакцию.

    В конце соединение возвращается в пул (commit): дальше запрос до обработчика проходит
    без обращений к базе, и соединение не удерживается, пока запрос ждёт поток.
    """
    token = request.cookies.get(settings.session_cookie_name)
    session = resolve_session(db, token)
    if session is None:
        raise Unauthorized("Войдите в систему", code="not_authenticated")
    if request.method not in SAFE_METHODS:
        header = request.headers.get("x-csrf-token", "")
        if not header or not constant_time_equals(header, session.csrf_token):
            raise Forbidden("Сессия устарела: обновите страницу", code="csrf_failed")
    user = db.scalars(select(User).options(joinedload(User.access), selectinload(User.access_units),
                               selectinload(User.head_links))
                      .where(User.id == session.user_id)).unique().first()
    db.commit()
    if user is None or not user.is_active:
        raise Unauthorized("Учётная запись недоступна", code="not_authenticated")
    return AuthContext(session, user)


# Проверки ниже — без обращений к базе, поэтому async: они не занимают поток пула.

async def current_session(ctx: AuthContext = Depends(auth_context)) -> UserSession:
    return ctx.session


async def current_user(ctx: AuthContext = Depends(auth_context)) -> User:
    return ctx.user


async def active_user(user: User = Depends(current_user)) -> User:
    """Пользователь, которому не нужно сначала сменить временный пароль."""
    if user.must_change_password:
        raise Forbidden("Смените временный пароль, чтобы продолжить", code="password_change_required")
    return user


async def require_admin(user: User = Depends(active_user)) -> User:
    if not user.is_admin:
        raise Forbidden("Действие доступно только администратору")
    return user


def require_capability(capability: str) -> Callable[..., User]:
    """Фабрика зависимостей: полномочие администрирования (org.manage, users.manage) или роль администратора."""
    if capability not in CAPABILITIES:  # pragma: no cover - ошибка программиста
        raise ValueError(capability)

    async def checker(user: User = Depends(active_user)) -> User:
        if not user.can(capability):
            raise Forbidden("Недостаточно полномочий: " + CAPABILITIES[capability].split(":")[0].lower())
        return user

    checker.__name__ = f"require_{capability.replace('.', '_')}"
    return checker


def require_service(service_key: str, minimum: str = "viewer") -> Callable[..., User]:
    """Фабрика зависимостей: доступ к службе не ниже уровня minimum."""
    if service_key not in SERVICE_BY_KEY:  # pragma: no cover - ошибка программиста
        raise ValueError(service_key)

    async def checker(user: User = Depends(active_user)) -> User:
        _check_service(user, service_key, minimum)
        return user

    checker.__name__ = f"require_{service_key}_{minimum}"
    return checker


# ---------------------------------------------------------------- модель доступа 2.0 (ADR-0009)
# Фабрики запоминают зависимость: один и тот же объект в нескольких обработчиках и параметрах,
# поэтому FastAPI выполняет проверку один раз на запрос. Порядок проверок: служба → записи →
# класс данных → выгрузка; при отказе в службе сообщение — о службе.

RECORDS_FORBIDDEN = "Исходные записи вам недоступны — доступны дашборды и сводки службы"
EXPORT_FORBIDDEN = "Выгрузка в Excel, CSV и PDF вам недоступна"


def _check_service(user: User, service_key: str | None, minimum: str) -> None:
    if service_key is None or access.has_level(user, service_key, minimum):
        return
    service = SERVICE_BY_KEY[service_key].title
    if access.access_level(user, service_key) is None:
        raise Forbidden(f"Нет доступа к службе «{service}»")
    raise Forbidden(f"Нужен уровень доступа «{ACCESS_LEVEL_LABELS[minimum]}» к службе «{service}»")


def _check_data_class(user: User, data_class: str | None) -> None:
    if data_class is not None and not access.effective(user).allows(data_class):
        raise Forbidden(access.DATA_CLASS_FORBIDDEN.get(data_class, "Нет доступа к этим данным"),
                        code="data_class_forbidden")


def _validate(service_key: str | None, data_class: str | None) -> None:
    if service_key is not None and service_key not in SERVICE_BY_KEY:  # pragma: no cover - ошибка программиста
        raise ValueError(service_key)
    if data_class is not None and data_class not in DATA_CLASSES:  # pragma: no cover - ошибка программиста
        raise ValueError(data_class)


@cache
def require_records(service_key: str, data_class: str | None = None) -> Callable[..., User]:
    """Исходные записи службы (реестры и списки): просмотр службы и право «Исходные записи»;
    data_class — класс данных записей (например, personal для реестра приёмов и увольнений)."""
    _validate(service_key, data_class)

    async def checker(user: User = Depends(active_user)) -> User:
        _check_service(user, service_key, "viewer")
        if not access.effective(user).can_view_records:
            raise Forbidden(RECORDS_FORBIDDEN, code="records_forbidden")
        _check_data_class(user, data_class)
        return user

    checker.__name__ = f"require_records_{service_key}" + (f"_{data_class}" if data_class else "")
    return checker


@cache
def require_export(service_key: str | None = None, *, records: bool = False,
                   data_class: str | None = None) -> Callable[..., User]:
    """Выгрузка в Excel, CSV и PDF; при service_key — и просмотр службы, records — выгрузка исходных
    записей (реестра), data_class — класс данных в выгрузке."""
    _validate(service_key, data_class)

    async def checker(user: User = Depends(active_user)) -> User:
        _check_service(user, service_key, "viewer")
        eff = access.effective(user)
        if records and not eff.can_view_records:
            raise Forbidden(RECORDS_FORBIDDEN, code="records_forbidden")
        _check_data_class(user, data_class)
        if not eff.can_export:
            raise Forbidden(EXPORT_FORBIDDEN, code="export_forbidden")
        return user

    checker.__name__ = "require_export" + (f"_{service_key}" if service_key else "")
    return checker


@cache
def require_data_class(data_class: str, service_key: str | None = None, minimum: str = "viewer") -> Callable[..., User]:
    """Класс данных (personal, financial); при service_key — и уровень доступа к службе не ниже minimum."""
    _validate(service_key, data_class)

    async def checker(user: User = Depends(active_user)) -> User:
        _check_service(user, service_key, minimum)
        _check_data_class(user, data_class)
        return user

    checker.__name__ = f"require_{data_class}" + (f"_{service_key}_{minimum}" if service_key else "")
    return checker
