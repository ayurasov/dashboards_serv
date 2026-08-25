"""Seed database with departments, users, metric definitions, traffic-light rules,
benchmarks, HR data for June & July 2026, dashboard modules, colour palette
and technology partnerships."""
import datetime
import json
from pathlib import Path
from sqlalchemy.orm import Session
from .database import engine, Base, SessionLocal
from .models import (
    User, Department, MonthRecord, EmployeeEvent, MetricDefinition, MetricValue,
    TrafficLightRule, Benchmark, RoleEnum, user_departments,
    DashboardModule, Partnership, ColorPalette, UserServiceAccess,
    TpReportRow, TpSettings, TP_DATA_COLUMNS,
    SERVICES, SERVICE_KEYS
)
from .security import hash_password

DATA_DIR = Path(__file__).resolve().parent / "data"
# tp-report seed data lives two directories up from backend/app/
TP_SEED_PATH = Path(__file__).resolve().parent.parent.parent / "tp-report" / "seed_data.json"

DEPARTMENTS = [
    ("ИТ-служба", "IT"),
    ("Техническая служба", "TECH"),
    ("Служба маркетинга", "MKT"),
    ("Коммерческая служба", "COMM"),
    ("АХО", "AHO"),
    ("Аппарат генерального директора", "ADMIN"),
    ("Проектная служба", "PROJ"),
]

# Ordered as the HR funnel reads: vacancies -> screening -> interviews -> offers ->
# hires -> speed, then adaptation, then retention. `sort_order` drives every table,
# chart and data-entry form, so the list order below is the single source of truth.
METRIC_DEFS = [
    # key, label, unit, category, value_type, aggregation, direction, description, sort_order
    ("total_employees", "Всего сотрудников", "чел.", "headcount", "numeric", "latest", "higher_is_better", "Общее число сотрудников", 0),
    ("projects_count", "Проекты найма", "шт.", "hiring", "numeric", "sum", "neutral", "Количество проектов (вакансий) в работе", 10),
    ("resumes_screened", "Отобрано резюме", "чел.", "hiring", "numeric", "sum", "neutral", "Количество отобранных резюме", 20),
    ("interviews_hr", "Интервью с HR", "чел.", "hiring", "numeric", "sum", "neutral", "Количество проведённых интервью с HR", 30),
    ("interviews_hm", "Интервью с заказчиком", "чел.", "hiring", "numeric", "sum", "neutral", "Количество интервью с нанимающими менеджерами", 40),
    ("offers_accepted_pct", "Принятые офферы", "%", "hiring", "numeric", "latest", "higher_is_better", "Доля принятых офферов от выставленных", 50),
    ("hired_count", "Нанято (по списку)", "чел.", "hiring", "numeric", "sum", "neutral", "Количество принятых сотрудников по списку", 60),
    ("avg_time_to_fill", "Среднее время закрытия позиций", "дн.", "hiring", "numeric", "avg", "lower_is_better", "Среднее время от открытия вакансии до выхода кандидата", 70),
    ("on_adaptation_count", "Сотрудников на адаптации", "чел.", "adaptation", "numeric", "latest", "neutral", "Численность сотрудников на испытательном сроке", 80),
    ("adaptation_meetings", "Встречи по адаптации", "шт.", "adaptation", "numeric", "sum", "neutral", "Количество встреч по адаптации", 90),
    ("probation_completed", "Завершили ИС", "чел.", "adaptation", "numeric", "sum", "neutral", "Количество завершённых испытательных сроков", 100),
    ("probation_pass_rate", "Процент прохождения ИС (общий)", "%", "adaptation", "numeric", "latest", "higher_is_better", "Доля сотрудников, прошедших испытательный срок", 110),
    ("probation_pass_rate_adaptation", "Процент прохождения ИС (по адаптации)", "%", "adaptation", "numeric", "latest", "higher_is_better", "Процент прошедших ИС среди сотрудников на адаптации", 120),
    ("adaptation_dismissals", "Увольнения на адаптации", "чел.", "adaptation", "numeric", "sum", "lower_is_better", "Увольнения в период испытательного срока", 130),
    ("turnover", "Текучесть кадров", "%", "turnover", "numeric", "latest", "lower_is_better", "Текучесть накопительно с начала года", 140),
    ("turnover_company", "Текучесть по инициативе компании", "%", "turnover", "numeric", "latest", "lower_is_better", "Доля увольнений по инициативе компании", 150),
]

