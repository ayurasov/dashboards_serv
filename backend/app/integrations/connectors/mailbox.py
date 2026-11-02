"""Почтовые ящики коннектора «Почтовый ящик (Exchange)»: одна модель для трёх способов подключения.

- ImapBox — IMAP4rev1 стандартной библиотекой (imaplib): SSL/TLS или STARTTLS (если сервер его объявляет),
  письма — BODY.PEEK (без пометки прочитанным при чтении), курсор — UIDVALIDITY и последний UID; имена папок —
  в модифицированной UTF-7 (RFC 3501), «Входящие» — INBOX; перенос — MOVE, иначе COPY + \\Deleted + EXPUNGE;
- GraphBox — Microsoft Graph (Microsoft 365) через HttpClient каркаса: токен приложения (client credentials)
  на <адрес входа>/<тенант>/oauth2/v2.0/token, письма — /v1.0/users/<ящик>/mailFolders/<папка>/messages,
  вложения — …/attachments/<id>/$value; курсор — receivedDateTime и id писем этой секунды;
- EwsBox — Exchange Server по EWS через exchangelib (пакет необязательный: без него — понятная ошибка), NTLM или
  Basic, без автообнаружения; курсор — как у Graph.

Ящик открывается в with; ошибки сервера — IntegrationError с текстом для администратора. Пароль и секрет
приложения не попадают ни в тексты ошибок, ни в журнал.
"""
from __future__ import annotations

import base64
import contextlib
import email
import imaplib
import logging
import re
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.parser import BytesHeaderParser
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any
from urllib.parse import quote

from ..http import HttpClient, HttpResponse, IntegrationError
from .common import ANY_STATUS, download_limit, inbox_limit, iso, parse_time

SCAN_LIMIT = 500          # писем за запуск просматривается (заголовки); обрабатывает их коннектор
TIMEOUT = 30
INBOX_NAMES = ("inbox", "входящие")
GRAPH_URL = "https://graph.microsoft.com"
LOGIN_URL = "https://login.microsoftonline.com"
GRAPH_TITLE = "Microsoft 365"


@dataclass
class Attachment:
    name: str
    content_type: str
    content: bytes | None        # None — больше предела входящих, не скачивается
    size: int = 0


@dataclass
class Mail:
    key: str                     # UID (IMAP), id письма (Graph, EWS)
    message_id: str
    sender: str
    subject: str
    received: datetime | None    # UTC без tzinfo
    has_attachments: bool = True
    native: Any = None           # объект письма exchangelib


def folder_parts(path: str | None) -> list[str]:
    """«Входящие/Выгрузки» → ["Входящие", "Выгрузки"]; пусто — входящие."""
    return [p.strip() for p in re.split(r"[/\\]", path or "") if p.strip()]


class Mailbox(ABC):
    label = "Почтовый ящик"

    def __enter__(self) -> Mailbox:
        try:
            self.open()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def stats(self) -> tuple[int, int]:
        """(писем в папке, непрочитанных)."""

    @abstractmethod
    def folder_exists(self, path: str) -> bool: ...

    @abstractmethod
    def messages(self, *, unread_only: bool, cursor: dict | None) -> list[Mail]:
        """Заголовки писем папки по порядку получения (не больше SCAN_LIMIT): непрочитанные или новые после курсора."""

    @abstractmethod
    def attachments(self, mail: Mail) -> list[Attachment]: ...

    @abstractmethod
    def mark_read(self, mail: Mail) -> None: ...

    @abstractmethod
    def move(self, mail: Mail, folder: str) -> None: ...

    def cursor(self, mails: list[Mail], old: dict | None) -> dict | None:
        """Курсор по времени получения: самое позднее и id писем этой секунды (они не берутся повторно)."""
        times = [m.received for m in mails if m.received is not None]
        if not times:
            return old
        last = max(times).replace(microsecond=0)
        ids = [m.key for m in mails if m.received is not None and m.received.replace(microsecond=0) == last]
        if old and parse_time(old.get("received")) == last:
            ids = list(dict.fromkeys([*(old.get("ids") or []), *ids]))
        return {"received": iso(last), "ids": ids[-200:]}


# ================================================================ IMAP

