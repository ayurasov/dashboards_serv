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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import Conflict, NotFound, ValidationFailed
from ..models import ACCESS_LEVELS, ORG_SCOPES, SERVICE_ACCESS_LEVELS, AccessProfile, User, name_key
from . import audit, org
from .registry import (
    ACCESS_DIMENSIONS,
    ACCESS_LEVEL_LABELS,
    ACCESS_LEVEL_RANK,
    CAPABILITIES,
    DATA_CLASS_HINTS,
    DATA_CLASSES,
    DATA_SERVICE_KEYS,
    INDIVIDUAL_DEFAULTS,
    MAX_DRILL_DEPTH,
    ORG_SCOPE_LABELS,
    SERVICE_BY_KEY,
    SERVICE_KEYS,
    SERVICES,
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


def source_access() -> EffectiveAccess:
    """Доступ источника данных (входящие, подключения): все службы и классы данных, вся компания,
    без роли администратора и без выгрузок. Используется движками загрузки, когда данные применяет
    источник или пользователь с полномочием data.manage (app/services/inbox.py)."""
    return EffectiveAccess(
        is_admin=False, profile_key=None, profile_name="Источник данных",
        services={key: "manager" for key in SERVICE_KEYS}, service_scopes={}, org_scope="company",
        data_classes=ALL_CLASSES, drill_depth=None, can_view_records=True, can_export=False,
        sources={name: "source" for name in ("services", *INDIVIDUAL_DEFAULTS)},
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


def invalidate(user: User) -> None:
    """Сбросить запомненный действующий доступ — после изменения доступа пользователя в запросе."""
    user.__dict__.pop("_effective_access", None)


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


# ---------------------------------------------------------------- ключ кэша ответов

def cache_scope(db: Session, user: User, service_key: str = "hr") -> tuple:
    """Часть ключа кэша ответа, зависящая от прав (ADR-0009): область структуры (названия и коды
    подразделений — переименование подразделения меняет ключ), классы данных и исходные записи.
    Пользователи с разными правами не получают чужой ответ из кэша."""
    scope = department_scope(db, user, service_key)
    eff = effective(user)
    return (None if scope is None else tuple(sorted(scope)), tuple(sorted(eff.data_classes)), eff.can_view_records)


# ---------------------------------------------------------------- справочник измерений

SERVICE_LEVEL_LABELS: dict[str, str] = {"none": "Нет", **ACCESS_LEVEL_LABELS}
DIMENSION_LABELS: dict[str, tuple[str, str]] = {
    "org_scope": ("Область структуры", "Данные каких подразделений видны: вся компания, своя ветка или своё"),
    "data_classes": ("Классы данных", "Операционные — всегда; персональные и финансовые — по праву"),
    "drill_depth": ("Глубина детализации", "На сколько уровней ниже вершины своей области раскрываются отчёты"),
    "can_view_records": ("Исходные записи", "Реестры и списки — или только дашборды и сводки"),
    "can_export": ("Выгрузка", "Excel, CSV и PDF"),
}
DATA_CLASS_FORBIDDEN: dict[str, str] = {
    "personal": "Нет доступа к персональным данным: ФИО, должностям, причинам увольнения",
    "financial": "Нет доступа к финансовым показателям",
}


def meta() -> dict:
    """Справочник для форм доступа: классы данных, области, измерения, уровни, полномочия, службы."""
    return {
        "data_classes": [{"key": k, "label": v, "hint": DATA_CLASS_HINTS.get(k, ""), "always": k == "operational"}
                         for k, v in DATA_CLASSES.items()],
        "org_scopes": [{"key": k, "label": v} for k, v in ORG_SCOPE_LABELS.items()],
        "dimensions": [{"key": k, "label": DIMENSION_LABELS[k][0], "hint": DIMENSION_LABELS[k][1]}
                       for k in ACCESS_DIMENSIONS],
        "levels": [{"key": k, "label": v} for k, v in SERVICE_LEVEL_LABELS.items()],
        "capabilities": [{"key": k, "label": v} for k, v in CAPABILITIES.items()],
        "services": [{"key": s.key, "title": s.title, "short_title": s.short_title, "has_dashboard": s.has_dashboard,
                      "levels": list(SERVICE_LEVEL_LABELS)} for s in SERVICES],
        "max_drill_depth": MAX_DRILL_DEPTH,
    }


# ---------------------------------------------------------------- проверка значений

def normalize_classes(values) -> list[str]:
    """Классы данных в порядке справочника; операционные — всегда."""
    chosen = set(values or []) | {"operational"}
    return [k for k in DATA_CLASSES if k in chosen]


def validate_service_levels(levels: dict[str, str], *, allow_none: bool = False) -> dict[str, str]:
    allowed = SERVICE_ACCESS_LEVELS if allow_none else ACCESS_LEVELS
    out: dict[str, str] = {}
    for key, level in (levels or {}).items():
        if key not in SERVICE_BY_KEY:
            raise ValidationFailed(f"Неизвестная служба: {key}", fields={f"service_levels.{key}": "Нет такой службы"})
        if level not in allowed:
            raise ValidationFailed(f"Недопустимый уровень доступа к службе «{SERVICE_BY_KEY[key].title}»",
                                   fields={f"service_levels.{key}": "Недопустимый уровень"})
        out[key] = level
    return dict(sorted(out.items(), key=lambda kv: SERVICE_KEYS.index(kv[0])))


def normalize_overrides(raw: dict) -> dict:
    """Личные значения измерений поверх профиля (users.access_overrides). Ключа нет — как в профиле;
    drill_depth = None — явное «без ограничения»."""
    if not isinstance(raw, dict):
        raise ValidationFailed("Личные настройки доступа — объект «измерение: значение»")
    out: dict = {}
    for name, value in raw.items():
        field_name = f"overrides.{name}"
        if name not in ACCESS_DIMENSIONS:
            raise ValidationFailed(f"Неизвестное измерение доступа: {name}",
                                   fields={field_name: "Нет такого измерения"})
        label = DIMENSION_LABELS[name][0]
        if name == "org_scope":
            if value not in ORG_SCOPES:
                raise ValidationFailed(f"{label}: допустимо {', '.join(ORG_SCOPES)}",
                                       fields={field_name: "Недопустимое значение"})
        elif name == "data_classes":
            if not isinstance(value, list) or not all(isinstance(c, str) and c in DATA_CLASSES for c in value):
                raise ValidationFailed(f"{label}: допустимо {', '.join(DATA_CLASSES)}",
                                       fields={field_name: "Недопустимое значение"})
            value = normalize_classes(value)
        elif name == "drill_depth":
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)
                                      or not 0 <= value <= MAX_DRILL_DEPTH):
                raise ValidationFailed(f"{label}: от 0 до {MAX_DRILL_DEPTH} уровней или без ограничения",
                                       fields={field_name: "Недопустимое значение"})
        elif not isinstance(value, bool):
            raise ValidationFailed(f"{label}: да или нет", fields={field_name: "Нужно да или нет"})
        out[name] = value
    return {name: out[name] for name in ACCESS_DIMENSIONS if name in out}


