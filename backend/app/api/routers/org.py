"""Структура компании: подразделения, руководители, представления, перенос (ADR-0007).

/api/org — оргсхема и карточка сотрудника (всем вошедшим), настройки структуры, поля подчинения,
перенос структуры и сотрудников, загрузка списком, синхронизация с AD, история;
/api/departments — справочник подразделений (всем вошедшим) и его ведение.
Изменения — у администратора и ведущих структуру (полномочие org.manage).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from ...core.db import get_db
from ...core.errors import VALIDATION_MESSAGES, NotFound, ValidationFailed
from ...models import User
from ...schemas.common import Ok
from ...schemas.org import (
    AdStatusOut,
    AdSyncIn,
    DepartmentCreateIn,
    DepartmentOut,
    DepartmentUpdateIn,
    EmployeeDecisionIn,
    EmployeePlanOut,
    EmployeesImportIn,
    HeadsIn,
    ImportPlanOut,
    ListImportIn,
    OrgHistoryOut,
    OrgSettingsIn,
    OrgSettingsOut,
    OrgTreeOut,
    PersonCardOut,
    PersonOrgIn,
    StructureImportIn,
    StructurePlanOut,
)
from ...services import ad_sync, employee_transfer, org, org_admin, org_import, org_transfer
from ..deps import active_user, require_capability
from ..uploads import file_response, read_upload

log = logging.getLogger("app.org")
router = APIRouter(prefix="/api/org", tags=["Структура компании"])
departments_router = APIRouter(prefix="/api/departments", tags=["Подразделения"])
manage = require_capability("org.manage")

IMPORT_ERRORS = "Исправьте ошибки в файле — ничего не записано"
CONFLICT_RESPONSE = {409: {"description": "План с ошибками (code: import_has_errors) — ничего не записано"}}
UPLOAD_BODY = {
    "requestBody": {"content": {
        "multipart/form-data": {"schema": {"type": "object", "properties": {
            "file": {"type": "string", "format": "binary"}, "apply": {"type": "boolean"},
            "create_missing": {"type": "boolean"}, "new_users": {"type": "string"},
            "decisions": {"type": "string", "description": "JSON: решения по коллизиям"}}}},
        "application/json": {"schema": {"type": "object"}},
    }},
}


def _conflict(result: dict, detail: str = IMPORT_ERRORS) -> JSONResponse:
    return JSONResponse({**result, "applied": False, "detail": detail, "code": "import_has_errors"},
                        status_code=409)


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "да"}


async def _payload(request: Request) -> tuple[dict, UploadFile | None, bytes | None]:
    """Тело загрузки: multipart (файл и поля формы) или JSON."""
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form()
        file = form.get("file")
        fields = {k: v for k, v in form.items() if k != "file" and isinstance(v, str)}
        if not isinstance(file, UploadFile):
            raise ValidationFailed("Выберите файл", fields={"file": "Обязательное поле"})
        return fields, file, await read_upload(file)
    try:
        body = await request.json()
    except ValueError:
        raise ValidationFailed("Ожидается файл (multipart/form-data) или JSON") from None
    if not isinstance(body, dict):
        raise ValidationFailed("Ожидается объект JSON")
    return body, None, None


def _validate(model, data: Any):
    try:
        return TypeAdapter(model).validate_python(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        place = ".".join(str(p) for p in first.get("loc", ())) or "body"
        message = VALIDATION_MESSAGES.get(first.get("type", ""), "Недопустимое значение")
        raise ValidationFailed(f"{message}: {place}" if place != "body" else message,
                               fields={place: message}) from None


# ---------------------------------------------------------------- оргсхема и сотрудники

@router.get("/tree", response_model=OrgTreeOut, summary="Структура для оргсхемы",
            description="Подразделения с численностью и руководителями, сотрудники с непосредственными "
                        "руководителями. Отключённые сотрудники и email — только для ведущих структуру.")
def tree(db: Session = Depends(get_db), user: User = Depends(active_user)):
    return Response(content=org_admin.tree_body(db, user), media_type="application/json")


@router.get("/people/{person_id}", response_model=PersonCardOut, summary="Карточка сотрудника в структуре")
def person(person_id: int, db: Session = Depends(get_db), user: User = Depends(active_user)):
    return org_admin.person_card(org.snapshot(db), person_id, user.can("org.manage"))


@router.get("/people/{person_id}/avatar", summary="Фото сотрудника", response_class=Response,
            responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}, 404: {"description": "Нет фото"}})
def person_avatar(person_id: int, db: Session = Depends(get_db), user: User = Depends(active_user)):
    content, mime = org_admin.avatar(db, org.snapshot(db), person_id, user.can("org.manage"))
    return Response(content=content, media_type=mime, headers={"Cache-Control": "private, max-age=300"})


@router.patch("/people/{person_id}", response_model=PersonCardOut, summary="Изменить подчинение сотрудника")
def update_person(person_id: int, body: PersonOrgIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(manage)):
    org_admin.update_person(db, user, person_id, body, request)
    db.commit()
    return org_admin.person_card(org.snapshot(db), person_id, True)


# ---------------------------------------------------------------- настройки структуры

@router.get("/settings", response_model=OrgSettingsOut, summary="Настройки структуры")
def get_settings(db: Session = Depends(get_db), _: User = Depends(active_user)):
    return org_admin.settings_out(db)


@router.put("/settings", response_model=OrgSettingsOut, summary="Изменить настройки структуры")
def put_settings(body: OrgSettingsIn, request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    org_admin.update_settings(db, user, body, request)
    db.commit()
    return org_admin.settings_out(db)


# ---------------------------------------------------------------- перенос структуры

@router.get("/export", summary="Выгрузить структуру (JSON)", response_class=Response,
            responses={200: {"content": {"application/json": {}}}})
def export_structure(db: Session = Depends(get_db), _: User = Depends(manage)):
    body = json.dumps(org_transfer.export_structure(db), ensure_ascii=False, indent=2).encode("utf-8")
    name = org_transfer.export_filename()
    return Response(content=body, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.post("/import/structure", response_model=StructurePlanOut, responses=CONFLICT_RESPONSE,
             summary="Загрузить структуру: проверка (apply=false) или применение")
def import_structure(body: StructureImportIn, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(manage)):
    if not body.apply:
        return {**org_transfer.plan_structure(db, body.bundle, apply_settings=body.apply_settings).as_dict(),
                "applied": False, "settings_applied": False}
    result, applied = org_transfer.apply_structure(db, user, body.bundle, apply_settings=body.apply_settings,
                                                   request=request)
    if not applied:
        db.rollback()
        return _conflict(result)
    db.commit()
    log.info("org structure imported: %s", result["summary"])
    return {**result, "settings_applied": body.apply_settings and bool(result["settings"])}


# ---------------------------------------------------------------- перенос сотрудников

@router.get("/employees/export", summary="Выгрузить сотрудников (Excel, CSV, JSON)", response_class=Response)
def export_employees(format: Literal["xlsx", "csv", "json"] = "xlsx",
                     inactive: int = Query(1, ge=0, le=1, description="1 — вместе с отключёнными"),
                     db: Session = Depends(get_db), _: User = Depends(manage)):
    records = employee_transfer.export_records(db, include_inactive=bool(inactive))
    if format == "csv":
        return file_response(employee_transfer.export_csv(records), "Сотрудники.csv")
    if format == "json":
        response = file_response(employee_transfer.export_json(records), "Сотрудники.json")
        response.headers["content-type"] = "application/json"
        return response
    return file_response(employee_transfer.export_xlsx(records), "Сотрудники.xlsx")


def _employees_job(db: Session, user: User, records: list, options: dict, request: Request):
    if not options["apply"]:
        plan = employee_transfer.plan_employees(db, records, actor=user, new_users=options["new_users"],
                                                decisions=options["decisions"])
        return {**plan.as_dict(), "applied": False}
    result, applied = employee_transfer.apply_employees(db, user, records, new_users=options["new_users"],
                                                        decisions=options["decisions"], request=request)
    if not applied:
        db.rollback()
        return _conflict(result, IMPORT_ERRORS if result["summary"]["errors"]
                         else "Ответьте на вопросы по сотрудникам — ничего не записано")
    db.commit()
    log.info("employees imported: %s", result["summary"])
    return result


@router.post("/employees/import", response_model=EmployeePlanOut, responses=CONFLICT_RESPONSE,
             openapi_extra=UPLOAD_BODY, summary="Загрузить сотрудников: проверка (apply=false) или применение",
             description="Файл .xlsx, .csv или .json (multipart: file, apply, new_users, decisions — JSON-строка) "
                         "или JSON: {format, content, apply, new_users, decisions}. decisions — {email: {identity: "
                         "same|new, fields: {поле: {choice: current|incoming|merge|custom, value}}}}.")
async def import_employees(request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    fields, file, raw = await _payload(request)
    if file is not None:
        try:
            decisions = json.loads(fields.get("decisions") or "{}")
        except ValueError:
            raise ValidationFailed("decisions: ожидается JSON", fields={"decisions": "Некорректный JSON"}) from None
        new_users = fields.get("new_users") or "no_access"
        if new_users not in employee_transfer.NEW_USER_MODES:
            raise ValidationFailed("new_users: active, inactive или no_access", fields={"new_users": "Неизвестно"})
        options = {"apply": _flag(fields.get("apply")), "new_users": new_users,
                   "decisions": _validate(dict[str, EmployeeDecisionIn], decisions)}
        records = await run_in_threadpool(employee_transfer.parse_upload, file.filename or "", raw)
    else:
        body = _validate(EmployeesImportIn, fields)
        options = {"apply": body.apply, "new_users": body.new_users, "decisions": body.decisions}
        records = await run_in_threadpool(employee_transfer.parse_content, body.format, body.content)
    options["decisions"] = {k: v.model_dump() for k, v in options["decisions"].items()}
    return await run_in_threadpool(_employees_job, db, user, records, options, request)


# ---------------------------------------------------------------- загрузка списком и AD

def _import_job(db: Session, user: User, rows: list, options: dict, request: Request, detail: str = IMPORT_ERRORS):
    if not options.pop("apply"):
        return {**org_import.plan_import(db, rows, actor_id=user.id, **options).as_dict(), "applied": False}
    result, applied = org_import.apply_import(db, user, rows, request=request, **options)
    if not applied:
        db.rollback()
        return _conflict(result, detail)
    db.commit()
    log.info("org import applied (%s): %s", options.get("source"), result["summary"])
    return result


@router.post("/import/list", response_model=ImportPlanOut, responses=CONFLICT_RESPONSE, openapi_extra=UPLOAD_BODY,
             summary="Быстрая загрузка списком (CSV, Excel): проверка или применение",
             description="Столбцы: email, ФИО, Логин, Подразделение (путь через «/»), Должность, Руководитель "
                         "(email), Руководит (да/нет), Внешний ID. Multipart: file, create_missing, apply; "
                         "или JSON: {content: текст CSV, create_missing, apply}.")
async def import_list(request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    fields, file, raw = await _payload(request)
    if file is not None:
        options = {"apply": _flag(fields.get("apply")), "create_missing": _flag(fields.get("create_missing"))}
        rows = await run_in_threadpool(org_import.parse_upload, file.filename or "", raw)
    else:
        body = _validate(ListImportIn, fields)
        options = {"apply": body.apply, "create_missing": body.create_missing}
        rows = await run_in_threadpool(lambda: org_import.parse_rows(org_import.csv_rows(body.content)))
    return await run_in_threadpool(_import_job, db, user, rows, {**options, "source": "csv"}, request)


@router.get("/sync/ad", response_model=AdStatusOut, summary="Синхронизация с AD: настройка (без секретов)")
def ad_status(_: User = Depends(manage)):
    return ad_sync.status()


@router.post("/sync/ad", response_model=ImportPlanOut, summary="Синхронизация с AD: проверка или применение",
             responses={**CONFLICT_RESPONSE, 503: {"description": "Каталог недоступен (code: ad_unavailable)"}})
def ad_sync_run(body: AdSyncIn, request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    rows, refs = ad_sync.load_rows()
    options = {"apply": body.apply, "source": "ad", "create_missing": body.create_missing,
               "deactivate_missing": body.deactivate_missing, "manager_refs": refs}
    return _import_job(db, user, rows, options, request,
                       detail="В данных каталога есть ошибки — исправьте их в AD или в системе; ничего не записано")


# ---------------------------------------------------------------- история

@router.get("/history", response_model=list[OrgHistoryOut], summary="История изменений структуры")
def history(entity_type: Literal["department", "user"] | None = None, entity_id: str | None = None,
            limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(manage)):
    return org_admin.history(db, entity_type, entity_id, limit)


# ---------------------------------------------------------------- подразделения

def _department(db: Session, dept_id: int, privileged: bool = True) -> dict:
    snap = org.snapshot(db)
    if dept_id not in snap.units:
        raise NotFound("Подразделение не найдено")
    return org_admin.department_dict(snap, dept_id, privileged)


@departments_router.get("", response_model=list[DepartmentOut], summary="Подразделения",
                        description="Плоский список в порядке дерева: родители раньше вложенных.")
def list_departments(db: Session = Depends(get_db), user: User = Depends(active_user)):
    return org_admin.list_departments(org.snapshot(db), user.can("org.manage"))


@departments_router.get("/{dept_id}", response_model=DepartmentOut, summary="Подразделение")
def get_department(dept_id: int, db: Session = Depends(get_db), user: User = Depends(active_user)):
    return _department(db, dept_id, user.can("org.manage"))


@departments_router.post("", response_model=DepartmentOut, status_code=201, summary="Создать подразделение")
def create_department(body: DepartmentCreateIn, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(manage)):
    dept_id = org_admin.create_department(db, user, body, request)
    db.commit()
    return _department(db, dept_id)


@departments_router.patch("/{dept_id}", response_model=DepartmentOut, summary="Изменить подразделение")
@departments_router.put("/{dept_id}", response_model=DepartmentOut, include_in_schema=False)
def update_department(dept_id: int, body: DepartmentUpdateIn, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(manage)):
    org_admin.update_department(db, user, dept_id, body, request)
    db.commit()
    return _department(db, dept_id)


@departments_router.delete("/{dept_id}", response_model=Ok, summary="Удалить подразделение")
def delete_department(dept_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    name = org_admin.delete_department(db, user, dept_id, request)
    db.commit()
    return Ok(message=f"Подразделение «{name}» удалено")


@departments_router.put("/{dept_id}/heads", response_model=DepartmentOut, summary="Руководители подразделения",
                        description="Состав целиком; primary_id — основной (среди user_ids). Без primary_id "
                                    "основной сохраняется, единственный руководитель становится основным сам.")
def set_heads(dept_id: int, body: HeadsIn, request: Request, db: Session = Depends(get_db),
              user: User = Depends(manage)):
    org_admin.set_heads(db, user, dept_id, body, request)
    db.commit()
    return _department(db, dept_id)

