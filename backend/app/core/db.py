"""Подключение к базе данных: движок, фабрика сессий, базовый класс моделей.

Схемой управляет только Alembic (migrations/). Приложение таблицы не создаёт.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

# Единые имена ограничений: одинаковые на SQLite и PostgreSQL, предсказуемые в миграциях.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    """Текущее время UTC без tzinfo — так оно хранится в столбцах DateTime."""
    return datetime.now(UTC).replace(tzinfo=None)


def make_engine(url: str | None = None, **kwargs) -> Engine:
    url = url or settings.database_url
    options: dict = {"echo": settings.db_echo, "future": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    else:
        options.update(pool_size=settings.db_pool_size, max_overflow=settings.db_pool_size,
                       pool_pre_ping=True, pool_recycle=1800)
    options.update(kwargs)
    engine = create_engine(url, **options)
    if url.startswith("sqlite"):
        _configure_sqlite(engine)
    return engine


def _unicode_lower(value):
    return value.lower() if isinstance(value, str) else value


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):  # pragma: no cover - вызывается драйвером
        # Встроенная lower() в SQLite понижает только латиницу; поиск по кириллице без учёта
        # регистра требует юникодной версии (в PostgreSQL lower() корректна сама по себе).
        dbapi_connection.create_function("lower", 1, _unicode_lower, deterministic=True)
        cursor = dbapi_connection.cursor()
        # Без этой настройки SQLite не проверяет внешние ключи и не выполняет ON DELETE CASCADE.
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        if engine.url.database not in (None, "", ":memory:"):
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Зависимость FastAPI: сессия на запрос; незакоммиченное откатывается."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Сессия для фоновых задач и CLI: commit при успехе, rollback при ошибке."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
