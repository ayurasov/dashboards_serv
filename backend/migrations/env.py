"""Окружение Alembic. Адрес базы — из DATABASE_URL (как у приложения)."""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import MetaData, create_engine, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402,F401 — регистрирует таблицы в Base.metadata
from app.core.config import settings  # noqa: E402
from app.core.db import Base  # noqa: E402

config = context.config
if config.config_file_name is not None and not config.attributes.get("skip_logging"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _metadata():
    # Старые ревизии (до 0012) писались без единой конвенции имён ограничений; с ней
    # они конфликтуют на PostgreSQL. app.core.migrate прогоняет их отдельным шагом.
    if config.attributes.get("legacy_naming"):
        return MetaData()
    return target_metadata


def _url() -> str:
    return config.attributes.get("database_url") or settings.database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=_metadata(), literal_binds=True,
                      render_as_batch=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    url = _url()
    # Отдельный движок без PRAGMA foreign_keys: в SQLite перестройка таблиц требует
    # выключенной проверки внешних ключей (она выключена по умолчанию).
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as conn:
        _run(conn)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=_metadata(),
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
