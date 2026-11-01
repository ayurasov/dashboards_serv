"""Демонстрационные данные (DEMO_DATA=true или python -m app.cli demo-data).

Загружаются только в пустые разделы: существующие данные никогда не перезаписываются.
Учётные записи демо-стенда — в руководстве администратора, раздел «Демонстрационный стенд».
"""
from __future__ import annotations

import json
import logging
import math
import random
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..core.security import hash_password
from ..core.timeutil import local_today
from ..models import (
    TP_METRIC_COLUMNS,
    AccessProfile,
    DataImport,
    Department,
    DepartmentHead,
    HrEmployeeEvent,
    HrMetricValue,
    HrMonth,
    HrMonthNote,
    Indicator,
    IndicatorValue,
    NaumenTicket,
    Partnership,
    ServiceAccess,
    TpWeeklyReport,
    UnitStatusNote,
    User,
)
from .registry import DEMO_INDICATORS

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
    # Уровни сотрудников модели доступа 2.0 (профили — в DEMO_PROFILES)
    ("ceo", "Громов Андрей Викторович", "Генеральный директор", "user", "ceo12345", [], ["ALMI"]),
    # tech_dir вводит операционные показатели сквозного отчёта (служба-владелец — Аппарат ГД) по своей ветке
    ("tech_dir", "Соколова Мария Игоревна", "Технический директор", "user", "td123456",
     [("apparat_gd", "editor", False)], ["TECHDIR"]),
    ("engineer", "Петров Илья Сергеевич", "Инженер технической поддержки", "user", "en123456", [], ["SUP-OS"]),
)
DEMO_PROFILES = {"ceo": "executive", "tech_dir": "director", "tp_lead": "head", "it_viewer": "head",
                 "engineer": "employee"}

# Демо-структура: код, название, тип, код родителя, руководитель (логин)
DEMO_ORG = (
    ("ALMI", "АЛМИ Партнер", "company", None, "ceo"),
    ("ADMIN", "Аппарат генерального директора", "division", "ALMI", "ceo"),
    ("AHO", "АХО", "department", "ADMIN", None),
    ("HR", "Служба персонала", "service", "ADMIN", "hr_head"),
    ("COMMDIR", "Коммерческая дирекция", "division", "ALMI", None),
    ("COMM", "Коммерческая служба", "service", "COMMDIR", None),
    ("MKT", "Служба маркетинга", "service", "COMMDIR", None),
    ("TECHDIR", "Техническая дирекция", "division", "ALMI", "tech_dir"),
    ("TECH", "Техническая служба", "service", "TECHDIR", "tp_lead"),
    ("SUP-OS", "Группа поддержки AlterOS", "group", "TECH", None),
    ("SUP-OFFICE", "Группа поддержки AlterOffice", "group", "TECH", None),
    ("IT", "ИТ-служба", "service", "TECHDIR", "it_viewer"),
    ("PROJ", "Проектная служба", "service", "ALMI", "product"),
)


def _load(name: str):
    return json.loads((DEMO_DIR / name).read_text(encoding="utf-8"))


def _empty(db: Session, model) -> bool:
    return db.scalar(select(func.count()).select_from(model)) == 0


def _log_import(db: Session, service_key: str, dataset: str, filename: str, rows: int) -> None:
    db.add(DataImport(service_key=service_key, dataset=dataset, filename=filename, mode="demo",
                      rows_total=rows, rows_created=rows, username="system"))


def load_org(db: Session) -> None:
    """Дерево структуры поверх начального плоского списка (только если структура ещё плоская)."""
    existing = {d.code: d for d in db.scalars(select(Department)) if d.code}
    if any(d.parent_id for d in existing.values()):
        return
    for order, (code, name, kind, parent, _head) in enumerate(DEMO_ORG):
        unit = existing.get(code)
        if unit is None:
            unit = Department(name=name, code=code)
            db.add(unit)
            existing[code] = unit
        unit.kind = kind
        unit.sort_order = order
        unit.org_source = "demo"
        unit.parent_id = None
        db.flush()
        if parent:
            unit.parent_id = existing[parent].id
    db.flush()


def load_org_heads(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(DepartmentHead)):
        return
    units = {d.code: d for d in db.scalars(select(Department)) if d.code}
    users = {u.username: u for u in db.scalars(select(User))}
    for code, _name, _kind, _parent, head in DEMO_ORG:
        if head and code in units and head in users:
            db.add(DepartmentHead(department_id=units[code].id, user_id=users[head].id, is_primary=True))
    if "ceo" in users:
        users["ceo"].reports_to_none = True
    profiles = {p.key: p for p in db.scalars(select(AccessProfile))}
    for username, key in DEMO_PROFILES.items():
        if username in users and key in profiles and users[username].access_profile_id is None:
            users[username].access_profile_id = profiles[key].id
    db.flush()


