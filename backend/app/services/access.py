"""Модель доступа.

- Роль admin — полный доступ ко всему, включая пользователей, журнал и настройки системы.
- Остальным доступ выдаётся по службам: viewer (просмотр и выгрузки), editor (ввод и правка
  данных), manager (настройки службы: светофор, цели, загрузка файлов с заменой данных).
- department_scope ограничивает реестр приёмов и увольнений подразделениями пользователя.
"""
from __future__ import annotations

from ..models import User
from .registry import ACCESS_LEVEL_RANK, SERVICE_KEYS


def access_level(user: User, service_key: str) -> str | None:
    if user.is_admin:
        return "manager"
    for row in user.access:
        if row.service_key == service_key:
            return row.level
    return None


def has_level(user: User, service_key: str, minimum: str) -> bool:
    level = access_level(user, service_key)
    return level is not None and ACCESS_LEVEL_RANK[level] >= ACCESS_LEVEL_RANK[minimum]


def department_scope(user: User, service_key: str = "hr") -> set[str] | None:
    """Названия и коды подразделений, которыми ограничен пользователь, или None — без ограничений."""
    if user.is_admin:
        return None
    for row in user.access:
        if row.service_key == service_key and row.department_scope and row.level == "viewer":
            names: set[str] = set()
            for d in user.departments:
                names.update({d.name, d.code})
            return names
    return None


def accessible_services(user: User) -> list[tuple[str, str]]:
    """[(service_key, level)] для всех служб, доступных пользователю."""
    if user.is_admin:
        return [(key, "manager") for key in SERVICE_KEYS]
    return [(row.service_key, row.level) for row in user.access]
