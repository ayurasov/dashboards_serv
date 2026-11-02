"""Общее для коннекторов «По Делу», «Пульс проекта» и «Почтовый ящик»: сессия служебной учётной записи
Flask-приложения партнёра, понятные ошибки его ответов, отбор файлов данных и подписи статусов входящих.

Сессия партнёра (PartnerSession) — как вход браузера и как синхронизация структуры в «Пульсе» (ADR-0009 там):
GET <csrf> → POST /api/auth/login {login, password} с заголовками X-CSRF-Token, Referer и Origin → cookie
сессии → запросы (изменения — с X-CSRF-Token) → POST /api/auth/logout. Выход выполняется всегда: и после
ошибки входа (сессия с CSRF-токеном уже создана), и после ошибки в работе — блоком with. Сеть — только через
HttpClient каркаса (адрес, <ВИД>_ALLOWED_HOSTS, без перенаправлений, таймауты, предел размера).
Пароль уходит только в теле запроса входа и нигде не записывается: ни в журнал сервера, ни в тексты ошибок.
"""
from __future__ import annotations

import fnmatch
import hashlib
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from ...core.config import settings
from ..http import CONNECT_TIMEOUT, MAX_BYTES, READ_TIMEOUT, HttpClient, HttpResponse, IntegrationError

if TYPE_CHECKING:
    from ...models import InboxItem

# Любой ответ, кроме перенаправлений (их HttpClient превращает в ошибку сам): статус разбирает вызывающий
ANY_STATUS = tuple(s for s in range(200, 600) if not 300 <= s < 400)
# Файлы, которые могут оказаться набором входящих (Excel, CSV, JSON); картинки, PDF и архивы не берутся
DATA_EXTENSIONS = (".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".txt", ".json")


def is_data_file(name: str | None) -> bool:
    return (name or "").strip().lower().endswith(DATA_EXTENSIONS)


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def inbox_limit() -> int:
    """Предел файла входящих в байтах (INBOX_MAX_MB)."""
    return settings.inbox_max_mb * 1024 * 1024


def download_limit() -> int:
    """Предел ответа при скачивании файла: не меньше предела входящих (больше — элемент «ошибка» во входящих)."""
    return max(MAX_BYTES, inbox_limit() + 1024 * 1024)


def status_text(item: InboxItem) -> str:
    """Статус элемента входящих для отметки у источника («применён», «ожидает подтверждения» …)."""
    if item.status == "applied":
        return "применён"
    if item.status == "pending":
        return "ожидает подтверждения" if item.plan_ok else "в плане ошибки — нужна проверка на экране «Входящие»"
    if item.status == "duplicate":
        return f"повтор — этот файл уже получен (элемент №{item.duplicate_of_id})"
    if item.status in ("received", "recognized"):
        return "набор не распознан — нужно выбрать набор на экране «Входящие»"
    if item.status == "error":
        return f"ошибка: {item.error}"[:300] if item.error else "ошибка"
    return item.status


def parse_time(value: Any) -> datetime | None:
    """ISO-время партнёра («…Z», «…+03:00» или без зоны — UTC) → UTC без tzinfo; ошибка — None."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    return moment


def iso(moment: datetime) -> str:
    """UTC без tzinfo → «ГГГГ-ММ-ДДTЧЧ:ММ:ССZ» (с точностью до секунды)."""
    return moment.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def rule_lines(text: str | None) -> list[tuple[int, str, str]]:
    """Строки «левое = правое» (разделитель «=», «→», «->» или табуляция) → [(номер строки, левое, правое)];
    пустые строки и строки с «#» в начале пропускаются. Строка без разделителя — ValueError(номер)."""
    out = []
    for number, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"\s*(?:→|->|=|\t)\s*", line, maxsplit=1)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            raise ValueError(number)
        out.append((number, " ".join(parts[0].split()), " ".join(parts[1].split())))
    return out


def matches(patterns: Iterable[str], value: str) -> bool:
    text = (value or "").casefold()
    return any(fnmatch.fnmatchcase(text, p.casefold()) for p in patterns)


# ---------------------------------------------------------------- ошибки ответов партнёра

