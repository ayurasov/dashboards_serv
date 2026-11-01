"""Кэш готовых JSON-ответов аналитики.

Ключ ответа включает номер ревизии данных служб, от которых он зависит. Ревизия растёт при
каждом изменении данных службы (в той же транзакции, что и запись в журнал — см. audit.record),
поэтому все процессы сервера одновременно перестают отдавать устаревший ответ: проверка
ревизии — один запрос по первичному ключу. Кэш живёт в памяти процесса (LRU).
"""
from __future__ import annotations

import gzip
import json
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterable
from contextvars import ContextVar
from datetime import date, datetime

from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.db import utcnow
from ..models import DataRevision

# Клиент принимает gzip — выставляется middleware для каждого запроса
accepts_gzip: ContextVar[bool] = ContextVar("accepts_gzip", default=False)
GZIP_MIN_SIZE = 2048


def bump(db: Session, service_key: str) -> None:
    db.execute(update(DataRevision).where(DataRevision.service_key == service_key)
               .values(revision=DataRevision.revision + 1, updated_at=utcnow()))


def revisions(db: Session, service_keys: Iterable[str]) -> tuple:
    """((служба, номер, время изменения), …). Время в ключе защищает от совпадения номеров
    после восстановления базы из резервной копии."""
    keys = sorted(set(service_keys))
    rows = {k: (rev, ts) for k, rev, ts in db.execute(
        select(DataRevision.service_key, DataRevision.revision, DataRevision.updated_at)
        .where(DataRevision.service_key.in_(keys))).all()}
    return tuple((k, *rows.get(k, (0, None))) for k in keys)


def _default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(type(value))


class ResponseCache:
    def __init__(self, size: int):
        self.size = size
        self._data: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key):
        with self._lock:
            body = self._data.get(key)
            if body is not None:
                self._data.move_to_end(key)
                self.hits += 1
            else:
                self.misses += 1
            return body

    def put(self, key, body) -> None:
        with self._lock:
            self._data[key] = body
            self._data.move_to_end(key)
            while len(self._data) > self.size:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


cache = ResponseCache(settings.response_cache_size)


def serialize(data) -> bytes:
    return json.dumps(jsonable_encoder(data), ensure_ascii=False, separators=(",", ":"), default=_default).encode()


class _Entry:
    """Тело ответа и (для крупных) его gzip-версия — сжимается один раз, а не на каждый запрос."""

    __slots__ = ("body", "gz")

    def __init__(self, body: bytes):
        self.body = body
        self.gz = gzip.compress(body, compresslevel=6) if len(body) >= GZIP_MIN_SIZE else None


def _response(entry: _Entry) -> Response:
    if entry.gz is not None and accepts_gzip.get():
        return Response(entry.gz, media_type="application/json",
                        headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
    return Response(entry.body, media_type="application/json")


def cached_json(db: Session, services: Iterable[str], key: Hashable, compute: Callable[[], object]) -> Response:
    """Ответ из кэша, если данные служб не менялись; иначе вычисляет, сериализует и запоминает."""
    if not settings.response_cache:
        return Response(serialize(compute()), media_type="application/json")
    full_key = (key, revisions(db, services))
    entry = cache.get(full_key)
    if entry is None:
        entry = _Entry(serialize(compute()))
        cache.put(full_key, entry)
    return _response(entry)
