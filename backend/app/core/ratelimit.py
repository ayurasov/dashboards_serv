"""Ограничение частоты неудачных попыток входа (скользящее окно в памяти процесса).

Счётчик живёт в каждом рабочем процессе отдельно — при N процессах gunicorn предел
фактически до N раз выше. Для защиты от подбора пароля этого достаточно.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        return hits

    def blocked_for(self, key: str) -> int:
        """Сколько секунд ещё действует блокировка (0 — не заблокирован)."""
        now = time.monotonic()
        with self._lock:
            hits = self._trim(key, now)
            if len(hits) < self.limit:
                return 0
            return max(1, int(self.window - (now - hits[0])))

    def hit(self, key: str) -> None:
        with self._lock:
            self._trim(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()
