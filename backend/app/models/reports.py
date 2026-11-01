"""Сквозные отчёты (ADR-0010): каталог показателей, введённые значения, заметки о статусе, ревизия."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    update,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..core.db import Base, utcnow
from .core import TimestampMixin

INDICATOR_DIRECTIONS = ("higher_is_better", "lower_is_better", "neutral")
INDICATOR_ROLLUPS = ("sum", "avg", "none")
INDICATOR_RULES = ("threshold", "target")
INDICATOR_SOURCE_TYPES = ("computed", "manual")
VALUE_SOURCES = ("manual", "import")
NOTE_STATUSES = ("watch",)


class Indicator(TimestampMixin, Base):
    """Показатель сквозного отчёта: класс данных, направление, свёртка, правило светофора, источник.

    Вычисляемые показатели (source_type = computed) считаются из данных службы по источнику
    source_key (INDICATOR_SOURCES в registry.py) и не хранятся; вводимые (manual) — значения по
    подразделениям в indicator_values, вводят пользователи с уровнем «Ввод данных» к службе-владельцу.
    """

    __tablename__ = "indicators"
    __table_args__ = (
        CheckConstraint("data_class IN ('operational', 'personal', 'financial')", name="data_class"),
        CheckConstraint("direction IN ('higher_is_better', 'lower_is_better', 'neutral')", name="direction"),
        CheckConstraint("rollup IN ('sum', 'avg', 'none')", name="rollup"),
        CheckConstraint("rule_type IN ('threshold', 'target')", name="rule_type"),
        CheckConstraint("source_type IN ('computed', 'manual')", name="source_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(30), default="")
    data_class: Mapped[str] = mapped_column(String(20), default="operational")
    direction: Mapped[str] = mapped_column(String(20), default="higher_is_better")
    rollup: Mapped[str] = mapped_column(String(10), default="sum")
    # Правило светофора: пороги (зелёный / жёлтый) или отклонение от цели в % (в пределах — зелёный / жёлтый)
    rule_type: Mapped[str] = mapped_column(String(20), default="threshold")
    green_threshold: Mapped[float | None] = mapped_column(Float)
    yellow_threshold: Mapped[float | None] = mapped_column(Float)
    green_deviation: Mapped[float | None] = mapped_column(Float)
    yellow_deviation: Mapped[float | None] = mapped_column(Float)
    default_target: Mapped[float | None] = mapped_column(Float)
    source_type: Mapped[str] = mapped_column(String(20), default="manual")
    source_key: Mapped[str | None] = mapped_column(String(40))
    owner_service: Mapped[str | None] = mapped_column(
        ForeignKey("services.key", ondelete="SET NULL", onupdate="CASCADE"), index=True)
    # Типы уровней структуры, где значение ожидается; пусто — где есть значения
    expected_kinds: Mapped[list[str]] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class IndicatorValue(Base):
    """Введённое значение показателя за месяц по подразделению (period — первое число месяца).
    value может быть пустым: строка хранит только цель или комментарий уровня."""

    __tablename__ = "indicator_values"
    __table_args__ = (
        UniqueConstraint("indicator_id", "department_id", "period"),
        CheckConstraint("source IN ('manual', 'import')", name="source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicators.id", ondelete="CASCADE"))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), index=True)
    period: Mapped[date] = mapped_column(Date, index=True)
    value: Mapped[float | None] = mapped_column(Float)
    target: Mapped[float | None] = mapped_column(Float)
    comment: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(10), default="manual")
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class UnitStatusNote(Base):
    """Заметка руководителя о статусе подразделения за период («под контролем» с комментарием).
    Расчётный статус она не меняет — показывается рядом с ним."""

    __tablename__ = "unit_status_notes"
    __table_args__ = (
        UniqueConstraint("department_id", "period"),
        CheckConstraint("status IN ('watch')", name="status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"))
    period: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(10), default="watch")
    comment: Mapped[str] = mapped_column(Text, default="")
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReportRevision(Base):
    """Ревизия сквозных отчётов (одна строка): увеличивается в транзакции любого изменения каталога,
    значений, заметок и настройки подразделений служб. По ней процессы согласованно перестают
    отдавать рассчитанный отчёт из памяти."""

    __tablename__ = "report_revision"

    id: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)



# ---------------------------------------------------------------- ревизия отчётов
# События сессии регистрируются вместе с моделями: ревизия увеличивается в той же транзакции при любом
# способе изменения (API, загрузка демо-данных из командной строки, скрипты), и все процессы сервера
# перестают отдавать рассчитанный отчёт из памяти.

REPORT_MODELS = (Indicator, IndicatorValue, UnitStatusNote)


def mark_reports_changed(session: Session) -> None:
    """Изменение, которое не видят события сессии (настройка подразделений служб, массовые запросы):
    ревизия отчётов увеличится при commit этой транзакции."""
    session.info["reports_changed"] = True


def _touches_reports(session: Session) -> bool:
    return any(isinstance(obj, REPORT_MODELS) for obj in (*session.new, *session.deleted, *session.dirty))


@event.listens_for(Session, "before_flush")
def _mark_reports_change(session: Session, _context, _instances) -> None:
    if _touches_reports(session):
        session.info["reports_changed"] = True


@event.listens_for(Session, "before_commit")
def _bump_report_revision(session: Session) -> None:
    if session.info.get("reports_changed") or _touches_reports(session):
        session.flush()
        session.execute(update(ReportRevision).where(ReportRevision.id == 1)
                        .values(revision=ReportRevision.revision + 1, updated_at=utcnow()))
    session.info.pop("reports_changed", None)


@event.listens_for(Session, "after_rollback")
def _forget_reports_change(session: Session) -> None:
    session.info.pop("reports_changed", None)
