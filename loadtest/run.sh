#!/bin/sh
# Прогон нагрузочного сценария против уже запущенного сервера.
#   ./loadtest/run.sh http://127.0.0.1:8000 500 6m
#   ./loadtest/run.sh http://127.0.0.1:8000 1000 6m
# Сервер должен работать с демо-данными (DEMO_DATA=true). Результаты — loadtest/results/u<число>_*.csv
set -e
HOST=${1:-http://127.0.0.1:8000}
USERS=${2:-500}
DURATION=${3:-6m}
SPAWN=${SPAWN_RATE:-25}
cd "$(dirname "$0")"
mkdir -p results
locust -f locustfile.py --host "$HOST" --users "$USERS" --spawn-rate "$SPAWN" --run-time "$DURATION" \
  --headless --only-summary --csv "results/u${USERS}" --csv-full-history
