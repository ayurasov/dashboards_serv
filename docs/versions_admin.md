# Версии и release notes для администраторов

Технические и эксплуатационные изменения. Пользовательское окно «Что нового» использует `docs/versions.md`.

## Версия 0.4.1 (Ноябрь 2026 г.)

Исправление запуска в Docker; схема базы, интерфейс и настройки не меняются. Подробности — [release notes](release-notes/v0.4.1.md), регламент — [обновление до 0.4.1](runbooks/upgrade-to-0.4.1.md).

### Исправления

- контейнер `app` не становился здоровым с `.env` по умолчанию: `docker-compose.yml` передаёт `WEB_CONCURRENCY` всегда, пустой — «по умолчанию», а gunicorn читает эту переменную как число ещё до `gunicorn.conf.py` и с пустой строкой падает при старте (`ValueError: invalid literal for int() with base 10: ''`), `worker` не запускался («dependency failed to start: container …-app-1 is unhealthy»). Точка входа `docker-entrypoint.sh` убирает пустую `WEB_CONCURRENCY` — по умолчанию 2 × ядра + 1, не больше 9; обход в 0.4.0 — число в `.env`;
- точка входа находит каталог сервера по своему пути, а не по зашитому `/app/backend`.

### Сборка, CI, тесты

- workflow `Docker`: сборка образа и запуск `docker-compose.yml` с `.env` из `.env.example` (пустые значения по умолчанию) — здоровье `app`, `/api/health`, страница входа, вход администратора, запуск планировщика;
- `tests/test_deploy.py`: точка входа убирает пустую `WEB_CONCURRENCY` и сохраняет число, настройки gunicorn загружаются с пустыми значениями, настройки приложения принимают все переменные, которые `docker-compose.yml` передаёт пустыми.

### Документация

- «Обновление до 0.1.0 с версий до 0.1.0» (руководство по развёртыванию и регламент) — проверенный порядок перехода со старой версии на 0.4.1 с PostgreSQL: сначала `docker compose down` в старой версии (контейнер `dashboards_serv` занимает порт), имя тома — по имени папки (`<папка>_db_data`), код — в чистой папке через `git clone` (оставшийся `frontend/src/router.js` старой версии ломает сборку интерфейса: «Missing export»), команды с копией базы в смонтированной папке — с `-u root` (иначе «attempt to write a readonly database»), откат через прежнюю папку;
- «Обновление до 0.4.1» и регламент `upgrade-to-0.4.1.md`.

## Версия 0.4.0 (Ноябрь 2026 г.)

Интеграции и входящие данные: единый конвейер файлов (папка, загрузка, приём по API, подключения) с распознаванием набора, планом и применением сразу или после подтверждения; подключения к «По Делу», «Пульсу проекта», Jira, Confluence, Bitrix24, Exchange и 1С с зашифрованными секретами, несколькими расписаниями и журналом запусков; «По Делу» и «Пульс» — по ключам интеграций; планировщик `worker`. Нагрузочная проверка: 1000 пользователей — p50 19 мс, p95 63 мс без ошибок сервера ([отчёт](performance/load-test-0.4.0.md)). Подробности — [release notes](release-notes/v0.4.0.md), решение — [ADR-0011](architecture/adr-0011-integrations.md), регламенты — [обновление до 0.4.0](runbooks/upgrade-to-0.4.0.md), [неполадки интеграций](runbooks/integrations-troubleshooting.md).

### Схема БД — `0016_integrations` (откат поддерживается)

- новые таблицы: `integrations` (вид, название, `enabled`, `config` без секретов, `secret_encrypted` и `secret_bound_url`, `schedule` — список до 5 записей, `next_runs` — следующий запуск каждой записи, `next_run_at` — ближайший, `running_since`, `state`, `verified_at`, `last_run_at`, `last_ok_at`, `last_error_at`, `last_error`), `integration_runs` (действие, повод `manual` · `schedule` · `cli`, итог `ok` · `partial` · `error` · `interrupted`, сводка, сообщение, ошибка, кто), `inbound_keys` (название, `sha256`, `prefix` — 12 символов, `scopes` `files` · `status`, выпуск, `last_used_at`, `revoked_at`, окно ограничения частоты `rate_window_start` и `rate_count`), `inbox_items` (источник `folder` · `upload` · `api` · `integration`, файл до срока хранения, SHA-256, набор, статус, план, сводка, итог, пояснение источника), `inbox_rules` (источник × набор → `auto_apply`);
- частичный уникальный индекс `(dataset, sha256)` по живым статусам (`received`, `recognized`, `pending`, `applied`) — повтор файла распознаётся и при одновременном приёме;
- существующие таблицы не меняются; отметки `worker_status` и `inbox_folder_status` — в `app_settings`;
- откат (`downgrade 0015_reports`) удаляет таблицы и снимает `data.manage` и `integrations.manage` в `users.capabilities`.

