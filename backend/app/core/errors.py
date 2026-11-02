"""Единый формат ошибок API: {"detail": "текст для человека", "code": "машинный код"}.

Под /api/inbound/ (приём по API для внешних систем, ADR-0011) — те же значения ещё и в полях
{"error": код, "message": текст}, как в соглашениях интеграций «По Делу» и «Пульса»."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, detail: str, *, code: str | None = None, status_code: int | None = None,
                 fields: dict[str, str] | None = None, headers: dict[str, str] | None = None):
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.fields = fields or {}
        self.headers = headers or {}


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class Overloaded(AppError):
    """Сервер не успел принять запрос в работу: очередь к базе данных переполнена."""

    status_code = 503
    code = "overloaded"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_error"


class TooManyRequests(AppError):
    status_code = 429
    code = "too_many_requests"


HTTP_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
              405: "method_not_allowed", 409: "conflict", 413: "payload_too_large",
              422: "validation_error", 429: "too_many_requests"}

# Сообщения pydantic, которые встречаются в формах, — по-русски.
VALIDATION_MESSAGES = {
    "missing": "Обязательное поле",
    "string_too_short": "Слишком короткое значение",
    "string_too_long": "Слишком длинное значение",
    "string_pattern_mismatch": "Недопустимый формат значения",
    "string_type": "Нужна строка",
    "too_short": "Слишком мало значений",
    "too_long": "Слишком много значений",
    "value_error": "Недопустимое значение",
    "int_parsing": "Нужно целое число",
    "float_parsing": "Нужно число",
    "date_from_datetime_parsing": "Нужна дата",
    "date_parsing": "Нужна дата в формате ГГГГ-ММ-ДД",
    "bool_parsing": "Нужно да или нет",
    "greater_than_equal": "Значение меньше допустимого",
    "less_than_equal": "Значение больше допустимого",
    "literal_error": "Недопустимое значение",
    "enum": "Недопустимое значение",
    "json_invalid": "Некорректный JSON",
}


INTEROP_PREFIX = "/api/inbound/"


def _body(detail: str, code: str, fields: dict | None = None, request: Request | None = None) -> dict:
    body = {"detail": detail, "code": code}
    if fields:
        body["fields"] = fields
    if request is not None and request.url.path.startswith(INTEROP_PREFIX):
        body.update(error=code, message=detail)
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        headers = {"Retry-After": "5"} if exc.status_code == 503 else {}
        headers.update(exc.headers)
        return JSONResponse(_body(exc.detail, exc.code, exc.fields, request), status_code=exc.status_code,
                            headers=headers or None)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Ошибка запроса"
        if exc.status_code == 404 and detail == "Not Found":
            detail = "Ресурс не найден"
        if exc.status_code == 405:
            detail = "Метод не поддерживается"
        return JSONResponse(_body(detail, HTTP_CODES.get(exc.status_code, "error"), request=request),
                            status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
            name = ".".join(loc) or "body"
            message = err.get("msg", "")
            if err.get("type") != "value_error" or not message.startswith("Value error, "):
                message = VALIDATION_MESSAGES.get(err.get("type", ""), message)
            else:
                message = message.removeprefix("Value error, ")
            fields.setdefault(name, message)
        first = next(iter(fields.items()), ("", "Проверьте введённые данные"))
        detail = f"{first[1]}: {first[0]}" if first[0] and first[0] != "body" else first[1]
        return JSONResponse(_body(detail, "validation_error", fields, request), status_code=422)

    @app.exception_handler(IntegrityError)
    async def _integrity_error(request: Request, exc: IntegrityError):
        log.warning("integrity error: %s", exc.orig)
        return JSONResponse(_body("Запись конфликтует с существующими данными", "conflict", request=request),
                            status_code=409)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # pragma: no cover - страховка
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(_body("Внутренняя ошибка сервера", "internal_error", request=request), status_code=500)
