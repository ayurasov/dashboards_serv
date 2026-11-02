"""Папка «Входящие» (INBOX_DIR) как подключение: проверка папки и разбор по кнопке.

Самый простой коннектор — пример для авторов остальных: без адреса и секретов (url_field = None),
одно действие. Папку опрашивает и планировщик (python -m app.cli worker) на каждом такте — подключение
нужно, чтобы видеть её состояние, запускать разбор вручную и вести журнал запусков.
"""
from __future__ import annotations

from ...services import inbox_folder
from ..base import Action, CheckResult, Connector, RunContext, RunResult, register


@register
class FolderConnector(Connector):
    kind = "folder"
    title = "Папка «Входящие»"
    description = ("Файлы из папки INBOX_DIR на сервере: подпапки по наборам или корень с распознаванием; "
                   "обработанные переносятся в processed/ГГГГ-ММ/ или rejected/ с отчётом *.result.json")
    url_field = None
    singleton = True
    order = 80
    counter_labels = {"taken": "взято файлов", "applied": "применено", "pending": "ждут подтверждения",
                      "duplicates": "повторов", "errors": "ошибок", "waiting": "дописываются",
                      "skipped": "пропущено"}
    actions = (Action("scan", "Разобрать папку",
                      "Забрать файлы, которые не меняются дольше INBOX_SETTLE_SECONDS, во входящие"),)

    def check(self) -> CheckResult:
        state = inbox_folder.status()
        if not state["enabled"]:
            return CheckResult(False, "Папка не настроена: задайте INBOX_DIR (в Docker — том /data/inbox)", state)
        if not state["exists"]:
            return CheckResult(False, f"Папка {state['path']} не найдена", state)
        if not state["writable"]:
            return CheckResult(False, f"Нет прав на запись в {state['path']}: обработанные файлы не перенести", state)
        return CheckResult(True, f"Папка {state['path']} доступна; файлов ждут разбора: {state['waiting_files']}",
                           state)

    def run(self, action: str, ctx: RunContext) -> RunResult:
        self.action(action)
        result = inbox_folder.scan()
        counters = {k: v for k, v in result.as_dict().items() if isinstance(v, int) and not isinstance(v, bool)}
        if not result.enabled:
            return RunResult.failed("Папка не настроена: задайте INBOX_DIR")
        message = (f"Взято файлов: {result.taken}, применено: {result.applied}, ожидают: {result.pending}, "
                   f"повторов: {result.duplicates}, ошибок: {result.errors}")
        details = {"notes": result.notes} if result.notes else {}
        if result.errors:
            return RunResult.partial(message, "; ".join(result.notes[:5]), counters=counters, items=result.items,
                                     details=details)
        return RunResult.ok(message, counters=counters, items=result.items, details=details)