### Входящие данные

- наборы (`hr-months`, `hr-events`, `tp-weekly`, `naumen`, `partnerships`, `indicators`, `structure`, `employees`) — те же движки плана и применения, что у ручной загрузки; распознавание: подпапка, выбор, `dataset` API, затем содержимое (порог 50 баллов, имя файла по шаблону — +20, равенство лучших — не распознан), JSON по полю `format` (в том числе `podelu.org-structure`, `podelu.employees`);
- применение от имени источника (`source_actor`: все службы и классы данных, `org.manage` и `reports.manage`, без администратора и `users.manage`) или пользователя (с `data.manage` — права источника и журнал на пользователя, иначе — свои права); перед применением план строится заново; правила `inbox_rules` — для `folder`, `api`, `integration`; `apply=false` — только план;
- папка: `INBOX_SETTLE_SECONDS`, захват `os.replace` в `.work/`, `O_NOFOLLOW`, ссылки за пределы папки не читаются, `processed/ГГГГ-ММ/` и `rejected/` с `*.result.json`, возврат из `.work/` через час;
- срок хранения: содержимое завершённых элементов (`applied`, `rejected`, `duplicate`, `error`) старше `INBOX_RETENTION_DAYS` — `NULL` в базе, старые файлы — из `processed/` и `rejected/`; раз в час в планировщике или `inbox cleanup`;
- приём по API: Bearer `dash_` + `token_urlsafe(32)`, SHA-256 и `compare_digest`, `last_used_at` не чаще раза в минуту, `INBOUND_RATE_LIMIT` в минуту на ключ — счётчик окна в строке ключа, один атомарный `UPDATE … RETURNING` (`hit_rate_limit`), общий для всех процессов, `Retry-After` — секунд до конца окна; 201 — новый, 200 — повтор; ошибки дублируются в `error`/`message` для совместимости с «По Делу» и «Пульсом»;
- значения показателей: строка `clear` (столбец «Очистить»: «да», 1, x, +) удаляет сохранённое значение — действие `clear`, в сводке `cleared`; загрузка без изменений не пишет журнал и не меняет ревизию отчётов;
- загрузка и «Повторить» человеком применяются по флажку «применить сразу» без правила; сообщения ожидания — «Загружено для проверки — посмотрите план и примените», «План построен заново — посмотрите его и примените», у API с `apply=false` — «Ожидает подтверждения: отправитель попросил только план».

### Интеграции

