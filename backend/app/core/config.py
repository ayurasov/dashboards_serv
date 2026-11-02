"""Конфигурация приложения из переменных окружения (и файла .env при разработке).

Все переменные перечислены в .env.example и в руководстве по развёртыванию.
"""
from __future__ import annotations

import re
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent

# Значение-заглушка из .env.example: с ним сервер в режиме production не стартует.
PLACEHOLDER_SECRET = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Окружение: development — подсказки и мягкие проверки, production — строгие.
    app_env: Literal["development", "production", "test"] = "development"

    # PostgreSQL (рекомендуется): postgresql+psycopg://user:pass@host:5432/db
    # SQLite (разработка, небольшие установки): sqlite:///./dashboards.db
    database_url: str = "sqlite:///./dashboards.db"
    # Соединений на процесс: постоянных и дополнительных при пике. Сумма по всем процессам
    # WEB_CONCURRENCY × (DB_POOL_SIZE + DB_MAX_OVERFLOW) должна быть меньше max_connections
    # PostgreSQL (по умолчанию 100) с запасом; при нехватке запрос ждёт до DB_POOL_TIMEOUT.
    db_pool_size: int = Field(default=5, ge=1, le=100)
    db_max_overflow: int = Field(default=4, ge=0, le=100)
    db_pool_timeout: int = Field(default=30, ge=1, le=300)
    # Запросов к базе одновременно в процессе (0 — по числу соединений DB_POOL_SIZE + DB_MAX_OVERFLOW).
    # Остальные ждут очереди без потока и соединения; дольше DB_QUEUE_TIMEOUT — ответ 503.
    db_concurrency: int = Field(default=0, ge=0, le=200)
    db_queue_timeout: int = Field(default=30, ge=1, le=300)
    # Потоков для обработчиков в процессе (0 — по числу соединений с базой плюс 8)
    threadpool_size: int = Field(default=0, ge=0, le=200)
    # Одновременных PDF-отчётов в процессе (построение графиков нагружает процессор)
    pdf_concurrency: int = Field(default=2, ge=1, le=16)
    db_echo: bool = False

    secret_key: str = PLACEHOLDER_SECRET

    # Сессии: httpOnly-cookie + CSRF-токен в заголовке X-CSRF-Token.
    session_cookie_name: str = "ds_session"
    csrf_cookie_name: str = "ds_csrf"
    session_lifetime_hours: int = Field(default=12, ge=1, le=24 * 30)
    session_idle_minutes: int = Field(default=240, ge=5, le=24 * 60)
    session_cookie_secure: bool = False

    # Пароли и вход
    password_min_length: int = Field(default=8, ge=6, le=128)
    bcrypt_rounds: int = Field(default=12, ge=4, le=16)
    login_rate_limit: int = Field(default=10, ge=1, description="Неудачных попыток входа за окно")
    login_rate_window_seconds: int = Field(default=300, ge=10)

    # Первичная учётная запись администратора (создаётся, только если пользователей нет)
    admin_username: str = "admin"
    admin_password: str = ""

    # Вход по учётной записи домена (LDAP / Active Directory, ADR-0008). Секреты в API не попадают.
    auth_ldap_enabled: bool = False
    auth_ldap_url: str = ""                      # ldaps://dc.example.local:636 или ldap://…
    auth_ldap_base_dn: str = ""
    auth_ldap_bind_dn: str = ""                  # служебная учётная запись только для чтения
    auth_ldap_bind_password: str = ""
    auth_ldap_user_filter: str = ("(&(objectClass=person)(|(sAMAccountName={login})(userPrincipalName={login})"
                                  "(mail={login})(uid={login})))")
    auth_ldap_attr_id: str = "objectGUID"        # FreeIPA / OpenLDAP: entryUUID
    auth_ldap_attr_email: str = "mail"
    auth_ldap_attr_name: str = "displayName"     # FreeIPA: cn
    auth_ldap_attr_login: str = "sAMAccountName"  # FreeIPA: uid
    auth_ldap_attr_position: str = "title"
    auth_ldap_attr_groups: str = "memberOf"
    auth_ldap_ca_file: str = ""
    auth_ldap_start_tls: bool = False            # StartTLS для ldap:// (для ldaps:// не нужен)
    auth_ldap_timeout: int = Field(default=5, ge=1, le=30)
    auth_ldap_create_users: Literal["", "active", "inactive"] = ""  # первый вход без учётной записи
    auth_ldap_default_profile: str = ""          # ключ профиля доступа для созданных при входе
    # «DN группы=ключ профиля;DN группы=ключ профиля» — первое совпадение при создании учётной записи
    auth_ldap_group_profiles: str = ""
    auth_ldap_admin_group: str = ""              # DN группы, участники которой создаются администраторами
    auth_ldap_login_hint: str = ""               # подсказка на странице входа

    # Синхронизация структуры и сотрудников с Active Directory. Пустые адрес и учётные данные —
    # те же, что у входа по домену.
    ad_sync_url: str = ""
    ad_sync_base_dn: str = ""
    ad_sync_bind_dn: str = ""
    ad_sync_bind_password: str = ""
    ad_sync_user_filter: str = "(&(objectCategory=person)(objectClass=user)(mail=*))"
    ad_sync_path_source: Literal["attributes", "ou"] = "attributes"
    ad_sync_path_attributes: str = "company,division,department"
    ad_sync_detect_heads: bool = True
    ad_sync_ca_file: str = ""
    ad_sync_start_tls: bool = False

    # Демонстрационные данные: пользователи, месяцы службы персонала, отчёт ТП, заявки, партнёрства
    demo_data: bool = False

    # Применять миграции при старте (в Docker это делает docker-entrypoint.sh)
    migrate_on_start: bool = False

    # Часовой пояс компании: границы дней в фильтрах журнала, время в PDF-отчётах
    timezone: str = "Europe/Moscow"

    # Адрес, по которому пользователи открывают «Дашборды» (https://dashboards.company.ru), — для ссылок наружу:
    # страница сквозного отчёта в Confluence, комментарий в задаче «По Делу». Пусто — ссылки не ставятся
    public_url: str = ""

    cors_origins: str = ""
    log_level: str = "INFO"
    log_json: bool = False

    max_upload_mb: int = Field(default=20, ge=1, le=200)

    # Входящие данные (ADR-0011). Папка «Входящие» на сервере (в Docker — том /data/inbox);
    # пусто — папка не опрашивается. Файл берётся в работу, когда не меняется дольше INBOX_SETTLE_SECONDS.
    inbox_dir: str = ""
    inbox_settle_seconds: int = Field(default=10, ge=0, le=3600)
    # Предел размера файла во входящих (папка, загрузка, приём по API)
    inbox_max_mb: int = Field(default=20, ge=1, le=200)
    # Сколько дней хранятся исходные файлы обработанных элементов (в базе и в processed/, rejected/ папки)
    inbox_retention_days: int = Field(default=90, ge=1, le=3650)
    # Планировщик (python -m app.cli worker): период опроса папки и расписаний, секунд
    worker_tick_seconds: int = Field(default=30, ge=1, le=3600)
    # Запусков в журнале каждого подключения (старые удаляются)
    integration_runs_keep: int = Field(default=200, ge=10, le=10000)
    # Приём по API (/api/inbound/v1): запросов в минуту на один ключ
    inbound_rate_limit: int = Field(default=120, ge=1, le=10000)

    # Кэш готовых ответов аналитики (сбрасывается по ревизии данных службы)
    response_cache: bool = True
    response_cache_size: int = Field(default=512, ge=16, le=10000)

    frontend_dist: Path = PROJECT_DIR / "frontend" / "dist"

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, value: str) -> str:
        # Привычные postgres:// и postgresql:// ведут на драйвер psycopg 3.
        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://"):]
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://"):]
        return value

    @field_validator("public_url")
    @classmethod
    def _check_public_url(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            return ""
        if text.endswith("/"):
            raise ValueError("PUBLIC_URL — без «/» в конце: https://dashboards.company.ru")
        if not re.match(r"^https?://[^\s/?#@]+(/[^\s?#]*)?$", text, re.IGNORECASE):
            raise ValueError("PUBLIC_URL — адрес http(s)://узел[:порт][/путь] без логина, «?» и «#»")
        return text

    @model_validator(mode="after")
    def _check_production(self) -> Settings:
        if self.app_env == "production":
            if self.secret_key.startswith(PLACEHOLDER_SECRET) or len(self.secret_key) < 32:
                raise ValueError(
                    "SECRET_KEY не задан или короче 32 символов. "
                    "Сгенерируйте: openssl rand -hex 32"
                )
        elif self.secret_key.startswith(PLACEHOLDER_SECRET):
            # Разработка: случайный ключ на процесс — сессии сбрасываются при перезапуске.
            self.secret_key = secrets.token_hex(32)
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def inbox_path(self) -> Path | None:
        return Path(self.inbox_dir).expanduser() if self.inbox_dir.strip() else None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
