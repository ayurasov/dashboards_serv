"""Схемы входящих данных и интеграций (ADR-0011)."""
from __future__ import annotations

from typing import Any

from pydantic import Field

from .common import Input


class InboxApplyIn(Input):
    options: dict[str, Any] | None = Field(default=None, description="Параметры набора (например, mode, new_users, "
                                                                      "decisions) — заменяют сохранённые")


class InboxRejectIn(Input):
    reason: str = Field(default="", max_length=1000)


class InboxRetryIn(Input):
    dataset: str | None = Field(default=None, max_length=40, description="Набор, если распознан неверно или не "
                                                                          "распознан")
    options: dict[str, Any] | None = None
    apply: bool = Field(default=False, description="Применить сразу, если план без ошибок")


class InboxRuleIn(Input):
    source: str = Field(max_length=20)
    dataset: str = Field(max_length=40)
    auto_apply: bool
    # Подписи из ответа GET /api/inbox/rules — правило можно вернуть как получено; не используются
    source_label: str | None = Field(default=None, max_length=200)
    dataset_label: str | None = Field(default=None, max_length=200)


class InboxRulesIn(Input):
    """Тот же вид, что у ответа GET: {rules: [{source, dataset, auto_apply}]}."""

    rules: list[InboxRuleIn] = Field(max_length=200)


class ScheduleIn(Input):
    mode: str = Field(default="off", pattern="^(off|interval|daily)$")
    minutes: int | None = None
    time: str | None = Field(default=None, max_length=5)
    weekdays: list[int] = []
    actions: list[str] = []


class IntegrationCreateIn(Input):
    kind: str = Field(max_length=40)
    name: str = Field(default="", max_length=200)
    config: dict[str, Any] = {}
    secrets: dict[str, str] = Field(default={}, description="Секретные поля; в ответах не возвращаются")
    schedule: ScheduleIn | None = None
    enabled: bool = False


class IntegrationUpdateIn(Input):
    name: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None
    config: dict[str, Any] | None = Field(default=None, description="Изменяемые настройки (объединяются с текущими)")
    secrets: dict[str, str] | None = Field(default=None, description="Новые значения секретов; пустое — оставить "
                                                                      "сохранённое (если адрес не изменился)")
    clear_secrets: list[str] = Field(default=[], description="Стереть эти секреты")
    schedule: ScheduleIn | None = None


class IntegrationCheckIn(Input):
    config: dict[str, Any] | None = None
    secrets: dict[str, str] | None = None


class IntegrationDraftCheckIn(Input):
    kind: str = Field(max_length=40)
    config: dict[str, Any] = {}
    secrets: dict[str, str] = {}


class IntegrationRunIn(Input):
    action: str = Field(max_length=60)


class InboundKeyIn(Input):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default=["files"], description="files — приём файлов, status — чтение статусов")
