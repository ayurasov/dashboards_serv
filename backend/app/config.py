"""Application configuration.

Environment variables (no prefix — set directly in docker-compose.yml or .env):
  DATABASE_URL                  SQLite or PostgreSQL DSN
  SECRET_KEY                    JWT signing secret
  ACCESS_TOKEN_EXPIRE_MINUTES   Token lifetime (default 480 = 8 h)
  CORS_ORIGINS                  Comma-separated origins or * (default *)
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Docker: DATABASE_URL=sqlite:////data/hr_dashboard.db  (4 slashes = absolute path)
    # Local dev: defaults to a local SQLite file next to the backend/ run directory
    database_url: str = "sqlite:///./hr_dashboard.db"
    secret_key: str = "change-me-in-production-please-use-a-long-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours
    cors_origins: str = "*"

    model_config = {
        "env_file": ".env",
        # No env_prefix: env vars are passed without any prefix.
        # Variable names match the field names above (case-insensitive).
        # Docker compose passes DATABASE_URL, SECRET_KEY etc. directly.
    }

    @property
    def cors_list(self):
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()


def db_connect_args():
    """SQLite requires check_same_thread=False; other DBs need no extra args."""
    if settings.database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}
