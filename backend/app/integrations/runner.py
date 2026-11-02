"""Запуск подключений: экземпляр коннектора с секретами, проверка, действие, журнал запусков, расписание.

Расписание (integrations.schedule) — список записей, не больше MAX_ENTRIES (пустой — только вручную):
    [{"mode": "interval", "minutes": 30, "actions": ["pull"]},                  — каждые N минут (5…10080)
     {"mode": "daily", "time": "06:30", "weekdays": [1, 5], "actions": […]}]    — в ЧЧ:ММ по TIMEZONE;
        weekdays — дни недели ISO (1 — понедельник), пусто — каждый день
actions — действия коннектора с schedulable=True; по умолчанию — первое такое. Прежний вид — один объект
{"mode": …} или {} — принимается и читается как одна запись (entries_of).

У каждой записи свой следующий запуск (integrations.next_runs — список по порядку записей, ISO-время UTC);
integrations.next_run_at — ближайший из них (по нему планировщик выбирает подключения и его показывает карточка).

Занятие запуска атомарно (claim_due): UPDATE integrations SET next_run_at = <ближайший после занятия>,
next_runs = <записи, чей срок настал, — на следующий раз> WHERE id = … AND enabled AND next_run_at <= now
AND next_run_at = <прочитанное> — на PostgreSQL второй процесс ждёт блокировку строки и после неё условие уже не
выполняется, на SQLite записи и так идут по очереди. Поэтому несколько планировщиков не выполнят одну запись
дважды; занявший выполняет действия всех записей, чей срок настал. Ручной запуск во время идущего не начнётся:
running_since занимается тем же приёмом (begin_running).

Запуск, который идёт дольше RUNNING_TIMEOUT (процесс остановился посреди запуска: перезапуск, сбой), считается
прерванным: API показывает его «Запуск прерван» (статус interrupted), подключение снова можно запустить, а
begin_running и планировщик (reclaim_stale) занимают его заново и отмечают такие записи журнала прерванными.

Секреты не попадают ни в журнал сервера, ни в журнал запусков, ни в ответы API: тексты проверки и запуска
(сообщение, ошибка, подробности, last_error) и журнал неожиданных исключений (сообщение и трассировка —
без log.exception) проходят через http.scrub с секретами коннектора (Connector.secret_values()).
"""
from __future__ import annotations

import logging
import traceback
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from ..core import db as core_db
from ..core.config import settings
from ..core.db import utcnow
from ..core.errors import AppError, Conflict, NotFound, ValidationFailed
from ..core.secrets import SecretError, unseal
from ..models import Integration, IntegrationRun, User
from . import base
from .base import CheckResult, Connector, RunContext, RunResult
from .http import IntegrationError, record_health, scrub, scrub_data, secret_texts

log = logging.getLogger("app.integrations")

PURPOSE = "integration"
RUNNING_TIMEOUT = timedelta(hours=2)
MIN_INTERVAL, MAX_INTERVAL = 5, 7 * 24 * 60
MAX_ENTRIES = 5
MODES = ("interval", "daily")
INTERNAL_ERROR = "Внутренняя ошибка коннектора — подробности в журнале сервера"
INTERRUPTED = ("Запуск прерван: процесс приложения или планировщика остановился до окончания запуска (перезапуск, "
               "сбой) — подключение можно запустить снова")
WEEKDAY_NAMES = {1: "пн", 2: "вт", 3: "ср", 4: "чт", 5: "пт", 6: "сб", 7: "вс"}


def owner(integration_id: int | None) -> str:
    return f"integration:{integration_id}"


def url_of(cls: type[Connector], config: dict) -> str:
    """Адрес привязки секретов подключения (Connector.secret_url)."""
    return cls.secret_url(config or {})


def _secrets_of(connector: Connector | None, extra: dict | None = None) -> tuple[str, ...]:
    values: list[str] = list(connector.secret_values()) if connector is not None else []
    values += [str(v) for v in (extra or {}).values() if v]
    return secret_texts(values)


