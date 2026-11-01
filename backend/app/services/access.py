"""Модель доступа 2.0 (ADR-0009): профиль доступа + личные настройки пользователя.

Измерения доступа:
- уровень доступа к службе: viewer (просмотр и выгрузки), editor (ввод данных), manager
  (настройки службы); строка service_access перекрывает профиль, «none» запрещает службу;
- область структуры: company · branch (своя ветка) · unit (своё подразделение) — для данных,
  привязанных к подразделениям; можно задать отдельно для службы (service_access.org_scope);
- классы данных: operational (всегда) · personal · financial;
- глубина детализации сквозных отчётов (None — без ограничения);
- исходные записи (реестры) и выгрузка.

Каждое измерение — личное значение (users.access_overrides), иначе из профиля, иначе
значение по умолчанию «индивидуальной настройки» (как в 0.1.0). Администратор — всё.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import User
from . import org
from .registry import (
    ACCESS_LEVEL_RANK,
    DATA_CLASSES,
    DATA_SERVICE_KEYS,
    INDIVIDUAL_DEFAULTS,
    SERVICE_KEYS,
)

ALL_CLASSES = frozenset(DATA_CLASSES)


@dataclass(frozen=True)
class EffectiveAccess:
    is_admin: bool
    profile_key: str | None
    profile_name: str | None
    services: dict[str, str]                 # служба → уровень (только доступные)
    service_scopes: dict[str, str]           # служба → своя область структуры
    org_scope: str
    data_classes: frozenset[str]
    drill_depth: int | None                  # None — без ограничения
    can_view_records: bool
    can_export: bool
    # измерение → откуда значение: admin · personal · profile · default; для служб — service:<key>
    sources: dict[str, str] = field(default_factory=dict)

    def level(self, service_key: str) -> str | None:
        return self.services.get(service_key)

    def has_level(self, service_key: str, minimum: str) -> bool:
        level = self.services.get(service_key)
        return level is not None and ACCESS_LEVEL_RANK[level] >= ACCESS_LEVEL_RANK[minimum]

    def scope_for(self, service_key: str | None) -> str:
        if service_key and service_key in self.service_scopes:
            return self.service_scopes[service_key]
        return self.org_scope

    def allows(self, data_class: str) -> bool:
        return data_class == "operational" or data_class in self.data_classes

    def as_dict(self) -> dict:
        return {
            "is_admin": self.is_admin, "profile_key": self.profile_key, "profile_name": self.profile_name,
            "services": self.services, "service_scopes": self.service_scopes, "org_scope": self.org_scope,
            "data_classes": sorted(self.data_classes, key=list(DATA_CLASSES).index),
            "drill_depth": self.drill_depth, "can_view_records": self.can_view_records,
            "can_export": self.can_export, "sources": self.sources,
        }


def _admin_access() -> EffectiveAccess:
    return EffectiveAccess(
        is_admin=True, profile_key=None, profile_name=None,
        services={key: "manager" for key in SERVICE_KEYS}, service_scopes={}, org_scope="company",
        data_classes=ALL_CLASSES, drill_depth=None, can_view_records=True, can_export=True,
        sources={name: "admin" for name in ("services", *INDIVIDUAL_DEFAULTS)},
    )


def compute(user: User) -> EffectiveAccess:
    if user.is_admin:
        return _admin_access()
    profile = user.access_profile
    overrides = user.access_overrides or {}
    values: dict = {}
    sources: dict[str, str] = {}
    for name, default in INDIVIDUAL_DEFAULTS.items():
        if name in overrides:
            values[name], sources[name] = overrides[name], "personal"
        elif profile is not None:
            values[name], sources[name] = getattr(profile, name), "profile"
        else:
            values[name], sources[name] = default, "default"

    services: dict[str, str] = {}
    if profile is not None:
        for key, level in (profile.service_levels or {}).items():
            if key in SERVICE_KEYS and level in ACCESS_LEVEL_RANK:
                services[key] = level
                sources[f"service:{key}"] = "profile"
    scopes: dict[str, str] = {}
    for row in user.access:
        if row.level == "none":
            services.pop(row.service_key, None)
            sources[f"service:{row.service_key}"] = "personal"
            continue
        services[row.service_key] = row.level
        sources[f"service:{row.service_key}"] = "personal"
        if row.org_scope:
            scopes[row.service_key] = row.org_scope

    classes = frozenset(c for c in values["data_classes"] or [] if c in DATA_CLASSES) | {"operational"}
    return EffectiveAccess(
        is_admin=False, profile_key=profile.key if profile else None, profile_name=profile.name if profile else None,
        services=dict(sorted(services.items(), key=lambda kv: SERVICE_KEYS.index(kv[0]))),
        service_scopes=scopes, org_scope=values["org_scope"], data_classes=classes,
        drill_depth=values["drill_depth"], can_view_records=bool(values["can_view_records"]),
        can_export=bool(values["can_export"]), sources=sources,
    )


def effective(user: User) -> EffectiveAccess:
    """Действующий доступ; вычисляется один раз на объект пользователя (то есть на запрос)."""
    cached = user.__dict__.get("_effective_access")
    if cached is None:
        cached = compute(user)
        user.__dict__["_effective_access"] = cached
    return cached


# ---------------------------------------------------------------- совместимые функции 0.1.0

def access_level(user: User, service_key: str) -> str | None:
    return effective(user).level(service_key)


def has_level(user: User, service_key: str, minimum: str) -> bool:
    return effective(user).has_level(service_key, minimum)


def accessible_services(user: User) -> list[tuple[str, str]]:
    """[(service_key, level)] для всех служб, доступных пользователю."""
    return list(effective(user).services.items())


# ---------------------------------------------------------------- область структуры

def base_units(user: User, snap: org.OrgSnapshot) -> set[int]:
    """Вершины области: основное подразделение, руководимые и дополнительные."""
    units = {u for u in snap.headed.get(user.id, [])}
    if user.department_id in snap.units:
        units.add(user.department_id)
    units.update(d.id for d in user.access_units if d.id in snap.units)
    return units


def scope_units(db: Session, user: User, service_key: str | None = None) -> set[int] | None:
    """Подразделения области пользователя (для службы) или None — вся компания."""
    access = effective(user)
    scope = access.scope_for(service_key)
    if access.is_admin or scope == "company":
        return None
    snap = org.snapshot(db)
    roots = base_units(user, snap)
    return snap.descendants(roots) if scope == "branch" else roots


def department_scope(db: Session, user: User, service_key: str = "hr") -> set[str] | None:
    """Названия и коды подразделений области — для данных служб, где подразделение записано
    текстом (реестр приёмов и увольнений). None — без ограничений."""
    units = scope_units(db, user, service_key)
    if units is None:
        return None
    snap = org.snapshot(db)
    names: set[str] = set()
    for unit_id in units:
        unit = snap.units[unit_id]
        names.add(unit.name)
        if unit.code:
            names.add(unit.code)
    return names


def data_services() -> tuple[str, ...]:
    return DATA_SERVICE_KEYS