# Softened defaults: wider green/yellow zones so routine fluctuations don't read as red.
TL_RULES = [
    # metric_key, green, yellow, direction
    ("turnover", 5.0, 8.0, "lower_is_better"),
    ("turnover_company", 3.5, 5.5, "lower_is_better"),
    ("avg_time_to_fill", 40.0, 60.0, "lower_is_better"),
    ("offers_accepted_pct", 85.0, 65.0, "higher_is_better"),
    ("probation_pass_rate", 90.0, 75.0, "higher_is_better"),
    ("probation_pass_rate_adaptation", 85.0, 70.0, "higher_is_better"),
    ("adaptation_dismissals", 1.0, 3.0, "lower_is_better"),
]

# The dashboard modules mirror the service registry: one module per service, with
# only the two services that have content enabled.
LEGACY_MODULE_KEYS = {"product_partnerships": "project_product"}

# username -> [(service_key, access_level)]
SERVICE_ACCESS = {
    "admin": [(key, "admin") for key in SERVICE_KEYS],
    "hr_head": [("hr", "admin"), ("project_product", "read"), ("tech", "read")],
    "viewer": [("hr", "read"), ("project_product", "read"), ("tech", "read")],
    "it_viewer": [("it", "read"), ("hr", "read")],
}

# Mirrors the «Мягкая» preset below — kept as a named constant since it is also the
# in-app fallback (frontend/src/stores/palette.js FALLBACK) used before the API responds.
DEFAULT_PALETTE = {
    "traffic_light": {"green": "#5a9e68", "yellow": "#c9974a", "red": "#c97171", "neutral": "#b8bec7"},
    "charts": ["#5a9e68", "#6F8FBF", "#c9974a", "#8BBE9F", "#c97171", "#A9B2C3"],
    "brand": {"primary": "#c0392b", "muted": "#6b6a65"},
}

# Preset palettes offered to the admin in the UI. The hex values here must stay
# in sync with PRESETS in frontend/src/views/PaletteSettings.vue.
# «Мягкая» is the default/active one; the rest are seeded inactive.
PALETTE_PRESETS = [
    {
        "name": "Мягкая",
        "colors": {
            "traffic_light": {"green": "#5a9e68", "yellow": "#c9974a", "red": "#c97171",
                              "neutral": "#b8bec7"},
            "charts": ["#5a9e68", "#6F8FBF", "#c9974a", "#8BBE9F", "#c97171", "#A9B2C3"],
            "brand": {"primary": "#c0392b", "muted": "#6b6a65"},
        },
    },
    {
        "name": "Классическая",
        "colors": {
            "traffic_light": {"green": "#4caf50", "yellow": "#ffc107", "red": "#f44336",
                              "neutral": "#9E9E9E"},
            "charts": ["#4caf50", "#1F77B4", "#ffc107", "#8E44AD", "#f44336", "#7F8C8D"],
            "brand": {"primary": "#f44336", "muted": "#6B6A65"},
        },
    },
    {
        "name": "Холодная",
        "colors": {
            "traffic_light": {"green": "#26a69a", "yellow": "#42a5f5", "red": "#ff7043",
                              "neutral": "#8FA3B0"},
            "charts": ["#26a69a", "#42a5f5", "#6FB1E0", "#8E7CC3", "#ff7043", "#8FA3B0"],
            "brand": {"primary": "#26a69a", "muted": "#5A6B78"},
        },
    },
    {
        "name": "Контрастная",
        "colors": {
            "traffic_light": {"green": "#2e7d32", "yellow": "#ef6c00", "red": "#c62828",
                              "neutral": "#6E7378"},
            "charts": ["#2e7d32", "#0B5FA5", "#ef6c00", "#7B2FA0", "#c62828", "#5A6570"],
            "brand": {"primary": "#c62828", "muted": "#5A6570"},
        },
    },
]

JUNE_METRICS = {
    "avg_time_to_fill": (35.0, ""),
    "turnover": (3.87, "на момент июня 2026"),
    "turnover_company": (2.58, ""),
    "offers_accepted_pct": (100.0, ""),
    "resumes_screened": (249.0, ""),
    "interviews_hr": (53.0, ""),
    "interviews_hm": (5.0, ""),
    "projects_count": (8.0, ""),
    "adaptation_meetings": (4.0, ""),
    "probation_pass_rate": (99.35, "общий по компании"),
    "probation_pass_rate_adaptation": (93.33, "изначально посчитано от всех сотрудников на адаптации"),
    "on_adaptation_count": (15.0, ""),
    "adaptation_dismissals": (1.0, ""),
    "probation_completed": (5.0, ""),
    "hired_count": (2.0, ""),
}

