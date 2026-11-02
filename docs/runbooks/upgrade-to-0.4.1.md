# Runbook: обновление до 0.4.1

Применимо к установкам 0.4.0 в Docker. Схема базы, интерфейс и настройки не меняются, миграций нет; 2–5 минут.

## Что исправлено

В 0.4.0 контейнер `app` с `.env` по умолчанию не становился здоровым: `docker-compose.yml` передаёт `WEB_CONCURRENCY` всегда (пустой — «по умолчанию»), а gunicorn читает эту переменную как число ещё до `gunicorn.conf.py` и с пустой строкой не запускается. Признаки:

- `docker compose up -d` → `dependency failed to start: container …-app-1 is unhealthy`, `worker` не запускается;
- `docker compose logs app` → `ValueError: invalid literal for int() with base 10: ''`.

В 0.4.1 точка входа контейнера убирает пустую `WEB_CONCURRENCY`, и действует значение по умолчанию — 2 × ядра + 1, не больше 9.

Обход для 0.4.0 без обновления — задать число в `.env` и перезапустить:

```bash
W=$(( $(nproc) * 2 + 1 )); [ "$W" -gt 9 ] && W=9; sed -i "s/^WEB_CONCURRENCY=.*/WEB_CONCURRENCY=$W/" .env
docker compose up -d
```

## Обновление

```bash
docker compose exec -T db pg_dump -U dashboards -d dashboards -Fc > before-0.4.1.dump
git fetch && git checkout v0.4.1
docker compose up -d --build
```

Число в `WEB_CONCURRENCY`, заданное как обход, можно оставить или очистить.

## Проверка

1. `docker compose ps` — `app` в состоянии healthy, `worker` — running.
2. `curl -s http://127.0.0.1:<APP_PORT>/api/health` → `"status": "ok"`, `"version": "0.4.1"`, `schema.current == schema.head == "0016_integrations"`.
3. Войдите в систему; на странице **Входящие данные → Папка** — планировщик «Работает».

## Откат

Схема та же, поэтому достаточно вернуть код (с числом в `WEB_CONCURRENCY`, иначе 0.4.0 не запустится):

```bash
git checkout v0.4.0 && docker compose up -d --build
```