def mutf7(text: str) -> str:
    """Имя папки IMAP в модифицированной UTF-7 (RFC 3501, 5.1.3): «Входящие» → «&BBIERQQ+BDQETwRJBDgENQ-»."""
    out: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        if pending:
            raw = base64.b64encode("".join(pending).encode("utf-16-be")).decode().rstrip("=")
            out.append("&" + raw.replace("/", ",") + "-")
            pending.clear()

    for ch in text:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            pending.append(ch)
    flush()
    return "".join(out)


def imap_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return datetime(*value.utctimetuple()[:6]) if value.tzinfo else value


class ImapBox(Mailbox):
    label = "IMAP"

    def __init__(self, *, host: str, port: int, use_ssl: bool, login: str, password: str, folder: str,
                 verify: bool = True, timeout: int = TIMEOUT):
        self.host, self.port, self.use_ssl = host, port, use_ssl
        self._login_name, self._password = login, password
        self.folder, self.verify, self.timeout = folder, verify, timeout
        self.conn: imaplib.IMAP4 | None = None
        self.delimiter = "/"
        self.uidvalidity: int | None = None
        self.where = f"{host}:{port}"

    def _context(self) -> ssl.SSLContext:
        context = ssl.create_default_context()
        if not self.verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context

    @contextlib.contextmanager
    def _errors(self, doing: str):
        try:
            yield
        except IntegrationError:
            raise
        except ssl.SSLError as exc:
            raise IntegrationError(f"Ошибка TLS при подключении к {self.where}: если сервер использует самоподписанный "
                                   f"или корпоративный сертификат, выключите «Проверять TLS-сертификат» ({exc.reason})",
                                   code="tls", short="Ошибка TLS-сертификата почтового сервера") from None
        except TimeoutError:
            raise IntegrationError(f"Почтовый сервер {self.where} не ответил за {self.timeout} с ({doing})",
                                   code="read_timeout", short="Почтовый сервер не отвечает") from None
        except imaplib.IMAP4.abort:
            raise IntegrationError(f"Почтовый сервер {self.where} прервал соединение ({doing})", code="connect",
                                   short="Почтовый сервер прервал соединение") from None
        except imaplib.IMAP4.error as exc:
            raise IntegrationError(f"Почтовый сервер {self.where} отклонил команду ({doing}): {_text(exc)}",
                                   code="imap_error", short="Почтовый сервер отклонил команду") from None
        except OSError as exc:
            raise IntegrationError(f"Не удалось подключиться к почтовому серверу {self.where}: проверьте сервер, "
                                   f"порт и доступность сети ({exc.strerror or exc.__class__.__name__})",
                                   code="connect", short="Не удалось подключиться к почтовому серверу") from None

    def open(self) -> None:
        with self._errors("подключение"):
            if self.use_ssl:
                self.conn = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=self._context(), timeout=self.timeout)
            else:
                self.conn = imaplib.IMAP4(self.host, self.port, timeout=self.timeout)
                if "STARTTLS" in self.conn.capabilities:
                    self.conn.starttls(ssl_context=self._context())
        conn = self.conn
        try:
            with self._errors("вход"):
                if f"{self._login_name}{self._password}".isascii():
                    conn.login(imap_quote(self._login_name), self._password)
                else:   # кириллица в пароле: LOGIN — только ASCII, AUTHENTICATE PLAIN — UTF-8
                    conn.authenticate("PLAIN", lambda _: f"\0{self._login_name}\0{self._password}".encode())
        except IntegrationError as exc:
            if exc.code == "imap_error":
                raise IntegrationError(f"Почтовый сервер {self.where} отклонил вход: неверный логин или пароль",
                                       code="auth", short="Почтовый сервер отклонил учётные данные") from None
            raise
        with self._errors("список папок"):
            typ, data = conn.list('""', '""')
            match = re.search(rb'\) "((?:\\.|[^"])*)"', data[0]) if typ == "OK" and data and data[0] else None
            if match:
                self.delimiter = match.group(1).decode().replace("\\\\", "\\") or "/"
        mailbox = self.name(self.folder)
        with self._errors("выбор папки"):
            typ, data = conn.select(mailbox)
            if typ != "OK":
                raise IntegrationError(f"Папка «{self.folder or 'Входящие'}» не найдена в ящике ({_text(data)})",
                                       code="not_found")
            _code, values = conn.response("UIDVALIDITY")
            self.uidvalidity = int(values[0]) if values and values[0] else None
        self.mailbox = mailbox

    def close(self) -> None:
        conn, self.conn = self.conn, None
        if conn is None:
            return
        with contextlib.suppress(Exception):
            conn.logout()

    def name(self, path: str | None) -> str:
        parts = folder_parts(path) or ["INBOX"]
        if parts[0].casefold() in INBOX_NAMES:
            parts[0] = "INBOX"
        return imap_quote(mutf7(self.delimiter.join(parts)))

    def stats(self) -> tuple[int, int]:
        with self._errors("состояние папки"):
            typ, data = self.conn.status(self.mailbox, "(MESSAGES UNSEEN)")
        text = b" ".join(d for d in data if isinstance(d, bytes)) if typ == "OK" else b""
        total = re.search(rb"MESSAGES (\d+)", text)
        unseen = re.search(rb"UNSEEN (\d+)", text)
        return int(total.group(1)) if total else 0, int(unseen.group(1)) if unseen else 0

    def folder_exists(self, path: str) -> bool:
        with self._errors("проверка папки"):
            typ, _data = self.conn.status(self.name(path), "(MESSAGES)")
        return typ == "OK"

    def messages(self, *, unread_only: bool, cursor: dict | None) -> list[Mail]:
        same = bool(cursor) and cursor.get("uidvalidity") == self.uidvalidity
        after = int(cursor.get("uid") or 0) if same else 0
        if unread_only:
            criteria: tuple[str, ...] = ("UNSEEN",)
        else:
            criteria = ("UID", f"{after + 1}:*") if after else ("ALL",)
        with self._errors("поиск писем"):
            typ, data = self.conn.uid("SEARCH", *criteria)
        uids = sorted(int(x) for x in (data[0] or b"").split() if x.isdigit()) if typ == "OK" and data else []
        if not unread_only:
            uids = [u for u in uids if u > after]      # «n:*» возвращает последнее письмо и когда n больше
        uids = uids[:SCAN_LIMIT]
        if not uids:
            return []
        with self._errors("заголовки писем"):
            typ, data = self.conn.uid("FETCH", ",".join(map(str, uids)),
                                      "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID DATE)])")
        mails = []
        for meta, raw in _fetched(data):
            uid = re.search(rb"UID (\d+)", meta)
            if uid is None:
                continue
            headers = BytesHeaderParser(policy=policy.default).parsebytes(raw or b"")
            try:
                received = _utc(parsedate_to_datetime(str(headers.get("Date") or "")))
            except (TypeError, ValueError):
                received = None
            mails.append(Mail(key=uid.group(1).decode(), message_id=_message_id(headers.get("Message-ID")),
                              sender=parseaddr(str(headers.get("From") or ""))[1].lower(),
                              subject=str(headers.get("Subject") or ""), received=received))
        return sorted(mails, key=lambda m: int(m.key))

    def attachments(self, mail: Mail) -> list[Attachment]:
        with self._errors("получение письма"):
            typ, data = self.conn.uid("FETCH", mail.key, "(UID BODY.PEEK[])")
        raw = next((body for _meta, body in _fetched(data) if body), b"")
        message = email.message_from_bytes(raw, policy=policy.default)
        out = []
        for part in message.walk():
            if part.is_multipart():
                continue
            name = part.get_filename()
            if not name:
                continue
            content = part.get_payload(decode=True) or b""
            out.append(Attachment(str(name), part.get_content_type(), content, len(content)))
        return out

    def mark_read(self, mail: Mail) -> None:
        with self._errors("пометка прочитанным"):
            typ, data = self.conn.uid("STORE", mail.key, "+FLAGS", r"(\Seen)")
        if typ != "OK":
            raise IntegrationError(f"Почтовый сервер не пометил письмо прочитанным: {_text(data)}", code="imap_error")

    def move(self, mail: Mail, folder: str) -> None:
        target = self.name(folder)
        conn = self.conn
        with self._errors("перенос письма"):
            if "MOVE" in conn.capabilities:
                typ, data = conn.uid("MOVE", mail.key, target)
            else:
                typ, data = conn.uid("COPY", mail.key, target)
                if typ == "OK":
                    conn.uid("STORE", mail.key, "+FLAGS", r"(\Deleted)")
                    if "UIDPLUS" in conn.capabilities:
                        conn.uid("EXPUNGE", mail.key)
                    else:
                        conn.expunge()
        if typ != "OK":
            raise IntegrationError(f"Не удалось перенести письмо в папку «{folder}»: {_text(data)}", code="imap_error")

    def cursor(self, mails: list[Mail], old: dict | None) -> dict | None:
        uids = [int(m.key) for m in mails]
        if old and old.get("uidvalidity") == self.uidvalidity:
            uids.append(int(old.get("uid") or 0))
        return {"uidvalidity": self.uidvalidity, "uid": max(uids)} if uids else old