def _body(resp: HttpResponse) -> dict:
    try:
        data = resp.json()
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def partner_error(title: str, resp: HttpResponse, path: str, *, login: bool = False, denied: str | None = None,
                  not_found: str | None = None) -> IntegrationError:
    """Ошибка ответа Flask-приложения партнёра ({"error": код, "message": текст}) с подробным текстом для
    администратора и кратким — остальным."""
    data = _body(resp)
    code = data.get("error") if isinstance(data.get("error"), str) else ""
    message = str(data.get("message") or "")[:300] if isinstance(data.get("message"), str) else ""
    suffix = f": {message}" if message else ""
    status = resp.status
    where = "/" + path.lstrip("/")
    if status == 401:
        if login:
            return IntegrationError(f"«{title}» отклонила вход: неверный логин или пароль служебной учётной записи",
                                    code="auth", status=401,
                                    short=f"«{title}» отклонила учётные данные подключения")
        return IntegrationError(f"«{title}» не приняла сессию служебной учётной записи (401){suffix} — проверьте, что "
                                "прокси не убирает cookie, и повторите", code="session", status=401,
                                short=f"«{title}» не приняла сессию подключения")
    if status == 403:
        if code == "account_disabled":
            return IntegrationError(f"Служебная учётная запись отключена в «{title}»", code="account_disabled",
                                    status=403)
        if code == "no_account":
            return IntegrationError(f"Служебной учётной записи нет в «{title}»{suffix}", code="no_account",
                                    status=403, short=f"Служебной учётной записи нет в «{title}»")
        return IntegrationError(denied or f"Недостаточно прав в «{title}» (403){suffix}", code="forbidden",
                                status=403, short=denied or f"Недостаточно прав в «{title}»")
    if status == 400 and code == "csrf_error":
        return IntegrationError(f"«{title}» отклонила запрос защитой от подделки (CSRF){suffix.rstrip('. ')}. Укажите "
                                f"в подключении адрес, по которому открывается «{title}» (та же схема http/https и "
                                "тот же узел), и проверьте, что прокси не убирает cookie и заголовок Referer",
                                code="csrf", status=400, short=f"«{title}» отклонила запрос защитой от подделки (CSRF)")
    if status == 429:
        extra = ": много попыток входа — подождите несколько минут и повторите" if login else " — повторите позже"
        return IntegrationError(f"«{title}» ограничила число запросов (429){extra}", code="rate_limited", status=429)
    if status == 404:
        detail = not_found or (f"В «{title}» нет {where} (404) — проверьте адрес подключения: нужен адрес, по которому "
                               f"открывается «{title}»")
        return IntegrationError(detail, code="not_found", status=404, short=not_found or f"«{title}»: ресурс не найден")
    if status == 503 and code == "directory_unavailable":
        return IntegrationError(f"Сервер домена «{title}» не отвечает — попробуйте позже", code="unavailable",
                                status=503)
    if status >= 500:
        return IntegrationError(f"«{title}» вернула ошибку {status} ({where}) — попробуйте позже", code="http_error",
                                status=status, short=f"«{title}» вернула ошибку {status}")
    return IntegrationError(f"«{title}» вернула ошибку {status} ({where}){suffix}", code="http_error", status=status,
                            short=f"«{title}» вернула ошибку {status}")


# ---------------------------------------------------------------- сессия служебной учётной записи

