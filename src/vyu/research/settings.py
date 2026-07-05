from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ResearchSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VYU_",
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    source_registry_path: Path = Path("config/source_registry.example.json")
    policy_version: str = "research_api_v1"
    idempotency_ttl_hours: int = 24
    default_page_size: int = 20
    max_page_size: int = 100

    @field_validator("default_page_size", "max_page_size")
    @classmethod
    def validate_page_size(cls, value: int) -> int:
        if value < 1:
            raise ValueError("page size must be positive")
        return value

    @property
    def requires_only_approved_sources(self) -> bool:
        return self.env in {"staging", "production"}