- каркас `app/integrations`: `Connector` (поля, действия, `check`, `run`, `validate_config`, `secret_url` и `secret_url_fields`), реестр `@register`, `RunContext` (`inbox.add(..., note=)`, `plans.*`, `plans.ensure_indicator`, `state`), `HttpClient` (адрес, `<ВИД>_ALLOWED_HOSTS`, без перенаправлений, 5/30 с, 20 МБ, повтор 429/503 только у GET/HEAD/OPTIONS, вычистка секретов), `runner` (атомарный `claim_due` и `begin_running`, `RUNNING_TIMEOUT` 2 ч, `INTEGRATION_RUNS_KEEP`);
- расписание — список до 5 записей (`interval` 5–10080 мин или `daily` ЧЧ:ММ с днями недели, у каждой свои `actions`), прежний вид (один объект) читается как одна запись (`entries_of`); `claim_due` занимает только наступившие записи и переносит их одним `UPDATE` с проверкой прочитанного `next_run_at`; `schedule_label` — «В 06:00 ежедневно — Синхронизировать структуру; Каждые 30 мин — Забрать данные из задач»;
- прерванный запуск: `running` старше `RUNNING_TIMEOUT` в API — `interrupted` («Запуск прерван»), `begin_running` и планировщик (`reclaim_stale`) занимают подключение заново и отмечают записи журнала; `current_error` — последняя ошибка, только если она новее последнего успеха;
- `Connector.admin_only` (Confluence: публикует полный отчёт) — создать, изменить, проверить, запустить, удалить только администратору (403 `admin_only`), у подключения `can_manage`; `Connector.order` — порядок видов и карточек; `counter_labels` и общие `COMMON_COUNTER_LABELS` — подписи счётчиков журнала (без подписи не показываются); `Connector.stored_config` — чтение настроек, сохранённых до появления поля (подключения «По Делу» и «Пульса» без `mode` — служебная учётная запись); предпросмотр Jira, Bitrix24 и 1С считает значения показателей, которые будут созданы (`values_pending`);
- проверка: `CheckResult(ok, message, details, warnings)` — замечания при `ok` («Подключено с замечаниями», журнал изменений — «успешно, с замечаниями»), без хвостов «Внимание:» в сообщении; подписи подробностей — `Connector.detail_labels` (общие — каркаса), служебные ключи — `technical_details`; поле с `placeholder_if` (у «По Делу» в режиме ключа — «пусто — все списки ключа»);
- прокси: `HTTPS_PROXY` / `HTTP_PROXY` с разбором `NO_PROXY` в каркасе (`*.домен`, `IP:порт`, сеть, `*`), ошибка соединения называет прокси; IMAP — напрямую;
- секреты: Fernet, ключ `urlsafe_b64(sha256("integration:" + SECRET_KEY))`, в шифротексте — адрес привязки и владелец `integration:<id>`; смена адреса без новых секретов — 422 `secret_rebind_required`; смена `SECRET_KEY` — `secret_problem` у подключения, перешифрования нет;
- включение только после успешной проверки текущих настроек (409 `check_required`), изменение настроек или секретов снимает `verified_at`;
- коннекторы: `podelu`, `puls`, `jira`, `confluence`, `bitrix24`, `exchange`, `onec`, `folder` (одиночный); «По Делу» и «Пульс» — режим `mode`: `key` (по умолчанию) — ключ интеграции «По Делу» 1.4.5+ (`podelu_…`, `/api/integrations/v1`, области `org.read`, `users.read`, `tasks.attachments.read`, `tasks.comment`; задачи по курсору `activityAt`, повторы по `sha256` без скачивания, комментарий системы, 403 `comments_disabled` — предупреждение, 429 — «Частично» с продолжением) и «Пульса» 0.6.0+ (`puls_…`, `/api/integration/v1`, права `projects.read` и `projects.stats`, не больше 200 проектов), `session` — служебная учётная запись (CSRF, вход, выход всегда) для более ранних версий; ошибки ключа — не принят (401), отозван (`key_revoked`), нет области (`insufficient_scope`), лимит (429), нет API ключей (404 на `/ping`); ссылки наружу — по `PUBLIC_URL`; Confluence публикует `reports.company_scorecard` (отчёт без пользователя), поле «Адрес «Дашбордов компании»» убрано; «По Делу» с «Отключать отсутствующих» отключает только своих (`org_source = podelu`, журнал — «нет среди активных в «По Делу»»), служебная учётная запись защищена (`keep`).

### Доступ и администрирование

- полномочия `data.manage` («Входящие данные») и `integrations.manage` («Интеграции»); доступ ко «Входящим» без полномочия — `Dataset.can_apply` хотя бы одного набора (у `indicators` — любой уровень `editor`), видимость — свои наборы и свои загрузки;
- `/api/auth/me` → `inbox: {available, pending}` — пункт меню и счётчик (один COUNT по индексу): с `data.manage` — все ожидающие, иначе — наборов, которые пользователь применяет;
- `/api/inbox/rules` — `{rules: […]}`, `/api/inbox/folder` → `folders[].patterns` и `detect {threshold, name_bonus}`, `/api/integrations/keys` → `rate_limit`, `GET /api/integrations/keys/scopes` — подписи областей, `/kinds` → `secret_url_fields`, `order`, `admin_only`, `admin_only_note`, `counter_labels`; у подключения — `schedule` (записи с `label` и `next_run_at`), `can_manage`, `current_error`;
- описания `data.manage` и `integrations.manage` называют доступ к данным; «Руководство администратора» (`/guide/admin`) и «?» на страницах администрирования — администратору и сотрудникам с любым полномочием администрирования (`auth.canReadAdminGuide`), остальным — «Нет доступа» с причиной `admin-guide`;
- «Вход по домену» — `/admin/directory` (прежний `/admin/integrations` занят «Интеграциями»);
- журнал изменений: `inbox_item`, `inbox_rule`, `integration`, `inbound_key`.

### Развёртывание

- сервис `worker` (`python -m app.cli worker`, тот же образ, переменные — якорь `*app-environment`, том `inbox`, `depends_on: app healthy`, без healthcheck, `stop_grace_period: 60s`); несколько экземпляров безопасны;
- переменные `INBOX_DIR` (`/data/inbox`), `INBOX_SETTLE_SECONDS` (10), `INBOX_MAX_MB` (20), `INBOX_RETENTION_DAYS` (90), `INBOUND_RATE_LIMIT` (120), `WORKER_TICK_SECONDS` (30), `INTEGRATION_RUNS_KEEP` (200), `PUBLIC_URL`, `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` (передаются в `app` и `worker`), `PODELU_`, `PULS_`, `JIRA_`, `CONFLUENCE_`, `BITRIX24_`, `EXCHANGE_`, `ONEC_ALLOWED_HOSTS`;
- зависимости `requests`, `cryptography`, `exchangelib` (необязательная, для EWS); `docker-compose.yml` — тег образа по умолчанию `0.4.0`;
- команды `worker [--once]`, `inbox scan`, `inbox cleanup`, `integrations list`, `integrations run ID|ВИД [--action] [--force]` (выключенное подключение — только по номеру с `--force`, по виду — только включённые);
- интерфейс: контраст приглушённого текста и значков статусов — WCAG AA в светлой и тёмной теме.

