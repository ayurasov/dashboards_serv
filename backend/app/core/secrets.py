"""Секреты подключений: шифрование ключом, производным от SECRET_KEY (ADR-0011).

- Шифр — Fernet (AES-128-CBC + HMAC-SHA256) из пакета cryptography; ключ —
  urlsafe_b64(sha256(«назначение» + ":" + SECRET_KEY)). Разные назначения (purpose) дают разные
  ключи: секрет подключения не расшифровать ключом другого назначения.
- Секрет привязан к адресу, для которого его ввели: адрес хранится открыто рядом с секретом
  (столбец secret_bound_url — его видно в интерфейсе) и ещё раз внутри зашифрованного значения,
  поэтому подмена адреса в базе тоже обнаруживается. Сменили адрес — секрет нужно ввести заново:
  сохранённый токен никогда не уходит на адрес, для которого его не вводили.
- Секрет никогда не возвращается через API: наружу — только признак has_secret.

Смена SECRET_KEY (перешифрование) в 0.4.0 не поддерживается: после смены ключа сохранённые
секреты не расшифровываются (SecretUnreadable с понятным текстом), подключение показывает
«введите секрет заново», и администратор вводит секреты повторно. Переходный режим со старым
ключом (SECRET_KEY_PREVIOUS) — задача следующих версий.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import Fernet, InvalidToken

from .config import settings
from .errors import AppError

PAYLOAD_VERSION = 1


class SecretError(AppError):
    status_code = 422
    code = "secret_error"


class SecretUnreadable(SecretError):
    """Секрет зашифрован другим ключом: сменился SECRET_KEY или значение повреждено."""

    code = "secret_unreadable"


class SecretBindingError(SecretError):
    """Секрет введён для другого адреса."""

    code = "secret_rebind_required"


def _key(purpose: str) -> bytes:
    digest = hashlib.sha256(f"{purpose}:{settings.secret_key}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


def fernet(purpose: str) -> Fernet:
    if not purpose:  # pragma: no cover - ошибка программиста
        raise ValueError("purpose")
    return Fernet(_key(purpose))


def encrypt(purpose: str, value: Any) -> str:
    """Любое JSON-значение → зашифрованная строка (ASCII)."""
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return fernet(purpose).encrypt(raw).decode("ascii")


def decrypt(purpose: str, token: str) -> Any:
    try:
        raw = fernet(purpose).decrypt(token.encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise SecretUnreadable("Сохранённый секрет не удаётся расшифровать (сменился SECRET_KEY сервера) — "
                               "введите его заново") from exc


def normalize_url(url: str | None) -> str:
    """Адрес для сравнения привязки: схема и узел в нижнем регистре, без «/» в конце."""
    text = (url or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query,
                       parts.fragment))


def seal(purpose: str, values: dict[str, str], url: str | None, *, owner: str = "") -> tuple[str, str]:
    """Секретные поля → (зашифрованное значение, адрес привязки). owner — идентификатор владельца
    (например, «integration:5»): значение, перенесённое в другую строку, не расшифруется."""
    bound = normalize_url(url)
    token = encrypt(purpose, {"v": PAYLOAD_VERSION, "url": bound, "owner": owner, "values": values})
    return token, bound


def unseal(purpose: str, token: str, bound_url: str | None, url: str | None, *, owner: str = "") -> dict[str, str]:
    """Секретные поля для адреса url. Ошибка, если секрет введён для другого адреса или не читается."""
    target = normalize_url(url)
    if normalize_url(bound_url) != target:
        raise SecretBindingError(rebind_message(bound_url, url))
    payload = decrypt(purpose, token)
    if not isinstance(payload, dict) or payload.get("v") != PAYLOAD_VERSION or not isinstance(payload.get("values"),
                                                                                             dict):
        raise SecretUnreadable("Сохранённый секрет повреждён — введите его заново")
    if payload.get("url") != target or payload.get("owner", "") != owner:
        raise SecretBindingError(rebind_message(payload.get("url"), url))
    return {str(k): str(v) for k, v in payload["values"].items()}


def rebind_message(bound_url: str | None, url: str | None) -> str:
    if not (bound_url or "").strip():
        return f"Адрес изменён на {url} — введите токен или пароль заново"
    return f"Секрет введён для адреса {bound_url}, а подключение настроено на {url} — введите токен или пароль заново"


def problem(purpose: str, token: str | None, bound_url: str | None, url: str | None, *, owner: str = "") -> str | None:
    """Почему сохранённый секрет нельзя использовать (None — можно или секрета нет)."""
    if not token:
        return None
    try:
        unseal(purpose, token, bound_url, url, owner=owner)
    except SecretError as exc:
        return exc.detail
    return None
