"""Проектный и продуктовый офис: технологические партнёрства."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import extract, func, or_, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ...core.db import get_db
from ...core.errors import NotFound, ValidationFailed
from ...core.timeutil import local_today
from ...models import Partnership, User
from ...schemas.common import Ok
from ...schemas.partnerships import LightRuleChange, LightRuleOut, PartnershipIn, PartnershipPatch
from ...services import audit
from ...services import partnerships as p_service
from ...services.cache import cached_json
from ...services.registry import PARTNERSHIP_LIGHT_GROUPS
from ..deps import require_export, require_records, require_service
from ..uploads import file_response, read_upload
from .org import CONFLICT_RESPONSE, IMPORT_ERRORS, _conflict, _flag

router = APIRouter(prefix="/api/partnerships", tags=["Партнёрства"])
SERVICE = "project_product"
read = require_service(SERVICE, "viewer")
edit = require_service(SERVICE, "editor")
manage = require_service(SERVICE, "manager")
# Реестр, карточка и хронология — исходные записи; дашборд и сводка — агрегаты (ADR-0009)
records = require_records(SERVICE)
records_export = require_export(SERVICE, records=True)

SNAPSHOT_FIELDS = ("partner", "product", "direction", "almi_product", "almi_version", "status", "cert_date",
                   "nda", "agreement", "type", "bitrix", "website", "comment", "last_modified")


def _filtered(db: Session, *, year: int | None = None, status: str = "", almi_product: str = "",
              direction: str = "", type_: str = "", search: str = "", light: str = "") -> list[Partnership]:
    stmt = select(Partnership).order_by(Partnership.partner, Partnership.id)
    if year:
        stmt = stmt.where(extract("year", Partnership.cert_date) == year)
    if status:
        stmt = stmt.where(Partnership.status == status)
    if almi_product:
        stmt = stmt.where(Partnership.almi_product == almi_product)
    if direction:
        stmt = stmt.where(Partnership.direction == direction)
    if type_:
        stmt = stmt.where(Partnership.type == type_)
    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Partnership.partner).like(like), func.lower(Partnership.product).like(like),
                              func.lower(Partnership.direction).like(like), func.lower(Partnership.comment).like(like),
                              func.lower(Partnership.almi_version).like(like)))
    rows = list(db.scalars(stmt))
    if light:
        rules = p_service.rule_map(db)
        rows = [r for r in rows if p_service.record_light(r, rules)["light"] == light]
    return rows


def _get(db: Session, pid: int) -> Partnership:
    p = db.get(Partnership, pid)
    if p is None:
        raise NotFound("Партнёрство не найдено")
    return p


def _snapshot(p: Partnership) -> dict:
    return {f: getattr(p, f) for f in SNAPSHOT_FIELDS}


@router.get("/options", summary="Значения для фильтров и форм")
def options(db: Session = Depends(get_db), _: User = Depends(read)):
    return cached_json(db, [SERVICE], ("pp.options",), lambda: _options(db))


def _options(db: Session) -> dict:
    def distinct(column):
        return sorted({v for v in db.scalars(select(column).distinct()) if v})

    years = sorted({int(y) for y in db.scalars(select(extract("year", Partnership.cert_date)).distinct())
                    if y is not None})
    return {"statuses": distinct(Partnership.status), "almi_products": distinct(Partnership.almi_product),
            "directions": distinct(Partnership.direction), "types": distinct(Partnership.type), "years": years}


@router.get("", summary="Реестр партнёрств")
def list_partnerships(year: int | None = None, status: str = "", almi_product: str = "", direction: str = "",
                      type: str = "", search: str = "", light: str = "",
                      db: Session = Depends(get_db), _: User = Depends(records)):
    def compute():
        rules = p_service.rule_map(db)
        rows = _filtered(db, year=year, status=status, almi_product=almi_product, direction=direction, type_=type,
                         search=search, light=light)
        return [p_service.serialize(r, rules) for r in rows]

    key = ("pp.list", year, status, almi_product, direction, type, search.strip().lower(), light, local_today())
    return cached_json(db, [SERVICE], key, compute)


@router.get("/export.xlsx", summary="Выгрузить реестр в Excel")
def export(year: int | None = None, status: str = "", almi_product: str = "", direction: str = "", type: str = "",
           search: str = "", light: str = "", db: Session = Depends(get_db), _: User = Depends(records_export)):
    rules = p_service.rule_map(db)
    rows = [p_service.serialize(r, rules) for r in _filtered(
        db, year=year, status=status, almi_product=almi_product, direction=direction, type_=type, search=search,
        light=light)]
    return file_response(p_service.export_xlsx(rows), "Реестр технологических партнёрств.xlsx")


def _import_job(db: Session, user: User, rows: list, apply: bool, filename: str, request: Request):
    if not apply:
        return {**p_service.plan_import(db, rows), "applied": False}
    result, applied = p_service.apply_import(db, user, rows, filename, request)
    if not applied:
        db.rollback()
        return _conflict(result, IMPORT_ERRORS)
    db.commit()
    return result


@router.post("/import", responses=CONFLICT_RESPONSE,
             summary="Загрузить реестр (Excel, CSV): проверка (apply=false) или применение",
             description="Столбцы выгрузки реестра: №, Партнёр, Продукт партнёра, Направление, Продукт АЛМИ, Версия, "
                         "Тип, Статус, Дата сертификата, NDA, Соглашение, Битрикс, Сайт, Комментарий. Запись "
                         "сопоставляется по «№», иначе по партнёру, продукту и версии; пустая ячейка не стирает.")
async def import_partnerships(request: Request, file: UploadFile = File(...), apply: str = Form("false"),
                              db: Session = Depends(get_db), user: User = Depends(edit)):
    raw = await read_upload(file)
    rows = await run_in_threadpool(p_service.parse_upload, file.filename or "", raw)
    return await run_in_threadpool(_import_job, db, user, rows, _flag(apply), (file.filename or "")[:200], request)


@router.get("/analytics", summary="Аналитика партнёрств")
def analytics(year: int | None = None, status: str = "", almi_product: str = "",
              db: Session = Depends(get_db), _: User = Depends(read)):
    def compute():
        rows = _filtered(db, year=year, status=status, almi_product=almi_product)
        rules = p_service.rule_map(db)
        data = p_service.analytics(rows)
        data["lights"] = p_service.light_rows(rows, rules)
        # Распределение записей по светофору — дашборду не нужен реестр (право на исходные записи)
        data["record_lights"] = _record_lights(rows, rules)
        return data

    return cached_json(db, [SERVICE], ("pp.analytics", year, status, almi_product, local_today()), compute)


def _record_lights(rows: list[Partnership], rules) -> dict[str, int]:
    out = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
    for r in rows:
        light = p_service.record_light(r, rules)["light"] if rules else "gray"
        out[light if light in out else "gray"] += 1
    return out


@router.get("/summary", summary="Сводка по годам сертификации")
def summary(db: Session = Depends(get_db), _: User = Depends(read)):
    return cached_json(db, [SERVICE], ("pp.summary", local_today()),
                       lambda: p_service.summary_by_year(_filtered(db), p_service.rule_map(db)))


@router.get("/timeline", summary="Хронология сертификаций и изменений")
def timeline(db: Session = Depends(get_db), _: User = Depends(records)):
    def compute():
        rules = p_service.rule_map(db)
        rows = [r for r in _filtered(db) if r.last_modified or r.cert_date]
        rows.sort(key=lambda r: r.last_modified or r.cert_date, reverse=True)
        return [p_service.serialize(r, rules) for r in rows]

    return cached_json(db, [SERVICE], ("pp.timeline", local_today()), compute)


@router.get("/light-rules", response_model=list[LightRuleOut], summary="Правила светофора партнёрств")
def light_rules(db: Session = Depends(get_db), _: User = Depends(read)):
    return [LightRuleOut(key=r.key, group_key=r.group_key, group=PARTNERSHIP_LIGHT_GROUPS.get(r.group_key, r.group_key),
                         label=r.label, light=r.light, threshold=r.threshold, sort_order=r.sort_order)
            for r in p_service.rule_map(db).values()]


@router.put("/light-rules", response_model=list[LightRuleOut], summary="Изменить правила светофора")
def set_light_rules(body: list[LightRuleChange], request: Request, db: Session = Depends(get_db),
                    user: User = Depends(manage)):
    rules = p_service.rule_map(db)
    before, after = {}, {}
    for item in body:
        rule = rules.get(item.key)
        if rule is None:
            raise ValidationFailed(f"Неизвестное правило: {item.key}")
        if item.light is not None and item.light != rule.light:
            before[rule.key], after[rule.key] = rule.light, item.light
            rule.light = item.light
        if item.threshold is not None:
            if rule.group_key != "cert_age" or rule.key == "cert_age:stale":
                raise ValidationFailed("Порог задаётся только для сроков «актуален» и «устаревает»")
            if item.threshold != rule.threshold:
                before[f"{rule.key}:порог"], after[f"{rule.key}:порог"] = rule.threshold, item.threshold
                rule.threshold = item.threshold
    fresh, aging = rules["cert_age:fresh"].threshold, rules["cert_age:aging"].threshold
    if fresh is not None and aging is not None and fresh >= aging:
        raise ValidationFailed("Срок «актуален» должен быть меньше срока «устаревает»")
    if after:
        audit.record(db, user, service_key=SERVICE, entity_type="partnership_light_rule", action="update",
                     summary=f"Изменены правила светофора партнёрств: {len(after)}", before=before, after=after,
                     request=request)
    db.commit()
    return light_rules(db, user)


@router.get("/{pid}", summary="Карточка партнёрства")
def get_partnership(pid: int, db: Session = Depends(get_db), _: User = Depends(records)):
    return p_service.serialize(_get(db, pid), p_service.rule_map(db))


@router.post("", status_code=201, summary="Добавить партнёрство")
def create_partnership(body: PartnershipIn, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(edit)):
    p = Partnership(**body.model_dump())
    db.add(p)
    db.flush()
    audit.record(db, user, service_key=SERVICE, entity_type="partnership", entity_id=p.id, action="create",
                 summary=f"Добавлено партнёрство: {p.partner}", after=_snapshot(p), request=request)
    db.commit()
    return p_service.serialize(p, p_service.rule_map(db))


@router.patch("/{pid}", summary="Изменить партнёрство")
def update_partnership(pid: int, body: PartnershipPatch, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(edit)):
    p = _get(db, pid)
    before = _snapshot(p)
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None and field not in ("cert_date", "last_modified"):
            continue
        setattr(p, field, value)
    b, a = audit.diff(before, _snapshot(p))
    if a:
        audit.record(db, user, service_key=SERVICE, entity_type="partnership", entity_id=p.id, action="update",
                     summary=f"Изменено партнёрство: {p.partner}", before=b, after=a, request=request)
    db.commit()
    return p_service.serialize(p, p_service.rule_map(db))


@router.delete("/{pid}", response_model=Ok, summary="Удалить партнёрство")
def delete_partnership(pid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(edit)):
    p = _get(db, pid)
    audit.record(db, user, service_key=SERVICE, entity_type="partnership", entity_id=p.id, action="delete",
                 summary=f"Удалено партнёрство: {p.partner}", before=_snapshot(p), request=request)
    db.delete(p)
    db.commit()
    return Ok(message="Партнёрство удалено")
