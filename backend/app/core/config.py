"""Конфигурация приложения из переменных окружения (и файла .env при разработке).

Все переменные перечислены в .env.example и в руководстве по развёртыванию.
"""
from __future__ import annotations

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
    db_pool_size: int = Field(default=10, ge=1, le=100)
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

    # Демонстрационные данные: пользователи, месяцы службы персонала, отчёт ТП, заявки, партнёрства
    demo_data: bool = False

    # Применять миграции при старте (в Docker это делает docker-entrypoint.sh)
    migrate_on_start: bool = False

    cors_origins: str = ""
    log_level: str = "INFO"
    log_json: bool = False

    max_upload_mb: int = Field(default=20, ge=1, le=200)

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
