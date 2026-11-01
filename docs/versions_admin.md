# Версии и release notes для администраторов

Технические и эксплуатационные изменения. Пользовательское окно «Что нового» использует `docs/versions.md`.

## Версия 0.1.0 (Ноябрь 2026 г.)

Первая версия продукта. Подробности — [release notes](release-notes/v0.1.0.md), решения — [ADR-0001…0006](architecture/).

### Схема БД — `0012_v0_1_0_schema`, `0013_data_revisions`

- `0012` перестраивает все таблицы с переносом данных (откат не поддерживается — нужна резервная копия): `hr_months`, `hr_employee_events`, `hr_metric_definitions`, `hr_metric_values`, `hr_month_notes`, `hr_targets`, `tp_weekly_reports`, `naumen_tickets`, `partnerships`, `partnership_light_rules`, `traffic_light_rules` (персонал и ТП), `services`, `service_access`, `service_settings`, `user_sessions`, `data_imports`, `dashboard_layouts`, `custom_dashboards`, `custom_dashboard_widgets`, `color_palettes`, `audit_log`;
- база без истории Alembic распознаётся по таблицам и помечается `0011_naumen_tickets`; дубли недель ТП и номеров заявок Naumen схлопываются; значения неизвестных метрик сохраняются (метрика создаётся выключенной);
- `0013` — `data_revisions`: ревизия данных каждой службы (для кэша ответов), с рабочим откатом.

### Доступ

- роли: `admin`, `user`; уровни доступа к службе: `viewer`, `editor`, `manager`, признак `department_scope` для службы персонала;
- перенос: `hr_head` → `hr:manager`; `department_viewer` → `hr:viewer` + свои подразделения; `read` → `viewer`; `edit`, `edit_metrics` → `editor`; `admin` → `manager`.

### Вход и сессии

- серверные сессии (`user_sessions`), cookie `ds_session` (httpOnly) и `ds_csrf`; заголовок `X-CSRF-Token` для изменяющих запросов;
- `SESSION_LIFETIME_HOURS` (12), `SESSION_IDLE_MINUTES` (240), `SESSION_COOKIE_SECURE`, `PASSWORD_MIN_LENGTH` (8), `LOGIN_RATE_LIMIT` (10) / `LOGIN_RATE_WINDOW_SECONDS` (300);
- первичный администратор: `ADMIN_USERNAME` / `ADMIN_PASSWORD`, при пустом пароле — временный пароль в журнале.

### Развёртывание

- образ: интерфейс собирается стадией Node 22, сервер — Python 3.12-slim, gunicorn + uvicorn-worker, пользователь без привилегий, HEALTHCHECK `/api/health`;
- `docker-compose.yml`: приложение + PostgreSQL 16 (том `pg_data`); обязательные `SECRET_KEY`, `POSTGRES_PASSWORD`;
- миграции при старте: `python -m app.cli migrate` (advisory-блокировка PostgreSQL);
- `DEMO_DATA=true` — демо-стенд (только пустые разделы);
- обновление с прежних версий (SQLite в томе `db_data`): `docs/runbooks/upgrade-to-0.1.0.md`; перенос в PostgreSQL — `backend/scripts/sqlite_to_postgres.py`.

### Производительность

- кэш ответов аналитики (`RESPONSE_CACHE`, `RESPONSE_CACHE_SIZE`), пул соединений (`DB_POOL_SIZE`), процессы (`WEB_CONCURRENCY`), `GUNICORN_TIMEOUT`, `GUNICORN_MAX_REQUESTS`;
- нагрузочная проверка 500 и 1000 пользователей: `docs/performance/load-test-0.1.0.md`.

### Обслуживание

- `python -m app.cli` — `migrate`, `demo-data`, `create-admin`, `reset-password`, `check-schema`, `cleanup-sessions`;
- журнал JSON: `LOG_JSON=true`; `X-Request-ID` в ответах.
