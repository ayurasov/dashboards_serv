# Dashboard

Полноценное full-stack приложение для визуализации и управления метриками HR-команды.
Стек: **Vue 3 + Vite + Apache ECharts** (фронтенд) и **Python FastAPI + SQLAlchemy + SQLite** (бэкенд).

## Возможности

- **Дашборд** — KPI-карточки, графики (принятые/уволенные, текучесть, светофор метрик), таблица метрик со статусами
- **Реестр сотрудников** — приёмы и увольнения по месяцам, поиск, фильтры
- **Сводка по периодам** — агрегация по кварталам, полугодиям, годам
- **Ролевая модель** — Администратор, Начальник HR, Просмотр, Просмотр отдела
- **Авторизация** — JWT, bcrypt, смена пароля, обязательная смена при первом входе
- **Аналитика светофора** — настраиваемые пороги (зелёный/жёлтый/красный) для каждой метрики
- **Кастомные дашборды** — создание персональных и общих дашбордов с виджетами
- **История изменений** — полный аудит-лог всех операций (создание, изменение, удаление)
- **Экспорт PDF** — красивый отчёт с графиками и таблицами (reportlab + matplotlib)
- **Тёмная тема** — переключение светлая/тёмная тема

## Тестовые пользователи

| Логин | Пароль | Роль | Описание |
|-------|--------|------|----------|
| admin | admin123 | Администратор | Полный доступ, смена пароля при первом входе |
| hr_head | hr123 | Начальник HR | Редактирование данных, кастомные дашборды, заметки |
| viewer | view123 | Просмотр | Только просмотр всех данных |
| it_viewer | it123 | Просмотр отдела | Доступ к данным ИТ-службы |

## Развёртывание на Windows

### Предварительные требования