def _fetched(data: list) -> list[tuple[bytes, bytes]]:
    """Ответ FETCH imaplib → [(сведения о письме, содержимое литерала)]: UID может прийти и после литерала."""
    records: list[list[bytes]] = []
    for part in data or []:
        if isinstance(part, tuple) and len(part) == 2:
            records.append([bytes(part[0]), bytes(part[1])])
        elif isinstance(part, bytes) and records:
            records[-1][0] += part
    return [(meta, body) for meta, body in records]


def _message_id(value: Any) -> str:
    return str(value or "").strip().strip("<>").strip()


def _text(value: Any) -> str:
    if isinstance(value, list | tuple):
        value = b" ".join(v for v in value if isinstance(v, bytes)) if value else b""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value)[:300]


# ================================================================ Microsoft Graph

def graph_error(resp: HttpResponse, mailbox: str, what: str = "") -> IntegrationError:
    try:
        body = resp.json()
    except (ValueError, UnicodeDecodeError):
        body = {}
    error = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else {}
    code = str(error.get("code") or "")
    message = str(error.get("message") or "")[:300]
    tag = f", {code}" if code else ""
    if resp.status == 401:
        return IntegrationError(f"{GRAPH_TITLE} не принял токен приложения (401{tag})", code="auth", status=401)
    if resp.status == 403:
        return IntegrationError(f"У приложения нет доступа к ящику «{mailbox}» (403{tag}): нужны права приложения "
                                "Mail.ReadWrite (и разрешение ApplicationAccessPolicy на этот ящик)", code="forbidden",
                                status=403, short=f"У приложения нет доступа к ящику {GRAPH_TITLE}")
    if resp.status == 404:
        if what:
            return IntegrationError(what, code="not_found", status=404)
        extra = f": {message}" if message else ""
        return IntegrationError(f"Ящик «{mailbox}» не найден в {GRAPH_TITLE} (404{tag}){extra}", code="not_found",
                                status=404, short=f"Ящик не найден в {GRAPH_TITLE}")
    return IntegrationError(f"{GRAPH_TITLE} вернул ошибку {resp.status}{tag}{': ' + message if message else ''}",
                            code="http_error", status=resp.status, short=f"{GRAPH_TITLE} вернул ошибку {resp.status}")


