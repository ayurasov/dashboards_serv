# Runbook: автоматические миграции при старте

- Контейнер выполняет `python -m app.cli migrate` перед запуском gunicorn (`backend/docker-entrypoint.sh`). Команда: миграции Alembic → справочники → демо-данные (если `DEMO_DATA=true`) → первичный администратор (если пользователей нет).
- На PostgreSQL миграции идут под `pg_advisory_lock`: второй контейнер ждёт первого, затем видит актуальную схему и ничего не делает.
- Без Docker (разработка): `cd backend && python -m app.cli migrate`; либо `MIGRATE_ON_START=true` для запуска миграций при старте uvicorn.
- Состояние схемы: `python -m app.cli check-schema` (код 0 — актуальна) и `/api/health` (`degraded`, если нет).
- Новая миграция: измените модели, затем `cd backend && alembic revision --autogenerate -m "описание"`, проверьте файл, добавьте преобразование данных, напишите тест в `tests/test_migrations.py`. Тест сверки схемы (`test_fresh_sqlite_matches_models`, на PostgreSQL — `test_fresh_postgres_matches_models`) не пропустит расхождение моделей и миграций.
- Миграции после 0012 обязаны иметь рабочий `downgrade()` или явный отказ с объяснением.
