"""Папка «Входящие» на сервере (INBOX_DIR, в Docker — том /data/inbox), ADR-0011.

Устройство папки:
    <INBOX_DIR>/                 корень: набор распознаётся по имени и содержимому файла
    <INBOX_DIR>/<набор>/         hr-months, hr-events, tp-weekly, naumen, partnerships, indicators,
                                 structure, employees — набор задан подпапкой
    <INBOX_DIR>/processed/ГГГГ-ММ/  принятые файлы (ожидают подтверждения или применены)
    <INBOX_DIR>/rejected/        не принятые: ошибка, повтор, слишком большой
    <INBOX_DIR>/.work/           файлы в обработке (служебная)
Рядом с каждым перенесённым файлом — отчёт «<имя>.result.json» (номер элемента, статус, сводка, ошибки).

Правила:
- файл берётся, когда не меняется дольше INBOX_SETTLE_SECONDS (дописывается — не трогаем); если он
  изменился, пока его читали, он возвращается на место до следующего опроса;
- скрытые и временные файлы не берутся: «.*», «~$*», «*.part», «*.tmp», «*.crdownload», «*.partial»,
  «*.swp», «*~», «*.result.json», Thumbs.db, desktop.ini;
- символьные ссылки на файлы не открываются никогда; подпапка-ссылка читается, только если ведёт
  внутрь INBOX_DIR; файл открывается с O_NOFOLLOW;
- файл «занимается» атомарным переносом в .work/ — два планировщика не возьмут один файл;
- каждый файл — своя транзакция: элемент входящих фиксируется, затем файл переносится.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from fastapi.encoders import jsonable_encoder

from ..core import db as core_db
from ..core.config import settings
from ..core.db import utcnow
from ..models import AppSetting, InboxItem
from . import inbox
from . import inbox_datasets as datasets
from .registry import INBOX_STATUS_LABELS

log = logging.getLogger("app.inbox.folder")

PROCESSED, REJECTED, WORK = "processed", "rejected", ".work"
SPECIAL = {PROCESSED, REJECTED, WORK}
IGNORED_SUFFIXES = (".part", ".tmp", ".crdownload", ".partial", ".swp", "~", ".result.json")
IGNORED_NAMES = {"thumbs.db", "desktop.ini"}
ACCEPTED = ("received", "recognized", "pending", "applied")
STALE_WORK_SECONDS = 3600
STATUS_SETTING = "inbox_folder_status"
LABEL = "Входящие · папка"


@dataclass
class ScanResult:
    enabled: bool = True
    taken: int = 0
    applied: int = 0
    pending: int = 0
    duplicates: int = 0
    errors: int = 0
    waiting: int = 0
    skipped: int = 0
    items: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"enabled": self.enabled, "taken": self.taken, "applied": self.applied, "pending": self.pending,
                "duplicates": self.duplicates, "errors": self.errors, "waiting": self.waiting,
                "skipped": self.skipped, "items": self.items, "notes": self.notes[:50]}


def ignored(name: str) -> bool:
    low = name.lower()
    return name.startswith((".", "~$")) or low.endswith(IGNORED_SUFFIXES) or low in IGNORED_NAMES


def _inside(path: str, root: str) -> bool:
    return os.path.commonpath([os.path.realpath(path), root]) == root


def ensure_layout(root: Path) -> None:
    for name in (*(d.key for d in datasets.all_datasets()), PROCESSED, REJECTED, WORK):
        (root / name).mkdir(parents=True, exist_ok=True)


def status() -> dict:
    root = settings.inbox_path
    out = {"enabled": root is not None, "path": str(root) if root else "", "exists": False, "writable": False,
           "settle_seconds": settings.inbox_settle_seconds, "max_mb": settings.inbox_max_mb,
           "retention_days": settings.inbox_retention_days, "waiting_files": 0,
           "folders": [{"folder": d.key, "dataset": d.key, "label": d.label, "patterns": list(d.patterns)}
                       for d in datasets.all_datasets()]}
    if root is not None and root.is_dir():
        out["exists"] = True
        out["writable"] = os.access(root, os.W_OK | os.X_OK)
        out["waiting_files"] = sum(1 for _ in _candidates(root, os.path.realpath(root), ScanResult()))
    return out


def _candidates(root: Path, root_real: str, result: ScanResult):
    """(путь, набор или None) — файлы корня и подпапок наборов."""
    folders: list[tuple[Path, str | None]] = [(root, None)]
    for entry in os.scandir(root):
        if not entry.is_dir(follow_symlinks=True) or entry.name in SPECIAL or entry.name.startswith("."):
            continue
        if datasets.get(entry.name) is None:
            continue
        if entry.is_symlink() and not _inside(entry.path, root_real):
            result.skipped += 1
            result.notes.append(f"{entry.name}/: ссылка ведёт за пределы папки «Входящие» — пропущена")
            continue
        folders.append((Path(entry.path), entry.name))
    for folder, dataset in folders:
        for entry in os.scandir(folder):
            if ignored(entry.name):
                continue
            if entry.is_symlink():
                result.skipped += 1
                where = "за пределы папки «Входящие»" if not _inside(entry.path, root_real) else "на другой файл"
                result.notes.append(f"{_rel(Path(entry.path), root)}: ссылка {where} — не открывается")
                continue
            if entry.is_file(follow_symlinks=False):
                yield Path(entry.path), dataset


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _read(path: Path) -> tuple[bytes, os.stat_result]:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as fh:
        data = fh.read(settings.inbox_max_mb * 1024 * 1024 + 1)
        return data, os.fstat(fh.fileno())


def _unique(folder: Path, name: str, item_id: int | None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    if not target.exists():
        return target
    stem, dot, suffix = name.rpartition(".")
    stem, suffix = (stem, "." + suffix) if dot else (name, "")
    for n in range(1, 1000):
        candidate = folder / f"{stem} ({item_id or 'x'}{'-' + str(n) if n > 1 else ''}){suffix}"
        if not candidate.exists():
            return candidate
    return folder / f"{secrets.token_hex(4)}-{name}"  # pragma: no cover


def report(item: InboxItem) -> dict:
    """Отчёт *.result.json о судьбе файла."""
    dataset = datasets.get(item.dataset)
    return jsonable_encoder({
        "item_id": item.id, "status": item.status, "status_label": INBOX_STATUS_LABELS[item.status],
        "dataset": item.dataset, "dataset_label": dataset.label if dataset else None, "filename": item.filename,
        "source_ref": item.source_ref, "sha256": item.sha256, "size": item.size, "received_at": item.received_at,
        "processed_at": item.processed_at, "message": item.message, "error": item.error,
        "summary": item.summary, "errors": inbox.plan_errors(item.plan),
        "duplicate_of": item.duplicate_of_id,
    })


def _finish(root: Path, work: Path, name: str, item: InboxItem | None, payload: dict) -> Path | None:
    accepted = item is not None and item.status in ACCEPTED
    folder = root / PROCESSED / utcnow().strftime("%Y-%m") if accepted else root / REJECTED
    target = _unique(folder, name, item.id if item else None)
    try:
        os.replace(work, target)
        Path(str(target) + ".result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                                      encoding="utf-8")
    except OSError as exc:
        log.error("inbox folder: не удалось перенести %s в %s: %s", work, target, exc)
        return None
    return target


def _claim(path: Path, root: Path, dataset: str | None) -> Path | None:
    work = root / WORK / f"{secrets.token_hex(6)}__{dataset or '-'}__{path.name}"
    try:
        os.replace(path, work)
    except FileNotFoundError:
        return None  # взял другой процесс
    return work


def _release(work: Path, root: Path) -> None:
    """Вернуть файл из .work на прежнее место (изменился при чтении или процесс прервался)."""
    _token, dataset, name = work.name.split("__", 2)
    folder = root if dataset == "-" else root / dataset
    try:
        os.replace(work, _unique(folder, name, None) if (folder / name).exists() else folder / name)
    except OSError as exc:  # pragma: no cover - диск недоступен
        log.error("inbox folder: не удалось вернуть %s: %s", work, exc)


def _recover(root: Path, now: float) -> None:
    for entry in os.scandir(root / WORK):
        if entry.is_file(follow_symlinks=False) and "__" in entry.name and \
                now - entry.stat(follow_symlinks=False).st_mtime > STALE_WORK_SECONDS:
            log.warning("inbox folder: возвращаю незавершённый файл %s", entry.name)
            _release(Path(entry.path), root)


def scan(*, now: float | None = None) -> ScanResult:
    """Один проход по папке. now — время для проверки «файл не меняется» (для тестов)."""
    root = settings.inbox_path
    result = ScanResult()
    if root is None:
        result.enabled = False
        return result
    if not root.is_dir():
        result.errors += 1
        result.notes.append(f"Папка «Входящие» {root} не найдена")
        log.error("inbox folder: %s не найдена", root)
        return result
    now = time.time() if now is None else now
    root_real = os.path.realpath(root)
    ensure_layout(root)
    _recover(root, now)
    for path, dataset in list(_candidates(root, root_real, result)):
        try:
            _scan_file(root, path, dataset, now, result)
        except Exception:  # noqa: BLE001 — один файл не должен останавливать опрос
            log.exception("inbox folder: ошибка обработки %s", path)
            result.errors += 1
    if result.taken or result.skipped or result.errors:
        _save_status(result)
    return result


def _scan_file(root: Path, path: Path, dataset: str | None, now: float, result: ScanResult) -> None:
    st = os.stat(path, follow_symlinks=False)
    if now - st.st_mtime < settings.inbox_settle_seconds:
        result.waiting += 1
        return
    ref = _rel(path, root)
    name = path.name
    work = _claim(path, root, dataset)
    if work is None:
        return
    if st.st_size > settings.inbox_max_mb * 1024 * 1024:
        _too_large(root, work, name, ref, dataset, st.st_size, result)
        return
    content, after = _read(work)
    if (after.st_size, after.st_mtime_ns) != (st.st_size, st.st_mtime_ns):
        _release(work, root)
        result.waiting += 1
        return
    result.taken += 1
    with core_db.SessionLocal() as db:
        try:
            item = inbox.add(db, content, name, source="folder", source_ref=ref, dataset=dataset, label=LABEL)
            db.commit()
        except Exception as exc:
            db.rollback()
            detail = getattr(exc, "detail", None)
            if detail is None:
                log.exception("inbox folder: файл %s не принят", ref)
            payload = {"item_id": None, "status": "error", "status_label": "Ошибка", "filename": name,
                       "source_ref": ref, "error": detail or inbox.INTERNAL_ERROR}
            _finish(root, work, name, None, payload)
            result.errors += 1
            return
        payload = report(item)
        result.items.append(item.id)
        counter = {"applied": "applied", "pending": "pending", "duplicate": "duplicates", "error": "errors",
                   "received": "pending", "recognized": "pending"}.get(item.status, "errors")
        setattr(result, counter, getattr(result, counter) + 1)
    _finish(root, work, name, item, payload)


def _too_large(root: Path, work: Path, name: str, ref: str, dataset: str | None, size: int,
               result: ScanResult) -> None:
    digest = hashlib.sha256()
    fd = os.open(work, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    result.taken += 1
    result.errors += 1
    with core_db.SessionLocal() as db:
        item = inbox.add_failed(db, name, size=size, sha256=digest.hexdigest(), source="folder", source_ref=ref,
                                dataset=dataset, error=f"Файл больше {settings.inbox_max_mb} МБ", label=LABEL)
        db.commit()
        payload = report(item)
        result.items.append(item.id)
    _finish(root, work, name, item, payload)


def _save_status(result: ScanResult) -> None:
    with core_db.SessionLocal() as db:
        row = db.get(AppSetting, STATUS_SETTING)
        value = {"last_scan_at": utcnow().isoformat(timespec="seconds"), "last_result": result.as_dict()}
        if row is None:
            db.add(AppSetting(key=STATUS_SETTING, value=value))
        else:
            row.value = value
        db.commit()


def cleanup(now: float | None = None) -> int:
    """Удаляет из processed/ и rejected/ файлы старше INBOX_RETENTION_DAYS. Возвращает число файлов."""
    root = settings.inbox_path
    if root is None or not root.is_dir():
        return 0
    border = (time.time() if now is None else now) - timedelta(days=settings.inbox_retention_days).total_seconds()
    removed = 0
    for folder in (root / PROCESSED, root / REJECTED):
        if not folder.is_dir():
            continue
        for dirpath, _dirs, files in os.walk(folder, followlinks=False):
            for name in files:
                path = os.path.join(dirpath, name)
                try:
                    if os.lstat(path).st_mtime < border:
                        os.unlink(path)
                        removed += 1
                except OSError:  # pragma: no cover
                    continue
            if dirpath != str(folder) and not os.listdir(dirpath):
                os.rmdir(dirpath)
    return removed
