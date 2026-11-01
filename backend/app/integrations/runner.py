"""Запуск подключений: экземпляр коннектора с секретами, проверка, действие, журнал запусков, расписание.

Расписание (integrations.schedule):
    {}                                                    — только вручную
    {"mode": "interval", "minutes": 60, "actions": ["sync"]}            — каждые N минут (5…10080)
    {"mode": "daily", "time": "06:30", "weekdays": [1, 5], "actions": […]} — в ЧЧ:ММ по TIMEZONE;
        weekdays — дни недели ISO (1 — понедельник), пусто — каждый день
actions — действия коннектора с schedulable=True; по умолчанию — первое такое.

Занятие запуска атомарно (claim_due): UPDATE integrations SET next_run_at = <следующий> WHERE id = …
AND enabled AND next_run_at <= now — на PostgreSQL второй процесс ждёт блокировку строки и после неё
условие уже не выполняется, на SQLite записи и так идут по очереди. Поэтому несколько планировщиков не
выполнят один запуск дважды. Ручной запуск во время идущего не начнётся: running_since занимается тем же
приёмом (begin_running).
"""
from __future__ import annotations

import logging
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
from .http import IntegrationError, record_health

log = logging.getLogger("app.integrations")

PURPOSE = "integration"
RUNNING_TIMEOUT = timedelta(hours=2)
MIN_INTERVAL, MAX_INTERVAL = 5, 7 * 24 * 60
INTERNAL_ERROR = "Внутренняя ошибка коннектора — подробности в журнале сервера"


def owner(integration_id: int | None) -> str:
    return f"integration:{integration_id}"


def url_of(cls: type[Connector], config: dict) -> str:
    return (config or {}).get(cls.url_field) or "" if cls.url_field else ""


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

def normalize_schedule(cls: type[Connector], schedule: dict | None) -> dict:
    schedule = dict(schedule or {})
    mode = schedule.get("mode") or "off"
    if mode == "off":
        return {}
    schedulable = [a.key for a in cls.actions if a.schedulable]
    if not schedulable:
        raise ValidationFailed(f"У подключения «{cls.title}» нет действий по расписанию",
                               fields={"schedule": "Нет действий по расписанию"})
    actions = schedule.get("actions") or schedulable[:1]
    if not isinstance(actions, list) or any(a not in schedulable for a in actions):
        raise ValidationFailed(f"По расписанию выполняются: {', '.join(schedulable)}",
                               fields={"schedule.actions": "Недопустимое действие"})
    out: dict = {"mode": mode, "actions": list(dict.fromkeys(actions))}
    if mode == "interval":
        try:
            minutes = int(schedule.get("minutes"))
        except (TypeError, ValueError):
            raise ValidationFailed("Интервал — целое число минут", fields={"schedule.minutes": "Нужно число"}) from None
        if not MIN_INTERVAL <= minutes <= MAX_INTERVAL:
            raise ValidationFailed(f"Интервал — от {MIN_INTERVAL} минут до недели",
                                   fields={"schedule.minutes": "Вне допустимого"})
        out["minutes"] = minutes
    elif mode == "daily":
        time_text = str(schedule.get("time") or "")
        if not base.TIME_PATTERN.match(time_text):
            raise ValidationFailed("Время запуска — ЧЧ:ММ", fields={"schedule.time": "Нужно ЧЧ:ММ"})
        weekdays = schedule.get("weekdays") or []
        if not isinstance(weekdays, list) or any(not isinstance(d, int) or not 1 <= d <= 7 for d in weekdays):
            raise ValidationFailed("Дни недели — числа 1…7 (1 — понедельник)", fields={"schedule.weekdays": "1…7"})
        out.update(time=time_text, weekdays=sorted(set(weekdays)))
    else:
        raise ValidationFailed("Расписание: off, interval или daily", fields={"schedule.mode": "Недопустимо"})
    return out


def next_run(schedule: dict | None, after: datetime) -> datetime | None:
    """Следующий запуск после after (UTC без tzinfo); None — расписания нет."""
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