JULY_METRICS = {
    "offers_accepted_pct": (100.0, ""),
    "resumes_screened": (282.0, ""),
    "interviews_hr": (72.0, ""),
    "interviews_hm": (16.0, ""),
    "projects_count": (9.0, ""),
    "probation_pass_rate": (100.0, ""),
    "adaptation_meetings": (10.0, ""),
    "turnover": (2.0, "всего уволено 3 человека; в июле 2025: 1,65%"),
    "hired_count": (4.0, "по списку 4 найма; в тексте отчёта указано «нанято 3» — расхождение"),
    "on_adaptation_count": (14.0, ""),
    "adaptation_dismissals": (0.0, ""),
    "probation_completed": (3.0, ""),
}

JUNE_HIRES = [
    ("2026-06-08", "Райманов Савелий Александрович", "Разработчик 1С", "ИТ-служба", "Самозанятый"),
    ("2026-06-23", "Лапин Максим Витальевич", "Инженер-программист 1 категории", "Техническая служба", "ТД"),
]
JUNE_FIRES = [
    ("2026-06-05", "Тарасов Иван Михайлович", "Разработчик 1С", "ИТ-служба"),
    ("2026-06-19", "Пономарева Злата Михайловна", "PR-менеджер", "Служба маркетинга"),
    ("2026-06-23", "Андреев Александр Александрович", "Менеджер по работе с ключевыми клиентами", "Коммерческая служба"),
    ("2026-06-29", "Черкашина Дарья Владимировна", "Бекенд разработчик", "Техническая служба"),
    ("2026-06-30", "Щуцкая Евгения Константиновна", "Директор по маркетингу", "Служба маркетинга"),
    ("2026-06-30", "Иванова Наталья Владиславовна", "Директор по развитию программных продуктов", "Служба маркетинга"),
]
JULY_HIRES = [
    ("2026-07-06", "Безносова Мария Андреевна", "Заместитель руководителя аппарата генерального директора по технической части", "Аппарат генерального директора", ""),
    ("2026-07-09", "Сергеев Алексей Васильевич", "Инженер-разработчик", "Техническая служба", ""),
    ("2026-07-13", "Стаценко Александр Игоревич", "разнорабочий-универсал", "АХО", ""),
    ("2026-07-15", "Гукова Белла Аликовна", "Руководитель проектов", "Проектная служба", ""),
]
JULY_FIRES = [
    ("2026-07-01", "Сабиров Руслан Альфирович", "девопс", "ИТ-служба"),
    ("2026-07-16", "Гурулев Владислав Владимирович", "Руководитель отдела разработки системного программирования", "Техническая служба"),
    ("2026-07-20", "Маммедов Хатаи Илтимас Оглы ИН", "аналитик 3 категории", "ИТ-служба"),
]

# Year the target values below belong to.
TARGET_YEAR = 2026

BENCHMARKS = [
    # metric_key, label, year, value, target_value, description, source
    ("turnover", "2025 год", 2025, 5.17, None,
     "Фактическая текучесть кадров за 2025 год", "Годовой отчёт службы персонала за 2025 год"),
    ("turnover", "Цель 2026", TARGET_YEAR, 5.0, 5.0,
     "Целевой уровень текучести кадров", "План службы персонала на 2026 год"),
    ("avg_time_to_fill", "Цель 2026", TARGET_YEAR, 30.0, 30.0,
     "Среднее время закрытия вакансии (дни)", "План службы персонала на 2026 год"),
    ("offers_accepted_pct", "Цель 2026", TARGET_YEAR, 90.0, 90.0,
     "Доля принятых офферов (%)", "План службы персонала на 2026 год"),
    ("probation_pass_rate", "Цель 2026", TARGET_YEAR, 95.0, 95.0,
     "Процент прохождения испытательного срока (%)", "План службы персонала на 2026 год"),
    ("probation_pass_rate_adaptation", "Цель 2026", TARGET_YEAR, 90.0, 90.0,
     "Доля неудач адаптации не более 10% — прохождение ИС не ниже 90%", "План службы персонала на 2026 год"),
]


def _date(s):
    return datetime.date.fromisoformat(s)


def _opt_date(s):
    """Seed JSON dates may be null or an empty string."""
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(str(s).strip())
    except ValueError:
        return None