class PartnerSession:
    """Сессия служебной учётной записи во Flask-приложении партнёра. Использование:

        with PartnerSession(url, kind="podelu", title="По Делу", login=…, password=…,
                            csrf_path="api/auth/csrf-token") as s:
            s.user                      # пользователь из ответа входа
            s.get_json("api/lists", kind=list)
        # здесь выход уже выполнен — и при исключении внутри блока
    """

    def __init__(self, url: str, *, kind: str, title: str, login: str, password: str, csrf_path: str,
                 verify: bool = True, detailed: bool = True, max_bytes: int = MAX_BYTES,
                 timeout: tuple[float, float] = (CONNECT_TIMEOUT, READ_TIMEOUT)):
        if not login or not password:
            raise IntegrationError(f"Укажите логин и пароль служебной учётной записи «{title}»", code="config")
        if re.search(r"[\x00-\x1f\x7f]", f"{login}{password}"):
            raise IntegrationError("Логин или пароль содержит недопустимые символы — введите их заново", code="config")
        self.title = title
        self.csrf_path = csrf_path
        self._login = login
        self._password = password
        self.client = HttpClient(url, kind=kind, title=title, verify=verify, detailed=detailed, cookies=True,
                                 max_bytes=max_bytes, timeout=timeout)
        parts = urlsplit(self.client.base_url)
        self.secure = parts.scheme.lower() == "https"
        # Flask-WTF сверяет Referer HTTPS-запросов, меняющих данные, со своим адресом (WTF_CSRF_SSL_STRICT)
        self.client.session.headers.update({"Referer": self.client.base_url + "/",
                                            "Origin": f"{parts.scheme}://{parts.netloc}"})
        self.csrf: str | None = None
        self.user: dict = {}
        self.logged_out = False

    def __enter__(self) -> PartnerSession:
        try:
            self.login()
        except BaseException:
            self.logout()
            raise
        return self

    def __exit__(self, *_exc) -> None:
        self.logout()

    # --- вход и выход
    def login(self) -> dict:
        data = self.get_json(self.csrf_path)
        token = data.get("csrfToken")
        if not isinstance(token, str) or not token or len(token) > 500:
            raise IntegrationError(f"«{self.title}» не выдала CSRF-токен — проверьте адрес подключения",
                                   code="bad_response")
        self.csrf = token
        self._check_cookies(required=False)
        resp = self.client.request("POST", "api/auth/login", json={"login": self._login, "password": self._password},
                                   headers={"X-CSRF-Token": token}, expect=ANY_STATUS)
        if resp.status != 200:
            raise partner_error(self.title, resp, "api/auth/login", login=True)
        data = self.client.parse(resp, dict)
        self._check_cookies(required=True)
        self.user = data.get("user") if isinstance(data.get("user"), dict) else {}
        return self.user

    def _check_cookies(self, *, required: bool) -> None:
        cookies = list(self.client.session.cookies)
        if required and not cookies:
            raise IntegrationError(f"«{self.title}» не выдала cookie сессии после входа — проверьте адрес подключения",
                                   code="session")
        if not self.secure and any(cookie.secure for cookie in cookies):
            raise IntegrationError(f"«{self.title}» выдаёт cookie сессии только для HTTPS: укажите адрес https://, по "
                                   f"которому открывается «{self.title}»", code="session")

    def logout(self) -> None:
        """Выход — сессия служебной учётной записи не остаётся открытой. Ошибки выхода не важны."""
        if self.logged_out:
            return
        self.logged_out = True
        try:
            if self.csrf is not None:
                self.client.request("POST", "api/auth/logout", json={}, headers={"X-CSRF-Token": self.csrf},
                                    expect=ANY_STATUS)
        except IntegrationError:
            pass
        finally:
            self.csrf = None
            self.client.close()

    # --- запросы
    def request(self, method: str, path: str, *, params: dict | None = None, json: Any = None,
                expect: tuple[int, ...] = (200,), denied: str | None = None, not_found: str | None = None,
                headers: dict | None = None) -> HttpResponse:
        if method != "GET" and self.csrf:
            headers = {**(headers or {}), "X-CSRF-Token": self.csrf}
        resp = self.client.request(method, path, params=params, json=json, headers=headers, expect=ANY_STATUS)
        if resp.status not in expect:
            raise partner_error(self.title, resp, path, denied=denied, not_found=not_found)
        return resp

    def get_json(self, path: str, *, kind: type | tuple[type, ...] = dict, **kwargs) -> Any:
        return self.client.parse(self.request("GET", path, **kwargs), kind)

    def post_json(self, path: str, body: Any, *, kind: type | tuple[type, ...] = dict,
                  expect: tuple[int, ...] = (200, 201), **kwargs) -> Any:
        return self.client.parse(self.request("POST", path, json=body, expect=expect, **kwargs), kind)


def secret_url(*urls: str | None) -> str:
    """Адреса, к которым привязан секрет: «основной → для запросов сервера». Каркас привязывает секрет к одному
    полю (url_field), поэтому коннектор с несколькими адресами хранит их сочетание в скрытом поле."""
    return " → ".join(u for u in urls if u)
