# Runbook: обновление до 0.1.0 с версий до 0.1.0

Применимо к установкам «Dashboards API 1.1» (SQLite в томе Docker `db_data` или локальный файл `backend/hr_dashboard.db`).

## Перед обновлением

1. Объявите окно обслуживания (5–15 минут).
2. Остановите старую версию (`docker compose down` в её папке — контейнер `dashboards_serv` занимает порт) и сохраните копии базы вне папки проекта. Имя тома начинается с имени папки проекта: `docker volume ls | grep db_data` (для папки `dashboards` — `dashboards_db_data`):
   ```bash
   mkdir -p ~/dashboards-backup && git rev-parse HEAD > ~/dashboards-backup/old-commit.txt && cp .env ~/dashboards-backup/env-old
   docker run --rm -v dashboards_db_data:/data -v ~/dashboards-backup:/backup alpine sh -c "cp /data/hr_dashboard.db /backup/hr_dashboard-original.db && cp /data/hr_dashboard.db /backup/hr_dashboard-work.db"
   ```
3. Запишите контрольные числа (в старой версии или через `sqlite3`): число пользователей, месяцев службы персонала (`month_records`), недель отчёта ТП (`tp_report_rows`), заявок Naumen (`naumen_tickets`), партнёрств (`partnerships`).

## Обновление

См. «Руководство по развёртыванию», раздел «Обновление до 0.1.0 с версий до 0.1.0»: код новой версии — в чистой папке (`git clone` в папку с тем же именем: оставшиеся файлы старой версии, например `frontend/src/router.js`, ломают сборку интерфейса), новый `.env`, сборка образа и перенос копии базы в PostgreSQL. Команды с копией базы в смонтированной папке выполняются с `-u root` — иначе «attempt to write a readonly database».

Миграция `0012_v0_1_0_schema` выполняется автоматически и пишет в журнал `Схема базы обновлена: 0011_naumen_tickets → 0012_v0_1_0_schema`. База без истории Alembic распознаётся по таблицам прежней версии и сначала помечается ревизией `0011_naumen_tickets` (`WARNING … без истории миграций`).

## Проверка

1. `curl -s http://127.0.0.1:8000/api/health` → `"status": "ok"`, `schema.current == schema.head`.
2. Войдите администратором → «Администрирование → О системе»: числа пользователей, месяцев, недель ТП, заявок и партнёрств совпадают с записанными (недели ТП могут быть меньше на число дублей одной недели и строк без года — миграция их схлопывает и отбрасывает).
3. «Администрирование → Пользователи»: у бывших «Начальников службы персонала» — «Управление» службой персонала, у «Просмотра отдела» — «Просмотр» с отметкой «только свои подразделения».
4. Откройте дашборды трёх служб и PDF-отчёт любой страницы.

## Откат

Откат миграции 0012 не поддерживается, но старый том не меняется — переносится копия базы. Верните прежнюю папку и код:

```bash
docker compose down
cd .. && mv dashboards dashboards-new && mv dashboards-old dashboards && cd dashboards
git checkout $(cat ~/dashboards-backup/old-commit.txt) && cp ~/dashboards-backup/env-old .env
docker compose up -d --build
```