## Версия 0.3.0 (Ноябрь 2026 г.)

Сквозные отчёты, светофоры и статусы по уровням сотрудников: каталог показателей, свёртка по структуре, статус подразделений с объяснением, отбор под доступ пользователя (область, глубина детализации, классы данных), ввод значений и загрузка Excel, PDF. Подробности — [release notes](release-notes/v0.3.0.md), решение — [ADR-0010](architecture/adr-0010-cross-reports.md), регламент — [обновление до 0.3.0](runbooks/upgrade-to-0.3.0.md).

### Схема БД — `0015_reports` (откат поддерживается)

- новые таблицы: `indicators` (каталог: класс данных, направление, свёртка `sum` · `avg` · `none`, правило `threshold` · `target`, пороги и допустимые отклонения, цель по умолчанию, источник `manual` · `computed` и `source_key`, служба-владелец, `expected_kinds`, порядок, активность), `indicator_values` (показатель, подразделение, период — первое число месяца; значение, цель, комментарий, источник `manual` · `import`, кто и когда; уникальность показатель + подразделение + период), `unit_status_notes` (заметка `watch` за период с комментарием и автором), `report_revision` (одна строка);
- существующие таблицы не меняются; настройка `report_service_units` в `app_settings` создаётся при первом изменении;
- откат (`downgrade 0014_org_access`) удаляет таблицы отчётов и `report_service_units`; полномочие `reports.manage` в `users.capabilities` остаётся — снимите его до отката.

### Расчёт и доступ

- вычисляемые показатели (`INDICATOR_SOURCES`): `hr.hired`, `hr.fired` — по подразделению записи реестра (сопоставление по коду или названию), `hr.turnover`, `hr.time_to_fill` — уровня компании, `tech.in_work`, `tech.solved`, `tech.ratio`, `pp.green_share` — подразделения службы (`report_service_units`, по умолчанию коды HR, TECH, PROJ); не хранятся;
- значение — собственное или свёртка вложенных; статус подразделения — худший из показателей и вложенных; пропуск ожидаемого значения (`expected_kinds`, с месяца создания или первого значения) — «Нет данных» и критичное нарушение полноты, статус не ухудшает;
- расчёт за период — один раз на ревизии структуры, данных служб и значений (`report_revision`) в памяти процесса, затем отбор под пользователя: вершины — область, глубина — `drill_depth` (при области `unit` — 0), показатели недоступных классов не передаются и не влияют на статус и объяснение; ключ кэша ответов — права просмотра;
- ввод: уровень `editor` к `owner_service` в области пользователя для службы или `reports.manage`; класс данных показателя должен быть доступен; сохранение всё-или-ничего, ошибки — `fields["items.N.*"]`;
- заметка «под контролем» — руководитель подразделения или `reports.manage`.

### API

- `/api/reports/scorecard`, `/units/{id}`, `/periods`, `/summary`, `/meta`, `/indicators` (CRUD, `DELETE ?force=`), `/values` (GET/PUT), `/values/import` (план → применение, 409 `import_has_errors`), `/units/{id}/note`, `/settings`; `/api/pdf/reports/scorecard` (право на выгрузку);
- коды ошибок: `unit_out_of_scope`, `entry_forbidden`, `note_forbidden`, `indicator_has_values`, `import_has_errors`.

### Доступ и администрирование

- полномочие `reports.manage` («Ведёт сквозные отчёты»): «Администрирование → Показатели», ввод любой службы во всех подразделениях, заметки о любом подразделении;
- глубина детализации и класс `financial` модели доступа 2.0 начинают действовать — в сквозном отчёте;
- журнал изменений: `indicator`, `indicator_value` (сохранение и загрузка), `unit_status_note`, `report_settings`.

### Развёртывание

- новых переменных окружения и зависимостей нет; `docker-compose.yml` — тег образа по умолчанию `0.3.0`;
- при первом запуске каталог получает восемь вычисляемых показателей служб; вводимые показатели добавляет администратор, удалённые вычисляемые повторно не создаются;
- демо-стенд: 14 показателей и значения за 12 месяцев, пропуск и заметка; `tech_dir` — `apparat_gd: editor`;
- нагрузочная проверка — `docs/performance/load-test-0.3.0.md`.

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
