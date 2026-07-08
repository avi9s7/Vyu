from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class SynthesisApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VYU_",
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    idempotency_ttl_hours: int = 24
