"""HTTP-клиент подключений: общие сетевые правила ADR-0011 (как в burndown_tool и соглашениях «По Делу» / «Пульса»).

- адрес — только http(s)://узел[:порт][/путь], без логина в адресе, «?», «#» и пробелов (check_base_url);
- разрешённые узлы — переменная окружения <ВИД>_ALLOWED_HOSTS через запятую («jira.company.ru»
  или «.company.ru» — домен и все поддомены); пусто — без ограничения;
- перенаправления не выполняются: 3xx — ошибка с адресом перенаправления (токен уходит только
  на адрес, для которого его ввели);
- таймауты 5 с на соединение и 30 с на чтение; ответ не больше 20 МБ; JSON проверяется по виду
  (объект или список) — иначе «возможно, отвечает страница входа или прокси»;
- повтор только при 429 и 503: до 3 попыток, пауза Retry-After (не больше 10 с) — только у безопасных
  запросов (GET, HEAD, OPTIONS). POST, PUT, PATCH и DELETE повторяются, только если вызывающий передал
  retry=True: повтор входа или изменения у партнёра тратит его ограничение попыток и может выполнить
  действие дважды;
- секреты не выходят в тексты ошибок: значения секретов подключения (secrets), пароль Basic, токен из
  Authorization, логин и пароль в адресе (userinfo) и сегменты пути, равные секрету, заменяются на «…»
  во всех IntegrationError клиента (scrub — и для журнала запуска в runner.py);
- прокси — из HTTPS_PROXY / HTTP_PROXY окружения сервера (requests берёт их сам); «не проверять
  сертификат» — только явным параметром verify=False;
- ошибки типизированы (IntegrationError.code) и с двумя текстами: подробный — администратору при
  проверке подключения, краткий — остальным («— сообщите администратору»); из тела ответа
  показываются только поля errorMessages/errors/message/error/detail (до 300 символов);
- состояние подключения (последний успех и ошибка) записывает record_health.
"""
from __future__ import annotations

import json as jsonlib
import logging
import os
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from http.cookiejar import DefaultCookiePolicy
from typing import Any
from urllib.parse import quote, quote_plus, unquote, urlsplit

import requests

from ..core.config import BACKEND_DIR
from ..core.db import utcnow
from ..core.errors import AppError

CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 30.0
MAX_BYTES = 20 * 1024 * 1024
MAX_ATTEMPTS = 3
MAX_RETRY_AFTER = 10.0
ADMIN_HINT = " — сообщите администратору (подключение настраивается в разделе «Интеграции»)"
# Повторяются при 429/503 без явного retry=True: запросы, не меняющие данные у партнёра
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
REDACTED = "…"
# Секрет короче вычищается только как целый сегмент пути или userinfo адреса (иначе портились бы слова)
MIN_SECRET_LENGTH = 4

# Строки запросов urllib3 (уровень DEBUG) содержат путь целиком — у вебхука Bitrix24 в нём код доступа
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)


class IntegrationError(Exception):
    """Ошибка обращения к внешней системе: code — машинный код, detail — подробно (администратору),
    short — кратко, без адресов и технических подробностей (остальным)."""

    def __init__(self, detail: str, *, code: str = "integration_error", short: str | None = None,
                 status: int | None = None):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.short = short or detail
        self.status = status

    def message(self, detailed: bool = True) -> str:
        if detailed or self.short == self.detail:
            return self.detail
        return self.short + ADMIN_HINT

    def to_app_error(self, detailed: bool = True) -> AppError:
        """Ошибка API: внешняя система ответила не так — 502, неверная настройка — 422."""
        status = 422 if self.code in ("bad_url", "host_not_allowed", "config") else 502
        return AppError(self.message(detailed), code=self.code, status_code=status)


# ---------------------------------------------------------------- вычистка секретов

_USERINFO = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)[^/\s@\"'<>«»]+@")
_PATHLIKE = re.compile(r"/[^\s\"'<>«»()\[\]{},;]+")


