from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VYU_",
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    database_url: str = "postgresql+psycopg://vyu_app:local-vyu-password@127.0.0.1:5432/vyu"
    migration_database_url: str = (
        "postgresql+psycopg://vyu_migrator:local-migrator-password@127.0.0.1:5432/vyu"
    )
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_max_overflow: int = Field(default=5, ge=0, le=100)
    database_pool_timeout_seconds: int = Field(default=10, ge=1, le=120)
    database_statement_timeout_ms: int = Field(default=30_000, ge=1_000, le=300_000)
    database_echo: bool = False

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("VYU database URL must use PostgreSQL with Psycopg")
        return value
