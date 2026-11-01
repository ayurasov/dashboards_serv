"""Gunicorn: рабочие процессы uvicorn для FastAPI.

Переменные окружения:
  WEB_CONCURRENCY   число процессов (по умолчанию 2 × ядра + 1, не больше 9)
  GUNICORN_TIMEOUT  тайм-аут запроса, с (по умолчанию 120 — тяжёлые PDF-отчёты)
  PORT              порт (по умолчанию 8000)
"""
import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY") or min(multiprocessing.cpu_count() * 2 + 1, 9))
worker_class = "uvicorn_worker.UvicornWorker"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5
# Перезапуск процесса после N запросов страхует от утечек памяти (matplotlib, openpyxl)
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "2000"))
max_requests_jitter = 200
accesslog = None
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "*")
