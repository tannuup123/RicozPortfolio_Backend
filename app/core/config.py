"""Application configuration via pydantic-settings.

Reads all environment variables listed in architecture.md §10.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration — all values come from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ricozportfolio"

    # JWT
    JWT_SECRET_KEY: str = "change-me-to-a-random-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Redis (provisioned, idle for MVP)
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS / Cookies
    FRONTEND_ORIGIN: str = "http://localhost:5173"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"

    # Environment: local | staging | production
    ENVIRONMENT: str = "local"


settings = Settings()