def _log_failure(what: str, row: Integration, exc: BaseException, secrets: Iterable[str]) -> None:
    """Неожиданное исключение коннектора — в журнал сервера без секретов: сообщение и трассировка вычищены."""
    message = scrub(f"{type(exc).__name__}: {exc}", secrets)
    trace = scrub("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)), secrets)
    log.error("integration %s (%s): %s failed: %s\n%s", row.id, row.kind, what, message, trace)


def clean_check(result: CheckResult, secrets: Iterable[str]) -> CheckResult:
    return CheckResult(result.ok, scrub(result.message, secrets), scrub_data(result.details, secrets))


def clean_run(result: RunResult, secrets: Iterable[str]) -> RunResult:
    result.message = scrub(result.message, secrets)
    result.error = scrub(result.error, secrets)
    result.details = scrub_data(result.details, secrets)
    return result


def stored_secrets(row: Integration, cls: type[Connector] | None = None) -> dict[str, str]:
    """Расшифрованные секреты для текущего адреса подключения; SecretError — ввести заново."""
    if not row.secret_encrypted:
        return {}
    cls = cls or base.get(row.kind)
    return unseal(PURPOSE, row.secret_encrypted, row.secret_bound_url, url_of(cls, row.config), owner=owner(row.id))


def connector_for(row: Integration, *, detailed: bool = True, config: dict | None = None,
                  secrets: dict | None = None) -> Connector:
    """Экземпляр коннектора записи. config/secrets — несохранённые значения (проверка перед сохранением)."""
    cls = base.get(row.kind)
    config = row.config if config is None else config
    if secrets is None:
        try:
            secrets = stored_secrets(row, cls)
        except SecretError as exc:
            raise IntegrationError(exc.detail, code=exc.code, short="Секрет подключения нужно ввести заново") from None
    missing = cls.missing_secrets(config, secrets)
    if missing:
        raise IntegrationError(f"Не задано: {missing[0].label}", code="secret_missing",
                               short="Подключение настроено не полностью")
    return cls(config, secrets, name=row.name, integration_id=row.id, detailed=detailed)


# ---------------------------------------------------------------- расписание

def entries_of(schedule: object) -> list[dict]:
    """Записи расписания: список (0.4.0) или прежний вид — один объект {mode, …} ({} и mode off — вручную)."""
    if isinstance(schedule, dict):
        schedule = schedule["entries"] if isinstance(schedule.get("entries"), list) else [schedule]
    if not isinstance(schedule, list):
        return []
    return [dict(e) for e in schedule if isinstance(e, dict) and e.get("mode") in MODES]


def schedule_actions(schedule: object) -> list[str]:
    """Действия всех записей расписания по порядку, без повторов."""
    return list(dict.fromkeys(a for e in entries_of(schedule) for a in e.get("actions") or []))


def _normalize_entry(cls: type[Connector], schedule: dict, schedulable: list[str], place: str) -> dict | None:
    mode = schedule.get("mode") or "off"
    if mode == "off":
        return None
    actions = schedule.get("actions") or schedulable[:1]
    if not isinstance(actions, list) or any(a not in schedulable for a in actions):
        raise ValidationFailed(f"По расписанию выполняются: {', '.join(schedulable)}",
                               fields={f"{place}.actions": "Недопустимое действие"})
    out: dict = {"mode": mode, "actions": list(dict.fromkeys(actions))}
    if mode == "interval":
        try:
            minutes = int(schedule.get("minutes"))
        except (TypeError, ValueError):
            raise ValidationFailed("Интервал — целое число минут", fields={f"{place}.minutes": "Нужно число"}) from None
        if not MIN_INTERVAL <= minutes <= MAX_INTERVAL:
            raise ValidationFailed(f"Интервал — от {MIN_INTERVAL} минут до недели",
                                   fields={f"{place}.minutes": "Вне допустимого"})
        out["minutes"] = minutes
    elif mode == "daily":
        time_text = str(schedule.get("time") or "")
        if not base.TIME_PATTERN.match(time_text):
            raise ValidationFailed("Время запуска — ЧЧ:ММ", fields={f"{place}.time": "Нужно ЧЧ:ММ"})
        weekdays = schedule.get("weekdays") or []
        if not isinstance(weekdays, list) or any(not isinstance(d, int) or not 1 <= d <= 7 for d in weekdays):
            raise ValidationFailed("Дни недели — числа 1…7 (1 — понедельник)", fields={f"{place}.weekdays": "1…7"})
        out.update(time=time_text, weekdays=sorted(set(weekdays)))
    else:
        raise ValidationFailed("Расписание: off, interval или daily", fields={f"{place}.mode": "Недопустимо"})
    return out


def normalize_schedule(cls: type[Connector], schedule: object) -> list[dict]:
    """Расписание из API: список записей {mode: interval | daily, minutes, time, weekdays, actions} (не больше
    MAX_ENTRIES) или прежний вид — один объект (становится одной записью; {} и mode off — вручную). Записи с mode
    off пропускаются. Ошибка — ValidationFailed с полем schedule.<номер записи с 0>.<поле> (у одного объекта —
    schedule.<поле>)."""
    single = not isinstance(schedule, list)
    raw = [schedule or {}] if single else list(schedule)
    if any(not isinstance(e, dict) for e in raw):
        raise ValidationFailed("Расписание — список записей {mode, minutes, time, weekdays, actions}",
                               fields={"schedule": "Нужен список записей"})
    if all((e.get("mode") or "off") == "off" for e in raw):
        return []
    schedulable = [a.key for a in cls.actions if a.schedulable]
    if not schedulable:
        raise ValidationFailed(f"У подключения «{cls.title}» нет действий по расписанию",
                               fields={"schedule": "Нет действий по расписанию"})
    out = [entry for n, e in enumerate(raw)
           if (entry := _normalize_entry(cls, e, schedulable, "schedule" if single else f"schedule.{n}"))]
    if len(out) > MAX_ENTRIES:
        raise ValidationFailed(f"Не больше {MAX_ENTRIES} записей расписания у подключения",
                               fields={"schedule": f"Не больше {MAX_ENTRIES}"})
    return out


def next_run(schedule: dict | None, after: datetime) -> datetime | None:
    """Следующий запуск записи расписания после after (UTC без tzinfo); None — записи нет."""
    schedule = schedule or {}
    mode = schedule.get("mode")
    if mode == "interval":
        return after + timedelta(minutes=int(schedule["minutes"]))
    if mode != "daily":
        return None
    zone = ZoneInfo(settings.timezone)
    local = after.replace(tzinfo=UTC).astimezone(zone)
    hour, minute = (int(x) for x in schedule["time"].split(":"))
    weekdays = set(schedule.get("weekdays") or range(1, 8))
    for days in range(0, 8):
        day = (local + timedelta(days=days)).date()
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)
        if candidate > local and candidate.isoweekday() in weekdays:
            return candidate.astimezone(UTC).replace(tzinfo=None)
    return None  # pragma: no cover - за неделю день находится всегда


