"""API службы «Проектный офис» (ADR-0012, этап 3): дашборд, план часов, сопоставления авторов."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from ...models import ExternalIdentity, JiraWorklog, ProjectHourPlan, User
from ...schemas.common import Ok
from ...services import access, project_office
from ...services.cache import cached_json
from ..deps import active_user, current_user

router = APIRouter(prefix="/api/project-office", tags=["Проектный офис"])

SERVICE = project_office.SERVICE


def _viewer(db: Session, user: User) -> None:
    if not access.has_level(user, SERVICE, "viewer"):
        raise Forbidden("Нет доступа к службе «Проектный офис»")


def _manager(db: Session, user: User) -> None:
    if not access.has_level(user, SERVICE, "manager"):
        raise Forbidden("Нужно право «Управление» службы «Проектный офис»")


def _month(raw: str) -> date:
    """«ГГГГ-ММ» (как ключи периодов отчётов) → первый день месяца."""
    parts = str(raw or "").split("-")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValidationFailed("Месяц — в формате ГГГГ-ММ", fields={"month": "Формат"})
    year, month = int(parts[0]), int(parts[1])
    if not 2020 <= year <= 2100 or not 1 <= month <= 12:
        raise ValidationFailed("Месяц — в формате ГГГГ-ММ", fields={"month": "Формат"})
    return date(year, month, 1)


@router.get("/dashboard", summary="Дашборд: часы, проекты, задачи, активность разработки")
def dashboard(month: str = Query("", description="ГГГГ-ММ; пусто — последний месяц с трудозатратами"),
              db: Session = Depends(get_db), user: User = Depends(active_user)):
    _viewer(db, user)
    chosen = _month(month) if month else None
    if chosen is None:
        # Последний месяц с данными, но не будущий: в сырье встречаются ошибочные записи «2044 год»
        today = date.today().replace(day=1)
        latest = db.scalar(select(JiraWorklog.started)
                           .where(JiraWorklog.started < datetime(today.year, today.month, 1))
                           .order_by(JiraWorklog.started.desc()).limit(1))
        latest_day = latest.date() if hasattr(latest, "date") else latest
        chosen = (latest_day or today).replace(day=1)
    # Кэш — по месяцу и ревизии сырья: сырьё перезаливается расписанием, ревизия меняется
    from ...models import DataRevision
    revision = max((r.revision for r in db.scalars(select(DataRevision)
                                                   .where(DataRevision.service_key.in_(("jira", "gitlab"))))),
                   default=0)
    key = ("po-dashboard", chosen.isoformat(), revision)
    return cached_json(db, ("project_office",), key, lambda: project_office.dashboard(db, chosen))


# ---------------------------------------------------------------- реестры (этап 3b)


@router.get("/issues", summary="Реестр задач Jira (окно сырья)")
def issues(project: str = "", status: str = "", assignee: str = "", search: str = "",
           open_only: bool = False, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
           db: Session = Depends(get_db), user: User = Depends(active_user)):
    _viewer(db, user)
    return project_office.issue_registry(db, project=project, status=status, assignee=assignee,
                                         search=search, open_only=open_only, page=page, page_size=page_size)


@router.get("/issues/{issue_key}/merge-requests", summary="Мерж-реквесты задачи — связка «задача → код»")
def issue_mrs(issue_key: str, db: Session = Depends(get_db), user: User = Depends(active_user)):
    _viewer(db, user)
    return project_office.issue_merge_requests(db, issue_key)


@router.get("/merge-requests", summary="Реестр мерж-реквестов GitLab (окно сырья)")
def merge_requests(project_id: int | None = None, state: str = "", author: str = "", jira_key: str = "",
                   search: str = "", page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                   db: Session = Depends(get_db), user: User = Depends(active_user)):
    _viewer(db, user)
    return project_office.merge_request_registry(db, project_id=project_id, state=state, author=author,
                                                 jira_key=jira_key, search=search, page=page, page_size=page_size)


# ---------------------------------------------------------------- план часов


@router.get("/plans", summary="План часов по проектам на месяц")
def plans(month: str, db: Session = Depends(get_db), user: User = Depends(active_user)):
    _viewer(db, user)
    return list(db.scalars(select(ProjectHourPlan).where(ProjectHourPlan.month == _month(month))
                           .order_by(ProjectHourPlan.project_key)))


@router.put("/plans/{project_key}", summary="Задать план часов проекта на месяц")
def set_plan(project_key: str, body: dict, request: Request, db: Session = Depends(get_db),
             user: User = Depends(active_user)):
    _manager(db, user)
    month = _month(str(body.get("month") or ""))
    hours = body.get("hours")
    if not isinstance(hours, (int, float)) or hours < 0 or hours > 100000:
        raise ValidationFailed("Часы — число от 0 до 100 000", fields={"hours": "Число"})
    row = db.scalar(select(ProjectHourPlan).where(ProjectHourPlan.project_key == project_key,
                                                  ProjectHourPlan.month == month))
    before = row.hours if row else None
    if row is None:
        row = ProjectHourPlan(project_key=project_key, month=month, hours=hours, note=str(body.get("note") or ""))
        db.add(row)
    else:
        row.hours, row.note = hours, str(body.get("note") or row.note)
    from ...services import audit
    audit.record(db, user, service_key=SERVICE, entity_type="project_hour_plan",
                 entity_id=f"{project_key}/{month.isoformat()}", action="update",
                 summary=f"План часов: {project_key} — {hours:g} ч", before={"hours": before},
                 after={"hours": hours}, request=request)
    db.commit()
    return row


@router.delete("/plans/{project_key}", summary="Удалить план часов")
def delete_plan(project_key: str, month: str, request: Request, db: Session = Depends(get_db),
                user: User = Depends(active_user)):
    _manager(db, user)
    row = db.scalar(select(ProjectHourPlan).where(ProjectHourPlan.project_key == project_key,
                                                  ProjectHourPlan.month == _month(month)))
    if row is None:
        raise NotFound("План не найден")
    from ...services import audit
    audit.record(db, user, service_key=SERVICE, entity_type="project_hour_plan",
                 entity_id=f"{project_key}/{_month(month).isoformat()}", action="delete",
                 summary=f"План часов удалён: {project_key}", before={"hours": row.hours}, request=request)
    db.delete(row)
    db.commit()
    return Ok(message="План удалён")


@router.get("/employees", summary="Сотрудники для сопоставления (кто видит службу)")
def employees(db: Session = Depends(get_db), user: User = Depends(current_user)):
    _viewer(db, user)
    return [{"id": u.id, "full_name": u.full_name, "email": u.email}
            for u in db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name))]


# ---------------------------------------------------------------- сопоставления авторов


@router.get("/identities", summary="Сопоставления внешних авторов с сотрудниками")
def identities(db: Session = Depends(get_db), user: User = Depends(current_user)):
    _viewer(db, user)
    users = {u.id: u for u in db.scalars(select(User))}
    return [{"id": row.id, "service": row.service, "external_email": row.external_email,
             "user_id": row.user_id, "user_name": users[row.user_id].full_name
             if row.user_id in users else "", "note": row.note}
            for row in db.scalars(select(ExternalIdentity).order_by(ExternalIdentity.external_email))]


@router.get("/identities/unmatched", summary="Авторы сырья без сопоставления")
def unmatched(db: Session = Depends(get_db), user: User = Depends(current_user)):
    _viewer(db, user)
    return project_office.unmatched_authors(db)


@router.post("/identities", summary="Сопоставить автора с сотрудником", status_code=201)
def add_identity(body: dict, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(active_user)):
    _manager(db, user)
    email = str(body.get("external_email") or "").strip().lower()
    service = str(body.get("service") or "*")
    user_id = body.get("user_id")
    if not email or "@" not in email:
        raise ValidationFailed("E-mail автора обязателен", fields={"external_email": "E-mail"})
    if db.get(User, user_id) is None:
        raise NotFound("Сотрудник не найден")
    if service not in ("jira", "gitlab", "*"):
        raise ValidationFailed("Служба: jira, gitlab или * (любая)", fields={"service": "Служба"})
    exists = db.scalar(select(ExternalIdentity).where(ExternalIdentity.external_email == email,
                                                      ExternalIdentity.service == service))
    if exists:
        raise Conflict("Такое сопоставление уже есть", fields={"external_email": "Уже есть"})
    row = ExternalIdentity(service=service, external_email=email, user_id=user_id,
                           note=str(body.get("note") or ""))
    db.add(row)
    from ...services import audit
    audit.record(db, user, service_key=SERVICE, entity_type="external_identity", entity_id=email,
                 action="create", summary=f"Сопоставление: {email} → сотрудник #{user_id}",
                 request=request)
    db.commit()
    return {"id": row.id, "service": row.service, "external_email": row.external_email,
            "user_id": row.user_id, "note": row.note}


@router.delete("/identities/{identity_id}", summary="Убрать сопоставление")
def delete_identity(identity_id: int, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(active_user)):
    _manager(db, user)
    row = db.get(ExternalIdentity, identity_id)
    if row is None:
        raise NotFound("Сопоставление не найдено")
    from ...services import audit
    audit.record(db, user, service_key=SERVICE, entity_type="external_identity",
                 entity_id=row.external_email, action="delete",
                 summary=f"Сопоставление удалено: {row.external_email}", request=request)
    db.delete(row)
    db.commit()
    return Ok(message="Сопоставление удалено")
