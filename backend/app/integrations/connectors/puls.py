"""«Пульс проекта»: проекты → вычисляемые у нас показатели сквозного отчёта по подразделениям (ADR-0011).

Подключение — только чтение, два режима (настройка mode):
- ключ интеграции (key, по умолчанию; «Пульс» 0.6.0 и новее, ADR-0011 там): Bearer puls_…, без cookie и CSRF;
  GET /api/integration/v1/ping (версия, название и права ключа), /directions (направления с числом проектов),
  /projects?limit=200 (больше API не отдаёт, листания нет). Права ключа: projects.read («Проекты и планы») —
  обязательно; projects.stats («Показатели проектов») — у проектов ещё inwork, blocked и directionInfo {id, name}:
  без него puls.blocked не пишется, а направления сопоставляются только по названию. Ключ выпускает администратор
  «Пульса»: «Интеграции → Ключи доступа», система «Дашборды компании»; предел — 120 запросов в минуту на ключ;
- служебная учётная запись «Пульса» (session; для версий до 0.6.0): GET /api/auth/csrf → POST /api/auth/login
  (X-CSRF-Token, Referer, Origin) → GET /api/health/ready, /api/directions, /api/projects → POST /api/auth/logout
  (всегда).
Подключения, сохранённые без режима, работают служебной учётной записью (stored_config).

«Обновить показатели проектов» за текущий месяц (по TIMEZONE): проект относится к подразделению по сопоставлению
«направление → подразделение» (направление — id или название, подразделение — код или путь), несопоставленный —
к корню структуры. Для каждого сопоставленного подразделения, его вышестоящих и корня считаются показатели по
проектам ветки (у корня — по всем): проекты в работе (есть незавершённые задачи), просроченные (есть просроченные
задачи или срок окончания прошёл при прогрессе меньше 100 %), заблокированные задачи, средний прогресс и доля
проектов в срок. Светофор проекта выводится здесь же: красный — просрочен, жёлтый — есть заблокированные задачи
или до окончания не больше 14 дней при прогрессе меньше 80 %, зелёный — остальные в работе и завершённые,
серый — без задач. Показатели каталога создаются при первом запуске (ctx.plans.ensure_indicator; служба-владелец —
проектный и продуктовый офис, вводимые, операционные); значения пишет движок загрузки (ctx.plans.indicator_values)
с комментарием «из «Пульса проекта»». У подразделения без проектов в работе средний прогресс и доля в срок не
определены: сохранённое прошлым запуском значение очищается (строка clear), а не остаётся старым.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ...core import db as core_db
from ...core.config import settings
from ...core.errors import AppError, Conflict, ValidationFailed
from ...models import name_key
from ...services import org, reports
from ...services.inbox import plan_errors
from ...services.org_import import split_path
from ...services.reports import IndicatorDef
from ..base import Action, CheckResult, Connector, Field, Option, RunContext, RunResult, register
from ..http import IntegrationError
from .common import (
    KEY_MODE,
    MODE_LABELS,
    SESSION_MODE,
    KeyApi,
    PartnerSession,
    connection_mode,
    rule_lines,
)

TITLE = "Пульс проекта"
COMMENT = "из «Пульса проекта»"
SOON_DAYS = 14
SOON_PROGRESS = 80
MAX_DETAILS = 50
# --- API ключей интеграций «Пульса» 0.6.0+ (ADR-0011 «Пульса»)
V1 = "api/integration/v1"
KEY_PREFIX = "puls_"
SCOPE_READ, SCOPE_STATS = "projects.read", "projects.stats"
# Подписи прав — как в «Пульсе» («Интеграции → Ключи доступа»)
SCOPE_LABELS = {SCOPE_READ: "«Проекты и планы» (projects.read)", SCOPE_STATS: "«Показатели проектов» (projects.stats)"}
KEYS_PLACE = "«Пульс» → «Интеграции → Ключи доступа»"
NO_API = ("По адресу подключения нет API ключей интеграций «Пульса» (/api/integration/v1/ping, 404): «Пульс» старше "
          "0.6.0 или адрес указан неверно. Обновите «Пульс» до 0.6.0 или выберите режим «Служебная учётная запись (для "
          "версий до 0.6.0)»")
# /projects отдаёт не больше 200 проектов и не листается
PROJECTS_MAX = 200
NO_STATS = (f"у ключа нет права {SCOPE_LABELS[SCOPE_STATS]}: «Пульс» не отдаёт задачи «в работе» и «заблокировано» "
            "и id направлений — puls.blocked не обновляется, направления сопоставляются только по названию")
LIMITED = (f"возможно, проектов больше {PROJECTS_MAX} — показатели посчитаны по первым {PROJECTS_MAX}")


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
        """Проект API ключа: с правом projects.stats — ещё blocked и directionInfo {id, name} (направление по id);
        без него — направление только названием, заблокированных задач нет (None)."""
        info = raw.get("directionInfo") if isinstance(raw.get("directionInfo"), dict) else {}
        return cls(raw.get("id"), str(raw.get("title") or ""), info.get("id"),
                   info.get("name") or raw.get("direction") or None, _int(raw.get("total")), _int(raw.get("done")),
                   _int(raw.get("blocked")) if "blocked" in raw else None, _int(raw.get("overdue")),
                   float(raw.get("progress") or 0), _day(raw.get("end")), raw.get("nextMilestone"))


def today_local() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def _number(value: float) -> str:
    value = round(float(value), 1)
    return str(int(value)) if value.is_integer() else str(value)


# ---------------------------------------------------------------- каталог показателей

def ensure_indicators(ctx: RunContext, notes: list[str]) -> tuple[dict[str, IndicatorDef], list[str]]:
    """Показатели puls.* в каталоге: недостающие создаёт каркас (ctx.plans.ensure_indicator — функция каталога,
    журнал от имени подключения, фиксация сразу), значения пишутся отдельной транзакцией движка загрузки.
    Название занято другим показателем — пробуется «<название> («Пульс»)»."""
    catalog = {i.key: i for i in reports.state(ctx.db).catalog if i.key in INDICATOR_KEYS}
    created: list[str] = []
    for spec in INDICATORS:
        if spec.key in catalog:
            continue
        for name in (spec.name, f"{spec.name} («Пульс»)"):
            body = {"key": spec.key, "name": name, "description": spec.description, "unit": spec.unit,
                    "data_class": "operational", "direction": spec.direction, "rollup": spec.rollup,
                    "rule_type": "threshold", "green_threshold": spec.green, "yellow_threshold": spec.yellow,
                    "source_type": "manual", "owner_service": "project_product", "sort_order": spec.sort_order}
            try:
                catalog[spec.key] = ctx.plans.ensure_indicator(body)
            except Conflict:
                continue
            created.append(spec.key)
            break
        else:
            notes.append(f"Показатель {spec.key} не создан: название «{spec.name}» занято другим показателем")
    return catalog, created


# ---------------------------------------------------------------- коннектор

@register
class PulsConnector(Connector):
    kind = "puls"
    order = 20
    counter_labels = {
        "projects": "проектов", "mapped": "сопоставлено с подразделениями", "unmapped": "без подразделения",
        "units": "подразделений", "projects_green": "зелёных", "projects_yellow": "жёлтых",
        "projects_red": "красных", "projects_gray": "без задач", "values_create": "значений: новых",
        "values_update": "значений: изменено", "values_unchanged": "значений без изменений",
        "values_cleared": "значений очищено", "values_errors": "ошибок в значениях",
    }
    # Подробности проверки: версия, режим, ключ (название и права) или учётная запись, направления с подразделениями
    detail_labels = {
        "user": "Служебная учётная запись", "stats": "Право «Показатели проектов»",
        "without_direction": "Проектов без направления", "directions": "Направления",
        "unmapped": "Без подразделения (в корень структуры)", "role": "Роль в «Пульсе»",
    }
    technical_details = ("schema",)
    title = TITLE
    description = ("Проекты «Пульса проекта» → показатели сквозного отчёта по подразделениям (сопоставление "
                   "«направление → подразделение»): проекты в работе, просроченные, заблокированные задачи, средний "
                   "прогресс и доля проектов в срок; светофор проекта выводится в «Дашбордах». Подключение — ключом "
                   "интеграции «Пульса» 0.6.0 и новее (права projects.read и projects.stats) или, для более ранних "
                   "версий, служебной учётной записью только для чтения")
    fields = (
        Field("base_url", "Адрес «Пульса проекта»", "url", required=True, placeholder="https://puls.company.ru"),
        Field("mode", "Режим подключения", "select", required=True, default=KEY_MODE,
              options=(Option(KEY_MODE, "Ключ интеграции (Пульс 0.6.0 и новее)"),
                       Option(SESSION_MODE, "Служебная учётная запись (для версий до 0.6.0)")),
              hint="Рекомендуется ключ интеграции: у «Дашбордов» свой ключ только для чтения проектов, без входа "
                   "учётной записью. Служебная учётная запись — для «Пульса» до 0.6.0, где ключей для других систем "
                   "нет"),
        Field("api_key", "Ключ интеграции", "password", required=True, secret=True, show_if={"mode": (KEY_MODE,)},
              placeholder="puls_…",
              hint="Выпускает администратор «Пульса»: «Интеграции → Ключи доступа» → «Выпустить ключ» — система "
                   "«Дашборды компании», права «Проекты и планы» (projects.read) и «Показатели проектов» "
                   "(projects.stats). Ключ показывается один раз"),
        Field("login", "Служебная учётная запись", required=True, show_if={"mode": (SESSION_MODE,)},
              hint="Для «Пульса» до 0.6.0. Только чтение: доступ к нужным направлениям (роль «Наблюдатель» с правами "
                   "на направления или администратор)"),
        Field("password", "Пароль", "password", required=True, secret=True, show_if={"mode": (SESSION_MODE,)}),
        Field("verify_tls", "Проверять TLS-сертификат", "bool", default=True,
              hint="Выключите только для самоподписанного или корпоративного сертификата"),
        Field("directions", "Направление → подразделение", "text",
              placeholder="Внедрение = PROJ\n7 = АЛМИ Партнер / Техническая дирекция",
              hint="По строке на направление: «направление = подразделение»; направление — название или id (id — "
                   "по ключу с правом projects.stats или служебной учётной записью), подразделение — код или путь "
                   "через «/». Проекты несопоставленных направлений относятся к корню структуры; список направлений "
                   "— в результате проверки"),
    )
    actions = (Action("indicators", "Обновить показатели проектов",
                      "Проекты в работе, просроченные, заблокированные задачи, средний прогресс и доля проектов в "
                      "срок за текущий месяц — по подразделениям сопоставления"),)

    @classmethod
    def validate_config(cls, config: dict) -> dict:
        config = dict(config or {})
        if not config.get("mode"):
            # Новое подключение — по ключу; запрос с логином служебной учётной записи и без режима — как раньше
            config["mode"] = connection_mode(config)
        out = super().validate_config(config)
        parse_mapping(out.get("directions"))
        return out

    @classmethod
    def stored_config(cls, config: dict | None) -> dict:
        """Подключение, сохранённое без режима, — служебная учётная запись (так оно и работало)."""
        out = super().stored_config(config)
        if out.get("mode") not in MODE_LABELS:
            out["mode"] = connection_mode(out)
        return out

    @property
    def mode(self) -> str:
        return connection_mode(self.config)

    # --- чтение «Пульса»
    def session(self) -> PartnerSession:
        return PartnerSession(self.config["base_url"], kind=self.kind, title=TITLE,
                              login=self.config.get("login") or "", password=self.secrets.get("password") or "",
                              csrf_path="api/auth/csrf",
                              verify=bool(self.config.get("verify_tls", True)), detailed=self.detailed)

    def key_api(self) -> KeyApi:
        key = (self.secrets.get("api_key") or "").strip()
        if not key.startswith(KEY_PREFIX):
            raise IntegrationError(f"Ключ интеграции «Пульса» начинается с {KEY_PREFIX} — проверьте ключ",
                                   code="config")
        client = self.http(headers={"Authorization": f"Bearer {key}"}, cookies=False)
        return KeyApi(client, title=TITLE, prefix=V1, place=KEYS_PLACE, no_api=NO_API)

    def load(self, *, projects: bool = True) -> tuple[list[Project], list[dict], dict]:
        """(проекты, направления [{id, name} — у ключа ещё projects: число проектов], сведения о версии, режиме,
        учётной записи или ключе). projects=False — без проектов (проверке по ключу хватает числа проектов из
        направлений)."""
        if self.mode == KEY_MODE:
            return self.load_key(projects=projects)
        with self.session() as s:
            ready = s.get_json("api/health/ready")
            directions = [d for d in s.get_json("api/directions", kind=list) if isinstance(d, dict)]
            raw = [p for p in s.get_json("api/projects", kind=list) if isinstance(p, dict)]
            user = s.user
        names = {d.get("id"): str(d.get("name") or "") for d in directions}
        info = {"version": str(ready.get("version") or ""), "schema": ready.get("schema"), "mode": SESSION_MODE,
                "user": {"login": user.get("login"), "name": user.get("name"), "role": user.get("role")}}
        return [Project.from_session(p, names) for p in raw], \
            [{"id": d.get("id"), "name": str(d.get("name") or "")} for d in directions], info

    def load_key(self, *, projects: bool = True) -> tuple[list[Project], list[dict], dict]:
        """Ключ: /ping (версия, название и права), /directions, /projects?limit=200 (без листания)."""
        with self.key_api() as api:
            ping = api.ping("puls")
            version = str(ping.get("version") or "")
            key = ping.get("key") if isinstance(ping.get("key"), dict) else {}
            if not isinstance(key.get("scopes"), list):
                # «Пульс» 0.5.x: ключ один (для «По Делу»), прав и направлений у API нет
                raise IntegrationError(f"«{TITLE}» {version} не сообщает права ключа — это версия до 0.6.0, где ключ "
                                       "интеграции один и выдан «По Делу». Обновите «Пульс» до 0.6.0 или выберите "
                                       "режим «Служебная учётная запись (для версий до 0.6.0)»", code="no_api",
                                       short=f"В «{TITLE}» нет ключей интеграций для других систем")
            scopes = [str(s) for s in key["scopes"]]
            if SCOPE_READ not in scopes:
                raise IntegrationError(f"У ключа «{api.key_name}» нет права {SCOPE_LABELS[SCOPE_READ]} — добавьте его "
                                       f"ключу: {KEYS_PLACE}", code="insufficient_scope",
                                       short=f"У ключа интеграции «{TITLE}» нет доступа к проектам")
            listed = api.get("directions")
            raw = [p for p in api.get("projects", params={"limit": PROJECTS_MAX}).get("projects") or []
                   if isinstance(p, dict)] if projects else []
        directions = [{"id": d.get("id"), "name": str(d.get("name") or ""), "projects": _int(d.get("projects"))}
                      for d in listed.get("directions") or [] if isinstance(d, dict)]
        without = _int(listed.get("withoutDirection"))
        info = {"version": version, "mode": KEY_MODE, "key": {"name": api.key_name, "scopes": scopes},
                "stats": SCOPE_STATS in scopes, "total": sum(d["projects"] for d in directions) + without,
                "without_direction": without, "limited": len(raw) >= PROJECTS_MAX}
        return [Project.from_key(p) for p in raw], directions, info

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

    def _id_lines(self, directions: list[dict]) -> list[str]:
        """Строки сопоставления по id направления, которые без права projects.stats не сработают (у проектов нет
        id направления): подсказка — название направления."""
        out = []
        for number, direction, _unit in parse_mapping(self.config.get("directions")):
            by_id = next((d for d in directions if d["id"] is not None and direction == str(d["id"])), None)
            if by_id and not any(name_key(direction) == name_key(d["name"]) for d in directions):
                out.append(f"строка {number} («{direction}»): без права projects.stats направление сопоставляется "
                           f"только по названию — укажите «{by_id['name']}»")
        return out

    # --- проверка
    def check(self) -> CheckResult:
        projects, directions, info = self.load(projects=self.mode != KEY_MODE)
        key_mode = info["mode"] == KEY_MODE
        problems: list[str] = []
        warnings: list[str] = []
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
            count = d["projects"] if "projects" in d else \
                sum(1 for p in projects if (d["id"] is not None and p.direction_id == d["id"])
                    or (d["id"] is None and p.direction == d["name"]))
            listed.append({"id": d["id"], "name": d["name"], "projects": count,
                           "department": paths.get(unit_id) if unit_id else None})
        unmapped = [d["name"] for d in listed if not d["department"]]
        total = info["total"] if key_mode else len(projects)
        if key_mode:
            if not info["stats"]:
                warnings.append(NO_STATS)
                problems.extend(self._id_lines(directions))
            if total > PROJECTS_MAX:
                warnings.append(f"проектов в «Пульсе» {total}, а API отдаёт не больше {PROJECTS_MAX} — показатели "
                                f"будут посчитаны по первым {PROJECTS_MAX}")
            key = info["key"]
            who = f"«{key['name']}», права: {', '.join(key['scopes']) or 'нет'}" if key["name"] else \
                f"права: {', '.join(key['scopes']) or 'нет'}"
        else:
            who = info.get("user", {}).get("name") or info.get("user", {}).get("login")
        version = f" {info['version']}" if info.get("version") else ""
        message = (f"Подключено к «{TITLE}»{version} ({MODE_LABELS[info['mode']]}{f' {who}' if who else ''}): "
                   f"проектов {total}, направлений {len(directions)}, сопоставлено {len(directions) - len(unmapped)}")
        if unmapped:
            message += f"; без подразделения (в корень структуры): {', '.join(unmapped[:10])}"
        # Число проектов — projects (у ключа total — оно же); limited — признак запуска: проверка по ключу проекты не
        # читает, предел видно по числу проектов
        details = {**{k: v for k, v in info.items() if k not in ("limited", "total")}, "projects": total,
                   "directions": listed, "unmapped": unmapped}
        # Замечания: права и пределы ключа, затем строки сопоставления, которые не сработают
        problems = [f"сопоставление, {p}" if p.startswith("строка ") else p for p in problems]
        return CheckResult(True, message, details, [*warnings, *problems])

    # --- запуск
    def run(self, action: str, ctx: RunContext) -> RunResult:
        self.action(action)
        projects, directions, info = self.load()
        key_mode = info["mode"] == KEY_MODE
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
        if key_mode and not info["stats"]:
            notes.extend(self._id_lines(directions))
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
        catalog, created = ensure_indicators(ctx, notes)
        usable = {}
        for key in INDICATOR_KEYS:
            ind = catalog.get(key)
            if ind is None:
                continue
            if not ind.is_active or ind.computed:
                notes.append(f"показатель {key} {'выключен' if not ind.is_active else 'вычисляемый'} — не обновляется")
                continue
            usable[key] = ind
        # Ограничения ключа — сведения, а не ошибка настройки: запуск от них не становится «частичным»
        limits: list[str] = []
        if key_mode and not info["stats"]:
            usable.pop("puls.blocked", None)
            limits.append(NO_STATS)
        if key_mode and info["limited"]:
            limits.append(LIMITED)
        rows = self._rows(snap, [u for u in order if u in targets], projects, root, usable, period, today, notes)
        mapped = sum(1 for p in projects if p.unit is not None)
        counters = {"projects": len(projects), "mapped": mapped, "unmapped": len(projects) - mapped,
                    "units": len({r["department"] for r in rows}), "indicators_created": len(created),
                    **{f"projects_{k}": v for k, v in lights.items()}}
        details: dict = {"period": period, "mode": info["mode"], "flagged": flagged[:MAX_DETAILS]}
        if key_mode:
            details.update(key=info["key"], stats=info["stats"])
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
                        values_cleared=summary.get("cleared", 0), values_unchanged=summary.get("unchanged", 0),
                        values_errors=summary.get("errors", 0))
        if not result.get("applied"):
            errors = plan_errors(result, 5) or ["план значений не применён"]
            return RunResult.failed(f"Показатели проектов не записаны: {'; '.join(errors)}", counters=counters,
                                    details=details)
        label = reports.period_label(date(today.year, today.month, 1)).lower()
        message = (f"Показатели проектов за {label}: проектов {len(projects)} (в работе "
                   f"{sum(1 for p in projects if p.in_work)}, красных {lights['red']}, жёлтых {lights['yellow']}), "
                   f"подразделений {counters['units']}; значений новых {counters['values_create']}, изменено "
                   f"{counters['values_update']}, без изменений {counters['values_unchanged']}")
        if counters["values_cleared"]:
            message += f", очищено {counters['values_cleared']} (нет проектов в работе)"
        if created:
            message += f"; созданы показатели: {', '.join(created)}"
        if limits:
            text = "; ".join(limits)
            message += f". {text[:1].upper()}{text[1:]}"
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
            values: dict[str, float | None] = {"puls.projects": len(active), "puls.overdue": len(late),
                                               "puls.blocked": sum(p.blocked or 0 for p in mine)}
            # Без проектов в работе среднего прогресса и доли в срок нет: значение прошлого запуска очищается
            values["puls.progress"] = sum(p.progress for p in active) / len(active) if active else None
            values["puls.on_time_share"] = (len(active) - len(late)) / len(active) * 100 if active else None
            for key, value in values.items():
                if key not in usable:
                    continue
                if value is None:
                    rows.append({"line": len(rows) + 1, "department": ref, "indicator": key, "period": period,
                                 "value": None, "target": None, "comment": None, "clear": True})
                else:
                    rows.append({"line": len(rows) + 1, "department": ref, "indicator": key, "period": period,
                                 "value": _number(value), "target": "", "comment": COMMENT})
        return rows