def seed_all(db=None):
    _own_session = db is None
    if _own_session:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
    try:
        # departments
        dept_map = {}
        for name, code in DEPARTMENTS:
            d = db.query(Department).filter(Department.code == code).first()
            if not d:
                d = Department(name=name, code=code)
                db.add(d)
                db.flush()
            dept_map[code] = d

        # Metric definitions are registry-owned: labels, categories and especially
        # sort_order are refreshed on every start so existing databases pick up
        # reordering. Thresholds live on TrafficLightRule and stay admin-editable.
        for key, label, unit, cat, vt, agg, direction, desc, order in METRIC_DEFS:
            md = db.query(MetricDefinition).filter(MetricDefinition.key == key).first()
            if not md:
                md = MetricDefinition(key=key)
                db.add(md)
            md.label, md.unit, md.category = label, unit, cat
            md.value_type, md.aggregation, md.direction = vt, agg, direction
            md.description, md.sort_order = desc, order
        db.flush()

        # traffic-light rules
        for key, g, y, direction in TL_RULES:
            if not db.query(TrafficLightRule).filter(TrafficLightRule.metric_key == key).first():
                db.add(TrafficLightRule(metric_key=key, green_threshold=g, yellow_threshold=y,
                                        direction=direction, enabled=True))
        db.flush()

        # Benchmarks: targets are admin-editable, so an existing row keeps its
        # target_value; only rows predating the target column get backfilled.
        for key, label, year, val, target, desc, source in BENCHMARKS:
            b = db.query(Benchmark).filter(Benchmark.metric_key == key, Benchmark.year == year).first()
            if not b:
                db.add(Benchmark(metric_key=key, label=label, year=year, value=val,
                                 target_value=target, description=desc, source=source))
                continue
            if b.target_value is None:
                b.target_value = target
            if not b.description:
                b.description = desc
            if not b.source:
                b.source = source
        db.flush()

        # users — only ever seeded into an empty table. Test/demo accounts (hr_head,
        # viewer, it_viewer) are admin-manageable afterwards, including deletion; if
        # we recreated them on every restart, a deleted account would silently come
        # back. The very first seed (empty users table) still creates everyone.
        if not db.query(User).first():
            users_data = [
                ("admin", "Администратор системы", None, RoleEnum.ADMIN, "admin123", True, []),
                ("hr_head", "Начальник службы персонала", None, RoleEnum.HR_HEAD, "hr123", False, []),
                ("viewer", "Пользователь (просмотр)", None, RoleEnum.VIEWER, "view123", False, []),
                ("it_viewer", "Пользователь ИТ-отдела", None, RoleEnum.DEPT_VIEWER, "it123", False, ["IT"]),
            ]
            for uname, fname, email, role, pwd, mcp, dept_codes in users_data:
                u = User(username=uname, full_name=fname, email=email, role=role,
                         hashed_password=hash_password(pwd), must_change_password=mcp)
                db.add(u)
                db.flush()
                for code in dept_codes:
                    u.departments.append(dept_map[code])
        db.flush()

        # month data
        _seed_month(db, 2026, 6, JUNE_METRICS, JUNE_HIRES, JUNE_FIRES,
                    "Подписано соглашение с Дмитриевой Евгенией с 29.06.2026 по 27.08.2026 — отпуск без сохранения заработной платы.")
        _seed_month(db, 2026, 7, JULY_METRICS, JULY_HIRES, JULY_FIRES,
                    "Расхождение в отчёте: текст указывает «нанято 3 человека», по списку найма — 4 записи. "
                    "Текучесть за июль 2025 составила 1,65%.")

        _seed_modules(db)
        _seed_service_access(db)
        _seed_palette(db)
        _seed_partnerships(db)
        _seed_tp_rows(db)

        db.commit()
        print("Seed completed successfully.")
    except Exception as e:
        db.rollback()
        print(f"Seed error: {e}")
        raise
    finally:
        if _own_session:
            db.close()


def _seed_month(db, year, month, metrics, hires, fires, notes):
    mr = db.query(MonthRecord).filter(MonthRecord.year == year, MonthRecord.month == month).first()
    if mr:
        return
    mr = MonthRecord(year=year, month=month, notes=notes)
    db.add(mr)
    db.flush()
    for key, (val, note) in metrics.items():
        db.add(MetricValue(month_record_id=mr.id, metric_key=key, numeric_value=val, source_note=note))
    for d, name, pos, dept, etype in hires:
        db.add(EmployeeEvent(month_record_id=mr.id, event_type="hired", event_date=_date(d),
                             full_name=name, position=pos, department=dept, employment_type=etype))
    for d, name, pos, dept in fires:
        db.add(EmployeeEvent(month_record_id=mr.id, event_type="fired", event_date=_date(d),
                             full_name=name, position=pos, department=dept, employment_type=""))
    db.flush()


