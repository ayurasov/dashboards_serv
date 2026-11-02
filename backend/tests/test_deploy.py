"""Запуск в Docker: точка входа контейнера и переменные, которые docker-compose.yml передаёт всегда.

docker-compose.yml передаёт каждую переменную из .env, в том числе пустую (`${WEB_CONCURRENCY:-}`). Сервер
обязан запускаться с пустыми значениями — так выглядит .env по умолчанию (в 0.4.0 пустой WEB_CONCURRENCY
останавливал gunicorn ещё до чтения gunicorn.conf.py, контейнер app не становился здоровым).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
ENTRYPOINT = BACKEND / "docker-entrypoint.sh"


def run_entrypoint(*args: str, **env: str) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **env}
    return subprocess.run(["sh", str(ENTRYPOINT), *args], env=full_env, capture_output=True, text=True, timeout=60,
                          cwd="/")


def test_entrypoint_drops_empty_web_concurrency():
    out = run_entrypoint(sys.executable, "-c", "import os; print(repr(os.environ.get('WEB_CONCURRENCY')))",
                         WEB_CONCURRENCY="")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "None"


def test_entrypoint_keeps_web_concurrency_number_and_runs_in_backend_dir():
    out = run_entrypoint(sys.executable, "-c", "import os; print(os.environ['WEB_CONCURRENCY'], os.getcwd())",
                         WEB_CONCURRENCY="5")
    assert out.returncode == 0, out.stderr
    number, cwd = out.stdout.split()
    assert number == "5" and Path(cwd) == BACKEND


def test_gunicorn_config_loads_with_compose_defaults():
    """gunicorn читает WEB_CONCURRENCY при импорте своих настроек — через точку входа пустое значение не мешает."""
    pytest.importorskip("gunicorn")
    code = ("import runpy, gunicorn.config; cfg = runpy.run_path('gunicorn.conf.py'); "
            "print(cfg['workers'] >= 1, cfg['bind'])")
    out = run_entrypoint(sys.executable, "-c", code, WEB_CONCURRENCY="", PORT="8000")
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["True", "0.0.0.0:8000"]


def test_compose_variables_with_empty_defaults_are_safe():
    """Каждая переменная, которую docker-compose.yml передаёт пустой по умолчанию, допустима пустой для настроек."""
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    empty = sorted(set(re.findall(r"^\s+([A-Z][A-Z0-9_]+): \$\{\1:-\}\s*$", compose, flags=re.M)))
    assert "WEB_CONCURRENCY" in empty and "PUBLIC_URL" in empty
    env = {name: "" for name in empty}
    code = "from app.core.config import Settings; Settings(); print('ok')"
    out = subprocess.run([sys.executable, "-c", code], env={**os.environ, **env}, cwd=BACKEND, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"