# ---------------------------------------------------------------- профили доступа

def profile_users_count(db: Session) -> dict[int, int]:
    rows = db.execute(select(User.access_profile_id, func.count()).where(User.access_profile_id.is_not(None))
                      .group_by(User.access_profile_id)).all()
    return {pid: count for pid, count in rows}


def list_profiles(db: Session) -> list[tuple[AccessProfile, int]]:
    counts = profile_users_count(db)
    profiles = db.scalars(select(AccessProfile).order_by(AccessProfile.sort_order, AccessProfile.id))
    return [(p, counts.get(p.id, 0)) for p in profiles]


def get_profile(db: Session, profile_id: int) -> AccessProfile:
    profile = db.get(AccessProfile, profile_id)
    if profile is None:
        raise NotFound("Профиль доступа не найден")
    return profile


def _check_unique(db: Session, *, key: str | None, name: str | None, profile_id: int | None = None) -> None:
    for other in db.scalars(select(AccessProfile)):
        if other.id == profile_id:
            continue
        if key is not None and other.key == key:
            raise Conflict("Профиль с таким ключом уже есть", fields={"key": "Ключ занят"})
        # Сравнение без регистра — в Python: lower() в SQLite не понимает кириллицу
        if name is not None and name_key(other.name) == name_key(name):
            raise Conflict(f"Профиль «{other.name}» уже есть", fields={"name": "Название занято"})


