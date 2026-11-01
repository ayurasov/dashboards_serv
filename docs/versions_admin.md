# Версии и release notes для администраторов

Технические и эксплуатационные изменения. Пользовательское окно «Что нового» использует `docs/versions.md`.

## Версия 0.2.0 (Ноябрь 2026 г.)

Структура компании, модель доступа 2.0 (профили доступа и личные настройки), вход по учётной записи домена и синхронизация с Active Directory. Подробности — [release notes](release-notes/v0.2.0.md), решения — [ADR-0007…0009](architecture/), проект следующей версии — [ADR-0010](architecture/adr-0010-cross-reports.md).

### Схема БД — `0014_org_access` (откат поддерживается)

- `departments` — дерево: `parent_id`, `kind`, `sort_order`, `external_id`, `org_source`, `name_key`; имена уникальны среди соседних (частичные индексы), `code` необязателен;
- новые: `department_heads` (основной руководитель — `is_primary`), `access_profiles`, `user_access_units`, `app_settings`, `org_revision`;
- `users`: `department_id`, `manager_id`, `reports_to_none`, `external_id`, `org_source`, `auth_source` (`local` · `ldap`), `auth_external_id`, `auth_linked_at`, `access_profile_id`, `access_overrides`, `capabilities`; `password_hash` может быть пустым;
- `user_departments` → основное подразделение (первое по алфавиту) + `user_access_units`; `service_access`: уровень `none`, `org_scope` вместо `department_scope` (`true` → `branch`);
- доступ существующих пользователей не меняется: профиль не назначен («Индивидуальная настройка» = поведение 0.1.0).

### Доступ

- действующий доступ = профиль + личные настройки + строки служб; измерения: уровень службы, область структуры (`company` · `branch` · `unit`, в том числе своя у службы), дополнительные подразделения, классы данных (`operational` · `personal` · `financial`), глубина детализации, исходные записи, выгрузка;
- встроенные профили: `executive`, `director`, `head`, `specialist`, `employee` (изменяемы, не удаляются);
- проверки на сервере: реестры и карточки — право на исходные записи; ФИО и причины увольнения — класс `personal`; все выгрузки Excel/CSV/PDF — право на выгрузку; ключ кэша ответов учитывает область, классы данных и записи;
- полномочия без роли администратора: `org.manage` (структура, импорт и экспорт), `users.manage` (пользователи и профили, кроме администраторов).

### Вход по домену и Active Directory

- `AUTH_LDAP_*` (ldap3): служебная привязка, поиск с экранированием, привязка от имени найденной записи, отключённые в AD не входят, LDAPS / StartTLS с проверкой сертификата; сопоставление — `objectGUID`/`entryUUID`, идентификатор синхронизации AD, e-mail; создание при первом входе (`AUTH_LDAP_CREATE_USERS`) с профилем по группам (`AUTH_LDAP_GROUP_PROFILES`, `AUTH_LDAP_DEFAULT_PROFILE`, `AUTH_LDAP_ADMIN_GROUP`); 503 при недоступном каталоге;
- страница «Вход по домену»: состояние, замечания настройки, проверка подключения и поиска учётной записи (`/api/system/ldap`);
- `AD_SYNC_*` (по умолчанию — адрес и учётные данные входа): проверка → план → применение одной транзакцией; отключаются только пришедшие из AD; `python -m app.cli org-sync --ad [--apply] [--create-missing] [--deactivate-missing]` — коды выхода 0/1/2.

### Структура компании

- `/api/org/tree` — все виды оргсхемы одним ответом из снимка структуры в памяти процесса (перестраивается по `org_revision`); `/api/org/people/{id}`, `/api/departments`, `/api/org/settings`, `/api/org/history`;
- перенос: структура (JSON `dashboards.org-structure` v1), сотрудники (Excel/CSV/JSON с разбором различий), быстрая загрузка списком; ничего не удаляется, руководители только добавляются.

### Развёртывание

- `TIMEZONE` (по умолчанию `Europe/Moscow`): границы дней в журнале, время в PDF; `tzdata` в зависимостях;
- `docker-compose.yml` передаёт `TIMEZONE` и `AUTH_LDAP_ENABLED`, `_URL`, `_BASE_DN`, `_BIND_DN`, `_BIND_PASSWORD`; остальные `AUTH_LDAP_*`, `AD_SYNC_*` и сертификат — через `docker-compose.override.yml`;
- команды `python -m app.cli` в контейнере — с `-w /app/backend`;
- обновление и откат: `docs/runbooks/upgrade-to-0.2.0.md`.

### Производительность

- нагрузочная проверка: 1000 одновременных пользователей всех уровней на 4 ядрах — p50 16 мс, p95 53 мс без ошибок сервера; `/api/org/tree` — p95 32 мс (`docs/performance/load-test-0.2.0.md`);
- действующий доступ вычисляется один раз на запрос без обращений к базе, область — по снимку структуры в памяти процесса.

### Исправлено

- PDF: по фильтрам страницы (диапазон сводки персонала, несколько лет недельного отчёта, фильтры партнёрств), числа вправо, цвета светофора, знак «−»;
- цели года — по данным своего года; ось месяцев Naumen — по месяцам регистрации; сравнение периодов ТП — только равных интервалов; кэш «Обзора» и аналитики партнёрств учитывает дату;
- незаполненный показатель со светофором — «Нет данных» и отдельная отметка критичного нарушения полноты (дашборд персонала, «Обзор», ввод данных, PDF; поле `missing` в API).

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

- кэш ответов аналитики (`RESPONSE_CACHE`, `RESPONSE_CACHE_SIZE`), пул соединений (`DB_POOL_SIZE` = 5, `DB_MAX_OVERFLOW` = 4), очередь к базе (`DB_CONCURRENCY`, `DB_QUEUE_TIMEOUT`), потоки (`THREADPOOL_SIZE`), PDF (`PDF_CONCURRENCY`), процессы (`WEB_CONCURRENCY`), `GUNICORN_TIMEOUT`, `GUNICORN_MAX_REQUESTS`;
- при перегрузке — ответ 503 «Сервер перегружен» с `Retry-After`, а не зависание;
- нагрузочная проверка: 1000 одновременных пользователей на 4 ядрах — p95 46 мс без ошибок сервера (`docs/performance/load-test-0.1.0.md`).

### Обслуживание

- `python -m app.cli` — `migrate`, `demo-data`, `create-admin`, `reset-password`, `check-schema`, `cleanup-sessions`;
- журнал JSON: `LOG_JSON=true`; `X-Request-ID` в ответах.
