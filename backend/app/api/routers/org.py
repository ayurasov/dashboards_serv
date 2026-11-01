"""Структура компании: подразделения, руководители, представления, перенос (ADR-0007)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.errors import Conflict, NotFound
from ...models import Department, User
from ...schemas.common import Ok
from ...schemas.users import DepartmentIn, DepartmentOut
from ...services import audit
from ..deps import require_admin

router = APIRouter(prefix="/api/org", tags=["Структура компании"])
departments_router = APIRouter(prefix="/api/departments", tags=["Подразделения"])


# ---------- Подразделения ----------

@departments_router.get("", response_model=list[DepartmentOut], summary="Подразделения")
def list_departments(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return list(db.scalars(select(Department).order_by(Department.name)))


def _check_department(db: Session, body: DepartmentIn, dept_id: int | None = None) -> None:
    for column, value, label in ((Department.name, body.name, "Название"), (Department.code, body.code, "Код")):
        stmt = select(Department.id).where(func.lower(column) == value.lower())
        if dept_id:
            stmt = stmt.where(Department.id != dept_id)
        if db.scalar(stmt):
            raise Conflict(f"{label} подразделения уже используется")


@departments_router.post("", response_model=DepartmentOut, status_code=201, summary="Создать подразделение")
def create_department(body: DepartmentIn, request: Request, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    _check_department(db, body)
    dept = Department(name=body.name, code=body.code.upper())
    db.add(dept)
    db.flush()
    audit.record(db, admin, entity_type="department", entity_id=dept.id, action="create",
                 summary=f"Создано подразделение {dept.name}", after={"name": dept.name, "code": dept.code},
                 request=request)
    db.commit()
    return dept


@departments_router.put("/{dept_id}", response_model=DepartmentOut, summary="Изменить подразделение")
def update_department(dept_id: int, body: DepartmentIn, request: Request, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    dept = db.get(Department, dept_id)
    if dept is None:
        raise NotFound("Подразделение не найдено")
    _check_department(db, body, dept_id)
    before = {"name": dept.name, "code": dept.code}
    dept.name, dept.code = body.name, body.code.upper()
    b, a = audit.diff(before, {"name": dept.name, "code": dept.code})
    audit.record(db, admin, entity_type="department", entity_id=dept.id, action="update",
                 summary=f"Изменено подразделение {dept.name}", before=b, after=a, request=request)
    db.commit()
    return dept


@departments_router.delete("/{dept_id}", response_model=Ok, summary="Удалить подразделение")
def delete_department(dept_id: int, request: Request, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    dept = db.get(Department, dept_id)
    if dept is None:
        raise NotFound("Подразделение не найдено")
    audit.record(db, admin, entity_type="department", entity_id=dept.id, action="delete",
                 summary=f"Удалено подразделение {dept.name}", before={"name": dept.name, "code": dept.code},
                 request=request)
    db.delete(dept)
    db.commit()
    return Ok(message="Подразделение удалено")
