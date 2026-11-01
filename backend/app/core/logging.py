"""Журнал сервера: текстовый для разработки, JSON для систем сбора логов (LOG_JSON=true)."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime

from .config import settings

_SECRET_RE = re.compile(r"(password|token|secret|session)=([^&\s]+)", re.IGNORECASE)


def redact(text: str) -> str:
    return _SECRET_RE.sub(lambda m: f"{m.group(1)}=***", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        for key in ("request_id", "method", "path", "status", "duration_ms", "user"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level.upper())
    for noisy in ("uvicorn.access", "matplotlib", "PIL", "fontTools"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
