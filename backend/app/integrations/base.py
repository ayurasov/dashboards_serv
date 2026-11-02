"""Каркас коннекторов (ADR-0011): описание настроек, проверка, действия, контекст запуска, реестр.

Как написать коннектор — app/integrations/__init__.py (руководство) и app/integrations/connectors/folder.py
(простейший пример). Коротко:

    @register
    class PuLSConnector(Connector):
        kind = "puls"
        title = "Пульс проекта"
        fields = (Field("base_url", "Адрес", "url", required=True),
                  Field("login", "Служебная учётная запись", required=True),
                  Field("password", "Пароль", "password", required=True, secret=True))
        actions = (Action("projects", "Забрать проекты"),)

        def check(self) -> CheckResult:
            with self.http() as client:
                meta = client.get_json("api/meta")
            return CheckResult(True, f"Подключено: {meta.get('name')}")

        def run(self, action: str, ctx: RunContext) -> RunResult:
            ...
            item = ctx.inbox.add(content, "projects.json", dataset="indicators", source_ref="puls:projects")
            return RunResult.ok("Проекты забраны", counters={"projects": n}, items=[item.id])

Коннектор не пишет в таблицы служб сам: он отдаёт файлы в конвейер входящих (ctx.inbox.add) или
план/применение движкам загрузки (ctx.plans). Секреты (поля secret=True) приходят расшифрованными
в self.secrets — только для адреса, для которого их ввели; наружу (API, журнал) они не выходят:
HttpClient из self.http() и runner вычищают их (и secret_values()) из текстов ошибок и журнала.
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..core.errors import ValidationFailed
from .http import HttpClient, IntegrationError, allowed_hosts_env, check_base_url

if TYPE_CHECKING:
    from ..models import InboxItem, Integration, User
    from ..services.reports import IndicatorDef

FIELD_TYPES = ("string", "text", "url", "password", "int", "bool", "select", "multiselect", "list", "time", "json")
JSON_MAX_BYTES = 64 * 1024
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# Подписи счётчиков журнала запусков, общие для коннекторов (Connector.counter_labels дополняет и уточняет их):
# значения показателей (ctx.plans.indicator_values, _metrics.write), файлы во «Входящие» (ctx.inbox) и их статусы.
# Счётчик без подписи интерфейс не показывает (номер элемента, служебное число) — подпишите каждый, который
# должен быть виден.
INBOX_STATUS_COUNTER_LABELS: dict[str, str] = {
    "status_received": "не распознано", "status_recognized": "распознано", "status_pending": "ждут подтверждения",
    "status_applied": "применено сразу", "status_rejected": "отклонено", "status_error": "с ошибкой",
    "status_duplicate": "повторов",
}
COMMON_COUNTER_LABELS: dict[str, str] = {
    "values": "значений", "created": "новых", "updated": "изменено", "unchanged": "без изменений",
    "cleared": "очищено", "values_pending": "значений новых показателей", "indicators_created": "создано показателей",
    "files": "файлов", "added": "во «Входящие»", "seen": "уже забраны", "skipped_type": "пропущено: не данные",
    "too_large": "пропущено: слишком большие", "duplicates": "повторов", "skipped": "пропущено",
    "errors": "ошибок", "items": "элементов входящих",
    **INBOX_STATUS_COUNTER_LABELS,
}


# ---------------------------------------------------------------- описание настроек

@dataclass(frozen=True)
class Option:
    value: str
    label: str


@dataclass(frozen=True)
class Field:
    """Поле настроек для интерфейса. type: string · text · url · password · int · bool · select ·
    multiselect · list (список строк) · time (ЧЧ:ММ) · json (разобранное значение JSON — список правил,
    запросов; принимает и JSON-текст, до 64 КБ). secret=True — значение шифруется и не
    возвращается (в API — только признак «задано»). show_if — {поле: [значения]}: показывать поле,
    только когда другое поле имеет одно из значений (например, логин — только для типа «cloud»)."""

    key: str
    label: str
    type: str = "string"
    hint: str = ""
    required: bool = False
    secret: bool = False
    options: tuple[Option, ...] = ()
    default: Any = None
    placeholder: str = ""
    min: int | None = None
    max: int | None = None
    show_if: dict[str, tuple[str, ...]] | None = None

    def __post_init__(self):
        if self.type not in FIELD_TYPES:  # pragma: no cover - ошибка программиста
            raise ValueError(f"{self.key}: тип {self.type}")

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "type": self.type, "hint": self.hint,
                "required": self.required, "secret": self.secret, "default": self.default,
                "placeholder": self.placeholder, "min": self.min, "max": self.max,
                "options": [{"value": o.value, "label": o.label} for o in self.options],
                "show_if": {k: list(v) for k, v in (self.show_if or {}).items()} or None}

    def visible(self, config: dict) -> bool:
        return not self.show_if or all(config.get(k) in v for k, v in self.show_if.items())


@dataclass(frozen=True)
class Action:
    """Действие коннектора («Синхронизировать структуру», «Забрать данные»). schedulable — можно
    выполнять по расписанию."""

    key: str
    label: str
    description: str = ""
    schedulable: bool = True

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "description": self.description,
                "schedulable": self.schedulable}


@dataclass
class CheckResult:
    ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "message": self.message, "details": jsonable_encoder(self.details)}


@dataclass
class RunResult:
    """Итог действия: status ok · partial (часть не удалась) · error; counters — счётчики для журнала
    запусков; items — номера созданных элементов входящих."""

    status: str = "ok"
    message: str = ""
    counters: dict[str, int] = field(default_factory=dict)
    items: list[int] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @classmethod
    def ok(cls, message: str = "", **kwargs) -> RunResult:
        return cls("ok", message, **kwargs)

    @classmethod
    def partial(cls, message: str, error: str = "", **kwargs) -> RunResult:
        return cls("partial", message, error=error, **kwargs)

    @classmethod
    def failed(cls, error: str, **kwargs) -> RunResult:
        return cls("error", error, error=error, **kwargs)

    def summary(self) -> dict:
        return jsonable_encoder({**self.counters, **({"items": self.items} if self.items else {}),
                                 **({"details": self.details} if self.details else {})})


# ---------------------------------------------------------------- контекст запуска

class InboxGateway:
    """Входящие для коннектора: ctx.inbox.add(content, filename, dataset=None, source_ref=…) — элемент
    входящих от имени подключения (источник «Подключение»; «применять сразу» — по правилу источника
    «integration» и набора). Каждый элемент фиксируется сразу (commit): падение позже его не теряет."""

    def __init__(self, ctx: RunContext):
        self.ctx = ctx
        self.added: list[int] = []

    def add(self, content: bytes, filename: str, dataset: str | None = None, *, source_ref: str = "",
            content_type: str = "", options: dict | None = None, apply: bool | None = None,
            note: str = "") -> InboxItem:
        """note — откуда файл для человека (до 500 символов): «Задача «…» · автор», «Письмо «…» от …»;
        показывается под именем файла в списке «Входящих» и в карточке элемента."""
        from ..services import inbox

        db = self.ctx.db
        item = inbox.add(db, content, filename, source="integration", source_ref=source_ref, dataset=dataset,
                         integration_id=self.ctx.integration.id if self.ctx.integration else None,
                         label=self.ctx.label, content_type=content_type, options=options, apply=apply, note=note)
        db.commit()
        self.added.append(item.id)
        return item

    def seen(self, source_ref: str) -> InboxItem | None:
        """Элемент этого подключения с тем же source_ref (вложение уже забирали)."""
        from sqlalchemy import select

        from ..models import InboxItem

        stmt = select(InboxItem).where(InboxItem.source_ref == source_ref[:500])
        if self.ctx.integration is not None:
            stmt = stmt.where(InboxItem.integration_id == self.ctx.integration.id)
        return self.ctx.db.scalar(stmt.order_by(InboxItem.id.desc()).limit(1))


class PlanEngines:
    """Движки загрузки для коннектора — те же, что у ручной загрузки. apply=False — план без записи;
    apply=True — применение одной транзакцией (commit при успехе, откат при ошибках плана) от имени
    подключения. Возвращают план или итог (словарь со summary, can_apply, applied).
    ensure_indicator — показатель каталога сквозных отчётов (создать недостающий)."""

    def __init__(self, ctx: RunContext):
        self.ctx = ctx

    def _run(self, plan_fn, apply_fn, apply: bool) -> dict:
        db = self.ctx.db
        if not apply:
            return {**plan_fn(), "applied": False}
        result, applied = apply_fn()
        if applied:
            db.commit()
        else:
            db.rollback()
        return result

    def structure(self, bundle: dict, *, apply: bool = False, apply_settings: bool = False) -> dict:
        """bundle — документ dashboards.org-structure (app/services/org_transfer.py)."""
        from ..services import org_transfer

        actor = self.ctx.actor
        return self._run(lambda: org_transfer.plan_structure(self.ctx.db, bundle, apply_settings=apply_settings)
                         .as_dict(),
                         lambda: org_transfer.apply_structure(self.ctx.db, actor, bundle,
                                                              apply_settings=apply_settings), apply)

    def employees(self, document: dict | list, *, apply: bool = False, new_users: str = "no_access",
                  decisions: dict | None = None) -> dict:
        """document — dashboards.employees или список записей (app/services/employee_transfer.py)."""
        from ..services import employee_transfer

        records = employee_transfer.parse_json(document)
        actor = self.ctx.actor
        return self._run(lambda: employee_transfer.plan_employees(self.ctx.db, records, actor=actor,
                                                                  new_users=new_users, decisions=decisions).as_dict(),
                         lambda: employee_transfer.apply_employees(self.ctx.db, actor, records, new_users=new_users,
                                                                   decisions=decisions), apply)

    def org_list(self, rows: list, *, apply: bool = False, create_missing: bool = False,
                 deactivate_missing: bool = False, manager_refs: dict | None = None,
                 keep: set[str] | None = None) -> dict:
        """Быстрая загрузка списком (app/services/org_import.py, Row): источник — вид подключения
        (сопоставление по внешнему ID этого источника, затем email). deactivate_missing — отключить сотрудников
        этого источника, которых нет в rows (умеют источники org_import.DEACTIVATING_SOURCES: ad, podelu);
        keep — логины и email служебных учётных записей, которые не отключаются никогда."""
        from ..services import org_import

        source = self.ctx.kind
        options = {"source": source, "create_missing": create_missing, "deactivate_missing": deactivate_missing,
                   "manager_refs": manager_refs, "keep": set(keep or ())}
        actor = self.ctx.actor
        return self._run(lambda: org_import.plan_import(self.ctx.db, rows, **options).as_dict(),
                         lambda: org_import.apply_import(self.ctx.db, actor, rows, **options), apply)

    def indicator_values(self, rows: list[dict], *, apply: bool = False, filename: str = "") -> dict:
        """rows — [{"line", "department" (путь или код), "indicator" (ключ или название), "period" (ГГГГ-ММ),
        "value", "target", "comment"}] текстом (app/services/report_admin.py). Строка {"clear": True} без
        значения, цели и комментария удаляет сохранённое значение показателя подразделения за месяц
        (в плане — действие clear, в сводке — cleared); пустое значение без clear ничего не стирает."""
        from ..services import report_admin

        actor = self.ctx.actor
        name = filename or self.ctx.label
        return self._run(lambda: report_admin.plan_import(self.ctx.db, actor, rows)[0],
                         lambda: report_admin.apply_import(self.ctx.db, actor, rows, name), apply)

    def ensure_indicator(self, body: dict) -> IndicatorDef:
        """Показатель каталога сквозных отчётов по ключу body["key"]: есть — возвращается как есть (настройки
        каталога подключение не меняет: их правят в разделе «Показатели»); нет — создаётся функцией каталога
        (report_admin.create_indicator: те же проверки и запись в журнал изменений) от имени подключения.

        body — поля IndicatorCreateIn: key, name, unit, data_class, direction, rollup, rule_type, границы,
        source_type ("manual"), owner_service, description, sort_order… Ошибки — ValidationFailed (недопустимое
        описание) или Conflict (название занято другим показателем); транзакция при них откатывается.

        Созданный показатель фиксируется сразу (commit) — это единственный commit коннектора помимо ctx.inbox
        и движков загрузки: каталог для плана значений (reports.state) берётся по ревизии сквозных отчётов,
        а она растёт только при фиксации. Без commit план значений в этом же запуске показателя не увидит."""
        from pydantic import ValidationError as PydanticError

        from ..core.errors import AppError
        from ..schemas.reports import IndicatorCreateIn
        from ..services import report_admin, reports

        db = self.ctx.db
        key = str(body.get("key") or "")
        found = next((i for i in reports.state(db).catalog if i.key == key), None)
        if found is not None:
            return found
        try:
            data = IndicatorCreateIn(**body)
        except PydanticError as exc:
            place = ".".join(map(str, exc.errors()[0]["loc"]))
            raise ValidationFailed(f"Показатель «{key}» не создан: недопустимое значение поля «{place}»",
                                   fields={place: "Недопустимое значение"}) from None
        try:
            report_admin.create_indicator(db, self.ctx.actor, data)
            db.commit()
        except AppError:
            db.rollback()
            raise
        return next(i for i in reports.state(db).catalog if i.key == key)


@dataclass
class RunContext:
    """Всё, что нужно действию коннектора.

    db — сессия базы (commit делают ctx.inbox и ctx.plans; свои записи коннектор не делает);
    integration — запись подключения (может быть None в тестах); trigger — повод запуска; user — кто
    запустил (None — по расписанию); detailed — подробные ошибки (запускает администратор);
    state — состояние между запусками (курсоры, отметки), сохраняется после действия;
    inbox, plans — см. InboxGateway и PlanEngines; log — журнал сервера."""

    db: Session
    integration: Integration | None = None
    trigger: str = "manual"
    user: User | None = None
    run_id: int | None = None
    detailed: bool = True
    state: dict[str, Any] = field(default_factory=dict)
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("app.integrations"))

    def __post_init__(self):
        self.inbox = InboxGateway(self)
        self.plans = PlanEngines(self)

    @property
    def kind(self) -> str:
        return self.integration.kind if self.integration else "integration"

    @property
    def label(self) -> str:
        name = self.integration.name if self.integration else self.kind
        return f"Подключение «{name}»"[:100]

    @property
    def actor(self) -> User:
        """От чьего имени движки пишут журнал: подключение (права «источника данных»)."""
        from ..services.inbox import source_actor

        return source_actor(self.label)

    def now(self) -> datetime:
        return utcnow()


# ---------------------------------------------------------------- коннектор

class Connector(ABC):
    """Вид подключения. Атрибуты класса описывают его для интерфейса; экземпляр создаётся на одну проверку
    или один запуск с настройками (config, без секретов) и расшифрованными секретами (secrets)."""

    kind: ClassVar[str]
    title: ClassVar[str]
    description: ClassVar[str] = ""
    fields: ClassVar[tuple[Field, ...]] = ()
    actions: ClassVar[tuple[Action, ...]] = ()
    # Поле адреса для self.http(); проверяется по <ВИД>_ALLOWED_HOSTS. None — адреса нет. По умолчанию
    # секреты привязаны к нему (secret_url)
    url_field: ClassVar[str | None] = "base_url"
    # Поля, от которых зависит адрес привязки секретов (secret_url): их изменение требует ввести секреты заново.
    # None — (url_field,). Перечисляются в /api/integrations/kinds — форма предупреждает до сохранения
    secret_url_fields: ClassVar[tuple[str, ...] | None] = None
    # Не больше одного подключения этого вида
    singleton: ClassVar[bool] = False
    # Только администратор создаёт, настраивает, проверяет, запускает, удаляет подключение этого вида и меняет его
    # расписание (подключение отдаёт наружу данные, которые не видит пользователь с integrations.manage: Confluence
    # публикует полный сквозной отчёт). Остальным с integrations.manage карточка видна только для чтения
    admin_only: ClassVar[bool] = False
    # Почему только администратор — продолжение «Только администратор: …» на карточке и в выборе вида
    admin_only_reason: ClassVar[str] = ""
    # Порядок в выборе вида и среди карточек (меньше — выше); виды с одинаковым порядком — по названию
    order: ClassVar[int] = 1000
    # Подписи счётчиков журнала запусков (RunResult.counters) по-русски: {"tasks": "задач в списке"}; общие
    # счётчики (значения, файлы во «Входящие», статусы) подписаны каркасом — COMMON_COUNTER_LABELS
    counter_labels: ClassVar[dict[str, str]] = {}
    # Только для тестов: не показывается в списке видов
    hidden: ClassVar[bool] = False

    def __init__(self, config: dict | None = None, secrets: dict | None = None, *, name: str = "",
                 integration_id: int | None = None, detailed: bool = True):
        self.config = dict(config or {})
        self.secrets = dict(secrets or {})
        self.name = name or self.title
        self.integration_id = integration_id
        self.detailed = detailed

    # --- описание
    @classmethod
    def meta(cls) -> dict:
        binding = cls.binding_fields()
        return {"kind": cls.kind, "title": cls.title, "description": cls.description,
                "fields": [f.as_dict() for f in cls.fields], "actions": [a.as_dict() for a in cls.actions],
                "url_field": cls.url_field, "secret_url_fields": list(binding), "singleton": cls.singleton,
                "allowed_hosts_env": allowed_hosts_env(cls.kind) if cls.url_field or binding else None,
                "order": cls.order, "admin_only": cls.admin_only, "admin_only_note": cls.admin_only_note(),
                "counter_labels": cls.all_counter_labels()}

    @classmethod
    def admin_only_note(cls) -> str:
        """«Только администратор: публикует полный сквозной отчёт» — для карточки и выбора вида."""
        if not cls.admin_only:
            return ""
        return "Только администратор" + (f": {cls.admin_only_reason}" if cls.admin_only_reason else "")

    @classmethod
    def all_counter_labels(cls) -> dict[str, str]:
        """Подписи счётчиков журнала запусков: общие каркаса и свои коннектора (свои сильнее)."""
        return {**COMMON_COUNTER_LABELS, **cls.counter_labels}

    @classmethod
    def binding_fields(cls) -> tuple[str, ...]:
        """secret_url_fields или (url_field,)."""
        if cls.secret_url_fields is not None:
            return tuple(cls.secret_url_fields)
        return (cls.url_field,) if cls.url_field else ()

    @classmethod
    def secret_url(cls, config: dict) -> str:
        """Адрес, к которому привязаны секреты (seal/unseal в app/core/secrets.py): сменился — секреты вводятся
        заново, сохранённый токен не уходит на адрес, для которого его не вводили. По умолчанию — значение
        url_field. Коннектор, чей секрет уходит на несколько адресов или на адрес, зависящий от режима
        («По Делу»: адрес и адрес для запросов сервера; Exchange: EWS, Graph или IMAP), переопределяет метод
        и перечисляет поля в secret_url_fields."""
        return str((config or {}).get(cls.url_field) or "") if cls.url_field else ""

    @classmethod
    def config_keys(cls) -> set[str]:
        return {f.key for f in cls.fields if not f.secret}

    @classmethod
    def secret_fields(cls) -> tuple[Field, ...]:
        return tuple(f for f in cls.fields if f.secret)

    @classmethod
    def action(cls, key: str) -> Action:
        for action in cls.actions:
            if action.key == key:
                return action
        raise ValidationFailed(f"У подключения «{cls.title}» нет действия «{key}»", fields={"action": "Нет такого"})

    # --- проверка настроек
    @classmethod
    def validate_config(cls, config: dict) -> dict:
        """Настройки без секретов: типы, обязательные поля, адрес. Переопределите для связей между полями
        (вызовите super().validate_config). Ошибка — ValidationFailed с fields={"config.<поле>": …}."""
        config = dict(config or {})
        known = {f.key: f for f in cls.fields if not f.secret}
        unknown = sorted(set(config) - set(known))
        if unknown:
            raise ValidationFailed(f"Неизвестная настройка: {unknown[0]}", fields={f"config.{unknown[0]}": "Нет такой"})
        out: dict = {}
        for key, f in known.items():
            value = config.get(key, f.default)
            out[key] = _coerce(cls, f, value)
        for f in known.values():
            if f.required and f.visible(out) and out.get(f.key) in (None, "", []):
                raise ValidationFailed(f"Обязательное поле: {f.label}", fields={f"config.{f.key}": "Обязательное поле"})
        return out

    @classmethod
    def validate_secrets(cls, secrets: dict) -> dict:
        known = {f.key for f in cls.secret_fields()}
        unknown = sorted(set(secrets or {}) - known)
        if unknown:
            raise ValidationFailed(f"Неизвестный секрет: {unknown[0]}", fields={f"secrets.{unknown[0]}": "Нет такого"})
        return {k: str(v) for k, v in (secrets or {}).items() if v not in (None, "")}

    @classmethod
    def missing_secrets(cls, config: dict, secrets: dict) -> list[Field]:
        return [f for f in cls.secret_fields() if f.required and f.visible(config) and not secrets.get(f.key)]

    # --- работа
    @property
    def url(self) -> str | None:
        return self.config.get(self.url_field) if self.url_field else None

    def secret_values(self) -> tuple[str, ...]:
        """Значения, которые не должны попасть в тексты ошибок, журнал сервера и журнал запусков: секреты
        подключения. Переопределите, если секрет уходит в запросы в производном виде (код вебхука в адресе,
        подпись) — добавьте эти части."""
        return tuple(str(v) for v in self.secrets.values() if v)

    def http(self, **kwargs) -> HttpClient:
        """HTTP-клиент на адрес подключения с сетевыми правилами ADR-0011; verify — из настройки verify_tls,
        если она есть; секреты подключения (secret_values) вычищаются из текстов его ошибок. kwargs — auth,
        headers, timeout, cookies и т. п."""
        if not self.url:
            raise IntegrationError("Не задан адрес подключения", code="config")
        kwargs.setdefault("verify", bool(self.config.get("verify_tls", True)))
        kwargs["secrets"] = (*self.secret_values(), *kwargs.get("secrets", ()))
        return HttpClient(self.url, kind=self.kind, title=self.title, detailed=self.detailed, **kwargs)

    @abstractmethod
    def check(self) -> CheckResult:
        """Проверка подключения: адрес, доступ, версия. Сеть и ответы — через self.http(); ошибки —
        IntegrationError (каркас превратит в {ok: false, message})."""

    @abstractmethod
    def run(self, action: str, ctx: RunContext) -> RunResult:
        """Выполнить действие action (ключ из actions). Данные — в ctx.inbox или ctx.plans."""


def _coerce(cls: type[Connector], f: Field, value: Any) -> Any:
    place = {f"config.{f.key}": "Недопустимое значение"}
    if value in (None, ""):
        return [] if f.type in ("multiselect", "list") else (False if f.type == "bool" else None)
    if f.type in ("string", "text", "password"):
        return str(value).strip()
    if f.type == "json":
        return _coerce_json(f, value)
    if f.type == "url":
        try:
            return check_base_url(str(value), kind=cls.kind, title=f.label)
        except IntegrationError as exc:
            raise ValidationFailed(exc.detail, code=exc.code, fields={f"config.{f.key}": exc.detail}) from None
    if f.type == "int":
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValidationFailed(f"{f.label}: нужно целое число", fields=place) from None
        if (f.min is not None and number < f.min) or (f.max is not None and number > f.max):
            raise ValidationFailed(f"{f.label}: от {f.min} до {f.max}", fields=place)
        return number
    if f.type == "bool":
        return value if isinstance(value, bool) else str(value).strip().lower() in {"1", "true", "yes", "да", "on"}
    if f.type == "time":
        if not TIME_PATTERN.match(str(value)):
            raise ValidationFailed(f"{f.label}: время ЧЧ:ММ", fields=place)
        return str(value)
    values = {o.value for o in f.options}
    if f.type == "select":
        if str(value) not in values:
            raise ValidationFailed(f"{f.label}: недопустимое значение «{value}»", fields=place)
        return str(value)
    items = value if isinstance(value, list) else [v for v in str(value).replace("\n", ",").split(",")]
    items = [str(v).strip() for v in items if str(v).strip()]
    if f.type == "multiselect" and set(items) - values:
        raise ValidationFailed(f"{f.label}: недопустимое значение", fields=place)
    return items


def _coerce_json(f: Field, value: Any) -> Any:
    place = f"config.{f.key}"
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationFailed(f"{f.label}: ошибка JSON в строке {exc.lineno}, позиция {exc.colno} — проверьте "
                                   "кавычки (только двойные), запятые и скобки",
                                   fields={place: "Ошибка JSON"}) from None
    try:
        size = len(json.dumps(value, ensure_ascii=False).encode())
    except (TypeError, ValueError):
        raise ValidationFailed(f"{f.label}: недопустимое значение", fields={place: "Недопустимое значение"}) from None
    if size > JSON_MAX_BYTES:
        raise ValidationFailed(f"{f.label}: не больше {JSON_MAX_BYTES // 1024} КБ", fields={place: "Слишком большое"})
    return value


# ---------------------------------------------------------------- реестр

_CONNECTORS: dict[str, type[Connector]] = {}
_loaded = False


def register(cls: type[Connector]) -> type[Connector]:
    """Декоратор: зарегистрировать вид подключения. kind — латиница, цифры, «_» и «-»."""
    if not re.match(r"^[a-z][a-z0-9_-]{1,39}$", cls.kind or ""):  # pragma: no cover - ошибка программиста
        raise ValueError(f"kind «{cls.kind}»")
    if cls.kind in _CONNECTORS and _CONNECTORS[cls.kind] is not cls:  # pragma: no cover
        raise ValueError(f"Вид подключения {cls.kind} уже зарегистрирован")
    _CONNECTORS[cls.kind] = cls
    return cls


def unregister(kind: str) -> None:
    _CONNECTORS.pop(kind, None)


def load_connectors() -> None:
    """Импорт встроенных коннекторов (один раз на процесс): модули регистрируют свои классы (@register) и чужие
    форматы JSON входящих (inbox_datasets.register_json_format). Вызывается реестром и распознаванием набора —
    в любом процессе (сервер, планировщик, командная строка), без отдельного шага при старте."""
    global _loaded
    if not _loaded:
        from . import connectors  # noqa: F401 — модули коннекторов регистрируются при импорте

        _loaded = True


_load = load_connectors


def get(kind: str) -> type[Connector]:
    _load()
    cls = _CONNECTORS.get(kind)
    if cls is None:
        raise ValidationFailed(f"Неизвестный вид подключения: {kind}", fields={"kind": "Нет такого"})
    return cls


def find(kind: str) -> type[Connector] | None:
    _load()
    return _CONNECTORS.get(kind)


def sort_key(cls: type[Connector]) -> tuple[int, str]:
    """Порядок видов: Connector.order, затем название."""
    return cls.order, cls.title.casefold()


def all_connectors(*, include_hidden: bool = False) -> list[type[Connector]]:
    """Виды подключений в порядке Connector.order: «По Делу», «Пульс проекта», Jira, Confluence, Bitrix24,
    почтовый ящик Exchange, 1С, папка «Входящие»."""
    _load()
    return sorted((c for c in _CONNECTORS.values() if include_hidden or not c.hidden), key=sort_key)
