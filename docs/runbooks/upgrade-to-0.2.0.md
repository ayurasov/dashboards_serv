# Runbook: обновление до 0.2.0

Применимо к установкам версии 0.1.0 (схема `0013_data_revisions`). Установки до 0.1.0 сначала обновляются по `upgrade-to-0.1.0.md` — миграции 0012–0014 выполнятся за один старт.

Что меняется — «Руководство по развёртыванию», раздел «Обновление до 0.2.0»; решения — ADR-0007 (структура), ADR-0008 (пользователи и LDAP), ADR-0009 (модель доступа). Миграция `0014_org_access` не меняет доступ существующих пользователей и поддерживает откат.

## Перед обновлением

1. Объявите окно обслуживания (5–15 минут); приложение перезапускается один раз.
2. Убедитесь, что установлена 0.1.0 и схема актуальна:
   ```bash
   curl -s http://127.0.0.1:8000/api/health        # "version": "0.1.0", schema.current == "0013_data_revisions"
   ```
3. Сохраните копию базы и проверьте, что файл не пустой:
   ```bash
   docker compose exec -T db pg_dump -U dashboards -d dashboards -Fc > before-0.2.0.dump
   ls -lh before-0.2.0.dump
   ```
   SQLite — через API резервного копирования (см. `backup-restore.md`).
4. Запишите контрольные числа:
   ```bash
   docker compose exec -T db psql -U dashboards -d dashboards -c "
     SELECT (SELECT count(*) FROM users) AS users,
            (SELECT count(*) FROM users WHERE is_active) AS active,
            (SELECT count(*) FROM departments) AS departments,
            (SELECT count(*) FROM user_departments) AS user_departments,
            (SELECT count(*) FROM service_access) AS service_access,
            (SELECT count(*) FROM service_access WHERE department_scope) AS scoped;"
   ```
5. Проверьте, что у администраторов нет e-mail, совпадающих с адресами в каталоге домена, если вход по домену будет включаться (сопоставление учётных записей идёт по e-mail).

## Обновление

```bash
git fetch && git checkout v0.2.0
# при необходимости — TIMEZONE в .env (по умолчанию Europe/Moscow)
docker compose up -d --build
docker compose logs app | grep -E "Схема базы|ERROR"
```

В журнале — `Схема базы обновлена: 0013_data_revisions → 0014_org_access`. Справочники (встроенные профили доступа, типы уровней структуры) создаются при этом же старте.

## Проверка

1. `curl -s http://127.0.0.1:8000/api/health` → `"status": "ok"`, `"version": "0.2.0"`, `schema.current == schema.head == "0014_org_access"`.
2. Контрольные числа после обновления:
   ```bash
   docker compose exec -T db psql -U dashboards -d dashboards -c "
     SELECT (SELECT count(*) FROM users) AS users,                                   -- как до обновления
            (SELECT count(*) FROM users WHERE is_active) AS active,                  -- как до обновления
            (SELECT count(*) FROM departments) AS departments,                       -- как до обновления
            (SELECT count(*) FROM departments WHERE parent_id IS NOT NULL) AS nested, -- 0: подразделения — верхний уровень
            (SELECT count(*) FROM users WHERE department_id IS NOT NULL)
              + (SELECT count(*) FROM user_access_units) AS user_departments,        -- = user_departments до обновления
            (SELECT count(*) FROM service_access) AS service_access,                 -- как до обновления
            (SELECT count(*) FROM service_access WHERE org_scope = 'branch') AS scoped, -- = scoped до обновления
            (SELECT count(*) FROM users WHERE access_profile_id IS NOT NULL) AS with_profile, -- 0
            (SELECT count(*) FROM users WHERE auth_source <> 'local') AS ldap_users;  -- 0"
   docker compose exec -T db psql -U dashboards -d dashboards -c "SELECT key, name FROM access_profiles ORDER BY sort_order;"
   # executive, director, head, specialist, employee
   ```