def secret_texts(values: Iterable[str | None]) -> tuple[str, ...]:
    """Секреты и их запись в адресах (процентная кодировка) — длинные первыми."""
    out: set[str] = set()
    for value in values or ():
        text = str(value or "")
        for variant in (text, text.strip(), quote(text, safe=""), quote_plus(text), quote(text, safe="/")):
            if variant:
                out.add(variant)
    return tuple(sorted(out, key=len, reverse=True))


def scrub(text: str | None, secrets: Iterable[str | None] = ()) -> str:
    """Текст без секретов: логин и пароль в адресе (scheme://логин:пароль@узел), сегменты пути, равные секрету,
    и сами значения секретов (не короче MIN_SECRET_LENGTH) заменяются на «…»."""
    if not text:
        return text or ""
    text = _USERINFO.sub(lambda m: m.group("scheme") + REDACTED + "@", str(text))
    values = secret_texts(secrets)
    if not values:
        return text
    exact = set(values)

    def segments(match: re.Match) -> str:
        parts = match.group(0).split("/")
        for index, part in enumerate(parts):
            core = re.split(r"[?#]", part, maxsplit=1)[0]
            if core and (core in exact or unquote(core) in exact):
                parts[index] = REDACTED + part[len(core):]
        return "/".join(parts)

    text = _PATHLIKE.sub(segments, text)
    for value in values:
        if len(value) >= MIN_SECRET_LENGTH:
            text = text.replace(value, REDACTED)
    return text


