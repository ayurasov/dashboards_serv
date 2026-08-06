"""Application configuration."""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # SQLite for dev/Windows; set DATABASE_URL=postgresql+psycopg2://... for production
    database_url: str = "sqlite:///./hr_dashboard.db"
    secret_key: str = "change-me-in-production-please-use-a-long-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours
    cors_origins: str = "*"

    class Config:
        env_file = ".env"
        env_prefix = "HR_"

    @property
    def cors_list(self):
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

# For SQLite we need check_same_thread=False
def db_connect_args():
    if settings.database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}