def load_users(db: Session) -> None:
    departments = {d.code: d for d in db.scalars(select(Department))}
    existing = set(db.scalars(select(User.username)))
    for username, full_name, position, role, password, grants, dept_codes in DEMO_USERS:
        if username in existing:
            continue
        user = User(username=username, full_name=full_name, position=position, role=role,
                    password_hash=hash_password(password), password_changed_at=utcnow())
        home = [departments[c] for c in dept_codes if c in departments]
        user.department_id = home[0].id if home else None
        db.add(user)
        db.flush()
        for service_key, level, scoped in grants:
            db.add(ServiceAccess(user_id=user.id, service_key=service_key, level=level,
                                 org_scope="branch" if scoped else None))
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


# ---------------------------------------------------------------- сквозные отчёты (ADR-0010)

# Вводимые показатели за 12 месяцев: показатель → [(код подразделения, значение, цель)] —
# базовые значения месяца; последний месяц задан точно (DEMO_REPORT_LATEST), остальные — с сезонностью
# и разбросом. Цель None — по умолчанию из каталога.
DEMO_REPORT_BASE: dict[str, tuple[tuple[str, float, float | None], ...]] = {
    "fin.revenue": (("COMM", 62.0, 64.0), ("TECH", 18.0, 18.0), ("PROJ", 24.0, 25.0)),
    "fin.costs": (("AHO", 3.1, 3.2), ("HR", 2.4, 2.5), ("COMM", 11.6, 12.0), ("MKT", 6.8, 7.0), ("TECH", 11.8, 12.0),
                  ("IT", 5.0, 5.0), ("PROJ", 9.1, 9.5), ("SUP-OS", 5.9, 6.0), ("SUP-OFFICE", 4.8, 5.0)),
    "fin.payroll": (("AHO", 1.9, 1.9), ("HR", 1.6, 1.6), ("COMM", 5.7, 5.7), ("MKT", 3.0, 3.0), ("TECH", 8.4, 8.5),
                    ("IT", 3.4, 3.4), ("PROJ", 4.9, 5.0)),
    "fin.budget": (("ADMIN", 98.0, None), ("COMMDIR", 97.0, None), ("TECHDIR", 97.0, None), ("PROJ", 99.0, None)),
    "ops.plan": (("AHO", 97.0, None), ("HR", 98.0, None), ("COMM", 96.0, None), ("MKT", 95.0, None),
                 ("TECH", 96.0, None), ("IT", 99.0, None), ("PROJ", 97.0, None), ("SUP-OS", 97.0, None),
                 ("SUP-OFFICE", 95.0, None)),
    "ops.csat": (("COMM", 4.6, None), ("SUP-OS", 4.6, None), ("SUP-OFFICE", 4.7, None), ("PROJ", 4.8, None)),
}
# Последний месяц — без разброса (базовые значения в норме), кроме жёлтых и красных случаев ниже:
# (показатель, код) → (значение, комментарий); у денежных показателей значение — доля от цели месяца.
# «Выполнение плана работ» Службы маркетинга не заполнено: значение ожидается у служб — «Нет данных»
# и нарушение полноты.
DEMO_REPORT_LATEST: dict[tuple[str, str], tuple[float | None, str]] = {
    ("fin.revenue", "COMM"): (0.89, "Перенос оплаты по контракту с РусГидро на следующий месяц"),
    ("fin.costs", "TECH"): (1.10, "Внеплановая закупка оборудования тестового стенда"),
    ("fin.costs", "SUP-OS"): (1.15, "Привлечение подрядчика на третью линию"),
    ("fin.payroll", "MKT"): (1.033, ""),
    ("fin.budget", "COMMDIR"): (92.0, ""),
    ("ops.plan", "COMM"): (93.0, ""),
    ("ops.plan", "MKT"): (None, ""),
    ("ops.plan", "SUP-OFFICE"): (78.0, "Внедрение у заказчика перенесено на следующий месяц"),
    ("ops.csat", "SUP-OS"): (4.3, "Рост времени решения заявок третьей линии"),
}
MONEY_INDICATORS = ("fin.revenue", "fin.costs", "fin.payroll")
DEMO_REPORT_NOTE = ("TECH", "tp_lead", "Очередь заявок разбираем: подключены инженеры группы AlterOffice, "
                                       "срок — до конца следующего месяца")


