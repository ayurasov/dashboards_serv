"""Проектный и продуктовый офис: технологические партнёрства и сертификация."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from .core import TimestampMixin

LIGHTS = ("green", "yellow", "red", "gray")
PARTNERSHIP_STATUSES = ("В работе", "Завершено", "Отложено", "Не подписывают")
PARTNERSHIP_TYPES = ("ПО", "ПАК", "Оборудование")


class Partnership(TimestampMixin, Base):
    __tablename__ = "partnerships"

    id: Mapped[int] = mapped_column(primary_key=True)
    partner: Mapped[str] = mapped_column(String(300), index=True)
    product: Mapped[str] = mapped_column(String(300), default="")
    direction: Mapped[str] = mapped_column(String(300), default="")
    almi_product: Mapped[str] = mapped_column(String(200), default="", index=True)
    almi_version: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(60), default="В работе", index=True)
    cert_date: Mapped[date | None] = mapped_column(Date)
    nda: Mapped[bool] = mapped_column(Boolean, default=False)
    agreement: Mapped[bool] = mapped_column(Boolean, default=False)
    bitrix: Mapped[str] = mapped_column(String(500), default="")
    website: Mapped[str] = mapped_column(String(500), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[str] = mapped_column(String(30), default="ПО")
    last_modified: Mapped[date | None] = mapped_column(Date)


class PartnershipLightRule(Base):
    """Правило светофора партнёрств: категория (статус, NDA, соглашение, срок сертификата) → цвет."""

    __tablename__ = "partnership_light_rules"
    __table_args__ = (CheckConstraint("light IN ('green', 'yellow', 'red', 'gray')", name="light"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    group_key: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(200))
    light: Mapped[str] = mapped_column(String(20), default="gray")
    threshold: Mapped[float | None] = mapped_column(Float)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
