"""Техническая поддержка: недельный отчёт и заявки Naumen SD."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base, utcnow
from .core import TimestampMixin

# Числовые показатели недельного отчёта — в порядке столбцов исходной таблицы Excel.
TP_METRIC_COLUMNS: tuple[str, ...] = (
    "total_in_work", "avail_total",
    "rushydro_hours", "transneft_hours", "roscosmos_hours", "bryansk_hours",
    "mchs_hours", "internal_sales_hours",
    "new_received", "renewed", "ratio_solved_received",
    "altos_rusg_email", "altos_rusg_tf", "altos_other_email", "altos_other_tf",
    "altoffice_rusg_email", "altoffice_rusg_tf", "altoffice_other_email", "altoffice_other_tf",
    "projserver_taken", "total_solved_week",
    "altos_avg_time", "altos_total", "altos_1_2line", "altos_3line",
    "altoffice_avg_time", "altoffice_total", "altoffice_1_2line", "altoffice_3line",
    "projserver_solved",
    "altos_avail_total", "altos_avail_1_3", "altos_avail_4_7", "altos_avail_8_10",
    "altoffice_avail_total", "altoffice_avail_1_3", "altoffice_avail_4_7", "altoffice_avail_8_10",
    "projserver_avail",
)


class TpWeeklyReport(TimestampMixin, Base):
    """Неделя отчёта техподдержки: нагрузка, трудозатраты, поток и решение заявок."""

    __tablename__ = "tp_weekly_reports"
    __table_args__ = (
        UniqueConstraint("year", "week"),
        CheckConstraint("week BETWEEN 1 AND 53", name="week_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer)
    week: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default="")

    total_in_work: Mapped[float | None] = mapped_column(Float)
    avail_total: Mapped[float | None] = mapped_column(Float)
    rushydro_hours: Mapped[float | None] = mapped_column(Float)
    transneft_hours: Mapped[float | None] = mapped_column(Float)
    roscosmos_hours: Mapped[float | None] = mapped_column(Float)
    bryansk_hours: Mapped[float | None] = mapped_column(Float)
    mchs_hours: Mapped[float | None] = mapped_column(Float)
    internal_sales_hours: Mapped[float | None] = mapped_column(Float)
    new_received: Mapped[float | None] = mapped_column(Float)
    renewed: Mapped[float | None] = mapped_column(Float)
    ratio_solved_received: Mapped[float | None] = mapped_column(Float)
    altos_rusg_email: Mapped[float | None] = mapped_column(Float)
    altos_rusg_tf: Mapped[float | None] = mapped_column(Float)
    altos_other_email: Mapped[float | None] = mapped_column(Float)
    altos_other_tf: Mapped[float | None] = mapped_column(Float)
    altoffice_rusg_email: Mapped[float | None] = mapped_column(Float)
    altoffice_rusg_tf: Mapped[float | None] = mapped_column(Float)
    altoffice_other_email: Mapped[float | None] = mapped_column(Float)
    altoffice_other_tf: Mapped[float | None] = mapped_column(Float)
    projserver_taken: Mapped[float | None] = mapped_column(Float)
    total_solved_week: Mapped[float | None] = mapped_column(Float)
    altos_avg_time: Mapped[float | None] = mapped_column(Float)
    altos_total: Mapped[float | None] = mapped_column(Float)
    altos_1_2line: Mapped[float | None] = mapped_column(Float)
    altos_3line: Mapped[float | None] = mapped_column(Float)
    altoffice_avg_time: Mapped[float | None] = mapped_column(Float)
    altoffice_total: Mapped[float | None] = mapped_column(Float)
    altoffice_1_2line: Mapped[float | None] = mapped_column(Float)
    altoffice_3line: Mapped[float | None] = mapped_column(Float)
    projserver_solved: Mapped[float | None] = mapped_column(Float)
    altos_avail_total: Mapped[float | None] = mapped_column(Float)
    altos_avail_1_3: Mapped[float | None] = mapped_column(Float)
    altos_avail_4_7: Mapped[float | None] = mapped_column(Float)
    altos_avail_8_10: Mapped[float | None] = mapped_column(Float)
    altoffice_avail_total: Mapped[float | None] = mapped_column(Float)
    altoffice_avail_1_3: Mapped[float | None] = mapped_column(Float)
    altoffice_avail_4_7: Mapped[float | None] = mapped_column(Float)
    altoffice_avail_8_10: Mapped[float | None] = mapped_column(Float)
    projserver_avail: Mapped[float | None] = mapped_column(Float)

    @property
    def period(self) -> str:
        return f"{self.year}-W{self.week:02d}"


class NaumenTicket(Base):
    """Заявка из выгрузки Naumen Service Desk."""

    __tablename__ = "naumen_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int | None] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(String(50), default="")
    registered_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    solved_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(100), default="")
    org: Mapped[str] = mapped_column(String(300), default="", index=True)
    responsible: Mapped[str] = mapped_column(String(300), default="")
    team: Mapped[str] = mapped_column(String(200), default="")
    first_line: Mapped[str] = mapped_column(String(300), default="")
    channel: Mapped[str] = mapped_column(String(100), default="")
    is_overdue: Mapped[bool] = mapped_column(Boolean, default=False)
    is_reopened: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_hours: Mapped[float | None] = mapped_column(Float)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
