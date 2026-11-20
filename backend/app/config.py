from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os
from pathlib import Path

# Locate backend/.env file relative to this file
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"

class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/postgres",
        description="PostgreSQL connection string (Supabase or local)"
    )
    supabase_url: str = Field(
        default="https://example.supabase.co",
        description="Supabase project URL"
    )
    supabase_publishable_key: str = Field(
        default="example-publishable-key",
        description="Supabase anon/publishable API key"
    )
    app_origin: str = Field(
        default="http://localhost:8000",
        description="Origin for CORS and redirect security"
    )
    session_secret: str = Field(
        default="mb-associates-dev-session-secret-change-in-prod-at-least-32-chars",
        description="Secret key for signing staff sessions and CSRF tokens"
    )
    environment: str = Field(
        default="development",
        description="development, staging, or production"
    )
    cookie_name: str = "mb_staff_session"
    session_max_age_seconds: int = 86400  # 24 hours

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore"
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings()