- **Python 3.11+** (рекомендуется 3.12) — [python.org](https://www.python.org/downloads/)
- **Node.js 20+** — [nodejs.org](https://nodejs.org/)
- **Git** (опционально)

### Шаг 1. Бэкенд

```cmd
cd hr-dashboard-app\backend

:: Создание виртуального окружения
python -m venv venv
venv\Scripts\activate

:: Установка зависимостей
pip install -r requirements.txt

:: Сборка фронтенда (см. Шаг 2), затем запуск:
uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

Приложение будет доступно по адресу: http://127.0.0.1:8100
Документация API (Swagger): http://127.0.0.1:8100/docs

### Шаг 2. Сборка фронтенда

```cmd
cd hr-dashboard-app\frontend

:: Установка зависимостей
npm install

:: Сборка production-версии
npm run build
```

Собранные файлы попадут в `frontend\dist\` и автоматически раздаются бэкендом.

### Шаг 3. Режим разработки (опционально)

Для разработки фронтенда с hot-reload:

```cmd
:: Терминал 1 — бэкенд
cd hr-dashboard-app\backend
venv\Scripts\activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8100

:: Терминал 2 — фронтенд (dev server)
cd hr-dashboard-app\frontend
npm run dev
```

Фронтенд будет на http://127.0.0.1:5173, API проксируется на порт 8100.

## Развёртывание на Ubuntu 24

### Предварительные требования

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv nodejs npm
```

### Установка и запуск

```bash
cd hr-dashboard-app/backend

python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Сборка фронтенда
cd ../frontend
npm install
npm run build

# Запуск
cd ../backend
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

### Production (с systemd)

Создать `/etc/systemd/system/hr-dashboard.service`:

```ini
[Unit]
Description=HR Dashboard API
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/hr-dashboard-app/backend
ExecStart=/opt/hr-dashboard-app/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable hr-dashboard
sudo systemctl start hr-dashboard
```

### Опционально: PostgreSQL

По умолчанию используется SQLite (файл `hr_dashboard.db`). Для PostgreSQL:

```bash
pip install psycopg2-binary
```

Установить переменную окружения:
```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/hr_dashboard"
```

## Тесты

```bash
cd hr-dashboard-app/backend
source venv/bin/activate  # Linux
# или venv\Scripts\activate  # Windows
pip install pytest httpx
pytest tests/ -v
```

## Структура проекта

```
hr-dashboard-app/
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py          # FastAPI app, роутер, статика
│   │   ├── config.py         # Настройки (DATABASE_URL, JWT, CORS)
│   │   ├── database.py       # SQLAlchemy engine, session
│   │   ├── models.py         # Модели БД (User, MonthRecord, MetricDefinition, ...)
│   │   ├── security.py       # bcrypt хеширование, JWT токены
│   │   ├── deps.py           # Зависимости: get_current_user, RBAC checks
│   │   ├── audit.py          # Сервис аудита (логирование изменений)
│   │   ├── analytics.py      # Агрегации, светофор, бенчмарки
│   │   ├── schemas.py        # Pydantic схемы для API
│   │   ├── seed.py           # Начальные данные (пользователи, метрики, Июнь+Июль 2026)
│   │   ├── routers/
│   │   │   ├── auth.py       # Логин, /me, смена пароля
│   │   │   ├── users.py      # CRUD пользователей (admin)
│   │   │   ├── hr.py         # Месяцы, метрики, сотрудники, аналитика
│   │   │   ├── traffic_light.py  # Настройка порогов светофора (admin)
│   │   │   ├── dashboards.py # Кастомные дашборды (hr_head+)
│   │   │   ├── audit.py      # Просмотр аудита (admin)
│   │   │   └── pdf.py        # Экспорт PDF
│   │   └── services/
│   │       └── pdf_export.py # Генерация PDF (reportlab + matplotlib)
│   └── tests/
│       └── test_api.py       # 17 тестов (auth, RBAC, data, traffic-light, PDF, audit)
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.js           # Точка входа
        ├── App.vue           # Layout (sidebar, topbar, theme, modals)
        ├── router.js         # Vue Router с guards (RBAC)
        ├── style.css         # Дизайн-система (переменные, компоненты)
        ├── api/client.js     # HTTP клиент с JWT
        ├── stores/auth.js    # Pinia store авторизации
        ├── components/
        │   └── EChart.vue    # Обёртка Apache ECharts
        └── views/
            ├── Login.vue           # Страница входа
            ├── Dashboard.vue       # Главный дашборд
            ├── Registry.vue       # Реестр сотрудников
            ├── Summary.vue        # Сводка по периодам
            ├── CustomDashboard.vue # Кастомные дашборды
            ├── Users.vue          # Управление пользователями (admin)
            ├── TrafficLightConfig.vue # Настройка светофора (admin)
            └── AuditLog.vue       # История изменений (admin)
```

## Данные

Данные за **Июнь** и **Июль 2026** загружаются автоматически при первом запуске (seed).

### Метрики (15 определений)

- Среднее время закрытия позиций (дн.)
- Текучесть кадров (%)
- Текучесть кадров компании (%)
- Принятые офферы (%)
- Отобрано резюме (чел.)
- Интервью с HR / заказчиком (чел.)
- Количество проектов
- Встречи по адаптации (шт.)
- Процент прохождения ИС — общий / по адаптации (%)
- На адаптации / увольнения на адаптации / завершено ИС (чел.)
- Нанято по списку (чел.)

### Светофор (7 правил)

| Метрика | Зелёный | Жёлтый | Направление |
|---------|---------|--------|-------------|
| Текучесть кадров | ≤3% | ≤5% | Меньше — лучше |
| Текучесть компании | ≤2% | ≤3% | Меньше — лучше |
| Время закрытия | ≤30 дн. | ≤45 дн. | Меньше — лучше |
| Офферы приняты | ≥95% | ≥80% | Больше — лучше |
| ИС общий | ≥95% | ≥85% | Больше — лучше |
| ИС адаптация | ≥90% | ≥80% | Больше — лучше |
| Увольнения на адаптации | ≤0 | ≤2 | Меньше — лучше |

## Расширение

Приложение спроектировано для расширения:
- Новые метрики — через админку или прямое добавление в `MetricDefinition`
- Новые роли — через `RoleEnum` в `models.py`
- PostgreSQL — через `DATABASE_URL`
- Новые виджеты — через `widget_type` в `DashboardWidget`
- Новые пороги светофора — через админку

## Технологии

- **Backend**: FastAPI 0.115, SQLAlchemy 2.0, bcrypt 4.2, python-jose (JWT), reportlab, matplotlib
- **Frontend**: Vue 3.5, Vue Router 4, Pinia 2, Apache ECharts 5, Vite 6
- **Database**: SQLite (по умолчанию), PostgreSQL (опционально)
