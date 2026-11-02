"""Папка «Входящие»: подпапки и корень, время «не меняется», перенос в processed/ и rejected/ с отчётом,
скрытые и временные файлы, символьные ссылки, слишком большие файлы, два планировщика, срок хранения."""
from __future__ import annotations

import json
import os
import time

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import InboxItem, InboxRule
from app.services import inbox_folder
from tests.test_inbox import hr_events_file, partnerships_file, tp_file


@pytest.fixture()
def folder(tmp_path, monkeypatch, engine):
    root = tmp_path / "inbox"
    root.mkdir()
    monkeypatch.setattr(settings, "inbox_dir", str(root))
    monkeypatch.setattr(settings, "inbox_settle_seconds", 10)
    return root


def put(path, content: bytes, age: float = 60):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


def items(db):
    db.expire_all()
    return list(db.scalars(select(InboxItem).order_by(InboxItem.id)))


def test_disabled_without_inbox_dir(monkeypatch):
    monkeypatch.setattr(settings, "inbox_dir", "")
    assert inbox_folder.scan().enabled is False
    assert inbox_folder.status()["enabled"] is False


def test_layout_and_status(folder):
    status = inbox_folder.status()
    assert status["enabled"] and status["exists"] and status["writable"] and status["settle_seconds"] == 10
    # Распознавание в корне — по содержимому; имя по шаблону только добавляет очки (одного имени мало)
    assert status["detect"] == {"threshold": 50, "name_bonus": 20}
    assert status["detect"]["name_bonus"] < status["detect"]["threshold"]
    inbox_folder.scan()
    names = {p.name for p in folder.iterdir()}
    assert {"hr-months", "tp-weekly", "naumen", "processed", "rejected", ".work"} <= names


def test_subfolder_root_detection_and_moves(folder, db):
    put(folder / "tp-weekly" / "week.xlsx", tp_file())
    put(folder / "registry.xlsx", hr_events_file())
    result = inbox_folder.scan()
    assert (result.taken, result.pending, result.errors) == (2, 2, 0)
    rows = items(db)
    assert {r.dataset for r in rows} == {"tp-weekly", "hr-events"}
    assert {r.source_ref for r in rows} == {"tp-weekly/week.xlsx", "registry.xlsx"}
    assert all(r.source == "folder" and r.received_by == "Входящие · папка" for r in rows)
    month = next((folder / "processed").iterdir())
    moved = {p.name for p in month.iterdir()}
    assert moved == {"week.xlsx", "week.xlsx.result.json", "registry.xlsx", "registry.xlsx.result.json"}
    report = json.loads((month / "week.xlsx.result.json").read_text(encoding="utf-8"))
    assert report["status"] == "pending" and report["dataset"] == "tp-weekly" and report["item_id"]
    assert report["summary"]["create"] == 1 and "не включено" in report["message"]
    assert not (folder / "tp-weekly" / "week.xlsx").exists()
    assert inbox_folder.scan().taken == 0, "перенесённые файлы не берутся снова"


def test_auto_apply_rule_for_folder(folder, db):
    db.merge(InboxRule(source="folder", dataset="tp-weekly", auto_apply=True))
    db.commit()
    put(folder / "tp-weekly" / "week.xlsx", tp_file())
    result = inbox_folder.scan()
    assert result.applied == 1 and items(db)[0].status == "applied"


def test_settle_time(folder, db):
    path = put(folder / "tp-weekly" / "week.xlsx", tp_file(), age=2)
    result = inbox_folder.scan()
    assert result.waiting == 1 and result.taken == 0 and path.exists() and not items(db)
    assert inbox_folder.scan(now=time.time() + 30).taken == 1


def test_file_changed_while_reading_is_put_back(folder, db, monkeypatch):
    path = put(folder / "tp-weekly" / "week.xlsx", tp_file())
    real = inbox_folder._read

    def growing(work):
        with open(work, "ab") as fh:
            fh.write(b"more")
        return real(work)

    monkeypatch.setattr(inbox_folder, "_read", growing)
    result = inbox_folder.scan()
    assert result.waiting == 1 and result.taken == 0 and path.exists() and not items(db)


def test_errors_and_duplicates_go_to_rejected(folder, db):
    put(folder / "tp-weekly" / "broken.xlsx", b"not excel")
    put(folder / "first.xlsx", partnerships_file())
    inbox_folder.scan()
    put(folder / "again.xlsx", partnerships_file())
    inbox_folder.scan()
    rejected = {p.name for p in (folder / "rejected").iterdir()}
    assert {"broken.xlsx", "broken.xlsx.result.json", "again.xlsx", "again.xlsx.result.json"} <= rejected
    report = json.loads((folder / "rejected" / "again.xlsx.result.json").read_text(encoding="utf-8"))
    assert report["status"] == "duplicate" and report["duplicate_of"]
    broken = json.loads((folder / "rejected" / "broken.xlsx.result.json").read_text(encoding="utf-8"))
    assert broken["status"] == "error" and "Excel" in broken["error"]