def scrub_data(data: Any, secrets: Iterable[str | None]) -> Any:
    """scrub для всех строк вложенной структуры (сводка, подробности проверки)."""
    values = secret_texts(secrets)
    if not values:
        return data

    def walk(value: Any) -> Any:
        if isinstance(value, str):
            return scrub(value, values)
        if isinstance(value, dict):
            return {walk(k) if isinstance(k, str) else k: walk(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [walk(v) for v in value]
        return value

    return walk(data)


def scrubbed(exc: IntegrationError, secrets: Iterable[str | None]) -> IntegrationError:
    """Та же ошибка с вычищенными текстами (подробным и кратким)."""
    values = secret_texts(secrets)
    detail, short = scrub(exc.detail, values), scrub(exc.short, values)
    if detail == exc.detail and short == exc.short:
        return exc
    return IntegrationError(detail, code=exc.code, short=short, status=exc.status)


# ---------------------------------------------------------------- адрес и разрешённые узлы

def allowed_hosts_env(kind: str) -> str:
    return f"{re.sub(r'[^A-Za-z0-9]', '_', kind).upper()}_ALLOWED_HOSTS"


@lru_cache(maxsize=1)
def _dotenv() -> dict[str, str]:
    try:
        from dotenv import dotenv_values
    except ImportError:  # pragma: no cover - python-dotenv ставится вместе с pydantic-settings
        return {}
    values: dict[str, str] = {}
    for path in (BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"):
        if path.is_file():
            values.update({k: v for k, v in dotenv_values(path).items() if v is not None})
    return values


def allowed_hosts(kind: str | None) -> list[str]:
    if not kind:
        return []
    name = allowed_hosts_env(kind)
    raw = os.environ.get(name)
    if raw is None:
        raw = _dotenv().get(name, "")
    return [h.strip().lower() for h in raw.split(",") if h.strip()]


def host_allowed(host: str, allowed: list[str]) -> bool:
    host = host.lower().rstrip(".")
    return not allowed or any(host == h or (h.startswith(".") and (host.endswith(h) or host == h[1:]))
                              for h in allowed)


def check_base_url(url: str | None, *, kind: str | None = None, title: str = "Адрес") -> str:
    """Адрес подключения: http(s)://узел[:порт][/путь] без «/» в конце; ошибка bad_url или host_not_allowed."""
    text = (url or "").strip().rstrip("/")
    if not re.match(r"^https?://", text, re.IGNORECASE):
        raise IntegrationError(f"{title} должен начинаться с http:// или https://", code="bad_url")
    try:
        parts = urlsplit(text)
        parts.port  # noqa: B018 — ValueError, если порт некорректный
    except ValueError:
        raise IntegrationError(f"{title}: некорректный адрес", code="bad_url") from None
    if not parts.hostname or "@" in parts.netloc or parts.query or parts.fragment or "?" in text or "#" in text \
            or re.search(r"\s", text):
        raise IntegrationError(f"{title} — только https://узел[:порт][/путь], без логина, параметров «?» и «#»",
                               code="bad_url")
    allowed = allowed_hosts(kind)
    if not host_allowed(parts.hostname, allowed):
        raise IntegrationError(f"Подключение к {parts.hostname} запрещено настройками сервера "
                               f"({allowed_hosts_env(kind or '')})", code="host_not_allowed")
    return text


# ---------------------------------------------------------------- ответ

@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    content: bytes
    url: str

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return jsonlib.loads(self.content.decode("utf-8-sig"))

    def header(self, name: str, default: str = "") -> str:
        return self.headers.get(name.lower(), default)


def error_text(resp: HttpResponse) -> str:
    """Сообщения об ошибке из JSON-ответа (errorMessages, errors, message, error, detail). Произвольное тело
    не показывается: адрес мог указывать не на ту систему."""
    try:
        data = resp.json()
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    messages: list[str] = []
    if isinstance(data.get("errorMessages"), list):
        messages += [str(m) for m in data["errorMessages"]]
    if isinstance(data.get("errors"), dict):
        messages += [f"{k}: {v}" for k, v in data["errors"].items()]
    for key in ("message", "error", "detail"):
        if not messages and isinstance(data.get(key), str):
            messages.append(data[key])
    return "; ".join(messages)[:300]


# ---------------------------------------------------------------- клиент

@dataclass
class HttpClient:
    """Клиент одного подключения. path в запросах — относительно base_url («api/myself»), полный
    адрес — только того же узла. auth — кортеж (логин, пароль) для Basic (UTF-8) или None; headers —
    например, {"Authorization": "Bearer …"}. detailed=False — краткие ошибки для неадминистраторов.
    secrets — значения секретов подключения: они (как и пароль Basic и токен Authorization) вычищаются
    из текстов всех ошибок клиента."""

    base_url: str
    kind: str | None = None
    title: str = "Система"
    auth: tuple[str, str] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    verify: bool | str = True
    timeout: tuple[float, float] = (CONNECT_TIMEOUT, READ_TIMEOUT)
    max_bytes: int = MAX_BYTES
    detailed: bool = True
    cookies: bool = True
    secrets: tuple[str, ...] = ()
    sleep: Callable[[float], None] = time.sleep
    calls: int = 0
    elapsed: float = 0.0

    def __post_init__(self):
        known = [*(self.secrets or ())]
        if self.auth is not None:
            known.append(self.auth[1])
        for name, value in self.headers.items():
            if name.lower() == "authorization" and value:
                known += [value, value.split(" ", 1)[-1]]
        self._secrets = secret_texts(known)
        self.base_url = check_base_url(self.base_url, kind=self.kind, title=f"Адрес «{self.title}»")
        self._host = urlsplit(self.base_url).netloc.lower()
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "dashboards-integrations",
                                     **self.headers})
        if self.auth is not None:
            # Basic в UTF-8: requests по умолчанию кодирует latin-1 и падает на кириллице
            self.session.auth = (self.auth[0].encode("utf-8"), self.auth[1].encode("utf-8"))
        if not self.cookies:
            self.session.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))
        self.session.verify = self.verify
        if self.verify is False:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # --- адреса и ошибки
    def url(self, path: str) -> str:
        if re.match(r"^https?://", path, re.IGNORECASE):
            if urlsplit(path).netloc.lower() != self._host:
                raise self.fail("bad_url", f"Запрос на другой узел ({urlsplit(path).netloc}) запрещён",
                                "Запрос на другой узел запрещён")
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def where(self, url: str) -> str:
        return url if self.detailed else urlsplit(url).path

    def scrub(self, text: str | None) -> str:
        """Текст без секретов этого клиента — для сообщений, собранных из ответа вне клиента."""
        return scrub(text, self._secrets)

    def fail(self, code: str, detailed: str, short: str, status: int | None = None) -> IntegrationError:
        return IntegrationError(self.scrub(detailed), code=code, short=self.scrub(short), status=status)

    # --- запрос
    def request(self, method: str, path: str, *, params: dict | None = None, json: Any = None, data: Any = None,
                headers: dict | None = None, files: Any = None, expect: tuple[int, ...] = (200,),
                not_found: str | None = None, retry: bool | None = None) -> HttpResponse:
        """Запрос; статус не из expect — IntegrationError. Повтор при 429/503 — у GET, HEAD, OPTIONS; POST, PUT,
        PATCH и DELETE повторяются только с retry=True (запрос, который у партнёра ничего не меняет, например
        чтение через POST); retry=False — не повторять и безопасный запрос."""
        url = self.url(path)
        method = method.upper()
        attempts = MAX_ATTEMPTS if (method in SAFE_METHODS if retry is None else retry) else 1
        resp: HttpResponse | None = None
        for attempt in range(1, attempts + 1):
            resp = self._send(method, url, params=params, json=json, data=data, headers=headers, files=files)
            if resp.status in (429, 503) and attempt < attempts:
                self.sleep(self._retry_after(resp, attempt))
                continue
            break
        assert resp is not None
        self.check(resp, expect=expect, not_found=not_found)
        return resp

    def _retry_after(self, resp: HttpResponse, attempt: int) -> float:
        try:
            return max(0.0, min(float(resp.header("retry-after") or attempt), MAX_RETRY_AFTER))
        except ValueError:
            return float(min(attempt, MAX_RETRY_AFTER))

    def _send(self, method: str, url: str, **kwargs) -> HttpResponse:
        title = self.title
        started = time.monotonic()
        self.calls += 1
        try:
            raw = self.session.request(method, url, timeout=self.timeout, allow_redirects=False, stream=True,
                                       **{k: v for k, v in kwargs.items() if v is not None})
        except requests.exceptions.SSLError as exc:
            raise self.fail("tls", f"Ошибка TLS-сертификата {self.base_url}: если сервер использует "
                                   f"самоподписанный или корпоративный сертификат, включите «Не проверять "
                                   f"сертификат» ({exc})", f"Ошибка TLS-сертификата «{title}»") from None
        except requests.exceptions.ConnectTimeout:
            raise self.fail("connect_timeout", f"Превышено время ожидания подключения к {self.base_url}",
                            f"«{title}» не отвечает") from None
        except requests.exceptions.ReadTimeout:
            raise self.fail("read_timeout", f"{self.base_url} не ответил за {self.timeout[1]:.0f} с",
                            f"«{title}» не ответила вовремя — попробуйте ещё раз") from None
        except requests.exceptions.ConnectionError as exc:
            raise self.fail("connect", f"Не удалось подключиться к {self.base_url}: проверьте адрес и доступность "
                                       f"сети ({exc})", f"Не удалось подключиться к «{title}»") from None
        except requests.exceptions.RequestException as exc:  # pragma: no cover - прочие ошибки requests
            raise self.fail("connect", f"Ошибка запроса к {self.base_url}: {exc}",
                            f"Ошибка связи с «{title}»") from None
        except UnicodeEncodeError:
            # Заголовки HTTP — только латиница: токен или логин с кириллицей сюда не передать
            raise self.fail("config", f"Токен или заголовок запроса к «{title}» содержит недопустимые символы "
                                      "(допустима только латиница) — проверьте секрет подключения",
                            f"Подключение к «{title}» настроено неверно") from None
        try:
            headers = {k.lower(): v for k, v in raw.headers.items()}
            if raw.is_redirect or 300 <= raw.status_code < 400:
                target = urlsplit(headers.get("location") or "")
                where = f" на {target.scheme}://{target.netloc}{target.path}" if target.netloc else \
                    (f" на {target.path}" if target.path else "")
                raise self.fail("redirect", f"{self.where(url)} перенаправляет запрос ({raw.status_code}){where} — "
                                            "укажите в подключении итоговый адрес (например, с https:// или с путём)",
                                f"«{title}» перенаправляет запросы на другой адрес — подключение нужно обновить",
                                raw.status_code)
            length = headers.get("content-length")
            if length and length.isdigit() and int(length) > self.max_bytes:
                raise self._too_large(url)
            chunks, size = [], 0
            for chunk in raw.iter_content(64 * 1024):
                size += len(chunk)
                if size > self.max_bytes:
                    raise self._too_large(url)
                chunks.append(chunk)
            return HttpResponse(raw.status_code, headers, b"".join(chunks), url)
        except requests.exceptions.RequestException:
            raise self.fail("read_timeout", f"{self.base_url}: ответ прерван", f"«{title}» прервала ответ") from None
        finally:
            raw.close()
            self.elapsed += time.monotonic() - started

    def _too_large(self, url: str) -> IntegrationError:
        mb = self.max_bytes // (1024 * 1024)
        return self.fail("too_large", f"Ответ {self.where(url)} больше {mb} МБ",
                         f"Ответ «{self.title}» слишком большой")

    def check(self, resp: HttpResponse, *, expect: tuple[int, ...] = (200,), not_found: str | None = None) -> None:
        if resp.status in expect:
            return
        title, text = self.title, error_text(resp)
        suffix = f": {text}" if text else ""
        if resp.status == 401:
            raise self.fail("auth", f"«{title}» отклонила учётные данные подключения (401){suffix}",
                            f"«{title}» отклонила учётные данные подключения (401)", 401)
        if resp.status == 403:
            raise self.fail("forbidden", f"Недостаточно прав в «{title}» (403){suffix}",
                            f"Недостаточно прав в «{title}» (403)", 403)
        if resp.status == 404:
            raise self.fail("not_found", not_found or f"{self.where(resp.url)} не найден (404)",
                            not_found or f"«{title}»: ресурс не найден (404)", 404)
        if resp.status == 429:
            raise self.fail("rate_limited", f"«{title}» ограничила частоту запросов (429) — повторите позже",
                            f"«{title}» ограничила частоту запросов — повторите позже", 429)
        if resp.status == 503:
            raise self.fail("unavailable", f"«{title}» временно недоступна (503){suffix}",
                            f"«{title}» временно недоступна", 503)
        raise self.fail("http_error", f"«{title}» вернула ошибку {resp.status}: {text or self.where(resp.url)}",
                        f"«{title}» вернула ошибку {resp.status}", resp.status)

    def parse(self, resp: HttpResponse, kind: type | tuple[type, ...] = dict) -> Any:
        try:
            data = resp.json()
        except (ValueError, UnicodeDecodeError):
            data = None
        if not isinstance(data, kind):
            raise self.fail("bad_response", f"{self.where(resp.url)} вернул неожиданный ответ — проверьте адрес; "
                                            "возможно, отвечает страница входа или прокси",
                            f"«{self.title}» вернула неожиданный ответ: возможно, отвечает страница входа или прокси",
                            resp.status)
        return data

    # --- удобные вызовы
    def get_json(self, path: str, *, kind: type | tuple[type, ...] = dict, **kwargs) -> Any:
        return self.parse(self.request("GET", path, **kwargs), kind)

    def post_json(self, path: str, body: Any = None, *, kind: type | tuple[type, ...] = dict, **kwargs) -> Any:
        """POST с JSON; при 429/503 не повторяется, если не передан retry=True (см. request)."""
        return self.parse(self.request("POST", path, json=body, **kwargs), kind)

    def get_bytes(self, path: str, **kwargs) -> bytes:
        return self.request("GET", path, **kwargs).content

    def stats(self) -> str:
        return f"{self.calls} запрос(ов) за {self.elapsed:.1f} с"

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


# ---------------------------------------------------------------- состояние подключения

def record_health(target: Any, *, ok: bool, error: str = "", now: datetime | None = None) -> None:
    """Последний успех и последняя ошибка — у любой записи с полями last_ok_at, last_error_at, last_error
    (models.Integration)."""
    now = now or utcnow()
    if ok:
        target.last_ok_at = now
    else:
        target.last_error_at = now
        target.last_error = (error or "Ошибка")[:2000]