def entry_label(entry: dict | None) -> str:
    """Подпись записи: «Каждые 60 мин», «В 06:30 (пн, пт)», «В 06:30 ежедневно»."""
    entry = entry or {}
    if entry.get("mode") == "interval":
        return f"Каждые {entry['minutes']} мин"
    if entry.get("mode") == "daily":
        days = entry.get("weekdays") or []
        return f"В {entry['time']}" + (f" ({', '.join(WEEKDAY_NAMES[d] for d in days)})" if days else " ежедневно")
    return "Вручную"


def schedule_label(schedule: object, cls: type[Connector] | None = None) -> str:
    """Подпись расписания: «Вручную»; одна запись — её подпись; несколько — через «;» с действиями
    («Каждые 30 мин — Забрать данные из задач; В 06:00 ежедневно — Синхронизировать структуру»)."""
    entries = entries_of(schedule)
    if not entries:
        return "Вручную"
    if len(entries) == 1:
        return entry_label(entries[0])

    def what(entry: dict) -> str:
        labels = {a.key: a.label for a in cls.actions} if cls is not None else {}
        names = [labels.get(a, a) for a in entry.get("actions") or []]
        return entry_label(entry) + (f" — {', '.join(names)}" if names else "")

    return "; ".join(what(e) for e in entries)


