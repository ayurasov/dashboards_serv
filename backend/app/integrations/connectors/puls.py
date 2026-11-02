"""«Пульс проекта»: проекты → вычисляемые у нас показатели сквозного отчёта по подразделениям (ADR-0011).

Подключение — только чтение:
- служебная учётная запись «Пульса» (сейчас): GET /api/auth/csrf → POST /api/auth/login (X-CSRF-Token, Referer,
  Origin) → GET /api/health/ready, /api/directions, /api/projects → POST /api/auth/logout (всегда);
- ключ интеграции (Bearer puls_…, без cookie): GET /api/integration/v1/ping и /api/integration/v1/projects — когда
  «Пульс» поддержит несколько ключей (сейчас ключ один и занят «По Делу»). В этом режиме «Пульс» не отдаёт число
  заблокированных задач и id направлений: показатель puls.blocked не пишется, направления сопоставляются по названию.

«Обновить показатели проектов» за текущий месяц (по TIMEZONE): проект относится к подразделению по сопоставлению
«направление → подразделение» (направление — id или название, подразделение — код или путь), несопоставленный —
к корню структуры. Для каждого сопоставленного подразделения, его вышестоящих и корня считаются показатели по
проектам ветки (у корня — по всем): проекты в работе (есть незавершённые задачи), просроченные (есть просроченные
задачи или срок окончания прошёл при прогрессе меньше 100 %), заблокированные задачи, средний прогресс и доля
проектов в срок. Светофор проекта выводится здесь же: красный — просрочен, жёлтый — есть заблокированные задачи
или до окончания не больше 14 дней при прогрессе меньше 80 %, зелёный — остальные в работе и завершённые,
серый — без задач. Показатели каталога создаются при первом запуске (служба-владелец — проектный и продуктовый
офис, вводимые, операционные); значения пишет движок загрузки (ctx.plans.indicator_values) с комментарием
«из «Пульса проекта»».
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core import db as core_db
from ...core.config import settings
from ...core.errors import AppError, Conflict, ValidationFailed
from ...models import Indicator, name_key
from ...schemas.reports import IndicatorCreateIn
from ...services import org, report_admin, reports
from ...services.inbox import plan_errors
from ...services.org_import import split_path
from ..base import Action, CheckResult, Connector, Field, Option, RunContext, RunResult, register
from ..http import HttpClient, IntegrationError
from .common import ANY_STATUS, PartnerSession, partner_error, rule_lines

TITLE = "Пульс проекта"
COMMENT = "из «Пульса проекта»"
SOON_DAYS = 14
SOON_PROGRESS = 80
MAX_DETAILS = 50
MODES = {"session": "служебная учётная запись", "key": "ключ интеграции"}


@dataclass(frozen=True)
class IndicatorSpec:
    key: str
    name: str
    unit: str
    direction: str
    rollup: str
    green: float | None
    yellow: float | None
    description: str
    sort_order: int


INDICATORS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec("puls.projects", "Проекты в работе", "шт.", "neutral", "sum", None, None,
                  "Проекты «Пульса проекта» с незавершёнными задачами — в подразделении и вложенных", 500),
    IndicatorSpec("puls.overdue", "Просроченные проекты", "шт.", "lower_is_better", "sum", 0, 1,
                  "Проекты в работе с просроченными задачами или прошедшим сроком окончания при прогрессе меньше "
                  "100 %; зелёный — нет, жёлтый — один, красный — два и больше", 510),
    IndicatorSpec("puls.on_time_share", "Проекты в срок", "%", "higher_is_better", "avg", 90, 70,
                  "Доля проектов в работе без просрочки; зелёный — от 90 %, жёлтый — от 70 %, красный — меньше 70 %",
                  520),
    IndicatorSpec("puls.progress", "Средний прогресс проектов", "%", "neutral", "avg", None, None,
                  "Средний прогресс проектов в работе (среднее поля «Прогресс» задач основного плана)", 530),
    IndicatorSpec("puls.blocked", "Заблокированные задачи проектов", "шт.", "lower_is_better", "sum", 0, 5,
                  "Задачи в статусе «Заблокирована» в проектах подразделения; зелёный — нет, жёлтый — до пяти", 540),
)
INDICATOR_KEYS = tuple(spec.key for spec in INDICATORS)


def parse_mapping(text: str | None) -> list[tuple[int, str, str]]:
    """«направление = подразделение» по строке → [(строка, направление, подразделение)]."""
    try:
        lines = rule_lines(text)
    except ValueError as exc:
        raise ValidationFailed(f"Сопоставление, строка {exc.args[0]}: нужно «направление = код или путь "
                               "подразделения»", fields={"config.directions": "Неверная строка"}) from None
    seen: dict[str, int] = {}
    for number, direction, _unit in lines:
        key = name_key(direction)
        if key in seen:
            raise ValidationFailed(f"Сопоставление, строка {number}: направление «{direction}» уже указано в строке "
                                   f"{seen[key]}", fields={"config.directions": "Повтор направления"})
        seen[key] = number
    return lines


def unit_resolver(snap: org.OrgSnapshot):
    """Подразделение по коду, пути через «/» или единственному названию → (id, ошибка)."""
    by_code = {u.code.casefold(): u.id for u in snap.units.values() if u.code}
    by_path = {tuple(name_key(n) for n in snap.path_names(u)): u for u in snap.units}
    by_name: dict[str, list[int]] = {}
    for unit in snap.units.values():
        by_name.setdefault(name_key(unit.name), []).append(unit.id)

    def resolve(text: str) -> tuple[int | None, str]:
        raw = (text or "").strip()
        if raw.casefold() in by_code:
            return by_code[raw.casefold()], ""
        parts = tuple(name_key(p) for p in split_path(raw))
        if parts in by_path:
            return by_path[parts], ""
        if len(parts) == 1 and len(by_name.get(parts[0], [])) == 1:
            return by_name[parts[0]][0], ""
        if len(parts) == 1 and by_name.get(parts[0]):
            return None, f"подразделений «{raw}» несколько — укажите код или путь через «/»"
        return None, f"подразделение «{raw}» не найдено"

    return resolve


def _day(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


@dataclass
class Project:
    id: Any
    title: str
    direction_id: Any
    direction: str | None
    total: int
    done: int
    blocked: int | None
    overdue: int
    progress: float
    end: date | None
    milestone: dict | None = None
    unit: int | None = None          # подразделение по сопоставлению; None — корень структуры

    @property
    def in_work(self) -> bool:
        return self.total > 0 and self.done < self.total

    def late(self, today: date) -> bool:
        return self.in_work and (self.overdue > 0 or (self.end is not None and self.end < today and
                                                      self.progress < 100))

    def light(self, today: date) -> tuple[str, str]:
        """Светофор проекта: (цвет, почему)."""
        if self.total == 0:
            return "gray", "нет задач в основном плане"
        if not self.in_work:
            return "green", "завершён"
        if self.late(today):
            if self.overdue:
                return "red", f"просроченных задач: {self.overdue}"
            return "red", f"срок окончания {self.end:%d.%m.%Y} прошёл, прогресс {self.progress:g} %"
        if self.blocked:
            return "yellow", f"заблокированных задач: {self.blocked}"
        if self.end is not None and (self.end - today).days <= SOON_DAYS and self.progress < SOON_PROGRESS:
            return "yellow", f"до окончания {(self.end - today).days} дн., прогресс {self.progress:g} %"
        return "green", "в срок"

    @classmethod
    def from_session(cls, raw: dict, directions: dict) -> Project:
        stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
        direction_id = raw.get("directionId")
        return cls(raw.get("id"), str(raw.get("title") or ""), direction_id, directions.get(direction_id),
                   _int(stats.get("total")), _int(stats.get("done")), _int(stats.get("blocked")),
                   _int(stats.get("overdue")), float(stats.get("progress") or 0), _day(stats.get("end")),
                   stats.get("nextMilestone"))

    @classmethod
    def from_key(cls, raw: dict) -> Project:
        return cls(raw.get("id"), str(raw.get("title") or ""), None, raw.get("direction") or None,
                   _int(raw.get("total")), _int(raw.get("done")), None, _int(raw.get("overdue")),
                   float(raw.get("progress") or 0), _day(raw.get("end")), raw.get("nextMilestone"))


def _error_code(resp) -> str:
    try:
        data = resp.json()
    except (ValueError, UnicodeDecodeError):
        return ""
    return str(data.get("error") or "") if isinstance(data, dict) else ""


def today_local() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def _number(value: float) -> str:
    value = round(float(value), 1)
    return str(int(value)) if value.is_integer() else str(value)


# ---------------------------------------------------------------- каталог показателей

def ensure_indicators(db: Session, actor, notes: list[str]) -> tuple[dict[str, Indicator], list[str]]:
    """Показатели puls.* в каталоге: недостающие создаются функциями каталога (report_admin.create_indicator)
    и фиксируются сразу — значения пишутся отдельной транзакцией движка загрузки."""
    rows = {r.key: r for r in db.scalars(select(Indicator).where(Indicator.key.in_(INDICATOR_KEYS)))}
    created: list[str] = []
    for spec in INDICATORS:
        if spec.key in rows:
            continue
        for name in (spec.name, f"{spec.name} («Пульс»)"):
            body = IndicatorCreateIn(key=spec.key, name=name, description=spec.description, unit=spec.unit,
                                     data_class="operational", direction=spec.direction, rollup=spec.rollup,
                                     rule_type="threshold", green_threshold=spec.green, yellow_threshold=spec.yellow,
                                     source_type="manual", owner_service="project_product", sort_order=spec.sort_order)
            try:
                with db.begin_nested():
                    rows[spec.key] = report_admin.create_indicator(db, actor, body)
                created.append(spec.key)
                break
            except Conflict:
                continue
        else:
            notes.append(f"Показатель {spec.key} не создан: название «{spec.name}» занято другим показателем")
    if created:
        db.commit()
    return rows, created


# ---------------------------------------------------------------- коннектор

@register
class PulsConnector(Connector):
    kind = "puls"
    title = TITLE
    description = ("Проекты «Пульса проекта» → показатели сквозного отчёта по подразделениям (сопоставление "
                   "«направление → подразделение»): проекты в работе, просроченные, заблокированные задачи, средний "
                   "прогресс и доля проектов в срок; светофор проекта выводится в «Дашбордах»")
    fields = (
        Field("base_url", "Адрес «Пульса проекта»", "url", required=True, placeholder="https://puls.company.ru"),
        Field("mode", "Режим подключения", "select", default="session",
              options=(Option("session", "Служебная учётная запись"),
                       Option("key", "Ключ интеграции (Bearer puls_…)")),
              hint="Ключ интеграции будет доступен, когда «Пульс» поддержит несколько ключей: сейчас ключ один и "
                   "занят «По Делу»"),
        Field("login", "Служебная учётная запись", required=True, show_if={"mode": ("session",)},
              hint="Только чтение: доступ к нужным направлениям (роль «Наблюдатель» с правами на направления или "
                   "администратор)"),
        Field("password", "Пароль", "password", required=True, secret=True, show_if={"mode": ("session",)}),
        Field("api_key", "Ключ интеграции", "password", required=True, secret=True, show_if={"mode": ("key",)},
              placeholder="puls_…"),
        Field("verify_tls", "Проверять TLS-сертификат", "bool", default=True,
              hint="Выключите только для самоподписанного или корпоративного сертификата"),
        Field("directions", "Направление → подразделение", "text",
              placeholder="Внедрение = PROJ\n7 = АЛМИ Партнер / Техническая дирекция",
              hint="По строке на направление: «направление = подразделение»; направление — название или id, "
                   "подразделение — код или путь через «/». Проекты несопоставленных направлений относятся к корню "
                   "структуры; список направлений — в результате проверки"),
    )
    actions = (Action("indicators", "Обновить показатели проектов",
                      "Проекты в работе, просроченные, заблокированные задачи, средний прогресс и доля проектов в "
                      "срок за текущий месяц — по подразделениям сопоставления"),)

    @classmethod
    def validate_config(cls, config: dict) -> dict:
        out = super().validate_config(config)
        parse_mapping(out.get("directions"))
        return out

    @property
    def mode(self) -> str:
        return self.config.get("mode") or "session"

    # --- чтение «Пульса»
    def session(self) -> PartnerSession:
        return PartnerSession(self.config["base_url"], kind=self.kind, title=TITLE,
                              login=self.config.get("login") or "", password=self.secrets.get("password") or "",
                              csrf_path="api/auth/csrf",
                              verify=bool(self.config.get("verify_tls", True)), detailed=self.detailed)

    def key_client(self) -> HttpClient:
        key = self.secrets.get("api_key") or ""
        if not key.startswith("puls_"):
            raise IntegrationError("Ключ интеграции «Пульса» начинается с puls_ — проверьте ключ", code="config")
        return self.http(headers={"Authorization": f"Bearer {key}"}, cookies=False)

    def _key_get(self, client: HttpClient, path: str, params: dict | None = None) -> dict:
        resp = client.request("GET", path, params=params, expect=ANY_STATUS)
        if resp.status == 401:
            raise IntegrationError(f"«{TITLE}» не принял ключ интеграции (401) — выпустите ключ в «Пульсе» "
                                   "(Администрирование → Интеграции) и введите его заново", code="auth", status=401,
                                   short=f"«{TITLE}» не принял ключ интеграции")
        if resp.status == 404 and not _error_code(resp):
            # 404 без кода ошибки — у «Пульса» нет API интеграции (соглашение «По Делу» ↔ «Пульс»)
            raise IntegrationError(f"В «{TITLE}» нет API интеграции ({'/' + path}, 404) — нужна версия «Пульса» с "
                                   "ключами интеграции или режим «Служебная учётная запись»", code="not_found",
                                   status=404, short=f"В «{TITLE}» нет API интеграции")
        if resp.status != 200:
            raise partner_error(TITLE, resp, path)
        return client.parse(resp, dict)

    def load(self) -> tuple[list[Project], list[dict], dict]:
        """(проекты, направления [{id, name}], сведения о версии и учётной записи)."""
        if self.mode == "key":
            with self.key_client() as client:
                ping = self._key_get(client, "api/integration/v1/ping")
                if ping.get("app") != "puls":
                    raise IntegrationError(f"Ключ принят, но отвечает не «{TITLE}» (app: {ping.get('app')}) — "
                                           "проверьте адрес", code="bad_response")
                data = self._key_get(client, "api/integration/v1/projects", {"limit": 200})
            raw = [p for p in data.get("projects") or [] if isinstance(p, dict)]
            projects = [Project.from_key(p) for p in raw]
            names = sorted({p.direction for p in projects if p.direction}, key=str.casefold)
            info = {"version": str(ping.get("version") or ""), "mode": "key", "limited": len(raw) >= 200}
            return projects, [{"id": None, "name": n} for n in names], info
        with self.session() as s:
            ready = s.get_json("api/health/ready")
            directions = [d for d in s.get_json("api/directions", kind=list) if isinstance(d, dict)]
            raw = [p for p in s.get_json("api/projects", kind=list) if isinstance(p, dict)]
            user = s.user
        names = {d.get("id"): str(d.get("name") or "") for d in directions}
        info = {"version": str(ready.get("version") or ""), "schema": ready.get("schema"), "mode": "session",
                "user": {"login": user.get("login"), "name": user.get("name"), "role": user.get("role")}}
        return [Project.from_session(p, names) for p in raw], \
            [{"id": d.get("id"), "name": str(d.get("name") or "")} for d in directions], info

    # --- сопоставление
    def mapping(self, snap: org.OrgSnapshot, problems: list[str]) -> list[tuple[str, int]]:
        """[(направление — id или название, подразделение)] для строк, чьё подразделение найдено."""
        resolve = unit_resolver(snap)
        out = []
        for number, direction, unit in parse_mapping(self.config.get("directions")):
            unit_id, error = resolve(unit)
            if unit_id is None:
                problems.append(f"строка {number} («{direction}»): {error}")
                continue
            out.append((direction, unit_id))
        return out

    @staticmethod
    def unit_of(project: Project, mapping: list[tuple[str, int]]) -> int | None:
        for direction, unit_id in mapping:
            if project.direction_id is not None and direction == str(project.direction_id):
                return unit_id
        for direction, unit_id in mapping:
            if project.direction and name_key(direction) == name_key(project.direction):
                return unit_id
        return None

    @staticmethod
    def _known(direction: str, directions: list[dict]) -> bool:
        return any((d["id"] is not None and direction == str(d["id"])) or name_key(direction) == name_key(d["name"])
                   for d in directions)

    # --- проверка
    def check(self) -> CheckResult:
        projects, directions, info = self.load()
        problems: list[str] = []
        try:
            with core_db.SessionLocal() as db:
                snap = org.build_snapshot(db)
                mapping = self.mapping(snap, problems)
                paths = {unit_id: snap.path_text(unit_id) for _d, unit_id in mapping}
        except AppError as exc:  # pragma: no cover - сопоставление проверено при сохранении
            problems.append(exc.detail)
            mapping, paths = [], {}
        for _number, direction, _unit in parse_mapping(self.config.get("directions")):
            if not self._known(direction, directions):
                problems.append(f"направления «{direction}» нет в «Пульсе»")
        listed = []
        for d in directions:
            probe = Project(None, "", d["id"], d["name"], 0, 0, None, 0, 0, None)
            unit_id = self.unit_of(probe, mapping)
            count = sum(1 for p in projects if (d["id"] is not None and p.direction_id == d["id"])
                        or (d["id"] is None and p.direction == d["name"]))
            listed.append({**d, "projects": count, "department": paths.get(unit_id) if unit_id else None})
        unmapped = [d["name"] for d in listed if not d["department"]]
        version = f" {info['version']}" if info.get("version") else ""
        who = info.get("user", {}).get("name") or info.get("user", {}).get("login")
        message = (f"Подключено к «{TITLE}»{version} ({MODES[info['mode']]}{f' {who}' if who else ''}): проектов "
                   f"{len(projects)}, направлений {len(directions)}, сопоставлено {len(directions) - len(unmapped)}")
        if unmapped:
            message += f"; без подразделения (в корень структуры): {', '.join(unmapped[:10])}"
        if info.get("limited"):
            problems.append("в режиме ключа «Пульс» отдаёт не больше 200 проектов")
        if problems:
            message += ". Проверьте: " + "; ".join(problems)
        return CheckResult(True, message, {**info, "projects": len(projects), "directions": listed,
                                           "unmapped": unmapped, "problems": problems})

    # --- запуск
    def run(self, action: str, ctx: RunContext) -> RunResult:
        self.action(action)
        projects, directions, info = self.load()
        today = today_local()
        period = f"{today:%Y-%m}"
        notes: list[str] = []
        snap = org.build_snapshot(ctx.db)
        order = snap.ordered_units()
        if not order:
            raise IntegrationError("В структуре компании нет подразделений — показатели некуда записать", code="config")
        root = order[0]
        mapping = self.mapping(snap, notes)
        for _number, direction, _unit in parse_mapping(self.config.get("directions")):
            if not self._known(direction, directions):
                notes.append(f"направления «{direction}» нет в «Пульсе»")
        lights = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
        flagged = []
        for project in projects:
            project.unit = self.unit_of(project, mapping)
            light, why = project.light(today)
            lights[light] += 1
            if light in ("red", "yellow"):
                flagged.append({"project": project.title, "direction": project.direction, "light": light,
                                "reason": why, "department": snap.path_text(project.unit or root)})
        targets = {root}
        for _direction, unit_id in mapping:
            targets.update(snap.path(unit_id))
        catalog, created = ensure_indicators(ctx.db, ctx.actor, notes)
        usable = {}
        for key in INDICATOR_KEYS:
            row = catalog.get(key)
            if row is None:
                continue
            if not row.is_active or row.source_type != "manual":
                notes.append(f"показатель {key} {'выключен' if not row.is_active else 'вычисляемый'} — не обновляется")
                continue
            usable[key] = row
        # Ограничения режима ключа — сведения, а не ошибка настройки: запуск от них не становится «частичным»
        limits: list[str] = []
        if info["mode"] == "key":
            usable.pop("puls.blocked", None)
            limits.append("в режиме ключа «Пульс» не отдаёт заблокированные задачи — puls.blocked не обновляется")
        if info.get("limited"):
            limits.append("в режиме ключа «Пульс» отдаёт не больше 200 проектов — показатели могут быть неполными")
        rows = self._rows(snap, [u for u in order if u in targets], projects, root, usable, period, today, notes)
        mapped = sum(1 for p in projects if p.unit is not None)
        counters = {"projects": len(projects), "mapped": mapped, "unmapped": len(projects) - mapped,
                    "units": len({r["department"] for r in rows}), "indicators_created": len(created),
                    **{f"projects_{k}": v for k, v in lights.items()}}
        details: dict = {"period": period, "mode": info["mode"], "flagged": flagged[:MAX_DETAILS]}
        if created:
            details["indicators_created"] = created
        if notes:
            details["notes"] = notes[:MAX_DETAILS]
        if limits:
            details["limits"] = limits
        if not rows:
            return RunResult.partial(f"Показатели проектов за {period} не записаны: нет доступных показателей puls.*",
                                     "; ".join(notes[:5]), counters=counters, details=details)
        name = f"«{TITLE}»: показатели проектов за {period}"
        result = ctx.plans.indicator_values(rows, apply=True, filename=name)
        summary = result.get("summary") or {}
        counters.update(values_create=summary.get("create", 0), values_update=summary.get("update", 0),
                        values_unchanged=summary.get("unchanged", 0), values_errors=summary.get("errors", 0))
        if not result.get("applied"):
            errors = plan_errors(result, 5) or ["план значений не применён"]
            return RunResult.failed(f"Показатели проектов не записаны: {'; '.join(errors)}", counters=counters,
                                    details=details)
        label = reports.period_label(date(today.year, today.month, 1)).lower()
        message = (f"Показатели проектов за {label}: проектов {len(projects)} (в работе "
                   f"{sum(1 for p in projects if p.in_work)}, красных {lights['red']}, жёлтых {lights['yellow']}), "
                   f"подразделений {counters['units']}; значений новых {counters['values_create']}, изменено "
                   f"{counters['values_update']}, без изменений {counters['values_unchanged']}")
        if created:
            message += f"; созданы показатели: {', '.join(created)}"
        if limits:
            message += f". {'; '.join(limits).capitalize()}"
        if notes:
            return RunResult.partial(message, "; ".join(notes[:5]), counters=counters, details=details)
        return RunResult.ok(message, counters=counters, details=details)

    def _rows(self, snap: org.OrgSnapshot, units: list[int], projects: list[Project], root: int,
              usable: dict, period: str, today: date, notes: list[str]) -> list[dict]:
        """Строки загрузки значений: по каждому подразделению — проекты его ветки."""
        rows: list[dict] = []
        for unit_id in units:
            unit = snap.units[unit_id]
            ref = unit.code or snap.path_text(unit_id)
            if not unit.code and any(ch in name for name in snap.path_names(unit_id) for ch in "/>\\"):
                notes.append(f"«{snap.path_text(unit_id)}»: в названии есть «/» — задайте подразделению код")
                continue
            branch = snap.descendants([unit_id])
            mine = [p for p in projects if (p.unit if p.unit is not None else root) in branch]
            active = [p for p in mine if p.in_work]
            late = [p for p in active if p.late(today)]
            values = {"puls.projects": len(active), "puls.overdue": len(late),
                      "puls.blocked": sum(p.blocked or 0 for p in mine)}
            if active:
                values["puls.progress"] = sum(p.progress for p in active) / len(active)
                values["puls.on_time_share"] = (len(active) - len(late)) / len(active) * 100
            for key, value in values.items():
                if key in usable:
                    rows.append({"line": len(rows) + 1, "department": ref, "indicator": key, "period": period,
                                 "value": _number(value), "target": "", "comment": COMMENT})
        return rows