def _add_months(period: date, months: int) -> date:
    index = period.year * 12 + period.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _report_anchor(db: Session) -> date:
    """Последний месяц демо-значений — последний месяц данных службы персонала (как в остальных
    демо-данных), а без них — прошлый месяц."""
    last = db.execute(select(HrMonth.year, HrMonth.month).order_by(HrMonth.year.desc(), HrMonth.month.desc())
                      .limit(1)).first()
    if last is not None:
        return date(last.year, last.month, 1)
    today = local_today()
    return _add_months(date(today.year, today.month, 1), -1)


def _season(key: str, month: int) -> float:
    """Сезонность выручки и затрат: пик — в декабре, спад — летом."""
    return 1 + 0.07 * math.cos(2 * math.pi * (month - 12) / 12) if key in ("fin.revenue", "fin.costs") else 1.0


def _demo_value(key: str, base: float, month: int, rng: random.Random) -> float:
    """Значение месяца: сезонность и разброс (±3 % у денежных показателей)."""
    if key == "ops.csat":
        return round(min(5.0, base + rng.uniform(-0.15, 0.1)), 1)
    if key in ("fin.budget", "ops.plan"):
        return float(round(min(104.0, base + rng.uniform(-3, 3))))
    return round(base * _season(key, month) * (1 + rng.uniform(-0.03, 0.03)), 1)


def load_reports(db: Session) -> None:
    """Каталог показателей и 12 месяцев вводимых значений — только в пустые таблицы."""
    if not _empty(db, Indicator):
        return
    indicators: dict[str, Indicator] = {}
    for order, item in enumerate(DEMO_INDICATORS, start=1):
        threshold = item.rule_type == "threshold"
        row = Indicator(key=item.key, name=item.name, description=item.description, unit=item.unit,
                        data_class=item.data_class, direction=item.direction, rollup=item.rollup,
                        rule_type=item.rule_type, green_threshold=item.green if threshold else None,
                        yellow_threshold=item.yellow if threshold else None,
                        green_deviation=None if threshold else item.green,
                        yellow_deviation=None if threshold else item.yellow, default_target=item.default_target,
                        source_type="computed" if item.source_key else "manual", source_key=item.source_key,
                        owner_service=item.owner_service, expected_kinds=list(item.expected_kinds),
                        sort_order=order * 10, is_active=True)
        db.add(row)
        indicators[item.key] = row
    db.flush()
    users = {u.username: u for u in db.scalars(select(User))}
    director = users.get("tech_dir")
    if director is not None and not any(a.service_key == "apparat_gd" for a in director.access):
        db.add(ServiceAccess(user_id=director.id, service_key="apparat_gd", level="editor"))
    if not _empty(db, IndicatorValue):
        return
    units = {d.code: d.id for d in db.scalars(select(Department)) if d.code}
    anchor = _report_anchor(db)
    author = users.get("admin")
    rng = random.Random(2026)
    count = 0
    for key, rows in DEMO_REPORT_BASE.items():
        indicator = indicators[key]
        for code, base, target_base in rows:
            if code not in units:
                continue
            for step in range(12):
                period = _add_months(anchor, step - 11)
                # План выручки и бюджет затрат — с той же сезонностью, что и факт, без разброса
                target = round(target_base * _season(key, period.month), 1) if target_base else None
                comment = ""
                if step < 11:
                    value = _demo_value(key, base, period.month, rng)
                elif (key, code) in DEMO_REPORT_LATEST:
                    value, comment = DEMO_REPORT_LATEST[(key, code)]
                    if value is not None and key in MONEY_INDICATORS:
                        value = round(target * value, 1)
                else:
                    value = round(base * _season(key, period.month), 1)
                if value is None:
                    continue
                db.add(IndicatorValue(indicator_id=indicator.id, department_id=units[code], period=period,
                                      value=value, target=target, comment=comment, source="manual",
                                      updated_by_id=author.id if author else None))
                count += 1
    code, head, comment = DEMO_REPORT_NOTE
    if code in units and head in users:
        db.add(UnitStatusNote(department_id=units[code], period=anchor, status="watch", comment=comment,
                              author_id=users[head].id))
    db.flush()
    log.info("Демонстрационный сквозной отчёт: показателей — %s, значений — %s, последний месяц — %s",
             len(indicators), count, anchor.isoformat()[:7])


def load_demo_data(db: Session) -> None:
    load_org(db)
    load_users(db)
    load_org_heads(db)
    load_hr(db)
    load_tp(db)
    load_naumen(db)
    load_partnerships(db)
    load_reports(db)
    log.info("Демонстрационные данные загружены")
