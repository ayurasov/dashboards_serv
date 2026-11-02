"""Интеграции и входящие данные (ADR-0011): подключения, запуски, элементы входящих, ключи, правила."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, column_property, mapped_column

from ..core.db import Base, utcnow
from .core import TimestampMixin

RUN_TRIGGERS = ("manual", "schedule", "webhook", "folder", "cli")
RUN_STATUSES = ("running", "ok", "partial", "error")
INBOX_SOURCES = ("folder", "upload", "api", "integration")
INBOX_STATUSES = ("received", "recognized", "pending", "applied", "rejected", "error", "duplicate")
# «Живые» элементы: по ним распознаётся повтор файла (один и тот же набор и SHA-256)
INBOX_LIVE_STATUSES = ("received", "recognized", "pending", "applied")
KEY_SCOPES = ("files", "status")

_LIVE = text("status IN ('received', 'recognized', 'pending', 'applied')")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class Integration(TimestampMixin, Base):
    """Подключение к внешней системе: вид коннектора, настройки (без секретов), зашифрованные секреты,
    расписание и состояние."""

    __tablename__ = "integrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Секретные поля настроек одним зашифрованным значением (app/core/secrets.py) и адрес привязки
    secret_encrypted: Mapped[str | None] = mapped_column(Text)
    secret_bound_url: Mapped[str | None] = mapped_column(String(500))
    # {"mode": "interval", "minutes": 60, "actions": [...]} · {"mode": "daily", "time": "06:30", ...} · {}
    schedule: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    # Состояние коннектора между запусками: курсоры, отметки обработанного
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Запуск идёт с этого времени (занимается атомарно, см. app/integrations/runner.py)
    running_since: Mapped[datetime | None] = mapped_column(DateTime)
    # Успешная проверка после последнего изменения настроек: включить можно только проверенное
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class IntegrationRun(Base):
    """Запуск действия подключения: повод, время, итог, счётчики. Хранятся последние
    INTEGRATION_RUNS_KEEP запусков каждого подключения."""

    __tablename__ = "integration_runs"
    __table_args__ = (
        Index("ix_integration_runs_integration_id_started_at", "integration_id", "started_at"),
        CheckConstraint(f"trigger IN ({_in(RUN_TRIGGERS)})", name="trigger"),
        CheckConstraint(f"status IN ({_in(RUN_STATUSES)})", name="status"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(60))
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    message: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str] = mapped_column(String(100), default="system")


class InboxItem(Base):
    """Элемент входящих: файл из любого источника, распознанный набор, план и итог применения.
    Исходный файл хранится в content до срока хранения (INBOX_RETENTION_DAYS)."""

    __tablename__ = "inbox_items"
    __table_args__ = (
        # Повтор: у набора не больше одного «живого» элемента с тем же содержимым
        Index("uq_inbox_items_dataset_sha256", "dataset", "sha256", unique=True,
              sqlite_where=_LIVE, postgresql_where=_LIVE),
        # Фильтр по статусу и счётчик «ожидают» по наборам (/api/auth/me) — одним COUNT по индексу
        Index("ix_inbox_items_status_dataset", "status", "dataset"),
        CheckConstraint(f"source IN ({_in(INBOX_SOURCES)})", name="source"),
        CheckConstraint(f"status IN ({_in(INBOX_STATUSES)})", name="status"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    source: Mapped[str] = mapped_column(String(20))
    source_ref: Mapped[str] = mapped_column(String(500), default="")
    integration_id: Mapped[int | None] = mapped_column(ForeignKey("integrations.id", ondelete="SET NULL"), index=True)
    inbound_key_id: Mapped[int | None] = mapped_column(ForeignKey("inbound_keys.id", ondelete="SET NULL"), index=True)
    filename: Mapped[str] = mapped_column(String(300), default="")
    content_type: Mapped[str] = mapped_column(String(200), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    dataset: Mapped[str | None] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="received")
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # План и итог движка — крупные, со списком не загружаются; summary и plan_ok — для списка
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, deferred=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, deferred=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    plan_ok: Mapped[bool | None] = mapped_column(Boolean)
    error: Mapped[str] = mapped_column(Text, default="")
    # Пояснение статуса для человека: почему ожидает, итог применения, чей повтор
    message: Mapped[str] = mapped_column(Text, default="")
    # Откуда файл для человека — от источника: «Задача «…» · автор», «Письмо «…» от …» (до 500 символов)
    note: Mapped[str] = mapped_column(String(500), default="", server_default="")
    duplicate_of_id: Mapped[int | None] = mapped_column(BigInteger().with_variant(Integer, "sqlite"),
                                                        ForeignKey("inbox_items.id", ondelete="SET NULL"))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    received_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    received_by: Mapped[str] = mapped_column(String(100), default="")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime)
    applied_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    applied_by: Mapped[str] = mapped_column(String(100), default="")
    # Содержимое не загружается со списком элементов — только когда к нему обращаются
    content: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    content_purged_at: Mapped[datetime | None] = mapped_column(DateTime)


# Есть ли исходный файл — без загрузки самого содержимого
InboxItem.has_content = column_property(InboxItem.__table__.c.content.is_not(None))


class InboundKey(Base):
    """Ключ для входящих вызовов (dash_ + token_urlsafe(32)): показывается один раз, хранится SHA-256
    и префикс. Область: files — приём файлов, status — чтение статусов принятого этим ключом."""

    __tablename__ = "inbound_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    issued_by: Mapped[str] = mapped_column(String(100), default="")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InboxRule(Base):
    """Правило входящих: применять ли сразу план без ошибок для источника и набора.
    Нет строки — ждать подтверждения."""

    __tablename__ = "inbox_rules"

    source: Mapped[str] = mapped_column(String(20), primary_key=True)
    dataset: Mapped[str] = mapped_column(String(40), primary_key=True)
    auto_apply: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
