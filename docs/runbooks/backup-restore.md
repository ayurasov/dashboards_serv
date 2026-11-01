# Runbook: резервное копирование и восстановление

## Расписание (пример для systemd-timer или cron)

```bash
# /etc/cron.d/dashboards-backup — ежедневно в 02:30, хранить 14 дней
30 2 * * * root cd /opt/dashboards_serv && docker compose exec -T db pg_dump -U dashboards -d dashboards -Fc > /backup/dashboards-$(date +\%F).dump && find /backup -name 'dashboards-*.dump' -mtime +14 -delete
```

## Восстановление PostgreSQL

```bash
docker compose stop app
docker compose exec -T db pg_restore -U dashboards -d dashboards --clean --if-exists < /backup/dashboards-YYYY-MM-DD.dump
docker compose start app
curl -s http://127.0.0.1:8000/api/health
```

Если копия сделана более ранней версией приложения, при старте выполнятся недостающие миграции.

## Проверка копий

Раз в квартал восстанавливайте копию на тестовом стенде и сверяйте числа на странице «О системе».

## SQLite

Копирование без остановки — через API резервного копирования SQLite (см. «Руководство по развёртыванию»). Простое копирование файла во время работы может дать несогласованную копию в режиме WAL.
