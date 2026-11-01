"""Служба персонала: месяцы, приёмы и увольнения, метрики, заметки, цели."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base, utcnow
from .core import TimestampMixin, User

MONTH_NAMES = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
               "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
EVENT_TYPES = ("hired", "fired")


class HrMonth(TimestampMixin, Base):
    __tablename__ = "hr_months"
    __table_args__ = (
        UniqueConstraint("year", "month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="month_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text, default="")

    events: Mapped[list[HrEmployeeEvent]] = relationship(
        back_populates="month_record", cascade="all, delete-orphan", passive_deletes=True,
        order_by="HrEmployeeEvent.event_date",
    )
    values: Mapped[list[HrMetricValue]] = relationship(
        back_populates="month_record", cascade="all, delete-orphan", passive_deletes=True,
    )
    notes: Mapped[list[HrMonthNote]] = relationship(
        back_populates="month_record", cascade="all, delete-orphan", passive_deletes=True,
        order_by="HrMonthNote.created_at",
    )

    @property
    def key(self) -> str:
        return f"{self.year}-{self.month:02d}"

    @property
    def label(self) -> str:
        return f"{MONTH_NAMES[self.month]} {self.year}"


class HrEmployeeEvent(TimestampMixin, Base):
    __tablename__ = "hr_employee_events"
    __table_args__ = (CheckConstraint("event_type IN ('hired', 'fired')", name="event_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("hr_months.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(10))
    event_date: Mapped[date] = mapped_column(Date)
    full_name: Mapped[str] = mapped_column(String(300))
    position: Mapped[str] = mapped_column(String(300), default="")
    department: Mapped[str] = mapped_column(String(200), default="", index=True)
    employment_type: Mapped[str] = mapped_column(String(100), default="")
    reason: Mapped[str] = mapped_column(String(300), default="")

    month_record: Mapped[HrMonth] = relationship(back_populates="events")


class HrMetricDefinition(Base):
    """Справочник метрик. Источник — app/services/registry.py, синхронизируется при старте."""

    __tablename__ = "hr_metric_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    label: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(30), default="")
    category: Mapped[str] = mapped_column(String(40), default="general")
    aggregation: Mapped[str] = mapped_column(String(20), default="avg")
    direction: Mapped[str] = mapped_column(String(20), default="neutral")
    description: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class HrMetricValue(Base):
    __tablename__ = "hr_metric_values"
    __table_args__ = (UniqueConstraint("month_id", "metric_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("hr_months.id", ondelete="CASCADE"), index=True)
    metric_key: Mapped[str] = mapped_column(
        ForeignKey("hr_metric_definitions.key", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    value: Mapped[float | None] = mapped_column(Float)
    source_note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    month_record: Mapped[HrMonth] = relationship(back_populates="values")


class HrMonthNote(Base):
    __tablename__ = "hr_month_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("hr_months.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    month_record: Mapped[HrMonth] = relationship(back_populates="notes")
    author: Mapped[User | None] = relationship(lazy="joined")


class HrTarget(Base):
    """Цель по метрике на год и справочное значение прошлых лет (бенчмарк)."""

    __tablename__ = "hr_targets"
    __table_args__ = (UniqueConstraint("metric_key", "year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_key: Mapped[str] = mapped_column(
        ForeignKey("hr_metric_definitions.key", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(200), default="")
    reference_value: Mapped[float | None] = mapped_column(Float)
    target_value: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(300), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
