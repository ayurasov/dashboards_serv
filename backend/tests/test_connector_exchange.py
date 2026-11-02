"""Коннектор «Почтовый ящик (Exchange)»: IMAP против поддельного IMAP-сервера (socketserver в потоке, imaplib
настоящий), Microsoft Graph против поддельного API (tests/fake_http), EWS — с заглушкой exchangelib и без пакета.
Разрешённые отправители, вложения во «Входящие» с source_ref, повторы, курсор, пометка прочитанным и перенос,
правило «тема → набор», ошибки входа и папок, привязка секрета к адресу."""
from __future__ import annotations

import base64
import contextlib
import email
import hashlib
import json
import re
import socketserver
import sys
import threading
import types
from datetime import UTC, datetime
from email.message import EmailMessage
from email.policy import compat32
from urllib.parse import parse_qs, urlencode

import pytest
from sqlalchemy import func, select, update

from app.integrations.connectors.exchange import sender_allowed, senders
from app.integrations.connectors.mailbox import mutf7
from app.models import InboxItem, InboxRule, Integration
from tests.conftest import assert_counters_labelled
from tests.fake_http import FakeServer
from tests.test_inbox import csv_bytes, tp_file

IMAP_USER, IMAP_PASSWORD = "data@company.ru", "imap-pass-1"
GRAPH_SECRET = "graph-secret-value"
ALLOWED = ["1c@company.ru", "company.ru"]
PROCESSED = "Входящие/Обработано"


def indicators_csv(value="61,5") -> bytes:
    return csv_bytes([["Подразделение", "Показатель", "Период", "Значение"], ["COMM", "fin.revenue", "2031-01", value]])


def message(sender: str, subject: str, *files: tuple[str, bytes], msgid: str, day: int = 1) -> bytes:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = IMAP_USER
    msg["Subject"] = subject
    msg["Message-ID"] = f"<{msgid}@mail.company.ru>"
    msg["Date"] = email.utils.format_datetime(datetime(2026, 10, day, 9, 30, tzinfo=UTC))
    msg.set_content("Выгрузка во вложении")
    for name, content in files:
        maintype, subtype = ("image", "png") if name.endswith(".png") else ("application", "octet-stream")
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=name)
    return msg.as_bytes()


# ================================================================ поддельный IMAP