def test_name_collisions_in_destination(folder, db):
    put(folder / "tp-weekly" / "w.xlsx", b"broken one")
    inbox_folder.scan()
    put(folder / "tp-weekly" / "w.xlsx", b"broken two")
    inbox_folder.scan()
    names = sorted(p.name for p in (folder / "rejected").iterdir() if not p.name.endswith(".json"))
    assert len(names) == 2 and "w.xlsx" in names


def test_hidden_and_temporary_files_are_ignored(folder, db):
    for name in (".hidden.xlsx", "~$lock.xlsx", "upload.part", "x.tmp", "d.crdownload", "Thumbs.db",
                 "old.xlsx.result.json", "backup~"):
        put(folder / name, b"data")
    assert inbox_folder.scan().taken == 0 and not items(db)


def test_symlinks_are_never_followed(folder, tmp_path, db):
    outside = tmp_path / "secret.xlsx"
    outside.write_bytes(tp_file())
    os.symlink(outside, folder / "link.xlsx")
    inside = put(folder / "real.xlsx", b"x")
    os.symlink(inside, folder / "tp-weekly-link.xlsx")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    put(elsewhere / "w.xlsx", tp_file())
    (folder / "tp-weekly").mkdir(exist_ok=True)
    os.rmdir(folder / "tp-weekly")
    os.symlink(elsewhere, folder / "tp-weekly")
    stamp = time.time() - 60
    os.utime(folder / "link.xlsx", (stamp, stamp), follow_symlinks=False)
    result = inbox_folder.scan()
    assert outside.exists() and (folder / "link.xlsx").is_symlink(), "ссылка не перенесена и не прочитана"
    assert (elsewhere / "w.xlsx").exists(), "подпапка-ссылка наружу не читается"
    assert result.skipped >= 3 and any("за пределы" in n for n in result.notes)
    assert [r.filename for r in items(db)] == ["real.xlsx"]


def test_symlinked_subfolder_inside_is_read(folder, db):
    real = folder / "data" / "tp"
    put(real / "w.xlsx", tp_file())
    os.symlink(real, folder / "tp-weekly")
    assert inbox_folder.scan().taken == 1 and items(db)[0].dataset == "tp-weekly"


def test_too_large_file_is_rejected_without_reading(folder, db, monkeypatch):
    monkeypatch.setattr(settings, "inbox_max_mb", 1)
    put(folder / "tp-weekly" / "huge.xlsx", b"x" * (1024 * 1024 + 5))
    result = inbox_folder.scan()
    assert result.errors == 1
    row = items(db)[0]
    assert row.status == "error" and not row.has_content and "1 МБ" in row.error and row.size == 1024 * 1024 + 5
    assert (folder / "rejected" / "huge.xlsx").exists()


def test_two_scanners_take_a_file_once(folder, db, monkeypatch):
    """Файл занимается атомарным переносом в .work/: второй планировщик его уже не находит."""
    put(folder / "tp-weekly" / "w.xlsx", tp_file())
    real = inbox_folder._claim
    results = []

    def claim_with_rival(path, root, dataset):
        if not results:
            results.append("rival")
            rival = inbox_folder.ScanResult()
            inbox_folder._scan_file(root, path, dataset, time.time(), rival)  # второй процесс успел первым
            results.append(rival.taken)
        return real(path, root, dataset)

    monkeypatch.setattr(inbox_folder, "_claim", claim_with_rival)
    result = inbox_folder.scan()
    assert results == ["rival", 1] and result.taken == 0 and len(items(db)) == 1


def test_stale_work_files_are_recovered(folder, db):
    inbox_folder.ensure_layout(folder)
    work = put(folder / ".work" / "abc__tp-weekly__w.xlsx", tp_file(), age=2 * 3600)
    fresh = put(folder / ".work" / "def__tp-weekly__busy.xlsx", tp_file(), age=5)
    result = inbox_folder.scan()
    assert not work.exists() and fresh.exists(), "незавершённый час назад файл возвращён, идущий — нет"
    assert result.taken == 1 and items(db)[0].dataset == "tp-weekly" and items(db)[0].filename == "w.xlsx"


def test_cleanup_removes_old_processed_files(folder, db):
    put(folder / "tp-weekly" / "w.xlsx", tp_file())
    inbox_folder.scan()
    assert inbox_folder.cleanup() == 0
    assert inbox_folder.cleanup(now=time.time() + 400 * 86400) == 2
    assert not any((folder / "processed").iterdir())


def test_folder_api_and_scan_endpoint(folder, admin, login):
    put(folder / "naumen" / "x.xlsx", b"junk")
    status = admin.get("/api/inbox/folder").json()
    assert status["enabled"] and status["waiting_files"] == 1 and status["last_scan"] is None
    folders = {f["folder"]: f for f in status["folders"]}
    assert folders["naumen"]["patterns"] == ["*naumen*", "*наумен*", "*заявк*"], "шаблоны имени — у каждой подпапки"
    assert folders["structure"]["label"] == "Структура компании" and folders["structure"]["patterns"]
    scanned = admin.post("/api/inbox/folder/scan").json()
    assert scanned["taken"] == 1 and scanned["errors"] == 1
    assert admin.get("/api/inbox/folder").json()["last_scan"]["last_result"]["taken"] == 1
    assert login("tp_lead").get("/api/inbox/folder").status_code == 403
