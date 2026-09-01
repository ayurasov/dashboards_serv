#!/bin/sh
set -e

echo "[entrypoint] DATABASE_URL=${DATABASE_URL}"

echo "[entrypoint] Running alembic upgrade head..."
cd /app/backend
alembic upgrade head
echo "[entrypoint] Migrations complete."
echo "[entrypoint] Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --log-level info