def _stamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def entry_times(schedule: object, next_runs: object, next_run_at: datetime | None) -> list[datetime | None]:
    """Следующий запуск каждой записи. Сохранённые до 0.4.0 подключения (одна запись, без next_runs) и
    рассогласованные данные — по next_run_at подключения."""
    entries = entries_of(schedule)
    stored = next_runs if isinstance(next_runs, list) else []
    if len(stored) != len(entries):
        return [next_run_at] * len(entries)
    return [_parse(v) for v in stored]


def _set_times(row: Integration, times: list[datetime | None]) -> None:
    row.next_runs = [_stamp(t) for t in times]
    known = [t for t in times if t is not None]
    row.next_run_at = min(known) if known else None


def reschedule(row: Integration, now: datetime | None = None) -> None:
    """Следующий запуск каждой записи и ближайший (next_run_at) — после изменения расписания или включения;
    выключенное подключение по расписанию не запускается."""
    now = now or utcnow()
    entries = entries_of(row.schedule)
    _set_times(row, [next_run(e, now) for e in entries] if row.enabled else [None] * len(entries))


def schedule_out(row: Integration) -> list[dict]:
    """Записи расписания для API: определение, подпись и следующий запуск записи (у выключенного — нет)."""
    times = entry_times(row.schedule, row.next_runs, row.next_run_at)
    return [{**entry, "label": entry_label(entry), "next_run_at": time if row.enabled else None}
            for entry, time in zip(entries_of(row.schedule), times, strict=True)]


def _claim(db: Session, integration_id: int, now: datetime, new_next: datetime | None,
           next_runs: list[str | None] | None = None, seen: datetime | None = None) -> bool:
    """Занять запуск подключения одним UPDATE: срок настал (next_run_at <= now) и, если передано seen, ближайший
    запуск — тот же, что прочитан (расписание не меняли между чтением и занятием)."""
    conditions = [Integration.id == integration_id, Integration.enabled.is_(True), Integration.next_run_at <= now]
    if seen is not None:
        conditions.append(Integration.next_run_at == seen)
    values: dict = {"next_run_at": new_next}
    if next_runs is not None:
        values["next_runs"] = next_runs
    stmt = update(Integration).where(*conditions).values(**values).execution_options(synchronize_session=False)
    if db.get_bind().dialect.update_returning:
        claimed = db.execute(stmt.returning(Integration.id)).scalar() is not None
    else:  # pragma: no cover - SQLite до 3.35
        claimed = db.execute(stmt).rowcount == 1
    db.commit()
    return claimed


def claim_due(now: datetime | None = None, db: Session | None = None) -> list[tuple[int, list[str]]]:
    """Подключения, у которых настал срок хотя бы одной записи расписания и которые заняты этим процессом:
    [(id, действия записей, чей срок настал)]. Занятие переносит эти записи на следующий раз одним UPDATE."""
    now = now or utcnow()
    own = db is None
    db = db or core_db.SessionLocal()
    try:
        due = db.execute(select(Integration.id, Integration.schedule, Integration.next_runs, Integration.next_run_at)
                         .where(Integration.enabled.is_(True), Integration.next_run_at.is_not(None),
                                Integration.next_run_at <= now).order_by(Integration.next_run_at)).all()
        db.commit()
        claimed = []
        for integration_id, schedule, stored, seen in due:
            entries = entries_of(schedule)
            times = entry_times(schedule, stored, seen)
            ready = [n for n, t in enumerate(times) if t is None or t <= now]
            new = [next_run(e, now) if n in ready else times[n] for n, e in enumerate(entries)]
            known = [t for t in new if t is not None]
            if _claim(db, integration_id, now, min(known) if known else None, [_stamp(t) for t in new], seen):
                claimed.append((integration_id, list(dict.fromkeys(
                    a for n in ready if times[n] is not None for a in entries[n].get("actions") or []))))
        return claimed
    finally:
        if own:
            db.close()


# ---------------------------------------------------------------- идущий запуск

def running_stale(since: datetime | None, now: datetime | None = None) -> bool:
    """Запуск идёт дольше RUNNING_TIMEOUT — процесс остановился посреди него: запуск прерван."""
    return since is not None and since < (now or utcnow()) - RUNNING_TIMEOUT