def token_error(resp: HttpResponse, tenant: str, client_id: str) -> IntegrationError:
    try:
        body = resp.json()
    except (ValueError, UnicodeDecodeError):
        body = {}
    body = body if isinstance(body, dict) else {}
    error = str(body.get("error") or "")
    match = re.search(r"AADSTS\d+", str(body.get("error_description") or ""))
    aad = match.group(0) if match else ""
    tag = f" ({aad or error or resp.status})"
    if aad in ("AADSTS7000215", "AADSTS7000222") or (error == "invalid_client" and not aad):
        text = (f"{GRAPH_TITLE} отклонил секрет приложения{tag}: введите значение секрета (не его идентификатор) и "
                "проверьте срок его действия")
    elif aad == "AADSTS700016" or error == "unauthorized_client":
        text = f"Приложение {client_id} не найдено в тенанте «{tenant}»{tag}"
    elif aad in ("AADSTS90002", "AADSTS900023"):
        text = f"Тенант «{tenant}» не найден{tag}: укажите Directory ID (GUID) или домен *.onmicrosoft.com"
    else:
        text = f"{GRAPH_TITLE} не выдал токен приложения{tag}"
    return IntegrationError(text, code="auth", status=resp.status, short=f"{GRAPH_TITLE} отклонил учётные данные "
                                                                         "приложения")


