#!/bin/sh
# Миграции и справочники одним процессом (под блокировкой PostgreSQL), затем — сервер.
set -e
cd /app/backend
python -m app.cli migrate
exec gunicorn -c gunicorn.conf.py app.main:app