def is_running(row: Integration, now: datetime | None = None) -> bool:
    """Подключение выполняет запуск (не прерванный): новый запуск не начнётся, удалить нельзя."""
    return row.running_since is not None and not running_stale(row.running_since, now)


def begin_running(db: Session, integration_id: int, now: datetime) -> bool:
    """Занять подключение для запуска: свободно или идущий запуск прерван (старше RUNNING_TIMEOUT). Записи журнала
    этого подключения, оставшиеся «выполняется», после занятия — прерванные."""
    result = db.execute(update(Integration).where(
        Integration.id == integration_id,
        or_(Integration.running_since.is_(None), Integration.running_since < now - RUNNING_TIMEOUT))
        .values(running_since=now).execution_options(synchronize_session=False))
    if result.rowcount == 1:
        _interrupt(db, IntegrationRun.integration_id == integration_id)
    db.commit()
    return result.rowcount == 1


def _interrupt(db: Session, *conditions) -> int:
    return db.execute(update(IntegrationRun).where(IntegrationRun.status == "running", *conditions)
                      .values(status="interrupted", message=INTERRUPTED)
                      .execution_options(synchronize_session=False)).rowcount


def reclaim_stale(now: datetime | None = None, db: Session | None = None) -> int:
    """Прерванные запуски (старше RUNNING_TIMEOUT): подключение освобождается, запись журнала — «Запуск прерван».
    Вызывает планировщик на каждом такте; то же условие, что у begin_running и у API (running_stale)."""
    now = now or utcnow()
    own = db is None
    db = db or core_db.SessionLocal()
    try:
        border = now - RUNNING_TIMEOUT
        db.execute(update(Integration).where(Integration.running_since < border).values(running_since=None)
                   .execution_options(synchronize_session=False))
        count = _interrupt(db, IntegrationRun.started_at < border)
        db.commit()
        return count
    finally:
        if own:
            db.close()


def current_error(row: Integration) -> str:
    """Последняя ошибка, если она новее последнего успеха; ошибка до успешного запуска или проверки — только в
    журнале запусков."""
    if row.last_error_at and (row.last_ok_at is None or row.last_error_at > row.last_ok_at):
        return row.last_error or ""
    return ""


# ---------------------------------------------------------------- проверка

def check(row: Integration, *, detailed: bool = True, config: dict | None = None,
          secrets: dict | None = None) -> CheckResult:
    connector = None
    try:
        connector = connector_for(row, detailed=detailed, config=config, secrets=secrets)
        result = connector.check()
    except IntegrationError as exc:
        result = CheckResult(False, exc.message(detailed), {"code": exc.code})
    except AppError as exc:
        result = CheckResult(False, exc.detail, {"code": exc.code})
    except Exception as exc:
        _log_failure("check", row, exc, _secrets_of(connector, secrets))
        return CheckResult(False, INTERNAL_ERROR, {"code": "internal_error"})
    if not isinstance(result, CheckResult):  # pragma: no cover - ошибка автора коннектора
        return CheckResult(False, INTERNAL_ERROR, {"code": "internal_error"})
    return clean_check(result, _secrets_of(connector, secrets))


# ---------------------------------------------------------------- запуск

def run_action(integration_id: int, action: str, *, trigger: str = "manual", user: User | None = None) -> dict:
    """Выполнить действие: запись в журнале запусков, состояние, здоровье. Возвращает запуск (run_out)."""
    from ..services import audit
    from ..services.inbox import source_actor

    with core_db.SessionLocal() as db:
        row = db.get(Integration, integration_id)
        if row is None:
            raise NotFound("Подключение не найдено")
        cls = base.get(row.kind)
        cls.action(action)
        now = utcnow()
        if not begin_running(db, row.id, now):
            raise Conflict("Подключение уже выполняет запуск — дождитесь его окончания", code="run_in_progress")
        db.refresh(row)
        run = IntegrationRun(integration_id=row.id, action=action, trigger=trigger, status="running", started_at=now,
                             summary={}, message="", error="", user_id=user.id if user else None,
                             username=user.username if user else "system")
        db.add(run)
        db.commit()
        result, state = _execute(row, action, trigger, user, run.id)
        row = db.get(Integration, integration_id)
        finished = utcnow()
        run.status, run.finished_at = result.status, finished
        run.summary, run.message, run.error = result.summary(), result.message[:4000], result.error[:4000]
        if row is not None:
            row.state = jsonable_encoder(state)
            row.last_run_at = finished
            record_health(row, ok=result.status != "error", error=result.error or result.message, now=finished)
            row.running_since = None
            if user is not None or trigger == "cli":
                actor = user or source_actor("Командная строка")
                audit.record(db, actor, entity_type="integration", entity_id=row.id, action="run",
                             summary=f"Запуск «{row.name}»: {cls.action(action).label} — {result.message[:200]}",
                             after={"run_id": run.id, "action": action, "status": result.status,
                                    "trigger": trigger})
        db.commit()
        prune(db, integration_id)
        db.commit()
        return run_out(run)


