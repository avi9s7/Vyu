from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VYU_",
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    git_sha: str = "unknown"
    image_digest: str | None = None
    expected_migration_revision: str = "0003"
    service_name: str = "vyu-api"
