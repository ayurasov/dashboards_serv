"""Общие элементы схем API."""
from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Input(BaseModel):
    """Входные данные: лишние поля — ошибка, строки обрезаются по краям."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Page[T](Schema):
    items: list[T]
    total: int
    page: int
    page_size: int


class Ok(Schema):
    ok: bool = True
    message: str = ""


class ImportResult(Schema):
    ok: bool = True
    dataset: str
    mode: str
    rows_total: int
    rows_created: int
    rows_updated: int
    rows_skipped: int
    message: str = ""
