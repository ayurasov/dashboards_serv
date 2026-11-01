"""Справочники при старте: службы, подразделения, метрики, правила и палитры по умолчанию,
первичный администратор. Идемпотентно; запускается после миграций одним процессом.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.db import utcnow
from ..core.security import generate_password, hash_password
from ..models import (
    AccessProfile,
    AppSetting,
    ColorPalette,
    DataRevision,
    Department,
    HrMetricDefinition,
    HrTarget,
    Indicator,
    OrgRevision,
    PartnershipLightRule,
    ReportRevision,
    Service,
    ServiceAccess,
    TrafficLightRule,
    User,
)
from . import registry

log = logging.getLogger("app.reference")


def sync_services(db: Session) -> None:
    existing = {s.key: s for s in db.scalars(select(Service))}
    for order, item in enumerate(registry.SERVICES):
        service = existing.get(item.key) or Service(key=item.key)
        service.title = item.title
        service.short_title = item.short_title
        service.description = item.description
        service.icon = item.icon
        service.route_prefix = item.route_prefix
        service.has_dashboard = item.has_dashboard
        service.sort_order = order
        db.add(service)
    db.flush()
    known = set(db.scalars(select(DataRevision.service_key)))
    for item in registry.SERVICES:
        if item.key not in known:
            db.add(DataRevision(service_key=item.key, revision=0))
    db.flush()


def sync_departments(db: Session) -> None:
    """Начальный список подразделений — только при первом запуске: дальше структурой
    управляет администратор (ADR-0007), и удалённые подразделения не должны возвращаться."""
    if db.scalar(select(func.count()).select_from(Department)):
        return
    for order, (name, code) in enumerate(registry.DEPARTMENTS):
        db.add(Department(name=name, code=code, kind="service", sort_order=order))
    db.flush()


def ensure_access_profiles(db: Session) -> None:
    """Встроенные профили доступа создаются один раз; изменения администратора сохраняются."""
    existing = set(db.scalars(select(AccessProfile.key)))
    for item in registry.ACCESS_PROFILES:
        if item.key in existing:
            continue
        db.add(AccessProfile(key=item.key, name=item.name, description=item.description, is_system=True,
                             sort_order=item.sort_order, service_levels=dict(item.service_levels),
                             org_scope=item.org_scope, data_classes=list(item.data_classes),
                             drill_depth=item.drill_depth, can_view_records=item.can_view_records,
                             can_export=item.can_export))
    db.flush()


def ensure_computed_indicators(db: Session) -> None:
    """Вычисляемые из данных служб показатели — при первом запуске (каталог пуст): сквозной отчёт
    сразу показывает приём и увольнение, текучесть, заявки и партнёрства. Дальше каталог ведёт
    администратор; удалённые показатели не возвращаются."""
    if db.scalar(select(func.count()).select_from(Indicator)):
        return
    for order, item in enumerate(registry.DEMO_INDICATORS, start=1):
        if not item.source_key:
            continue
        threshold = item.rule_type == "threshold"
        db.add(Indicator(key=item.key, name=item.name, description=item.description, unit=item.unit,
                         data_class=item.data_class, direction=item.direction, rollup=item.rollup,
                         rule_type=item.rule_type, green_threshold=item.green if threshold else None,
                         yellow_threshold=item.yellow if threshold else None,
                         green_deviation=None if threshold else item.green,
                         yellow_deviation=None if threshold else item.yellow, default_target=item.default_target,
                         source_type="computed", source_key=item.source_key, owner_service=item.owner_service,
                         expected_kinds=list(item.expected_kinds), sort_order=order * 10, is_active=True))
    db.flush()


def ensure_org_settings(db: Session) -> None:
    existing = set(db.scalars(select(AppSetting.key)))
    for key, value in registry.ORG_SETTINGS_DEFAULTS.items():
        if key not in existing:
            db.add(AppSetting(key=key, value=value))
    if db.get(OrgRevision, 1) is None:
        db.add(OrgRevision(id=1, revision=0))
    if db.get(ReportRevision, 1) is None:
        db.add(ReportRevision(id=1, revision=0))
    db.flush()


def sync_hr_metrics(db: Session) -> None:
    """Описания метрик принадлежат коду: подписи, единицы и порядок обновляются при старте."""
    existing = {d.key: d for d in db.scalars(select(HrMetricDefinition))}
    for item in registry.HR_METRICS:
        definition = existing.get(item.key) or HrMetricDefinition(key=item.key)
        definition.label = item.label
        definition.unit = item.unit
        definition.category = item.category
        definition.aggregation = item.aggregation
        definition.direction = item.direction
        definition.description = item.description
        definition.sort_order = item.sort_order
        definition.is_active = True
        db.add(definition)
    db.flush()


def _ensure_rules(db: Session, service_key: str, defaults) -> None:
    known = set(db.scalars(select(TrafficLightRule.metric_key).where(TrafficLightRule.service_key == service_key)))
    for metric_key, green, yellow, direction, enabled in defaults:
        if metric_key not in known:
            db.add(TrafficLightRule(service_key=service_key, metric_key=metric_key, green_threshold=green,
                                    yellow_threshold=yellow, direction=direction, enabled=enabled))
    db.flush()


def ensure_targets(db: Session) -> None:
    known = {(t.metric_key, t.year) for t in db.scalars(select(HrTarget))}
    for metric_key, year, label, reference, target, description, source in registry.HR_DEFAULT_TARGETS:
        if (metric_key, year) not in known:
            db.add(HrTarget(metric_key=metric_key, year=year, label=label, reference_value=reference,
                            target_value=target, description=description, source=source))
    db.flush()


def ensure_partnership_rules(db: Session) -> None:
    known = set(db.scalars(select(PartnershipLightRule.key)))
    for order, (key, group, label, light, threshold) in enumerate(registry.PARTNERSHIP_DEFAULT_RULES):
        if key not in known:
            db.add(PartnershipLightRule(key=key, group_key=group, label=label, light=light,
                                        threshold=threshold, sort_order=order))
    db.flush()


def ensure_palettes(db: Session) -> None:
    palettes = {p.name: p for p in db.scalars(select(ColorPalette))}
    for preset in registry.PALETTE_PRESETS:
        palette = palettes.get(preset["name"])
        if palette is None:
            palette = ColorPalette(name=preset["name"], colors=preset["colors"], is_preset=True, is_active=False)
            db.add(palette)
            palettes[palette.name] = palette
        else:
            palette.is_preset = True
    if not any(p.is_active for p in palettes.values()):
        palettes[registry.DEFAULT_PALETTE_NAME].is_active = True
    db.flush()


def ensure_initial_admin(db: Session) -> str | None:
    """Создаёт администратора, если в базе нет ни одного пользователя. Возвращает пароль,
    если он сгенерирован (его нужно показать в журнале один раз)."""
    if db.scalar(select(User.id).limit(1)) is not None:
        return None
    password = settings.admin_password or generate_password()
    admin = User(username=settings.admin_username, full_name="Администратор", role="admin",
                 password_hash=hash_password(password), must_change_password=True,
                 password_changed_at=utcnow())
    db.add(admin)
    db.flush()
    generated = None if settings.admin_password else password
    if generated:
        log.warning("Создан администратор «%s» со временным паролем: %s — смените его при первом входе",
                    admin.username, generated)
    else:
        log.info("Создан администратор «%s» с паролем из ADMIN_PASSWORD", admin.username)
    return generated


def ensure_admin_access(db: Session) -> None:
    """Удаляет «осиротевшие» строки доступа к службам, которых больше нет в справочнике."""
    keys = set(registry.SERVICE_KEYS)
    for row in db.scalars(select(ServiceAccess)):
        if row.service_key not in keys:
            db.delete(row)
    db.flush()


def sync_reference_data(db: Session) -> None:
    sync_services(db)
    sync_departments(db)
    ensure_access_profiles(db)
    ensure_org_settings(db)
    ensure_computed_indicators(db)
    sync_hr_metrics(db)
    _ensure_rules(db, "hr", registry.HR_DEFAULT_RULES)
    _ensure_rules(db, "tech", registry.TP_DEFAULT_RULES)
    ensure_targets(db)
    ensure_partnership_rules(db)
    ensure_palettes(db)
    ensure_admin_access(db)
