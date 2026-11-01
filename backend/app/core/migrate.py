"""Применение миграций: одна точка входа для Docker, CLI и тестов.

- PostgreSQL: миграции выполняются под advisory-блокировкой, поэтому несколько
  одновременно стартующих контейнеров не мешают друг другу;
- база версии до 0.1.0, созданная без Alembic (таблицы есть, alembic_version нет),
  помечается последней старой ревизией и обновляется миграцией 0012.
"""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, pool, text
from sqlalchemy.engine import Connection

from .config import BACKEND_DIR, settings

log = logging.getLogger("app.migrate")

LEGACY_HEAD = "0011_naumen_tickets"
LEGACY_REVISIONS = (
    "0001_initial_schema", "0005_add_tp_tables", "0006_metric_definition_id", "0007_user_created_at",
    "0008_legacy_timestamp_columns", "0009_employee_event_created_at", "0010_align_remaining_orm_tables",
    LEGACY_HEAD,
)
ADVISORY_LOCK_ID = 0x0DA5B0A2D  # произвольная константа приложения
# Таблицы, по которым узнаётся база версии до 0.1.0
LEGACY_MARKERS = {"users", "month_records", "metric_values"}


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(BACKEND_DIR) / "migrations"))
    cfg.attributes["database_url"] = url or settings.database_url
    cfg.attributes["skip_logging"] = True
    return cfg


def head_revision(cfg: Config | None = None) -> str:
    return ScriptDirectory.from_config(cfg or alembic_config()).get_current_head()


def current_revision(conn: Connection) -> str | None:
    if "alembic_version" not in inspect(conn).get_table_names():
        return None
    return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def _stamp_unversioned_legacy(conn: Connection, cfg: Config) -> None:
    tables = set(inspect(conn).get_table_names())
    if "alembic_version" in tables or not tables >= LEGACY_MARKERS:
        return
    log.warning("База версии до 0.1.0 без истории миграций: помечаю ревизией %s", LEGACY_HEAD)
    cfg.attributes["connection"] = conn
    command.stamp(cfg, LEGACY_HEAD)


def upgrade(url: str | None = None, revision: str = "head") -> str:
    """Обновляет схему до revision и возвращает итоговую ревизию."""
    url = url or settings.database_url
    cfg = alembic_config(url)
    engine = create_engine(url, poolclass=pool.NullPool)
    try:
        with engine.connect() as conn:
            if conn.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": ADVISORY_LOCK_ID})
                conn.commit()
            try:
                _stamp_unversioned_legacy(conn, cfg)
                conn.commit()
                before = current_revision(conn)
                cfg.attributes["connection"] = conn
                if revision == "head" and (before is None or before in LEGACY_REVISIONS[:-1]):
                    cfg.attributes["legacy_naming"] = True
                    command.upgrade(cfg, LEGACY_HEAD)
                    conn.commit()
                    cfg.attributes["legacy_naming"] = False
                command.upgrade(cfg, revision)
                conn.commit()
                after = current_revision(conn)
                if before != after:
                    log.info("Схема базы обновлена: %s → %s", before or "пусто", after)
                else:
                    log.info("Схема базы актуальна: %s", after)
                return after
            finally:
                if conn.dialect.name == "postgresql":
                    conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": ADVISORY_LOCK_ID})
                    conn.commit()
    finally:
        engine.dispose()


def check_schema_is_current(conn: Connection) -> tuple[bool, str | None, str]:
    head = head_revision()
    current = current_revision(conn)
    return current == head, current, head
