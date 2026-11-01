"""Общие таблицы: пользователи, сессии, службы и доступ, журнал, настройки."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base, utcnow

GLOBAL_ROLES = ("admin", "user")
ACCESS_LEVELS = ("viewer", "editor", "manager")
LIGHT_DIRECTIONS = ("lower_is_better", "higher_is_better")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


user_departments = Table(
    "user_departments",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("department_id", Integer, ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    users: Mapped[list[User]] = relationship(secondary=user_departments, back_populates="departments")


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'user')", name="role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200), unique=True)
    position: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    avatar: Mapped[str | None] = mapped_column(Text)  # data URL, до ~1,5 МБ
    role: Mapped[str] = mapped_column(String(20), default="user")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    departments: Mapped[list[Department]] = relationship(
        secondary=user_departments, back_populates="users", lazy="selectin", order_by="Department.name"
    )
    access: Mapped[list[ServiceAccess]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin",
        foreign_keys="ServiceAccess.user_id", order_by="ServiceAccess.service_key",
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class UserSession(Base):
    """Сессия входа. В cookie — случайный токен, в базе — только его SHA-256."""

    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")

    user: Mapped[User] = relationship()


class Service(Base):
    """Справочник служб компании. Источник — app/services/registry.py, синхронизируется при старте."""

    __tablename__ = "services"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    short_title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(40), default="grid")
    route_prefix: Mapped[str] = mapped_column(String(80))
    has_dashboard: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ServiceAccess(Base):
    """Уровень доступа пользователя к службе. Роль admin даёт полный доступ ко всем службам."""

    __tablename__ = "service_access"
    __table_args__ = (
        UniqueConstraint("user_id", "service_key"),
        CheckConstraint("level IN ('viewer', 'editor', 'manager')", name="level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    service_key: Mapped[str] = mapped_column(
        ForeignKey("services.key", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(String(20), default="viewer")
    # Только записи своих подразделений (реестр приёмов и увольнений службы персонала)
    department_scope: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    granted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    user: Mapped[User] = relationship(back_populates="access", foreign_keys=[user_id])


class AuditEntry(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    username: Mapped[str] = mapped_column(String(100), default="system")
    service_key: Mapped[str | None] = mapped_column(String(40), index=True)
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(String(500), default="")
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")


class ColorPalette(TimestampMixin, Base):
    __tablename__ = "color_palettes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    colors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_preset: Mapped[bool] = mapped_column(Boolean, default=False)


class ServiceSetting(Base):
    """Настройки службы «ключ — JSON» (блоки дашборда, параметры отображения)."""

    __tablename__ = "service_settings"

    service_key: Mapped[str] = mapped_column(
        ForeignKey("services.key", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class TrafficLightRule(Base):
    """Пороговое правило светофора для числовой метрики службы (персонал, техподдержка)."""

    __tablename__ = "traffic_light_rules"
    __table_args__ = (
        UniqueConstraint("service_key", "metric_key"),
        CheckConstraint("direction IN ('lower_is_better', 'higher_is_better')", name="direction"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_key: Mapped[str] = mapped_column(
        ForeignKey("services.key", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    metric_key: Mapped[str] = mapped_column(String(80))
    direction: Mapped[str] = mapped_column(String(20), default="higher_is_better")
    green_threshold: Mapped[float | None] = mapped_column(Float)
    yellow_threshold: Mapped[float | None] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class DataImport(Base):
    """Журнал загрузок файлов: что, кем и когда загружено — для «Данные обновлены …»."""

    __tablename__ = "data_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_key: Mapped[str] = mapped_column(
        ForeignKey("services.key", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    dataset: Mapped[str] = mapped_column(String(60))
    filename: Mapped[str] = mapped_column(String(300), default="")
    mode: Mapped[str] = mapped_column(String(20), default="replace")
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_created: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str] = mapped_column(String(100), default="system")


class DashboardLayout(Base):
    """Личная раскладка виджетов дашборда службы: порядок, размер, видимость."""

    __tablename__ = "dashboard_layouts"
    __table_args__ = (UniqueConstraint("user_id", "service_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    service_key: Mapped[str] = mapped_column(
        ForeignKey("services.key", ondelete="CASCADE", onupdate="CASCADE")
    )
    layout: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class CustomDashboard(TimestampMixin, Base):
    __tablename__ = "custom_dashboards"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)

    owner: Mapped[User | None] = relationship(lazy="selectin")
    widgets: Mapped[list[CustomDashboardWidget]] = relationship(
        back_populates="dashboard", cascade="all, delete-orphan", lazy="selectin",
        order_by="CustomDashboardWidget.sort_order",
    )


WIDGET_TYPES = ("metric_card", "line_chart", "bar_chart", "table", "note")


class CustomDashboardWidget(Base):
    __tablename__ = "custom_dashboard_widgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    dashboard_id: Mapped[int] = mapped_column(ForeignKey("custom_dashboards.id", ondelete="CASCADE"), index=True)
    widget_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200), default="")
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    dashboard: Mapped[CustomDashboard] = relationship(back_populates="widgets")