3. Войдите администратором → «Администрирование → Пользователи»: у всех профиль «Индивидуальная настройка» и прежние уровни служб («лично: …»); у бывших «только свои подразделения» на вкладке «Доступ» у службы персонала — область «Своя ветка».
4. Войдите пользователем без роли администратора (или откройте его карточку → «Действующий доступ»): службы и разделы — как в 0.1.0.
5. Откройте «Структура компании», «Подразделения», «Профили доступа», дашборды трёх служб и PDF-отчёт любой страницы.

## После обновления

1. Постройте структуру компании: вложите подразделения в дерево, назначьте руководителей («Подразделения» или «Импорт и экспорт»).
2. Назначьте профили доступа по уровням сотрудников; личные уровни служб из 0.1.0 сохраняются поверх профиля — снимите лишние кнопкой «Как в профиле».
3. Выдайте полномочия «Ведёт структуру компании» и «Ведёт пользователей и доступ», если структуру и пользователей ведёт не администратор.

## Безопасное включение входа по домену

1. Задайте `AUTH_LDAP_URL`, `AUTH_LDAP_BASE_DN`, `AUTH_LDAP_BIND_DN`, `AUTH_LDAP_BIND_PASSWORD` при `AUTH_LDAP_ENABLED=false`; сертификат центра сертификации и остальные `AUTH_LDAP_*` — в `docker-compose.override.yml` («Руководство по развёртыванию», «Вход по домену и Active Directory»). `docker compose up -d`.
2. «Администрирование → Вход по домену»: состояние «Настроен, но выключен», замечаний нет, шифрование — LDAPS или StartTLS (не «Без шифрования»).
3. **Проверить подключение** → «Подключение установлено, служебная учётная запись принята».
4. **Найти учётную запись** для 3–5 сотрудников разных подразделений и для каждого администратора: запись одна, сопоставление ожидаемое («по e-mail» с нужной учётной записью). Администратор не должен сопоставляться с чужой записью каталога.
5. Решите, что делать с сотрудниками без учётной записи: оставить отказ (по умолчанию), `AUTH_LDAP_CREATE_USERS=inactive` (создавать отключёнными) или `active`; задайте `AUTH_LDAP_DEFAULT_PROFILE` и `AUTH_LDAP_GROUP_PROFILES` — страница покажет неизвестные ключи профилей.
6. `AUTH_LDAP_ENABLED=true`, `docker compose up -d`. Войдите тестовым сотрудником: в «Пользователях» у него метка «домен», в журнале изменений — «Вход по учётной записи домена: … привязан к каталогу …».
7. Сохраните хотя бы одного администратора с паролем системы: при недоступном каталоге он войдёт как обычно.

## Откат

Предпочтительно — восстановить копию и вернуть 0.1.0:

```bash
docker compose stop app
docker compose exec -T db pg_restore -U dashboards -d dashboards --clean --if-exists < before-0.2.0.dump
git checkout v0.1.0 && docker compose up -d --build
curl -s http://127.0.0.1:8000/api/health        # "version": "0.1.0"
```

Если после обновления внесены данные служб, которые нужно сохранить, откатите схему образом 0.2.0, затем верните 0.1.0:

```bash
docker compose stop app
docker compose run --rm --no-deps -w /app/backend --entrypoint alembic app downgrade 0013_data_revisions
git checkout v0.1.0 && docker compose up -d --build
```

При откате схемы теряется то, чего нет в 0.1.0: дерево и руководители подразделений (повторяющиеся названия получают номер, пустые коды — код `D<id>`), профили доступа, личные настройки, уровни «нет доступа», полномочия, привязка к домену. Уровни служб и «только свои подразделения» восстанавливаются. Доменным учётным записям и учётным записям «без доступа» после отката выдайте пароль: `docker compose exec -w /app/backend app python -m app.cli reset-password <логин>`.