def schedule_label(schedule: dict | None) -> str:
    schedule = schedule or {}
    if schedule.get("mode") == "interval":
        return f"Каждые {schedule['minutes']} мин"
    if schedule.get("mode") == "daily":
        names = {1: "пн", 2: "вт", 3: "ср", 4: "чт", 5: "пт", 6: "сб", 7: "вс"}
        days = schedule.get("weekdays") or []
        return f"В {schedule['time']}" + (f" ({', '.join(names[d] for d in days)})" if days else " ежедневно")
    return "Вручную"


def reschedule(row: Integration, now: datetime | None = None) -> None:
    row.next_run_at = next_run(row.schedule, now or utcnow()) if row.enabled else None


def _claim(db: Session, integration_id: int, now: datetime, new_next: datetime | None) -> bool:
    stmt = (update(Integration)
            .where(Integration.id == integration_id, Integration.enabled.is_(True), Integration.next_run_at <= now)
            .values(next_run_at=new_next).execution_options(synchronize_session=False))
    if db.get_bind().dialect.update_returning:
        claimed = db.execute(stmt.returning(Integration.id)).scalar() is not None
    else:  # pragma: no cover - SQLite до 3.35
        claimed = db.execute(stmt).rowcount == 1
    db.commit()
    return claimed


def claim_due(now: datetime | None = None, db: Session | None = None) -> list[tuple[int, list[str]]]:
    """Подключения, чей запуск настал и занят этим процессом: [(id, действия)]."""
    now = now or utcnow()
    own = db is None
    db = db or core_db.SessionLocal()
    try:
        due = db.execute(select(Integration.id, Integration.schedule)
                         .where(Integration.enabled.is_(True), Integration.next_run_at.is_not(None),
                                Integration.next_run_at <= now).order_by(Integration.next_run_at)).all()
        db.commit()
        claimed = []
        for integration_id, schedule in due:
            if _claim(db, integration_id, now, next_run(schedule, now)):
                claimed.append((integration_id, list((schedule or {}).get("actions") or [])))
        return claimed
    finally:
        if own:
            db.close()


def begin_running(db: Session, integration_id: int, now: datetime) -> bool:
    result = db.execute(update(Integration).where(
        Integration.id == integration_id,
        or_(Integration.running_since.is_(None), Integration.running_since < now - RUNNING_TIMEOUT))
        .values(running_since=now).execution_options(synchronize_session=False))
    db.commit()
    return result.rowcount == 1


# ---------------------------------------------------------------- проверка

def check(row: Integration, *, detailed: bool = True, config: dict | None = None,
          secrets: dict | None = None) -> CheckResult:
    try:
        connector = connector_for(row, detailed=detailed, config=config, secrets=secrets)
        result = connector.check()
    except IntegrationError as exc:
        return CheckResult(False, exc.message(detailed), {"code": exc.code})
    except AppError as exc:
        return CheckResult(False, exc.detail, {"code": exc.code})
    except Exception:
        log.exception("integration %s (%s): check failed", row.id, row.kind)
        return CheckResult(False, INTERNAL_ERROR, {"code": "internal_error"})
    if not isinstance(result, CheckResult):  # pragma: no cover - ошибка автора коннектора
        return CheckResult(False, INTERNAL_ERROR, {"code": "internal_error"})
    return result


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
    work = core_db.SessionLocal()
    state = dict(row.state or {})
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
        return result, ctx.state
    except IntegrationError as exc:
        work.rollback()
        return RunResult.failed(exc.message(True), counters={}), state
    except AppError as exc:
        work.rollback()
        return RunResult.failed(exc.detail), state
    except Exception:
        work.rollback()
        log.exception("integration %s (%s): action %s failed", row.id, row.kind, action)
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


def run_out(run: IntegrationRun) -> dict:
    from ..services.registry import RUN_STATUS_LABELS, RUN_TRIGGER_LABELS

    return {"id": run.id, "integration_id": run.integration_id, "action": run.action, "trigger": run.trigger,
            "trigger_label": RUN_TRIGGER_LABELS.get(run.trigger, run.trigger), "status": run.status,
            "status_label": RUN_STATUS_LABELS.get(run.status, run.status), "started_at": run.started_at,
            "finished_at": run.finished_at, "summary": run.summary or {}, "message": run.message,
            "error": run.error, "username": run.username}
