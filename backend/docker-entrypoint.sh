#!/bin/sh
# Без аргументов: миграции и справочники одним процессом (под блокировкой PostgreSQL), затем — сервер.
# С аргументами — выполняет их в каталоге сервера без миграций (их делает только сервис app), например:
#   docker compose run --rm app python -m app.cli org-sync --ad --apply
#   python -m app.cli worker — сервис worker в docker-compose.yml (ждёт, пока app обновит схему)
set -e
cd /app/backend
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
python -m app.cli migrate
exec gunicorn -c gunicorn.conf.py app.main:app
