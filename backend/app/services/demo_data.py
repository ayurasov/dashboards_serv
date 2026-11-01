"""Демонстрационные данные (DEMO_DATA=true или python -m app.cli demo-data).

Загружаются только в пустые разделы: существующие данные никогда не перезаписываются.
Учётные записи демо-стенда — в руководстве администратора, раздел «Демонстрационный стенд».
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..core.security import hash_password
from ..models import (
    TP_METRIC_COLUMNS,
    DataImport,
    Department,
    HrEmployeeEvent,
    HrMetricValue,
    HrMonth,
    HrMonthNote,
    NaumenTicket,
    Partnership,
    ServiceAccess,
    TpWeeklyReport,
    User,
)

log = logging.getLogger("app.demo")
DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"

# login, ФИО, должность, роль, пароль, [(служба, уровень, только свои подразделения)], подразделения
DEMO_USERS = (
    ("admin", "Администратор системы", "Администратор", "admin", "admin123", [], []),
    ("hr_head", "Начальник службы персонала", "Начальник службы персонала", "user", "hr123456",
     [("hr", "manager", False), ("project_product", "viewer", False), ("tech", "viewer", False)], []),
    ("tp_lead", "Руководитель техподдержки", "Руководитель группы", "user", "tp123456",
     [("tech", "manager", False)], ["TECH"]),
    ("product", "Руководитель продуктового офиса", "Руководитель офиса", "user", "pp123456",
     [("project_product", "manager", False)], ["PROJ"]),
    ("viewer", "Пользователь (просмотр)", "Аналитик", "user", "view1234",
     [("hr", "viewer", False), ("project_product", "viewer", False), ("tech", "viewer", False)], []),
    ("it_viewer", "Руководитель ИТ-службы", "Руководитель службы", "user", "it123456",
     [("hr", "viewer", True), ("it", "viewer", False)], ["IT"]),
)


def _load(name: str):
    return json.loads((DEMO_DIR / name).read_text(encoding="utf-8"))


def _empty(db: Session, model) -> bool:
    return db.scalar(select(func.count()).select_from(model)) == 0


def _log_import(db: Session, service_key: str, dataset: str, filename: str, rows: int) -> None:
    db.add(DataImport(service_key=service_key, dataset=dataset, filename=filename, mode="demo",
                      rows_total=rows, rows_created=rows, username="system"))


def load_users(db: Session) -> None:
    departments = {d.code: d for d in db.scalars(select(Department))}
    existing = set(db.scalars(select(User.username)))
    for username, full_name, position, role, password, grants, dept_codes in DEMO_USERS:
        if username in existing:
            continue
        user = User(username=username, full_name=full_name, position=position, role=role,
                    password_hash=hash_password(password), password_changed_at=utcnow())
        user.departments = [departments[c] for c in dept_codes if c in departments]
        db.add(user)
        db.flush()
        for service_key, level, scoped in grants:
            db.add(ServiceAccess(user_id=user.id, service_key=service_key, level=level, department_scope=scoped))
    db.flush()


def load_hr(db: Session) -> None:
    if not _empty(db, HrMonth):
        return
    for item in _load("hr_months.json"):
        month = HrMonth(year=item["year"], month=item["month"], comment=item.get("comment", ""))
        db.add(month)
        db.flush()
        for key, (value, note) in item["metrics"].items():
            db.add(HrMetricValue(month_id=month.id, metric_key=key, value=value, source_note=note))
        for d, name, position, department, employment in item["hired"]:
            db.add(HrEmployeeEvent(month_id=month.id, event_type="hired", event_date=date.fromisoformat(d),
                                   full_name=name, position=position, department=department,
                                   employment_type=employment))
        for d, name, position, department in item["fired"]:
            db.add(HrEmployeeEvent(month_id=month.id, event_type="fired", event_date=date.fromisoformat(d),
                                   full_name=name, position=position, department=department))
        for text in item.get("notes", []):
            db.add(HrMonthNote(month_id=month.id, content=text))
    db.flush()


def load_tp(db: Session) -> None:
    if not _empty(db, TpWeeklyReport):
        return
    rows = _load("tp_weekly_reports.json")
    count = 0
    for r in rows:
        if r.get("year") is None or r.get("week") is None:
            continue
        values = {c: r.get(c) for c in TP_METRIC_COLUMNS}
        db.add(TpWeeklyReport(year=int(r["year"]), week=int(r["week"]), note=r.get("extra") or "", **values))
        count += 1
    _log_import(db, "tech", "tp_weekly", "tp_weekly_reports.json", count)
    db.flush()


def _dt(value):
    return datetime.fromisoformat(value) if value else None


def load_naumen(db: Session) -> None:
    if not _empty(db, NaumenTicket):
        return
    rows = _load("naumen_tickets.json")
    for r in rows:
        db.add(NaumenTicket(
            number=r.get("number"), name=r.get("name") or "", registered_at=_dt(r.get("registered_at")),
            solved_at=_dt(r.get("solved_at")), deadline_at=_dt(r.get("deadline_at")),
            status=r.get("status") or "", org=r.get("org") or "", responsible=r.get("responsible") or "",
            team=r.get("team") or "", first_line=r.get("first_line") or "", channel=r.get("channel") or "",
            is_overdue=bool(r.get("overdue")), is_reopened=bool(r.get("reopened")),
            processing_hours=r.get("processing_hours"),
        ))
    _log_import(db, "tech", "naumen", "naumen_tickets.json", len(rows))
    db.flush()


def load_partnerships(db: Session) -> None:
    if not _empty(db, Partnership):
        return
    rows = _load("partnerships.json")
    for r in rows:
        db.add(Partnership(
            partner=r.get("partner") or "—", product=r.get("product") or "", direction=r.get("direction") or "",
            almi_product=r.get("almi_product") or "", almi_version=r.get("almi_version") or "",
            status=r.get("status") or "В работе",
            cert_date=date.fromisoformat(r["cert_date"]) if r.get("cert_date") else None,
            nda=bool(r.get("nda")), agreement=bool(r.get("agreement")), bitrix=r.get("bitrix") or "",
            website=r.get("website") or "", comment=r.get("comment") or "", type=r.get("type") or "ПО",
            last_modified=date.fromisoformat(r["last_modified"]) if r.get("last_modified") else None,
        ))
    _log_import(db, "project_product", "partnerships", "partnerships.json", len(rows))
    db.flush()


def load_demo_data(db: Session) -> None:
    load_users(db)
    load_hr(db)
    load_tp(db)
    load_naumen(db)
    load_partnerships(db)
    log.info("Демонстрационные данные загружены")