class GraphBox(Mailbox):
    label = "Microsoft Graph"

    def __init__(self, *, tenant: str, client_id: str, client_secret: str, mailbox: str, folder: str,
                 graph_url: str | None = None, login_url: str | None = None, verify: bool = True,
                 detailed: bool = True):
        self.tenant, self.client_id, self._secret = tenant, client_id, client_secret
        self.mailbox, self.folder = mailbox, folder
        self.graph_url = graph_url or GRAPH_URL
        self.login_url = login_url or LOGIN_URL
        self.verify, self.detailed = verify, detailed
        self.api: HttpClient | None = None
        self.base = f"v1.0/users/{quote(mailbox, safe='@')}"
        self._folders: dict[str, str] = {}

    def _client(self, url: str, **kwargs) -> HttpClient:
        return HttpClient(url, kind="exchange", title=GRAPH_TITLE, cookies=False, verify=self.verify,
                          detailed=self.detailed, **kwargs)

    def open(self) -> None:
        with self._client(self.login_url) as client:
            resp = client.request("POST", f"{quote(self.tenant, safe='')}/oauth2/v2.0/token", expect=ANY_STATUS,
                                  data={"client_id": self.client_id, "client_secret": self._secret,
                                        "scope": f"{self.graph_url.rstrip('/')}/.default",
                                        "grant_type": "client_credentials"})
            if resp.status != 200:
                raise token_error(resp, self.tenant, self.client_id)
            token = client.parse(resp, dict).get("access_token")
        if not isinstance(token, str) or not token:
            raise IntegrationError(f"{GRAPH_TITLE} не выдал токен приложения — проверьте адрес входа",
                                   code="bad_response")
        self.api = self._client(self.graph_url, headers={"Authorization": f"Bearer {token}"},
                                max_bytes=download_limit())
        self.folder_id = self.resolve(self.folder)

    def close(self) -> None:
        if self.api is not None:
            self.api.close()
            self.api = None

    def call(self, method: str, path: str, *, params: dict | None = None, json: Any = None,
             expect: tuple[int, ...] = (200,), what: str = "") -> HttpResponse:
        resp = self.api.request(method, path, params=params, json=json, expect=ANY_STATUS)
        if resp.status not in expect:
            raise graph_error(resp, self.mailbox, what)
        return resp

    def get(self, path: str, params: dict | None = None, what: str = "") -> dict:
        return self.api.parse(self.call("GET", path, params=params, what=what), dict)

    def _child(self, path: str, name: str) -> str:
        escaped = name.replace("'", "''")
        data = self.get(path, {"$filter": f"displayName eq '{escaped}'", "$select": "id,displayName", "$top": "10"})
        found = next((f for f in data.get("value") or [] if isinstance(f, dict) and f.get("id")), None)
        if found is None:
            raise IntegrationError(f"Папка «{name}» не найдена в ящике «{self.mailbox}»", code="not_found")
        return str(found["id"])

    def resolve(self, path: str | None) -> str:
        key = "/".join(p.casefold() for p in folder_parts(path))
        if key in self._folders:
            return self._folders[key]
        parts = folder_parts(path)
        if not parts or parts[0].casefold() in INBOX_NAMES:
            folder_id, rest = "inbox", parts[1:]
            self.get(f"{self.base}/mailFolders/inbox", {"$select": "id"})
        else:
            folder_id, rest = self._child(f"{self.base}/mailFolders", parts[0]), parts[1:]
        for name in rest:
            folder_id = self._child(f"{self.base}/mailFolders/{folder_id}/childFolders", name)
        self._folders[key] = folder_id
        return folder_id

    def stats(self) -> tuple[int, int]:
        data = self.get(f"{self.base}/mailFolders/{self.folder_id}", {"$select": "totalItemCount,unreadItemCount"})
        return int(data.get("totalItemCount") or 0), int(data.get("unreadItemCount") or 0)

    def folder_exists(self, path: str) -> bool:
        try:
            self.resolve(path)
        except IntegrationError as exc:
            if exc.code == "not_found":
                return False
            raise
        return True

    def messages(self, *, unread_only: bool, cursor: dict | None) -> list[Mail]:
        since = (cursor or {}).get("received") or "1900-01-01T00:00:00Z"
        skip = set((cursor or {}).get("ids") or [])
        # Свойство $orderby должно первым стоять и в $filter (ограничение Graph)
        filters = [f"receivedDateTime ge {since}"] + (["isRead eq false"] if unread_only else [])
        params: dict | None = {"$filter": " and ".join(filters), "$orderby": "receivedDateTime asc", "$top": "50",
                               "$select": "id,internetMessageId,subject,from,receivedDateTime,hasAttachments,isRead"}
        path = f"{self.base}/mailFolders/{self.folder_id}/messages"
        mails: list[Mail] = []
        while path and len(mails) < SCAN_LIMIT:
            data = self.get(path, params)
            for raw in data.get("value") or []:
                if not isinstance(raw, dict) or not raw.get("id") or raw["id"] in skip:
                    continue
                sender = ((raw.get("from") or {}).get("emailAddress") or {}).get("address") or ""
                mails.append(Mail(key=str(raw["id"]), message_id=_message_id(raw.get("internetMessageId")),
                                  sender=str(sender).lower(), subject=str(raw.get("subject") or ""),
                                  received=parse_time(raw.get("receivedDateTime")),
                                  has_attachments=bool(raw.get("hasAttachments"))))
                if len(mails) >= SCAN_LIMIT:
                    break
            path, params = data.get("@odata.nextLink"), None
        return mails

    def attachments(self, mail: Mail) -> list[Attachment]:
        if not mail.has_attachments:
            return []
        path = f"{self.base}/messages/{quote(mail.key, safe='')}/attachments"
        data = self.get(path, {"$select": "id,name,contentType,size,isInline"})
        out = []
        for raw in data.get("value") or []:
            if not isinstance(raw, dict) or raw.get("@odata.type") != "#microsoft.graph.fileAttachment" \
                    or raw.get("isInline"):
                continue
            size = int(raw.get("size") or 0)
            name, ctype = str(raw.get("name") or "файл"), str(raw.get("contentType") or "")
            if size > inbox_limit():
                out.append(Attachment(name, ctype, None, size))
                continue
            content = self.call("GET", f"{path}/{quote(str(raw.get('id')), safe='')}/$value").content
            out.append(Attachment(name, ctype, content, len(content)))
        return out

    def mark_read(self, mail: Mail) -> None:
        self.call("PATCH", f"{self.base}/messages/{quote(mail.key, safe='')}", json={"isRead": True})

    def move(self, mail: Mail, folder: str) -> None:
        target = self.resolve(folder)
        self.call("POST", f"{self.base}/messages/{quote(mail.key, safe='')}/move", json={"destinationId": target},
                  expect=(200, 201))


