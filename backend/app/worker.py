"""Планировщик (python -m app.cli worker, сервис worker в docker-compose), ADR-0011.

На каждом такте (WORKER_TICK_SECONDS, по умолчанию 30 с):
1. разбор папки «Входящие» (если задан INBOX_DIR) — app/services/inbox_folder.py;
2. запуски подключений по расписанию — занимаются атомарно в базе (app/integrations/runner.py),
   поэтому несколько планировщиков не выполнят один запуск дважды;
3. раз в час — срок хранения: исходные файлы обработанных элементов старше INBOX_RETENTION_DAYS
   удаляются из базы, старые файлы — из processed/ и rejected/ папки;
4. отметка «планировщик работает» (app_settings.worker_status) — её показывает экран «Входящие».

SIGTERM и SIGINT — мягкая остановка: текущий такт доделывается, новый не начинается. Схема базы
не обновляется планировщиком: миграции выполняет сервис app; планировщик ждёт актуальную схему.
"""
from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time

from . import __version__
from .core import db as core_db
from .core.config import settings
from .core.db import utcnow
from .models import AppSetting

log = logging.getLogger("app.worker")

CLEANUP_EVERY = 3600
STATUS_SETTING = "worker_status"


class Worker:
    def __init__(self, tick_seconds: int | None = None):
        self.tick_seconds = tick_seconds or settings.worker_tick_seconds
        self.stopping = threading.Event()
        self.last_cleanup: float | None = None
        self.ticks = 0

    # --- остановка
    def stop(self, *_args) -> None:
        if not self.stopping.is_set():
            log.info("Планировщик: получен сигнал остановки — доделываю текущий такт")
        self.stopping.set()

    def install_signals(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

    # --- такт
    def wait_for_schema(self, poll: float = 5.0) -> bool:
        """Ждать, пока сервис app применит миграции. False — остановлены раньше."""
        from .core.migrate import check_schema_is_current

        warned = False
        while not self.stopping.is_set():
            try:
                with core_db.engine.connect() as conn:
                    ok, current, head = check_schema_is_current(conn)
            except Exception as exc:  # noqa: BLE001 — база ещё не поднялась
                ok, current, head = False, None, str(exc.__class__.__name__)
            if ok:
                return True
            if not warned:
                log.warning("Планировщик ждёт актуальную схему базы (%s → %s): миграции выполняет сервис app",
                            current, head)
                warned = True
            self.stopping.wait(poll)
        return False

    def tick(self) -> dict:
        from .integrations import runner
        from .services import inbox, inbox_folder

        out: dict = {}
        if settings.inbox_path is not None:
            try:
                out["folder"] = inbox_folder.scan().as_dict()
            except Exception:  # noqa: BLE001 — такт не должен падать
                log.exception("Планировщик: ошибка разбора папки «Входящие»")
        if not self.stopping.is_set():
            try:
                out["runs"] = [r["id"] for r in runner.run_due()]
            except Exception:  # noqa: BLE001
                log.exception("Планировщик: ошибка запусков по расписанию")
        if not self.stopping.is_set() and (self.last_cleanup is None or
                                           time.monotonic() - self.last_cleanup >= CLEANUP_EVERY):
            self.last_cleanup = time.monotonic()
            try:
                with core_db.SessionLocal() as db:
                    purged = inbox.purge(db)
                    db.commit()
                out["cleanup"] = {"purged": purged, "files": inbox_folder.cleanup()}
            except Exception:  # noqa: BLE001
                log.exception("Планировщик: ошибка очистки по сроку хранения")
        self.ticks += 1
        self._heartbeat()
        return out

    def _heartbeat(self) -> None:
        try:
            with core_db.SessionLocal() as db:
                value = {"last_tick_at": utcnow().isoformat(timespec="seconds"), "host": socket.gethostname(),
                         "pid": os.getpid(), "version": __version__, "tick_seconds": self.tick_seconds,
                         "inbox_dir": bool(settings.inbox_path)}
                row = db.get(AppSetting, STATUS_SETTING)
                if row is None:
                    db.add(AppSetting(key=STATUS_SETTING, value=value))
                else:
                    row.value = value
                db.commit()
        except Exception:  # noqa: BLE001
            log.exception("Планировщик: не удалось записать отметку о работе")

    def run(self, *, once: bool = False) -> int:
        if not self.wait_for_schema():
            return 0
        log.info("Планировщик запущен: такт %s с, папка «Входящие»: %s", self.tick_seconds,
                 settings.inbox_path or "не задана")
        while not self.stopping.is_set():
            started = time.monotonic()
            self.tick()
            if once:
                break
            self.stopping.wait(max(0.0, self.tick_seconds - (time.monotonic() - started)))
        log.info("Планировщик остановлен")
        return 0