class FakeImap:
    """Минимальный IMAP4rev1: LOGIN/AUTHENTICATE PLAIN, LIST, SELECT, STATUS, UID SEARCH/FETCH/STORE/MOVE/COPY/
    EXPUNGE, EXPUNGE, LOGOUT. Папки хранятся по имени на проводе (модифицированная UTF-7)."""

    def __init__(self, *, move: bool = True):
        self.user, self.password = IMAP_USER, IMAP_PASSWORD
        self.folders: dict[str, list[dict]] = {"INBOX": [], mutf7("INBOX/Обработано"): [],
                                               mutf7("INBOX/Выгрузки"): []}
        self.capabilities = ["IMAP4rev1", "UIDPLUS", "AUTH=PLAIN"] + (["MOVE"] if move else [])
        self.uidvalidity = 7
        self.next_uid = 1
        self.commands: list[str] = []
        self.logins = 0
        self.lock = threading.Lock()

    def add(self, raw: bytes, *, folder: str = "INBOX", seen: bool = False) -> int:
        uid = self.next_uid
        self.next_uid += 1
        self.folders[folder].append({"uid": uid, "raw": raw, "flags": {"\\Seen"} if seen else set()})
        return uid

    def find(self, uid: int) -> dict | None:
        return next((m for msgs in self.folders.values() for m in msgs if m["uid"] == uid), None)

    def start(self) -> FakeImap:
        fake = self

        class Handler(socketserver.StreamRequestHandler):
            def send(self, line: str | bytes) -> None:
                self.wfile.write((line.encode() if isinstance(line, str) else line) + b"\r\n")

            def handle(self):
                self.selected: str | None = None
                self.send(f"* OK [CAPABILITY {' '.join(fake.capabilities)}] Поддельный IMAP готов".encode())
                while True:
                    raw = self.rfile.readline()
                    if not raw:
                        return
                    line = raw.decode().rstrip("\r\n")
                    tag, _, rest = line.partition(" ")
                    with fake.lock:
                        fake.commands.append(re.sub(r"(LOGIN \S+ ).*", r"\1***", rest))
                        if not fake.dispatch(self, tag, rest):
                            return

        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    # --- разбор команды
    @staticmethod
    def args(text: str) -> list[str]:
        out, i = [], 0
        while i < len(text):
            ch = text[i]
            if ch == " ":
                i += 1
            elif ch == '"':
                j, buf = i + 1, []
                while text[j] != '"':
                    if text[j] == "\\":
                        j += 1
                    buf.append(text[j])
                    j += 1
                out.append("".join(buf))
                i = j + 1
            elif ch == "(":
                depth, j = 0, i
                while True:
                    depth += {"(": 1, ")": -1}.get(text[j], 0)
                    if depth == 0:
                        break
                    j += 1
                out.append(text[i:j + 1])
                i = j + 1
            else:
                j = text.find(" ", i)
                j = len(text) if j < 0 else j
                out.append(text[i:j])
                i = j
        return out

    def uids(self, spec: str, folder: list[dict]) -> list[int]:
        have = [m["uid"] for m in folder]
        out: list[int] = []
        for part in spec.split(","):
            if ":" in part:
                low, high = part.split(":")
                top = max(have, default=0) if high == "*" else int(high)
                chosen = [u for u in have if int(low) <= u <= top]
                out += chosen or ([max(have)] if high == "*" and have else [])   # «n:*» — хотя бы последнее
            elif part.isdigit():
                out.append(int(part))
        return [u for u in dict.fromkeys(out) if u in have]

    def dispatch(self, h, tag: str, rest: str) -> bool:
        command, _, tail = rest.partition(" ")
        command = command.upper()
        args = self.args(tail)
        if command == "CAPABILITY":
            h.send(f"* CAPABILITY {' '.join(self.capabilities)}")
        elif command == "LOGIN":
            if args != [self.user, self.password]:
                h.send(f"{tag} NO [AUTHENTICATIONFAILED] Invalid credentials")
                return True
            self.logins += 1
        elif command == "AUTHENTICATE":
            h.send("+ ")
            answer = base64.b64decode(h.rfile.readline().strip()).decode()
            if answer.split("\0")[1:] != [self.user, self.password]:
                h.send(f"{tag} NO [AUTHENTICATIONFAILED] Invalid credentials")
                return True
            self.logins += 1
        elif command == "LIST":
            h.send('* LIST (\\Noselect) "/" ""')
        elif command in ("SELECT", "EXAMINE"):
            if args[0] not in self.folders:
                h.send(f"{tag} NO [NONEXISTENT] Unknown Mailbox")
                return True
            h.selected = args[0]
            h.send(f"* {len(self.folders[args[0]])} EXISTS")
            h.send(f"* OK [UIDVALIDITY {self.uidvalidity}] UIDs valid")
            h.send(f"* OK [UIDNEXT {self.next_uid}] Predicted next UID")
        elif command == "STATUS":
            if args[0] not in self.folders:
                h.send(f"{tag} NO [NONEXISTENT] Unknown Mailbox")
                return True
            msgs = self.folders[args[0]]
            unseen = sum(1 for m in msgs if "\\Seen" not in m["flags"])
            h.send(f'* STATUS "{args[0]}" (MESSAGES {len(msgs)} UNSEEN {unseen})')
        elif command == "UID":
            return self.uid_command(h, tag, args)
        elif command == "EXPUNGE":
            self.expunge(h, None)
        elif command == "LOGOUT":
            h.send("* BYE Пока")
            h.send(f"{tag} OK LOGOUT completed")
            return False
        elif command != "NOOP":
            h.send(f"{tag} BAD Unknown command")
            return True
        h.send(f"{tag} OK {command} completed")
        return True

    def expunge(self, h, only: set[int] | None) -> None:
        folder = self.folders[h.selected]
        for index in range(len(folder) - 1, -1, -1):
            if "\\Deleted" in folder[index]["flags"] and (only is None or folder[index]["uid"] in only):
                folder.pop(index)
                h.send(f"* {index + 1} EXPUNGE")

    def uid_command(self, h, tag: str, args: list[str]) -> bool:
        sub = args[0].upper()
        folder = self.folders[h.selected]
        if sub == "SEARCH":
            criteria = [a.upper() for a in args[1:]]
            if criteria == ["UNSEEN"]:
                found = [m["uid"] for m in folder if "\\Seen" not in m["flags"]]
            elif criteria[0] == "UID":
                found = self.uids(args[2], folder)
            else:
                found = [m["uid"] for m in folder]
            h.send("* SEARCH " + " ".join(map(str, found)))
        elif sub == "FETCH":
            items = args[2].upper()
            for uid in self.uids(args[1], folder):
                msg = self.find(uid)
                seq = folder.index(msg) + 1
                if "HEADER.FIELDS" in items:
                    parsed = email.message_from_bytes(msg["raw"], policy=compat32)
                    body = "".join(f"{k}: {parsed[k]}\r\n" for k in ("From", "Subject", "Message-ID", "Date")
                                   if parsed[k]).encode() + b"\r\n"
                    name = "BODY[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID DATE)]"
                else:
                    body, name = msg["raw"], "BODY[]"
                h.send(f"* {seq} FETCH (UID {uid} {name} {{{len(body)}}}".encode())
                h.wfile.write(body)
                h.send(")")
        elif sub == "STORE":
            flags = set(args[3].strip("()").split())
            for uid in self.uids(args[1], folder):
                msg = self.find(uid)
                msg["flags"] |= flags
                h.send(f"* {folder.index(msg) + 1} FETCH (UID {uid} FLAGS ({' '.join(sorted(msg['flags']))}))")
        elif sub in ("MOVE", "COPY"):
            if args[2] not in self.folders:
                h.send(f"{tag} NO [TRYCREATE] Mailbox doesn't exist")
                return True
            for uid in self.uids(args[1], folder):
                msg = self.find(uid)
                self.folders[args[2]].append({"uid": self.next_uid, "raw": msg["raw"], "flags": set(msg["flags"])})
                self.next_uid += 1
                if sub == "MOVE":
                    h.send(f"* {folder.index(msg) + 1} EXPUNGE")
                    folder.remove(msg)
        elif sub == "EXPUNGE":
            self.expunge(h, set(self.uids(args[1], folder)))
        h.send(f"{tag} OK UID {sub} completed")
        return True