def _execute(row: Integration, action: str, trigger: str, user: User | None, run_id: int) -> tuple[RunResult, dict]:
    """Действие коннектора в своей сессии. Итог — с вычищенными секретами (сообщение, ошибка, подробности)."""
    work = core_db.SessionLocal()
    state = dict(row.state or {})
    connector = None
    try:
        integration = work.get(Integration, row.id)
        connector = connector_for(integration, detailed=True)
        ctx = RunContext(db=work, integration=integration, trigger=trigger, user=user, run_id=run_id, detailed=True,
                         state=state)
        result = connector.run(action, ctx)
        if not isinstance(result, RunResult):  # pragma: no cover - ошибка автора коннектора
            result = RunResult.ok()
        work.commit()
        if ctx.inbox.added:
            result.items = list(dict.fromkeys([*result.items, *ctx.inbox.added]))
        return clean_run(result, _secrets_of(connector)), ctx.state
    except IntegrationError as exc:
        work.rollback()
        return clean_run(RunResult.failed(exc.message(True), counters={}), _secrets_of(connector)), state
    except AppError as exc:
        work.rollback()
        return clean_run(RunResult.failed(exc.detail), _secrets_of(connector)), state
    except Exception as exc:
        work.rollback()
        _log_failure(f"action {action}", row, exc, _secrets_of(connector))
        return RunResult.failed(INTERNAL_ERROR), state
    finally:
        work.close()


def run_due(now: datetime | None = None) -> list[dict]:
    """Запуски по расписанию, чей срок настал (вызывает планировщик на каждом такте)."""
    runs = []
    for integration_id, actions in claim_due(now):
        for action in actions:
            try:
                runs.append(run_action(integration_id, action, trigger="schedule"))
            except Conflict:
                log.info("integration %s: запуск %s пропущен — предыдущий ещё идёт", integration_id, action)
            except AppError as exc:
                log.warning("integration %s: запуск %s не выполнен: %s", integration_id, action, exc.detail)
    return runs


def prune(db: Session, integration_id: int) -> int:
    keep = settings.integration_runs_keep
    old = list(db.scalars(select(IntegrationRun.id).where(IntegrationRun.integration_id == integration_id)
                          .order_by(IntegrationRun.started_at.desc(), IntegrationRun.id.desc()).offset(keep)))
    if old:
        db.execute(delete(IntegrationRun).where(IntegrationRun.id.in_(old)))
    return len(old)


def run_out(run: IntegrationRun, now: datetime | None = None) -> dict:
    """Запись журнала для API. «Выполняется» дольше RUNNING_TIMEOUT — «Запуск прерван» (interrupted), как её
    отметят begin_running и планировщик."""
    from ..services.registry import RUN_STATUS_LABELS, RUN_TRIGGER_LABELS

    status, message = run.status, run.message
    if status == "running" and running_stale(run.started_at, now):
        status, message = "interrupted", INTERRUPTED
    return {"id": run.id, "integration_id": run.integration_id, "action": run.action, "trigger": run.trigger,
            "trigger_label": RUN_TRIGGER_LABELS.get(run.trigger, run.trigger), "status": status,
            "status_label": RUN_STATUS_LABELS.get(status, status), "started_at": run.started_at,
            "finished_at": run.finished_at, "summary": run.summary or {}, "message": message,
            "error": run.error, "username": run.username}