def profile_snapshot(profile: AccessProfile) -> dict:
    return {"name": profile.name, "description": profile.description, "sort_order": profile.sort_order,
            "service_levels": dict(profile.service_levels or {}), "org_scope": profile.org_scope,
            "data_classes": list(profile.data_classes or []), "drill_depth": profile.drill_depth,
            "can_view_records": profile.can_view_records, "can_export": profile.can_export}


def create_profile(db: Session, actor: User, fields: dict, request=None) -> AccessProfile:
    name = " ".join(fields["name"].split())
    _check_unique(db, key=fields["key"], name=name)
    profile = AccessProfile(
        key=fields["key"], name=name, description=fields.get("description") or "", is_system=False,
        sort_order=fields.get("sort_order", 100),
        service_levels=validate_service_levels(fields.get("service_levels") or {}),
        org_scope=fields.get("org_scope", "unit"), data_classes=normalize_classes(fields.get("data_classes")),
        drill_depth=fields.get("drill_depth"), can_view_records=fields.get("can_view_records", True),
        can_export=fields.get("can_export", True),
    )
    db.add(profile)
    db.flush()
    audit.record(db, actor, entity_type="access_profile", entity_id=profile.id, action="create",
                 summary=f"Создан профиль доступа «{profile.name}»", after={"key": profile.key,
                                                                            **profile_snapshot(profile)},
                 request=request)
    return profile


def update_profile(db: Session, actor: User, profile: AccessProfile, fields: dict, request=None) -> AccessProfile:
    before = profile_snapshot(profile)
    if fields.get("name") is not None:
        name = " ".join(fields["name"].split())
        _check_unique(db, key=None, name=name, profile_id=profile.id)
        profile.name = name
    if "description" in fields:
        profile.description = fields["description"] or ""
    for key in ("sort_order", "org_scope", "can_view_records", "can_export"):
        if fields.get(key) is not None:
            setattr(profile, key, fields[key])
    if "drill_depth" in fields:  # null — без ограничения
        profile.drill_depth = fields["drill_depth"]
    if fields.get("service_levels") is not None:
        profile.service_levels = validate_service_levels(fields["service_levels"])
    if fields.get("data_classes") is not None:
        profile.data_classes = normalize_classes(fields["data_classes"])
    b, a = audit.diff(before, profile_snapshot(profile))
    if a:
        audit.record(db, actor, entity_type="access_profile", entity_id=profile.id, action="update",
                     summary=f"Изменён профиль доступа «{profile.name}»", before=b, after=a, request=request)
    db.flush()
    return profile


def _users_dative(count: int) -> str:
    return "пользователю" if count % 10 == 1 and count % 100 != 11 else "пользователям"


def delete_profile(db: Session, actor: User, profile: AccessProfile, request=None) -> None:
    if profile.is_system:
        raise ValidationFailed("Встроенный профиль удалить нельзя — его можно изменить")
    in_use = db.scalar(select(func.count()).select_from(User).where(User.access_profile_id == profile.id)) or 0
    if in_use:
        raise Conflict(f"Профиль «{profile.name}» назначен {in_use} {_users_dative(in_use)} — "
                       "сначала назначьте им другой профиль или индивидуальную настройку", code="profile_in_use")
    audit.record(db, actor, entity_type="access_profile", entity_id=profile.id, action="delete",
                 summary=f"Удалён профиль доступа «{profile.name}»",
                 before={"key": profile.key, **profile_snapshot(profile)}, request=request)
    db.delete(profile)
    db.flush()