@pytest.fixture()
def imap():
    server = FakeImap().start()
    yield server
    server.stop()


def _imap_body(imap, **config) -> dict:
    return {"kind": "exchange", "name": "Почта", "config": {
        "mode": "imap", "imap_host": "127.0.0.1", "imap_port": imap.port, "imap_ssl": False, "username": IMAP_USER,
        "allowed_senders": ALLOWED, "move_to": PROCESSED,
        "subject_rules": "Недельный отчёт* = tp-weekly", **config}, "secrets": {"password": IMAP_PASSWORD}}


def _create(admin, body) -> dict:
    response = admin.post("/api/integrations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _run(admin, item) -> dict:
    response = admin.post(f"/api/integrations/{item['id']}/run", json={"action": "fetch"})
    assert response.status_code == 200, response.text
    return assert_counters_labelled(response.json(), "exchange")


def _items(db, integration_id) -> dict[str, InboxItem]:
    db.expire_all()
    return {i.filename: i for i in db.scalars(select(InboxItem).where(InboxItem.integration_id == integration_id))}


def _mailbox(imap):
    imap.add(message("1c@company.ru", "Недельный отчёт ТП", ("tp.xlsx", tp_file()), ("logo.png", b"\x89PNG"),
                     msgid="m1", day=1))
    imap.add(message("stranger@evil.ru", "Выручка", ("revenue.csv", indicators_csv("99")), msgid="m2", day=2))
    imap.add(message("Начальник <boss@sub.company.ru>", "Показатели", ("показатели.csv", indicators_csv()),
                     msgid="m3", day=3))
    imap.add(message("1c@company.ru", "Старое", ("old.csv", indicators_csv("1")), msgid="m4", day=4), seen=True)


# ================================================================ настройки

def test_senders_and_domains():
    allowed = senders(["1C@company.ru", "@corp.ru", "*.partner.ru", " "])
    assert allowed == ["1c@company.ru", "corp.ru", "partner.ru"]
    assert sender_allowed("1c@company.ru", allowed) and not sender_allowed("2c@company.ru", allowed)
    assert sender_allowed("a@corp.ru", allowed) and sender_allowed("a@x.corp.ru", allowed)
    assert not sender_allowed("a@notcorp.ru", allowed) and not sender_allowed("", allowed)
    assert mutf7("Входящие") == "&BBIERQQ+BDQETwRJBDgENQ-" and mutf7("A&B") == "A&-B"


def test_config_validation_per_mode(admin, monkeypatch):
    meta = {k["kind"]: k for k in admin.get("/api/integrations/kinds").json()}["exchange"]
    assert meta["title"] == "Почтовый ящик (Exchange)" and meta["actions"][0]["label"] == "Забрать вложения"
    fields = {f["key"]: f for f in meta["fields"]}
    assert fields["client_secret"]["show_if"] == {"mode": ["graph"]}
    assert "endpoint" not in fields, "привязка секрета — механизм каркаса (secret_url), а не скрытое поле"
    assert meta["url_field"] is None and meta["allowed_hosts_env"] == "EXCHANGE_ALLOWED_HOSTS"
    assert meta["secret_url_fields"] == ["mode", "ews_url", "tenant", "login_url", "graph_url", "imap_host",
                                         "imap_port", "imap_ssl"]

    def create(config, secrets=None):
        return admin.post("/api/integrations", json={"kind": "exchange", "config": {"allowed_senders": ALLOWED,
                                                                                   **config},
                                                     "secrets": secrets or {}})

    assert "secrets.password" in create({"mode": "imap", "imap_host": "imap.company.ru", "username": "u"}).json()[
        "fields"]
    assert "config.mailbox" in create({"mode": "graph", "tenant": "t", "client_id": "c"},
                                      {"client_secret": "s"}).json()["fields"]
    assert "config.imap_host" in create({"mode": "imap", "imap_host": "imap://x", "username": "u"},
                                        {"password": "p"}).json()["fields"]
    assert "config.allowed_senders" in create({"mode": "imap", "imap_host": "x.ru", "username": "u",
                                               "allowed_senders": []}, {"password": "p"}).json()["fields"]
    bad_rule = create({"mode": "imap", "imap_host": "x.ru", "username": "u", "subject_rules": "*ЗУП* = nope"},
                      {"password": "p"})
    assert bad_rule.status_code == 422 and "набора «nope» нет" in bad_rule.json()["detail"]
    monkeypatch.setenv("EXCHANGE_ALLOWED_HOSTS", ".company.ru")
    denied = create({"mode": "imap", "imap_host": "imap.evil.ru", "username": "u"}, {"password": "p"})
    assert denied.status_code == 422 and "EXCHANGE_ALLOWED_HOSTS" in denied.json()["detail"]
    ok = create({"mode": "imap", "imap_host": "IMAP.company.ru", "username": "u"}, {"password": "p"}).json()
    assert "endpoint" not in ok["config"] and ok["secret_bound_url"] == "imaps://imap.company.ru:993"
    moved = admin.patch(f"/api/integrations/{ok['id']}", json={"config": {"imap_host": "mail.company.ru"}})
    assert moved.status_code == 422 and moved.json()["code"] == "secret_rebind_required", \
        "пароль не уходит на другой почтовый сервер без повторного ввода"
    port = admin.patch(f"/api/integrations/{ok['id']}", json={"config": {"imap_port": 143, "imap_ssl": False}})
    assert port.status_code == 422 and port.json()["code"] == "secret_rebind_required"
    # Поле, от которого адрес не зависит (папка), секрет не трогает
    folder = admin.patch(f"/api/integrations/{ok['id']}", json={"config": {"folder": "Входящие/Выгрузки"}})
    assert folder.status_code == 200 and folder.json()["secret_problem"] is None
    # Смена способа подключения — другой адрес: секрет вводится заново
    graph = admin.patch(f"/api/integrations/{ok['id']}", json={"config": {
        "mode": "graph", "tenant": "t", "client_id": "c", "mailbox": "data@company.ru"}})
    assert graph.status_code == 422 and graph.json()["code"] == "secret_rebind_required"


# ================================================================ IMAP

def test_imap_check_counts_messages(admin, imap):
    _mailbox(imap)
    item = _create(admin, _imap_body(imap))
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"], check
    assert check["message"] == "Ящик доступен (IMAP): в папке «Входящие» писем 4, непрочитанных 3"
    assert check["details"] == {"mode": "imap", "folder": "Входящие", "total": 4, "unread": 3}
    assert imap.commands[-1] == "LOGOUT"


def test_imap_check_failures(admin, imap):
    item = _create(admin, _imap_body(imap, move_to="Входящие/Нет такой"))
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and "папки «Входящие/Нет такой» для обработанных писем нет" in check["message"]
    admin.patch(f"/api/integrations/{item['id']}", json={"config": {"folder": "Архив"}})
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["message"].startswith("Папка «Архив» не найдена в ящике")
    admin.patch(f"/api/integrations/{item['id']}", json={"secrets": {"password": "не тот"}})
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["details"]["code"] == "auth"
    assert check["message"] == f"Почтовый сервер 127.0.0.1:{imap.port} отклонил вход: неверный логин или пароль"
    assert any(c.startswith("AUTHENTICATE PLAIN") for c in imap.commands), "кириллица в пароле — AUTHENTICATE PLAIN"
    body = _imap_body(imap, imap_port=9)
    down = admin.post("/api/integrations/check", json={k: body[k] for k in ("kind", "config", "secrets")}).json()
    assert not down["ok"] and "Не удалось подключиться к почтовому серверу 127.0.0.1:9" in down["message"]
    assert IMAP_PASSWORD not in json.dumps([check, down], ensure_ascii=False)


def test_imap_run_takes_allowed_attachments_marks_and_moves(admin, imap, db):
    _mailbox(imap)
    db.merge(InboxRule(source="integration", dataset="tp-weekly", auto_apply=True))
    db.commit()
    item = _create(admin, _imap_body(imap))
    run = _run(admin, item)
    assert run["status"] == "ok", run
    summary = run["summary"]
    assert summary["processed"] == 2 and summary["added"] == 2 and summary["skipped_sender"] == 1
    assert summary["skipped_type"] == 1 and summary["status_applied"] == 1
    assert run["message"] == ("Писем от разрешённых отправителей 2, файлов во «Входящие» 2, уже забранных 0; писем "
                              "других отправителей (не тронуты) 1; пропущено вложений 1 (не данные или слишком "
                              "большие)")
    items = _items(db, item["id"])
    assert set(items) == {"tp.xlsx", "показатели.csv"}
    tp = items["tp.xlsx"]
    assert tp.dataset == "tp-weekly" and tp.status == "applied", "набор — по правилу темы"
    assert tp.source_ref == f"exchange:m1@mail.company.ru:tp.xlsx:{hashlib.sha256(tp_file()).hexdigest()}"
    assert items["показатели.csv"].dataset == "indicators" and items["показатели.csv"].status == "pending"
    inbox, processed = imap.folders["INBOX"], imap.folders[mutf7("INBOX/Обработано")]
    assert [m["uid"] for m in inbox] == [2, 4], "чужое письмо и прочитанное остаются на месте"
    assert "\\Seen" not in inbox[0]["flags"], "письмо чужого отправителя не помечается"
    assert len(processed) == 2 and all("\\Seen" in m["flags"] for m in processed)
    assert any(c.startswith("UID FETCH") and "BODY.PEEK[]" in c for c in imap.commands), "чтение — без \\Seen"
    assert tp.note == "Письмо «Недельный отчёт ТП» от 1c@company.ru", "откуда файл — пояснением элемента"
    files = summary["details"]["files"]
    assert files[0] == {"item": tp.id, "file": "tp.xlsx", "status": "применён"}, \
        "тема и отправитель — в пояснении элемента, а не в подробностях запуска"
    listed = admin.get("/api/inbox", params={"integration_id": item["id"]}).json()["items"]
    assert {i["filename"]: i["note"] for i in listed}["tp.xlsx"] == tp.note
    again = _run(admin, item)
    assert again["summary"]["added"] == 0 and again["summary"]["processed"] == 0
    assert again["summary"]["skipped_sender"] == 1


def test_imap_cursor_without_marking_and_dedup(admin, imap, db):
    _mailbox(imap)
    item = _create(admin, _imap_body(imap, mark_read=False, move_to=None))
    first = _run(admin, item)
    assert first["summary"]["processed"] == 3 and first["summary"]["added"] == 3, "и прочитанные — после курсора"
    db.expire_all()
    assert db.get(Integration, item["id"]).state["cursor"] == {"uidvalidity": 7, "uid": 4}
    assert all("\\Seen" not in m["flags"] for m in imap.folders["INBOX"][:3] if m["uid"] != 4), "не помечаются"
    imap.commands.clear()
    second = _run(admin, item)
    assert second["summary"]["messages"] == 0 and "UID SEARCH UID 5:*" in imap.commands
    # Повтор того же письма (тот же Message-ID и вложение) во «Входящие» не кладётся
    imap.add(message("1c@company.ru", "Недельный отчёт ТП", ("tp.xlsx", tp_file()), msgid="m1", day=5))
    imap.add(message("1c@company.ru", "Новые показатели", ("new.csv", indicators_csv("77")), msgid="m5", day=6))
    third = _run(admin, item)
    assert third["summary"]["seen"] == 1 and third["summary"]["added"] == 1
    assert set(_items(db, item["id"])) == {"tp.xlsx", "показатели.csv", "old.csv", "new.csv"}
    # Сменился UIDVALIDITY — ящик пересоздан: письма берутся заново, повторы распознаются
    imap.uidvalidity = 8
    fourth = _run(admin, item)
    assert fourth["summary"]["processed"] == 5 and fourth["summary"]["added"] == 0 and fourth["summary"]["seen"] == 5


def test_imap_cyrillic_folder_and_server_without_move(admin, db):
    imap = FakeImap(move=False).start()
    try:
        imap.add(message("1c@company.ru", "Показатели", ("data.csv", indicators_csv()), msgid="x1"),
                 folder=mutf7("INBOX/Выгрузки"))
        item = _create(admin, _imap_body(imap, folder="Входящие/Выгрузки"))
        run = _run(admin, item)
        assert run["status"] == "ok" and run["summary"]["added"] == 1
        assert f'SELECT "{mutf7("INBOX/Выгрузки")}"' in imap.commands
        assert any(c.startswith("UID COPY") for c in imap.commands) and any(c.startswith("UID EXPUNGE")
                                                                           for c in imap.commands)
        assert imap.folders[mutf7("INBOX/Выгрузки")] == [] and len(imap.folders[mutf7("INBOX/Обработано")]) == 1
    finally:
        imap.stop()


def test_imap_broken_attachment_message_is_retried(admin, imap, db, monkeypatch):
    _mailbox(imap)
    from app.core.errors import ValidationFailed
    from app.services import inbox

    real = inbox.add

    def flaky(db_, content, filename, **kwargs):
        if filename == "tp.xlsx":
            raise ValidationFailed("Сбой разбора")
        return real(db_, content, filename, **kwargs)

    monkeypatch.setattr(inbox, "add", flaky)
    item = _create(admin, _imap_body(imap, move_to=None))
    run = _run(admin, item)
    assert run["status"] == "partial" and run["summary"]["errors"] == 1 and "Сбой разбора" in run["error"]
    assert "\\Seen" not in imap.folders["INBOX"][0]["flags"], "письмо с ошибкой не помечается — повтор позже"
    monkeypatch.setattr(inbox, "add", real)
    again = _run(admin, item)
    assert again["status"] == "ok" and again["summary"]["added"] == 1 and again["summary"]["processed"] == 1


# ================================================================ Microsoft Graph

class FakeGraph:
    def __init__(self, server: FakeServer):
        self.server = server
        self.base = "/v1.0/users/data@company.ru"
        self.tokens = 0
        self.messages = {
            "M1": {"id": "M1", "internetMessageId": "<g1@company.ru>", "subject": "Недельный отчёт ТП",
                   "from": {"emailAddress": {"address": "1C@company.ru", "name": "1С"}},
                   "receivedDateTime": "2026-10-01T09:00:00Z", "hasAttachments": True, "isRead": False},
            "M2": {"id": "M2", "internetMessageId": "<g2@evil.ru>", "subject": "Чужое",
                   "from": {"emailAddress": {"address": "x@evil.ru"}}, "receivedDateTime": "2026-10-02T09:00:00Z",
                   "hasAttachments": True, "isRead": False},
            "M3": {"id": "M3", "internetMessageId": "<g3@company.ru>", "subject": "Показатели",
                   "from": {"emailAddress": {"address": "boss@company.ru"}},
                   "receivedDateTime": "2026-10-02T09:00:00Z", "hasAttachments": True, "isRead": False},
        }
        self.attachments = {
            "M1": [{"@odata.type": "#microsoft.graph.fileAttachment", "id": "A1", "name": "tp.xlsx",
                    "contentType": "application/vnd.openxmlformats", "size": len(tp_file()), "isInline": False,
                    "_content": tp_file()},
                   {"@odata.type": "#microsoft.graph.fileAttachment", "id": "A2", "name": "logo.png",
                    "contentType": "image/png", "size": 4, "isInline": True, "_content": b"\x89PNG"}],
            "M2": [{"@odata.type": "#microsoft.graph.fileAttachment", "id": "B1", "name": "x.csv",
                    "contentType": "text/csv", "size": 3, "isInline": False, "_content": b"x;y"}],
            "M3": [{"@odata.type": "#microsoft.graph.itemAttachment", "id": "C0", "name": "Пересланное",
                    "isInline": False, "size": 10},
                   {"@odata.type": "#microsoft.graph.fileAttachment", "id": "C1", "name": "показатели.csv",
                    "contentType": "text/csv", "size": len(indicators_csv()), "isInline": False,
                    "_content": indicators_csv()}],
        }
        self.folder = {"inbox": [], "F1": ["M1", "M2", "M3"], "F2": []}
        self.moved: list[tuple[str, str]] = []
        server.route("POST", "/tenant-1/oauth2/v2.0/token", self.token)
        server.route("GET", f"{self.base}/mailFolders/inbox", self.authed(lambda r: (200, {"id": "inbox"})))
        server.route("GET", f"{self.base}/mailFolders/inbox/childFolders", self.authed(self.children))
        server.route("GET", f"{self.base}/mailFolders/F1", self.authed(self.counts))
        server.route("GET", f"{self.base}/mailFolders/F1/messages", self.authed(self.list_messages))
        for mid, items in self.attachments.items():
            server.route("GET", f"{self.base}/messages/{mid}/attachments", self.authed(
                lambda r, items=items: (200, {"value": [{k: v for k, v in a.items() if k != "_content"}
                                                        for a in items]})))
            for att in items:
                if "_content" in att:
                    server.route("GET", f"{self.base}/messages/{mid}/attachments/{att['id']}/$value",
                                 self.authed(lambda r, att=att: (200, att["_content"])))
            server.route("PATCH", f"{self.base}/messages/{mid}", self.authed(lambda r, mid=mid: self.patch(r, mid)))
            server.route("POST", f"{self.base}/messages/{mid}/move", self.authed(lambda r, mid=mid: self.move(r, mid)))

    def token(self, request):
        form = {k: v[0] for k, v in parse_qs(request.body.decode()).items()}
        if form.get("client_secret") != GRAPH_SECRET:
            return 401, {"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret "
                                                                         "provided. Trace ID: 1"}
        assert form["grant_type"] == "client_credentials" and form["scope"].endswith("/.default")
        self.tokens += 1
        return 200, {"access_token": "graph-token", "token_type": "Bearer", "expires_in": 3599}

    def authed(self, handler):
        def wrapper(request):
            if request.headers.get("authorization") != "Bearer graph-token":
                return 401, {"error": {"code": "InvalidAuthenticationToken", "message": "Access token is empty."}}
            return handler(request)
        return wrapper

    def children(self, request):
        name = re.search(r"displayName eq '(.*)'", request.query["$filter"][0]).group(1)
        ids = {"Выгрузки": "F1", "Обработано": "F2"}
        return 200, {"value": [{"id": ids[name], "displayName": name}] if name in ids else []}

    def counts(self, request):
        ids = self.folder["F1"]
        return 200, {"totalItemCount": len(ids), "unreadItemCount": sum(not self.messages[i]["isRead"] for i in ids)}

    def list_messages(self, request):
        query = request.query.get("$filter", [""])[0]
        since = re.search(r"receivedDateTime ge (\S+)", query).group(1)
        assert request.query.get("$orderby", ["receivedDateTime asc"]) == ["receivedDateTime asc"]
        items = [self.messages[i] for i in self.folder["F1"] if self.messages[i]["receivedDateTime"] >= since
                 and ("isRead eq false" not in query or not self.messages[i]["isRead"])]
        start = int(request.query.get("$skiptoken", ["0"])[0])
        page = items[start:start + 2]
        body = {"value": page}
        if start + 2 < len(items):
            params = {k: v[0] for k, v in request.query.items() if k != "$skiptoken"}
            params["$skiptoken"] = str(start + 2)
            body["@odata.nextLink"] = f"{self.server.url}{self.base}/mailFolders/F1/messages?{urlencode(params)}"
        return 200, body

    def patch(self, request, mid):
        self.messages[mid].update(request.json())
        return 200, self.messages[mid]

    def move(self, request, mid):
        target = request.json()["destinationId"]
        self.folder["F1"].remove(mid)
        self.folder[target].append(mid)
        self.moved.append((mid, target))
        return 201, {"id": mid + "-moved"}


@pytest.fixture()
def graph(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.delenv("EXCHANGE_ALLOWED_HOSTS", raising=False)
    server = FakeServer()
    fake = FakeGraph(server)
    with server:
        yield fake


def _graph_body(graph, **config) -> dict:
    return {"kind": "exchange", "name": "Microsoft 365", "config": {
        "mode": "graph", "tenant": "tenant-1", "client_id": "app-1", "mailbox": "data@company.ru",
        "graph_url": graph.server.url, "login_url": graph.server.url, "folder": "Входящие/Выгрузки",
        "allowed_senders": ALLOWED, "move_to": PROCESSED, **config}, "secrets": {"client_secret": GRAPH_SECRET}}


def test_graph_check_and_wrong_secret(admin, graph):
    item = _create(admin, _graph_body(graph))
    assert item["secret_bound_url"] == f"{graph.server.url}/tenant-1 → {graph.server.url}"
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert check["ok"], check
    assert check["message"] == ("Ящик доступен (Microsoft 365 (Graph)): в папке «Входящие/Выгрузки» писем 3, "
                                "непрочитанных 3")
    admin.patch(f"/api/integrations/{item['id']}", json={"secrets": {"client_secret": "wrong"}})
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and "отклонил секрет приложения (AADSTS7000215)" in check["message"]
    assert GRAPH_SECRET not in json.dumps(check, ensure_ascii=False)
    admin.patch(f"/api/integrations/{item['id']}", json={"secrets": {"client_secret": GRAPH_SECRET},
                                                         "config": {"folder": "Входящие/Нет"}})
    check = admin.post(f"/api/integrations/{item['id']}/check").json()
    assert not check["ok"] and check["message"] == "Папка «Нет» не найдена в ящике «data@company.ru»"


def test_graph_run_pages_marks_moves_and_keeps_cursor(admin, graph, db):
    item = _create(admin, _graph_body(graph, mark_read=False))
    run = _run(admin, item)
    assert run["status"] == "ok", run
    summary = run["summary"]
    assert summary["processed"] == 2 and summary["added"] == 2 and summary["skipped_sender"] == 1
    assert summary["skipped_type"] == 0, "встроенная картинка и вложенное письмо не считаются файлами"
    items = _items(db, item["id"])
    assert items["tp.xlsx"].source_ref.startswith("exchange:g1@company.ru:tp.xlsx:")
    assert graph.moved == [("M1", "F2"), ("M3", "F2")] and graph.folder["F1"] == ["M2"]
    assert not graph.messages["M1"]["isRead"], "«Помечать прочитанными» выключено"
    db.expire_all()
    cursor = db.get(Integration, item["id"]).state["cursor"]
    assert cursor == {"received": "2026-10-02T09:00:00Z", "ids": ["M2", "M3"]}
    graph.server.requests.clear()
    again = _run(admin, item)
    assert again["summary"]["messages"] == 0
    query = next(r for r in graph.server.requests if r.path.endswith("/messages")).query["$filter"][0]
    assert query == "receivedDateTime ge 2026-10-02T09:00:00Z"


def test_graph_run_marks_read(admin, graph, db):
    item = _create(admin, _graph_body(graph, move_to=None))
    run = _run(admin, item)
    assert run["summary"]["processed"] == 2 and graph.messages["M1"]["isRead"] and graph.messages["M3"]["isRead"]
    assert not graph.messages["M2"]["isRead"] and graph.moved == []
    again = _run(admin, item)
    assert again["summary"]["processed"] == 0 and again["summary"]["skipped_sender"] == 1
    query = [r for r in graph.server.requests if r.path.endswith("/messages")][-1].query["$filter"][0]
    assert "isRead eq false" in query


# ================================================================ EWS (exchangelib)

def test_ews_without_exchangelib_is_a_clear_error(admin, monkeypatch):
    monkeypatch.setitem(sys.modules, "exchangelib", None)
    body = {"kind": "exchange", "config": {"mode": "ews", "ews_url": "https://mail.company.ru/EWS/Exchange.asmx",
                                           "username": "COMPANY\\dash", "mailbox": "data@company.ru",
                                           "allowed_senders": ALLOWED}, "secrets": {"password": "ews"}}
    check = admin.post("/api/integrations/check", json=body).json()
    assert not check["ok"] and check["details"]["code"] == "dependency_missing"
    assert "нужен пакет exchangelib" in check["message"] and "IMAP или Microsoft Graph" in check["message"]


def fake_exchangelib(store: dict) -> types.ModuleType:
    """Заглушка exchangelib: Account, папки с запросами filter/order_by/срез, письма с вложениями, save, move."""
    exl = types.ModuleType("exchangelib")

    class UnauthorizedError(Exception):
        pass

    class ErrorFolderNotFound(Exception):
        pass

    class Credentials:
        def __init__(self, username, password):
            self.username, self.password = username, password

    class Configuration:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            store["config"] = kwargs

    class FileAttachment:
        def __init__(self, name, content, content_type="application/octet-stream", is_inline=False):
            self.name, self.content, self.content_type, self.is_inline = name, content, content_type, is_inline
            self.size = len(content)

    class Message:
        def __init__(self, mid, sender, subject, received, files, read=False):
            self.id, self.message_id, self.subject = mid, f"<{mid}@ex.company.ru>", subject
            self.sender = types.SimpleNamespace(email_address=sender)
            self.datetime_received = received
            self.attachments = files
            self.has_attachments = bool(files)
            self.is_read = read
            self.folder = None

        def save(self, update_fields=None):
            store.setdefault("saved", []).append((self.id, tuple(update_fields or ())))

        def move(self, to_folder):
            self.folder.items.remove(self)
            to_folder.items.append(self)
            self.folder = to_folder

    class Query:
        def __init__(self, items):
            self.items = list(items)

        def filter(self, **kwargs):
            items = self.items
            if "is_read" in kwargs:
                items = [i for i in items if i.is_read == kwargs["is_read"]]
            if "datetime_received__gte" in kwargs:
                items = [i for i in items if i.datetime_received >= kwargs["datetime_received__gte"]]
            return Query(items)

        def order_by(self, name):
            return Query(sorted(self.items, key=lambda i: getattr(i, name)))

        def __getitem__(self, s):
            return self.items[s]

    class Folder:
        def __init__(self, name, children=()):
            self.name, self.items, self.children = name, [], {c.name: c for c in children}

        def __truediv__(self, name):
            if name not in self.children:
                raise ErrorFolderNotFound(name)
            return self.children[name]

        def refresh(self):
            self.total_count = len(self.items)
            self.unread_count = sum(not i.is_read for i in self.items)

        def all(self):
            return Query(self.items)

        def add(self, msg):
            msg.folder = self
            self.items.append(msg)

    class Account:
        def __init__(self, primary_smtp_address, config, autodiscover, access_type):
            if config.credentials.password != "ews-pass":
                raise UnauthorizedError("Invalid credentials for https://mail.company.ru/EWS/Exchange.asmx")
            assert autodiscover is False and access_type == "delegate"
            self.inbox = store["inbox"]
            self.msg_folder_root = Folder("root", [store["inbox"]])
            self.protocol = types.SimpleNamespace(close=lambda: store.__setitem__("closed", True))
            store["adapter_during"] = exl.BaseProtocol.HTTP_ADAPTER_CLS

    class BaseProtocol:
        HTTP_ADAPTER_CLS = "requests-adapter"

    exl.__dict__.update(Credentials=Credentials, Configuration=Configuration, Account=Account, Message=Message,
                        FileAttachment=FileAttachment, Folder=Folder, BaseProtocol=BaseProtocol,
                        NoVerifyHTTPAdapter="no-verify-adapter", NTLM="NTLM", BASIC="basic", DELEGATE="delegate",
                        UTC=UTC, EWSDateTime=datetime, FailFast=lambda: "fail-fast",
                        UnauthorizedError=UnauthorizedError, ErrorFolderNotFound=ErrorFolderNotFound)
    processed = Folder("Обработано")
    inbox = Folder("Inbox", [processed])
    store["inbox"], store["processed"] = inbox, processed
    inbox.add(Message("E1", "1c@company.ru", "Показатели", datetime(2026, 10, 1, 9, tzinfo=UTC),
                      [FileAttachment("показатели.csv", indicators_csv()),
                       FileAttachment("sign.png", b"\x89PNG", "image/png", is_inline=True)]))
    inbox.add(Message("E2", "x@evil.ru", "Чужое", datetime(2026, 10, 2, 9, tzinfo=UTC),
                      [FileAttachment("x.csv", b"1;2")]))
    return exl


@contextlib.contextmanager
def _ews(monkeypatch):
    store: dict = {}
    monkeypatch.setitem(sys.modules, "exchangelib", fake_exchangelib(store))
    yield store


def _ews_body(**config) -> dict:
    return {"kind": "exchange", "name": "Exchange", "config": {
        "mode": "ews", "ews_url": "https://mail.company.ru/EWS/Exchange.asmx", "username": "COMPANY\\dash",
        "mailbox": "data@company.ru", "allowed_senders": ALLOWED, "move_to": PROCESSED, **config},
        "secrets": {"password": "ews-pass"}}


def test_ews_check_and_run(admin, db, monkeypatch):
    import logging

    logger = logging.getLogger("exchangelib")
    monkeypatch.setattr(logger, "level", logging.DEBUG)
    with _ews(monkeypatch) as store:
        item = _create(admin, _ews_body(verify_tls=False, ews_auth="basic"))
        check = admin.post(f"/api/integrations/{item['id']}/check").json()
        assert logger.level == logging.INFO, "заголовки с паролем Basic не попадают в журнал и при LOG_LEVEL=DEBUG"
        assert check["ok"] and check["message"] == ("Ящик доступен (Exchange Server (EWS)): в папке «Входящие» "
                                                    "писем 2, непрочитанных 2")
        assert store["config"]["auth_type"] == "basic" and store["config"]["retry_policy"] == "fail-fast"
        assert store["adapter_during"] == "no-verify-adapter", "«не проверять сертификат» — на время работы"
        assert sys.modules["exchangelib"].BaseProtocol.HTTP_ADAPTER_CLS == "requests-adapter", "и возвращается"
        run = _run(admin, item)
        assert run["status"] == "ok" and run["summary"]["added"] == 1 and run["summary"]["skipped_sender"] == 1
        assert [m.id for m in store["processed"].items] == ["E1"] and store["processed"].items[0].is_read
        assert store["saved"] == [("E1", ("is_read",))] and store["closed"]
        assert _items(db, item["id"])["показатели.csv"].source_ref.startswith("exchange:E1@ex.company.ru:")
        admin.patch(f"/api/integrations/{item['id']}", json={"secrets": {"password": "wrong"}})
        check = admin.post(f"/api/integrations/{item['id']}/check").json()
        assert not check["ok"] and check["details"]["code"] == "auth" and "COMPANY\\dash" in check["message"]


def test_ews_cursor_mode(admin, db, monkeypatch):
    with _ews(monkeypatch) as store:
        item = _create(admin, _ews_body(mark_read=False, move_to=None))
        first = _run(admin, item)
        assert first["summary"]["processed"] == 1 and first["summary"]["added"] == 1
        db.expire_all()
        assert db.get(Integration, item["id"]).state["cursor"] == {"received": "2026-10-02T09:00:00Z", "ids": ["E2"]}
        second = _run(admin, item)
        assert second["summary"]["messages"] == 0, "письма до курсора и письмо этой секунды не берутся снова"
        db.execute(update(Integration).where(Integration.id == item["id"]).values(state={}))
        db.commit()
        third = _run(admin, item)
        assert third["summary"]["seen"] == 1 and third["summary"]["added"] == 0
        assert db.scalar(select(func.count()).select_from(InboxItem).where(InboxItem.integration_id == item["id"])) \
            == 1
        assert not store["inbox"].items[0].is_read
