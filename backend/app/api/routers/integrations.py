"""Интеграции (ADR-0011): подключения, проверка, запуск, журнал запусков, ключи для входящих вызовов.

Доступно администратору и пользователю с полномочием integrations.manage. Секреты подключений
в ответах не возвращаются — только has_secret и secret_fields. Подключение вида admin_only (Confluence: публикует
полный сквозной отчёт) создаёт, изменяет, проверяет, запускает и удаляет только администратор (403 admin_only),
остальным оно видно только для чтения (can_manage: false).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ...core.db import get_db
from ...models import User
from ...schemas.common import Ok
from ...schemas.integrations import (
    InboundKeyIn,
    IntegrationCheckIn,
    IntegrationCreateIn,
    IntegrationDraftCheckIn,
    IntegrationRunIn,
    IntegrationUpdateIn,
    schedule_body,
)
from ...services import integration_admin as admin
from ..deps import require_capability

router = APIRouter(prefix="/api/integrations", tags=["Интеграции"])
manage = require_capability("integrations.manage")


@router.get("/kinds", summary="Виды подключений: описание, поля настроек, действия")
def kinds(_: User = Depends(manage)):
    return admin.kinds()


@router.get("", summary="Подключения (с описанием вида и полями настроек)",
            description="В порядке видов (Connector.order), внутри вида — по названию. schedule — записи расписания "
                        "с подписью (label) и следующим запуском (next_run_at) каждой; next_run_at — ближайший.")
def list_integrations(db: Session = Depends(get_db), user: User = Depends(manage)):
    return admin.list_out(db, user)


@router.post("", status_code=201, summary="Создать подключение",
             description="Создаётся выключенным: включить можно после успешной проверки (PATCH enabled=true).")
def create(body: IntegrationCreateIn, request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    data = body.model_dump()
    data["schedule"] = schedule_body(body.schedule)
    row = admin.create(db, user, data, request)
    db.commit()
    return admin.integration_out(db, row, user)


@router.post("/check", summary="Проверить ещё не сохранённое подключение")
async def check_draft(body: IntegrationDraftCheckIn, user: User = Depends(manage)):
    return await run_in_threadpool(admin.check_draft, body.kind, body.config, body.secrets, user)


# ---------------------------------------------------------------- ключи для входящих вызовов

@router.get("/keys", summary="Ключи для входящих вызовов (без значений)")
def list_keys(db: Session = Depends(get_db), _: User = Depends(manage)):
    return admin.keys_out(db)


@router.get("/keys/scopes", summary="Области ключа: значение, подпись, подсказка")
def key_scopes(_: User = Depends(manage)):
    return admin.key_scopes()


@router.post("/keys", status_code=201, summary="Выпустить ключ (значение показывается один раз)")
def issue_key(body: InboundKeyIn, request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    row, token = admin.issue_key(db, user, body.name, body.scopes, request)
    db.commit()
    return {**admin.key_out(db, row), "key": token}


@router.post("/keys/{key_id}/reissue", summary="Выпустить ключ заново (старое значение перестаёт работать)")
def reissue_key(key_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    row = admin.get_key(db, key_id)
    token = admin.reissue_key(db, user, row, request)
    db.commit()
    return {**admin.key_out(db, row), "key": token}


@router.post("/keys/{key_id}/revoke", summary="Отозвать ключ")
def revoke_key(key_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    row = admin.get_key(db, key_id)
    admin.revoke_key(db, user, row, request)
    db.commit()
    return admin.key_out(db, row)


# ---------------------------------------------------------------- подключение

@router.get("/{integration_id}", summary="Подключение")
def get_integration(integration_id: int, db: Session = Depends(get_db), user: User = Depends(manage)):
    return admin.integration_out(db, admin.get(db, integration_id), user)


@router.patch("/{integration_id}", summary="Изменить подключение",
              description="config объединяется с текущими настройками; secrets — новые значения (пустые не меняют "
                          "сохранённые, если адрес не изменился); clear_secrets — стереть; enabled=true — только "
                          "после успешной проверки (409 check_required).")
def update(integration_id: int, body: IntegrationUpdateIn, request: Request, db: Session = Depends(get_db),
           user: User = Depends(manage)):
    row = admin.get(db, integration_id)
    data = body.model_dump(exclude_unset=True)
    if body.schedule is not None:
        data["schedule"] = schedule_body(body.schedule)
    admin.update(db, user, row, data, request)
    db.commit()
    return admin.integration_out(db, row, user)


@router.delete("/{integration_id}", response_model=Ok, summary="Удалить подключение (вместе с журналом запусков)")
def delete(integration_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(manage)):
    row = admin.get(db, integration_id)
    admin.delete(db, user, row, request)
    db.commit()
    return Ok(message="Подключение удалено")


def _check_job(db: Session, user: User, integration_id: int, body: dict, request: Request) -> dict:
    row = admin.get(db, integration_id)
    result = admin.check(db, user, row, body, request)
    db.commit()
    return result


@router.post("/{integration_id}/check", summary="Проверить подключение",
             description="Без тела — сохранённые настройки (успех отмечает подключение проверенным); с config/secrets "
                         "— несохранённые значения. Ответ: {ok, message, details, checked_at, draft}.")
async def check(integration_id: int, request: Request, body: IntegrationCheckIn | None = None,
                db: Session = Depends(get_db), user: User = Depends(manage)):
    data = body.model_dump(exclude_none=True) if body else {}
    return await run_in_threadpool(_check_job, db, user, integration_id, data, request)


@router.post("/{integration_id}/run", summary="Запустить действие подключения",
             description="Выполняется сразу; ответ — запись журнала запусков (status: ok · partial · error). "
                         "409 run_in_progress — запуск уже идёт.")
async def run(integration_id: int, body: IntegrationRunIn, db: Session = Depends(get_db),
              user: User = Depends(manage)):
    row = admin.get(db, integration_id)
    db.commit()
    return await run_in_threadpool(admin.run, user, row, body.action)


@router.get("/{integration_id}/runs", summary="Журнал запусков подключения")
def runs(integration_id: int, limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
         _: User = Depends(manage)):
    return admin.runs(db, admin.get(db, integration_id), limit)