# ================================================================ Exchange Web Services (exchangelib)

def load_exchangelib():
    """exchangelib — необязательная зависимость: без неё режим EWS недоступен (IMAP и Graph работают)."""
    try:
        import exchangelib
    except ImportError:
        raise IntegrationError("Для режима Exchange Server (EWS) на сервере нужен пакет exchangelib — установите его "
                               "(pip install exchangelib, он указан в requirements.txt) или выберите режим IMAP или "
                               "Microsoft Graph", code="dependency_missing",
                               short="Режим Exchange Server (EWS) недоступен на сервере") from None
    # exchangelib на уровне DEBUG пишет заголовки запросов, а с Basic в них — пароль: не ниже INFO при любом LOG_LEVEL
    logger = logging.getLogger("exchangelib")
    if logger.getEffectiveLevel() < logging.INFO:
        logger.setLevel(logging.INFO)
    return exchangelib


@dataclass
class EwsBox(Mailbox):
    url: str
    username: str
    password: str = field(repr=False)
    mailbox: str
    folder: str
    auth: str = "ntlm"
    verify: bool = True
    label = "Exchange Server (EWS)"

    def __post_init__(self):
        self.account = None
        self._adapter = None
        self.exl = None

    @contextlib.contextmanager
    def _errors(self, doing: str):
        try:
            yield
        except IntegrationError:
            raise
        except Exception as exc:  # noqa: BLE001 — исключения exchangelib различаются по имени класса
            name = type(exc).__name__
            if name in ("UnauthorizedError", "ErrorAccessDenied", "UnauthorizedAccessError"):
                raise IntegrationError(f"Exchange отклонил учётную запись {self.username} ({doing}): неверный логин "
                                       "или пароль либо нет доступа к ящику", code="auth",
                                       short="Exchange отклонил учётные данные подключения") from None
            if name in ("ErrorFolderNotFound", "DoesNotExist"):
                raise IntegrationError(f"Папка не найдена в ящике {self.mailbox} ({doing})", code="not_found") from None
            if name in ("ErrorNonExistentMailbox", "ErrorMailboxStoreUnavailable"):
                raise IntegrationError(f"Ящик {self.mailbox} не найден в Exchange", code="not_found") from None
            if name in ("TransportError", "RateLimitError", "ConnectionError", "SSLError", "ErrorServerBusy") \
                    or isinstance(exc, OSError):
                raise IntegrationError(f"Не удалось связаться с Exchange {self.url} ({doing}): проверьте адрес EWS и "
                                       f"доступность сети ({name})", code="connect",
                                       short="Не удалось подключиться к Exchange") from None
            raise IntegrationError(f"Ошибка Exchange ({doing}): {name}: {str(exc)[:300]}", code="ews_error",
                                   short="Ошибка Exchange — подробности у администратора") from None

    def open(self) -> None:
        exl = self.exl = load_exchangelib()
        if not self.verify:
            # Настройка exchangelib общая для процесса: на время работы ящика, затем возвращается
            self._adapter = exl.BaseProtocol.HTTP_ADAPTER_CLS
            exl.BaseProtocol.HTTP_ADAPTER_CLS = exl.NoVerifyHTTPAdapter
        with self._errors("подключение"):
            credentials = exl.Credentials(self.username, self.password)
            config = exl.Configuration(service_endpoint=self.url, credentials=credentials,
                                       auth_type=exl.BASIC if self.auth == "basic" else exl.NTLM,
                                       retry_policy=exl.FailFast())
            self.account = exl.Account(primary_smtp_address=self.mailbox, config=config, autodiscover=False,
                                       access_type=exl.DELEGATE)
            self.target = self.resolve(self.folder)

    def close(self) -> None:
        if self._adapter is not None and self.exl is not None:
            self.exl.BaseProtocol.HTTP_ADAPTER_CLS = self._adapter
            self._adapter = None
        account, self.account = self.account, None
        if account is not None:
            with contextlib.suppress(Exception):
                account.protocol.close()

    def resolve(self, path: str | None):
        parts = folder_parts(path)
        with self._errors(f"папка «{path or 'Входящие'}»"):
            if not parts or parts[0].casefold() in INBOX_NAMES:
                node, rest = self.account.inbox, parts[1:]
            else:
                node, rest = self.account.msg_folder_root, parts
            for name in rest:
                node = node / name
        return node

    def stats(self) -> tuple[int, int]:
        with self._errors("состояние папки"):
            self.target.refresh()
            return int(self.target.total_count or 0), int(self.target.unread_count or 0)

    def folder_exists(self, path: str) -> bool:
        try:
            self.resolve(path)
        except IntegrationError as exc:
            if exc.code == "not_found":
                return False
            raise
        return True

    def messages(self, *, unread_only: bool, cursor: dict | None) -> list[Mail]:
        exl = self.exl
        since = parse_time((cursor or {}).get("received"))
        skip = set((cursor or {}).get("ids") or [])
        mails: list[Mail] = []
        with self._errors("поиск писем"):
            query = self.target.all()
            if unread_only:
                query = query.filter(is_read=False)
            if since is not None:
                query = query.filter(datetime_received__gte=exl.EWSDateTime(*since.timetuple()[:6], tzinfo=exl.UTC))
            for item in query.order_by("datetime_received")[:SCAN_LIMIT + len(skip)]:
                if not isinstance(item, exl.Message) or item.id in skip:
                    continue
                sender = getattr(item.sender, "email_address", "") if item.sender else ""
                mails.append(Mail(key=str(item.id), message_id=_message_id(item.message_id),
                                  sender=str(sender or "").lower(), subject=str(item.subject or ""),
                                  received=_utc(item.datetime_received), has_attachments=bool(item.has_attachments),
                                  native=item))
                if len(mails) >= SCAN_LIMIT:
                    break
        return mails

    def attachments(self, mail: Mail) -> list[Attachment]:
        exl = self.exl
        out = []
        with self._errors("вложения письма"):
            for item in mail.native.attachments or []:
                if not isinstance(item, exl.FileAttachment) or item.is_inline:
                    continue
                size = int(item.size or 0)
                name, ctype = str(item.name or "файл"), str(item.content_type or "")
                if size > inbox_limit():
                    out.append(Attachment(name, ctype, None, size))
                    continue
                content = item.content or b""
                out.append(Attachment(name, ctype, content, len(content)))
        return out

    def mark_read(self, mail: Mail) -> None:
        with self._errors("пометка прочитанным"):
            mail.native.is_read = True
            mail.native.save(update_fields=["is_read"])

    def move(self, mail: Mail, folder: str) -> None:
        target = self.resolve(folder)
        with self._errors("перенос письма"):
            mail.native.move(to_folder=target)
