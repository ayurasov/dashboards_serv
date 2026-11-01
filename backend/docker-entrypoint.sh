#!/bin/sh
# Без аргументов: миграции и справочники одним процессом (под блокировкой PostgreSQL), затем — сервер.
# С аргументами — выполняет их в каталоге сервера, например:
#   docker compose run --rm app python -m app.cli org-sync --ad --apply
set -e
cd /app/backend
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
python -m app.cli migrate
exec gunicorn -c gunicorn.conf.py app.main:app
