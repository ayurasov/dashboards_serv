"""Службы и стартовый обзор, светофор служб, журнал, палитры, раскладки, загрузки."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.errors import Forbidden, NotFound, ValidationFailed
from ...models import (
    AuditEntry,
    ColorPalette,
    DashboardLayout,
    DataImport,
    HrMonth,
    NaumenTicket,
    Partnership,
    Service,
    TpWeeklyReport,
    TrafficLightRule,
    User,
)
from ...schemas.common import Ok, Page
from ...schemas.settings import (
    AuditOut,
    DataImportOut,
    LayoutIn,
    LayoutOut,
    PaletteIn,
    PaletteOut,
    ServiceOut,
    TrafficRuleIn,
    TrafficRuleOut,
)
from ...services import access, audit, traffic_light
from ...services import hr as hr_service
from ...services import partnerships as p_service
from ...services import tp as tp_service
from ...services.cache import cached_json
from ...services.registry import HR_METRIC_CATEGORIES, SERVICE_BY_KEY
from ..deps import active_user, current_user, require_admin
from ..uploads import file_response

router = APIRouter(prefix="/api", tags=["Общее"])

LIGHT_SERVICES = ("hr", "tech")


# ---------- службы и обзор ----------

def _data_updated(db: Session) -> dict[str, datetime | None]:
    return {
        "hr": db.scalar(select(func.max(HrMonth.updated_at))),
        "tech": max(filter(None, [db.scalar(select(func.max(TpWeeklyReport.updated_at))),
                                  db.scalar(select(func.max(NaumenTicket.imported_at)))]), default=None),
        "project_product": db.scalar(select(func.max(Partnership.updated_at))),
    }


@router.get("/services", response_model=list[ServiceOut], summary="Службы, доступные пользователю")
def list_services(all: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    key = ("services", bool(all and user.is_admin), tuple(sorted(access.accessible_services(user))))
    return cached_json(db, DATA_SERVICES, key, lambda: _services(db, user, all))


DATA_SERVICES = ("hr", "tech", "project_product")


def _services(db: Session, user: User, all: bool) -> list[ServiceOut]:
    levels = dict(access.accessible_services(user))
    updated = _data_updated(db)
    services = list(db.scalars(select(Service).order_by(Service.sort_order)))
    if not (all and user.is_admin):
        services = [s for s in services if s.key in levels]
    return [ServiceOut(key=s.key, title=s.title, short_title=s.short_title, description=s.description,
                       icon=s.icon, route_prefix=s.route_prefix, has_dashboard=s.has_dashboard,
                       level=levels.get(s.key), data_updated_at=updated.get(s.key)) for s in services]


def _hr_overview(db: Session, user: User) -> dict:
    data = hr_service.dashboard(db, [], access.department_scope(user))
    latest = data["latest"]
    if not latest:
        return {"empty": True}
    metric = {m["key"]: m for m in latest["metrics"]}
    pick = [k for k in ("turnover", "avg_time_to_fill", "offers_accepted_pct", "probation_pass_rate") if k in metric]
    return {
        "empty": False, "period": latest["label"], "light_counts": latest["light_counts"],
        "kpis": [{"label": "Принято", "value": latest["hired"], "unit": "чел."},
                 {"label": "Уволено", "value": latest["fired"], "unit": "чел."}]
        + [{"label": metric[k]["label"], "value": metric[k]["value"], "unit": metric[k]["unit"],
            "light": metric[k]["light"], "delta": metric[k]["delta"], "direction": metric[k]["direction"]}
           for k in pick],
    }


def _tp_overview(db: Session) -> dict:
    rows = list(db.scalars(select(TpWeeklyReport).order_by(TpWeeklyReport.year.desc(), TpWeeklyReport.week.desc())
                           .limit(2)))
    if not rows:
        return {"empty": True}
    last, prev = rows[0], (rows[1] if len(rows) > 1 else None)
    rules = traffic_light.rules_for(db, "tech")
    keys = ("total_in_work", "total_solved_week", "ratio_solved_received", "altos_avg_time")
    kpis = []
    for k in keys:
        value = getattr(last, k)
        prev_value = getattr(prev, k) if prev else None
        rule = rules.get(k)
        kpis.append({"label": tp_service.META_BY_KEY[k]["label"], "value": value,
                     "unit": tp_service.META_BY_KEY[k]["unit"], "light": traffic_light.evaluate(value, rule),
                     "delta": None if value is None or prev_value is None else round(value - prev_value, 4),
                     "direction": rule.direction if rule else "higher_is_better"})
    lights = [traffic_light.evaluate(getattr(last, k), r) for k, r in rules.items() if hasattr(last, k)]
    open_tickets = db.scalar(select(func.count()).select_from(NaumenTicket)
                             .where(NaumenTicket.status.not_in(("Закрыта", "Выполнена")))) or 0
    return {"empty": False, "period": f"Неделя {last.period}", "light_counts": traffic_light.counts(lights),
            "kpis": kpis + [{"label": "Заявок Naumen в работе", "value": open_tickets, "unit": "шт."}]}


def _pp_overview(db: Session) -> dict:
    rows = list(db.scalars(select(Partnership)))
    if not rows:
        return {"empty": True}
    rules = p_service.rule_map(db)
    lights = [p_service.record_light(r, rules)["light"] for r in rows]
    stats = p_service.analytics(rows)
    year = date.today().year
    return {"empty": False, "period": "Все партнёрства", "light_counts": traffic_light.counts(lights),
            "kpis": [{"label": "Всего партнёрств", "value": stats["total"], "unit": ""},
                     {"label": "Завершено", "value": stats["by_status"].get("Завершено", 0), "unit": ""},
                     {"label": "В работе", "value": stats["by_status"].get("В работе", 0), "unit": ""},
                     {"label": f"Сертификатов в {year}", "value": stats["by_year"].get(year, 0), "unit": ""}]}


@router.get("/overview", summary="Стартовая страница: главное по каждой доступной службе")
def overview(db: Session = Depends(get_db), user: User = Depends(active_user)):
    scope = access.department_scope(user)
    key = ("overview", tuple(sorted(access.accessible_services(user))), None if scope is None else tuple(sorted(scope)))
    return cached_json(db, DATA_SERVICES, key, lambda: _overview(db, user))


def _overview(db: Session, user: User) -> dict:
    levels = dict(access.accessible_services(user))
    updated = _data_updated(db)
    builders = {"hr": lambda: _hr_overview(db, user), "tech": lambda: _tp_overview(db),
                "project_product": lambda: _pp_overview(db)}
    cards = []
    for service in db.scalars(select(Service).order_by(Service.sort_order)):
        if service.key not in levels:
            continue
        card = {"key": service.key, "title": service.title, "short_title": service.short_title,
                "description": service.description, "icon": service.icon, "route_prefix": service.route_prefix,
                "has_dashboard": service.has_dashboard, "level": levels[service.key],
                "data_updated_at": updated.get(service.key)}
        card.update(builders[service.key]() if service.key in builders else {"empty": True})
        cards.append(card)
    imports = list(db.scalars(select(DataImport).where(DataImport.service_key.in_(list(levels)))
                              .order_by(DataImport.created_at.desc()).limit(5)))
    return {"services": cards, "recent_imports": [DataImportOut.model_validate(i) for i in imports]}


@router.get("/imports", response_model=list[DataImportOut], summary="Журнал загрузок файлов службы")
def imports(service: str, limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_db),
            user: User = Depends(active_user)):
    if not access.has_level(user, service, "viewer"):
        raise Forbidden("Нет доступа к службе")
    return list(db.scalars(select(DataImport).where(DataImport.service_key == service)
                           .order_by(DataImport.created_at.desc()).limit(limit)))


# ---------- светофор служб ----------

def _metric_meta(db: Session, service_key: str) -> list[dict]:
    if service_key == "hr":
        return [{"key": d.key, "label": d.label, "unit": d.unit, "group": HR_METRIC_CATEGORIES.get(d.category, ""),
                 "direction": d.direction} for d in hr_service.definitions(db)]
    return [{"key": k, "label": label, "unit": u, "group": tp_service.TP_GROUPS[g], "direction": None}
            for k, label, g, u in tp_service.COLUMN_META]


def _check_light_service(service_key: str) -> None:
    if service_key not in LIGHT_SERVICES:
        raise NotFound("Для этой службы нет порогового светофора")


@router.get("/traffic-light/{service_key}", response_model=list[TrafficRuleOut], summary="Правила светофора службы")
def light_rules(service_key: str, db: Session = Depends(get_db), user: User = Depends(active_user)):
    _check_light_service(service_key)
    if not access.has_level(user, service_key, "viewer"):
        raise Forbidden("Нет доступа к службе")
    rules = traffic_light.rules_for(db, service_key)
    out = []
    for meta in _metric_meta(db, service_key):
        rule = rules.get(meta["key"])
        direction = rule.direction if rule else (meta["direction"] if meta["direction"] in
                                                 ("lower_is_better", "higher_is_better") else "higher_is_better")
        out.append(TrafficRuleOut(metric_key=meta["key"], label=meta["label"], unit=meta["unit"], group=meta["group"],
                                  direction=direction, green_threshold=rule.green_threshold if rule else None,
                                  yellow_threshold=rule.yellow_threshold if rule else None,
                                  enabled=rule.enabled if rule else False,
                                  updated_at=rule.updated_at if rule else None))
    return out


@router.put("/traffic-light/{service_key}/{metric_key}", response_model=TrafficRuleOut, summary="Изменить правило")
def set_light_rule(service_key: str, metric_key: str, body: TrafficRuleIn, request: Request,
                   db: Session = Depends(get_db), user: User = Depends(active_user)):
    _check_light_service(service_key)
    if not access.has_level(user, service_key, "manager"):
        raise Forbidden("Настраивать светофор может уровень доступа «Управление»")
    meta = {m["key"]: m for m in _metric_meta(db, service_key)}.get(metric_key)
    if meta is None:
        raise NotFound("Метрика не найдена")
    g, y = body.green_threshold, body.yellow_threshold
    if body.enabled and (g is None or y is None):
        raise ValidationFailed("Для включённого правила задайте обе границы")
    if g is not None and y is not None:
        if body.direction == "lower_is_better" and g > y:
            raise ValidationFailed("«Меньше — лучше»: граница зелёного должна быть не больше границы жёлтого")
        if body.direction == "higher_is_better" and g < y:
            raise ValidationFailed("«Больше — лучше»: граница зелёного должна быть не меньше границы жёлтого")
    rule = db.scalar(select(TrafficLightRule).where(TrafficLightRule.service_key == service_key,
                                                    TrafficLightRule.metric_key == metric_key))
    before = None
    if rule is None:
        rule = TrafficLightRule(service_key=service_key, metric_key=metric_key)
        db.add(rule)
    else:
        before = {"direction": rule.direction, "green": rule.green_threshold, "yellow": rule.yellow_threshold,
                  "enabled": rule.enabled}
    rule.direction, rule.green_threshold, rule.yellow_threshold, rule.enabled = body.direction, g, y, body.enabled
    db.flush()
    audit.record(db, user, service_key=service_key, entity_type="traffic_light_rule", entity_id=metric_key,
                 action="update", summary=f"Светофор: «{meta['label']}»", before=before,
                 after={"direction": rule.direction, "green": g, "yellow": y, "enabled": rule.enabled},
                 request=request)
    db.commit()
    return TrafficRuleOut(metric_key=metric_key, label=meta["label"], unit=meta["unit"], group=meta["group"],
                          direction=rule.direction, green_threshold=g, yellow_threshold=y, enabled=rule.enabled,
                          updated_at=rule.updated_at)


# ---------- журнал ----------

def _audit_query(entity_type: str, action: str, username: str, service_key: str, search: str,
                 date_from: date | None, date_to: date | None):
    stmt = select(AuditEntry)
    if entity_type:
        stmt = stmt.where(AuditEntry.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditEntry.action == action)
    if username:
        stmt = stmt.where(AuditEntry.username == username)
    if service_key:
        stmt = stmt.where(AuditEntry.service_key == service_key)
    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(AuditEntry.summary).like(like), func.lower(AuditEntry.entity_id).like(like)))
    if date_from:
        stmt = stmt.where(AuditEntry.occurred_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(AuditEntry.occurred_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    return stmt


@router.get("/audit", response_model=Page[AuditOut], summary="Журнал изменений")
def audit_log(entity_type: str = "", action: str = "", username: str = "", service_key: str = "", search: str = "",
              date_from: date | None = None, date_to: date | None = None,
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
              db: Session = Depends(get_db), _: User = Depends(require_admin)):
    stmt = _audit_query(entity_type, action, username, service_key, search, date_from, date_to)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(AuditEntry.occurred_at.desc(), AuditEntry.id.desc())
                            .offset((page - 1) * page_size).limit(page_size)))
    return Page[AuditOut](items=[AuditOut.model_validate(i) for i in items], total=total, page=page,
                          page_size=page_size)


@router.get("/audit/facets", summary="Значения фильтров журнала")
def audit_facets(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    def distinct(column):
        return sorted({v for v in db.scalars(select(column).distinct()) if v})

    return {"entity_types": distinct(AuditEntry.entity_type), "actions": distinct(AuditEntry.action),
            "usernames": distinct(AuditEntry.username), "services": distinct(AuditEntry.service_key)}


@router.get("/audit/export.csv", summary="Выгрузить журнал в CSV")
def audit_export(entity_type: str = "", action: str = "", username: str = "", service_key: str = "",
                 search: str = "", date_from: date | None = None, date_to: date | None = None,
                 db: Session = Depends(get_db), _: User = Depends(require_admin)):
    stmt = _audit_query(entity_type, action, username, service_key, search, date_from, date_to)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Время (UTC)", "Пользователь", "Служба", "Объект", "ID", "Действие", "Описание", "IP"])
    for e in db.scalars(stmt.order_by(AuditEntry.occurred_at.desc()).limit(50_000)):
        service = SERVICE_BY_KEY[e.service_key].title if e.service_key in SERVICE_BY_KEY else ""
        writer.writerow([e.occurred_at.isoformat(sep=" ", timespec="seconds"), e.username, service, e.entity_type,
                         e.entity_id or "", e.action, e.summary, e.ip_address])
    return file_response(("﻿" + buf.getvalue()).encode("utf-8"), "Журнал изменений.csv")


# ---------- палитры ----------

@router.get("/palette/active", response_model=PaletteOut, summary="Активная палитра")
def active_palette(db: Session = Depends(get_db), _: User = Depends(current_user)):
    palette = db.scalar(select(ColorPalette).where(ColorPalette.is_active.is_(True)).limit(1))
    if palette is None:
        raise NotFound("Активная палитра не задана")
    return palette


@router.get("/palettes", response_model=list[PaletteOut], summary="Все палитры")
def palettes(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return list(db.scalars(select(ColorPalette).order_by(ColorPalette.is_preset.desc(), ColorPalette.name)))


def _palette(db: Session, pid: int) -> ColorPalette:
    p = db.get(ColorPalette, pid)
    if p is None:
        raise NotFound("Палитра не найдена")
    return p


def _unique_palette_name(db: Session, name: str, pid: int | None = None) -> None:
    stmt = select(ColorPalette.id).where(func.lower(ColorPalette.name) == name.lower())
    if pid:
        stmt = stmt.where(ColorPalette.id != pid)
    if db.scalar(stmt):
        raise ValidationFailed("Палитра с таким названием уже есть", fields={"name": "Название занято"})


@router.post("/palettes", response_model=PaletteOut, status_code=201, summary="Создать палитру")
def create_palette(body: PaletteIn, request: Request, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    _unique_palette_name(db, body.name)
    p = ColorPalette(name=body.name, colors=body.colors, is_active=False, is_preset=False)
    db.add(p)
    db.flush()
    audit.record(db, admin, entity_type="palette", entity_id=p.id, action="create",
                 summary=f"Создана палитра «{p.name}»", request=request)
    db.commit()
    return p


@router.put("/palettes/{pid}", response_model=PaletteOut, summary="Изменить палитру")
def update_palette(pid: int, body: PaletteIn, request: Request, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    p = _palette(db, pid)
    _unique_palette_name(db, body.name, pid)
    before = {"name": p.name, "colors": p.colors}
    p.name, p.colors = body.name, body.colors
    audit.record(db, admin, entity_type="palette", entity_id=p.id, action="update",
                 summary=f"Изменена палитра «{p.name}»", before=before, after={"name": p.name, "colors": p.colors},
                 request=request)
    db.commit()
    return p


@router.post("/palettes/{pid}/activate", response_model=PaletteOut, summary="Сделать палитру активной")
def activate_palette(pid: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    p = _palette(db, pid)
    for other in db.scalars(select(ColorPalette).where(ColorPalette.is_active.is_(True))):
        other.is_active = False
    db.flush()
    p.is_active = True
    audit.record(db, admin, entity_type="palette", entity_id=p.id, action="update",
                 summary=f"Активна палитра «{p.name}»", request=request)
    db.commit()
    return p


@router.delete("/palettes/{pid}", response_model=Ok, summary="Удалить палитру")
def delete_palette(pid: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    p = _palette(db, pid)
    if p.is_active:
        raise ValidationFailed("Нельзя удалить активную палитру — сначала активируйте другую")
    if p.is_preset:
        raise ValidationFailed("Встроенную палитру удалить нельзя")
    audit.record(db, admin, entity_type="palette", entity_id=p.id, action="delete",
                 summary=f"Удалена палитра «{p.name}»", request=request)
    db.delete(p)
    db.commit()
    return Ok(message="Палитра удалена")


# ---------- личные раскладки дашбордов ----------

def _layout_service(user: User, service_key: str) -> None:
    if service_key not in SERVICE_BY_KEY:
        raise NotFound("Служба не найдена")
    if not access.has_level(user, service_key, "viewer"):
        raise Forbidden("Нет доступа к службе")


@router.get("/layouts/{service_key}", response_model=LayoutOut, summary="Моя раскладка дашборда")
def get_layout(service_key: str, db: Session = Depends(get_db), user: User = Depends(active_user)):
    _layout_service(user, service_key)
    row = db.scalar(select(DashboardLayout).where(DashboardLayout.user_id == user.id,
                                                  DashboardLayout.service_key == service_key))
    return LayoutOut(service_key=service_key, widgets=(row.layout or {}).get("widgets", []) if row else [])


@router.put("/layouts/{service_key}", response_model=LayoutOut, summary="Сохранить раскладку")
def put_layout(service_key: str, body: LayoutIn, db: Session = Depends(get_db), user: User = Depends(active_user)):
    _layout_service(user, service_key)
    keys = [w.key for w in body.widgets]
    if len(keys) != len(set(keys)):
        raise ValidationFailed("Виджет указан дважды")
    row = db.scalar(select(DashboardLayout).where(DashboardLayout.user_id == user.id,
                                                  DashboardLayout.service_key == service_key))
    payload = {"widgets": [w.model_dump() for w in body.widgets]}
    if row is None:
        db.add(DashboardLayout(user_id=user.id, service_key=service_key, layout=payload))
    else:
        row.layout = payload
    db.commit()
    return LayoutOut(service_key=service_key, widgets=payload["widgets"])


@router.delete("/layouts/{service_key}", response_model=Ok, summary="Сбросить раскладку")
def reset_layout(service_key: str, db: Session = Depends(get_db), user: User = Depends(active_user)):
    _layout_service(user, service_key)
    row = db.scalar(select(DashboardLayout).where(DashboardLayout.user_id == user.id,
                                                  DashboardLayout.service_key == service_key))
    if row is not None:
        db.delete(row)
        db.commit()
    return Ok(message="Раскладка сброшена")
