# Дашборд техподдержки — серверная версия

## Состав
- `app.py` — Flask-приложение, SQLite БД (`data/tp_report.db`), REST API, отдача статики/шаблона.
- `templates/index.html` — фронтенд (Chart.js через CDN, без сборки).
- `seed_data.json` — исходные данные для первичной инициализации БД.
- `requirements.txt` — Python-зависимости.

Сборка npm не требуется — фронтенд не использует Node.js/webpack, весь JS/CSS встроен в `index.html` и подключает Chart.js через CDN.

## Установка на Ubuntu 24

```bash
cd /tp_report
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

gunicorn app:app --bind 0.0.0.0:39664
```

При первом запуске автоматически создаётся `data/tp_report.db` и заполняется данными из `seed_data.json`.

## Переменные окружения (опционально)

- `TP_PASSWORD` — пароль для правки/импорта/палитры (по умолчанию `TP26!`).
- `TP_SECRET_KEY` — секретный ключ Flask-сессии (генерируется случайно, если не задан; задайте фиксированный для сохранения сессии между перезапусками).

## Постоянный запуск (systemd)

```ini
# /etc/systemd/system/tp_report.service
[Unit]
Description=TP Report Dashboard
After=network.target

[Service]
WorkingDirectory=/tp_report
Environment="TP_PASSWORD=TP26!"
Environment="TP_SECRET_KEY=замените-на-случайную-строку"
ExecStart=/tp_report/venv/bin/gunicorn app:app --bind 0.0.0.0:39664 --workers 2
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tp_report
```

## API

- `GET/POST /api/rows`, `PUT/DELETE /api/rows/<id>`, `POST /api/rows/bulk_import` — данные отчёта.
- `GET/PUT /api/settings/traffic_rules` — правила светофора.
- `GET/PUT /api/settings/block_settings` — включённые блоки дашборда.
- `GET/PUT/DELETE /api/settings/color_palette` — палитра графиков.
- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/status` — сессионная авторизация паролем.

Все операции записи требуют предварительной авторизации (`/api/auth/login`), сессия хранится в cookie Flask.