def _seed_modules(db):
    # Databases created before the service registry carry the old partnership key.
    for old_key, new_key in LEGACY_MODULE_KEYS.items():
        stale = db.query(DashboardModule).filter(DashboardModule.key == old_key).first()
        if stale:
            if db.query(DashboardModule).filter(DashboardModule.key == new_key).first():
                db.delete(stale)
            else:
                stale.key = new_key
            db.flush()

    for order, (key, title, subtitle, icon, route_prefix, has_dashboard) in enumerate(SERVICES):
        module = db.query(DashboardModule).filter(DashboardModule.key == key).first()
        if not module:
            module = DashboardModule(key=key)
            db.add(module)
        # Titles and the enabled flag are owned by the registry, so refresh them.
        module.title = title
        module.subtitle = subtitle
        module.icon = icon
        module.route_prefix = route_prefix
        module.enabled = has_dashboard
        module.sort_order = order
    db.flush()


def _seed_service_access(db):
    for username, grants in SERVICE_ACCESS.items():
        user = db.query(User).filter(User.username == username).first()
        if not user:
            continue
        for service_key, level in grants:
            exists = (db.query(UserServiceAccess)
                      .filter(UserServiceAccess.user_id == user.id,
                              UserServiceAccess.service_key == service_key)
                      .first())
            if not exists:
                db.add(UserServiceAccess(user_id=user.id, service_key=service_key,
                                         access_level=level))
    db.flush()


def _seed_palette(db):
    """Seed the preset palettes, one row per preset name.

    Idempotent per name: presets that already exist are left untouched (so admin
    edits survive), missing ones are added. Only «Мягкая» is created active, and
    only when no global palette is active yet — so re-seeding never steals the
    active flag from a palette the admin has chosen.
    """
    has_active = (db.query(ColorPalette)
                  .filter(ColorPalette.scope == "global", ColorPalette.is_active.is_(True))
                  .first() is not None)
    for preset in PALETTE_PRESETS:
        if db.query(ColorPalette).filter(ColorPalette.name == preset["name"]).first():
            continue
        active = preset["name"] == "Мягкая" and not has_active
        if active:
            has_active = True
        db.add(ColorPalette(scope="global", module_key=None, name=preset["name"],
                            colors_json=json.dumps(preset["colors"], ensure_ascii=False),
                            is_active=active))
    db.flush()


def _seed_partnerships(db):
    if db.query(Partnership).first():
        return
    path = DATA_DIR / "tech_partnerships_seed.json"
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        records = json.load(f)
    for r in records:
        db.add(Partnership(
            partner=r.get("partner") or "",
            product=r.get("product") or "",
            direction=r.get("direction") or "",
            almi_product=r.get("almi_product") or "",
            almi_version=r.get("almi_version") or "",
            status=r.get("status") or "В работе",
            cert_date=_opt_date(r.get("cert_date")),
            nda=bool(r.get("nda")),
            agreement=bool(r.get("agreement")),
            bitrix=r.get("bitrix") or None,
            website=r.get("website") or None,
            comment=r.get("comment") or None,
            type=r.get("type") or "ПО",
            last_modified=_opt_date(r.get("last_modified")),
        ))
    db.flush()


def _seed_tp_rows(db):
    """Seed TP weekly rows from tp-report/seed_data.json.

    Idempotent: skips import if any rows already exist in tp_report_rows.
    The JSON is the canonical source exported from tp-report/data/tp_report.db.
    """
    if db.query(TpReportRow).first():
        return

    # Try the repo-level path first; fall back to DATA_DIR for Docker deployments
    # where the tp-report directory may have been copied alongside backend/app/data/.
    candidates = [
        TP_SEED_PATH,
        DATA_DIR / "tp_seed_data.json",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        print("[seed] tp_seed_data.json not found — skipping TP rows.")
        return

    with path.open(encoding="utf-8") as f:
        records = json.load(f)

    for r in records:
        kwargs = {col: r.get(col) for col in TP_DATA_COLUMNS}
        kwargs["period"] = r.get("period") or ""
        db.add(TpReportRow(**kwargs))

    db.flush()
    print(f"[seed] Loaded {len(records)} TP weekly rows from {path.name}.")


if __name__ == "__main__":
    seed_all()
