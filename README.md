# Дашборды компании v0.1.0

Показатели служб АЛМИ Партнер в одном месте: служба персонала, техническая поддержка, технологические партнёрства. Светофор «норма — внимание — критично» по настраиваемым порогам, динамика к прошлому периоду, цели, реестры, загрузка отчётов из Excel, PDF-отчёты и выгрузки, разграничение доступа по службам и журнал всех изменений.

## Возможности

- **Обзор** — главное по каждой доступной службе на одной странице: ключевые показатели, светофор, свежесть данных, последние загрузки.
- **Служба персонала** — дашборд (приём и увольнение, текучесть с целью, воронка найма, светофор по месяцам, подразделения), реестр приёмов и увольнений, ввод данных месяца, сводка по месяцам/кварталам/полугодиям/годам, цели и бенчмарки, пользовательские дашборды.
- **Техническая поддержка** — дашборд недельного отчёта (нагрузка, трудозатраты по клиентам, AlterOS, AlterOffice, Project Server, каналы), недельный отчёт с загрузкой xlsx/csv, сравнение периодов, аналитика заявок Naumen SD, сопоставление отчёта и Naumen.
- **Партнёрства** — реестр сертификаций совместимости со светофором каждой записи, аналитика, сводка по годам, хронология.
- **Доступ** — роли «Администратор» и «Пользователь», уровни доступа к службе «Просмотр», «Ввод данных», «Управление», ограничение реестра своими подразделениями.
- **Администрирование** — пользователи и матрица доступа, подразделения, журнал изменений, палитры, состояние системы.
- **Интерфейс** — светлая и тёмная тема, фильтры в адресе страницы, личная настройка дашбордов, встроенные руководства и история версий.

## Документация

| Документ | Для кого |
| --- | --- |
| [Руководство пользователя](docs/manuals/user-guide.md) ([PDF](docs/manuals/user-guide.pdf)) | сотрудники и руководители служб; встроено в приложение |
| [Руководство администратора](docs/manuals/admin-guide.md) ([PDF](docs/manuals/admin-guide.pdf)) | администраторы системы и руководители служб |
| [Руководство по развёртыванию](docs/manuals/deployment-guide.md) ([PDF](docs/manuals/deployment-guide.pdf)) | системные администраторы |
| [CHANGELOG](CHANGELOG.md), [история версий](docs/versions.md), [для администраторов](docs/versions_admin.md), [release notes](docs/release-notes) | все |
| [Архитектурные решения (ADR)](docs/architecture) | разработчики |
| [Регламенты](docs/runbooks): обновление до 0.1.0, миграции, резервное копирование | эксплуатация |
| [Нагрузочная проверка](docs/performance/load-test-0.1.0.md) | эксплуатация, разработчики |
| OpenAPI — `/api/docs` работающего сервера | интеграторы |

## Стек

| Часть | Технологии |
| --- | --- |
| Интерфейс | Vue 3.5, Vite 8, Pinia 4, Vue Router 5, Apache ECharts 6, Inter Variable; Vitest, ESLint, Playwright |
| Сервер | Python 3.12, FastAPI, SQLAlchemy 2.1, Alembic, Pydantic 2, psycopg 3, gunicorn + uvicorn-worker, ReportLab, Matplotlib, openpyxl; pytest, ruff |
| База данных | PostgreSQL 16 (рекомендуется), SQLite (разработка) |
| Поставка | Docker (многостадийный образ), Docker Compose, GitHub Actions |

## Быстрый запуск через Docker

```bash
git clone https://github.com/ayurasov/dashboards_serv.git && cd dashboards_serv
cp .env.example .env
openssl rand -hex 32        # вставьте в SECRET_KEY; задайте POSTGRES_PASSWORD и ADMIN_PASSWORD
docker compose up -d --build
curl -s http://127.0.0.1:8000/api/health
```

Откройте `http://127.0.0.1:8000` и войдите администратором (`ADMIN_USERNAME` / `ADMIN_PASSWORD`; если пароль не задан — временный пароль в `docker compose logs app`).

Демонстрационный стенд с данными и учётными записями разных уровней доступа: `DEMO_DATA=true docker compose up -d --build` (логины — в руководстве администратора, раздел «Демонстрационный стенд»).

## Разработка

```bash
# сервер (порт 8000)
cd backend
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
DEMO_DATA=true python -m app.cli migrate        # SQLite ./dashboards.db, демо-данные
uvicorn app.main:app --reload

# интерфейс (порт 5173, /api проксируется на 8000)
cd frontend
npm ci
npm run dev
```

Для работы с PostgreSQL задайте `DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/dashboards`.

## Тесты и проверки

```bash
cd backend && ruff check . && pytest                       # + TEST_POSTGRES_URL=… — миграции на PostgreSQL
cd frontend && npm run lint && npm test && npm run build
cd frontend && E2E_BASE_URL=http://127.0.0.1:8000 npx playwright test   # сервер с DEMO_DATA=true
locust -f loadtest/locustfile.py --host http://127.0.0.1:8000 --users 1000 --spawn-rate 25 --run-time 6m --headless
```

CI (GitHub Actions): `backend-ci` (ruff, pytest с PostgreSQL 16, миграции с нуля), `frontend-ci` (ESLint, Vitest, сборка), `e2e` (Playwright на демо-данных).

## База данных и миграции

Схемой управляет только Alembic; `python -m app.cli migrate` применяет миграции (под блокировкой на PostgreSQL), обновляет справочники и создаёт первичного администратора. В Docker это происходит при старте контейнера. Тест сверки схемы не даёт моделям и миграциям разойтись. Базы версий до 0.1.0 обновляются миграцией `0012_v0_1_0_schema` с переносом всех данных — см. [регламент](docs/runbooks/upgrade-to-0.1.0.md).

## Структура репозитория

```
backend/
  app/core        конфигурация, база, миграции, безопасность, ошибки, журнал
  app/models      модели SQLAlchemy (общие, персонал, техподдержка, партнёрства)
  app/schemas     схемы Pydantic
  app/services    аналитика служб, светофор, доступ, журнал, кэш, импорт/экспорт, PDF, справочники
  app/api         роутеры FastAPI и зависимости прав
  app/data/demo   наборы данных демо-стенда
  migrations      Alembic (0012 — схема 0.1.0)
  scripts         перенос SQLite → PostgreSQL
  tests           pytest
frontend/
  src/components  оболочка, компоненты дизайн-системы, графики
  src/views       экраны служб, администрирования, справки
  src/domain      предметная логика экранов (с тестами)
  e2e             Playwright
docs/             руководства, история версий, release notes, ADR, регламенты, производительность
loadtest/         нагрузочный сценарий Locust
tools/docs/       сборка руководств в PDF и DOCX, снимки экрана
```

## Версии и ветки

Версия — `backend/app/__init__.py` и `frontend/package.json`; ветка разработки версии — `vX.Y.Z`. Каждая версия сопровождается записью в CHANGELOG, историей версий, release notes и обновлёнными руководствами и тестами.

© Александр Юрасов, 2026
