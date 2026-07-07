from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class IngestionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VYU_",
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    source_registry_path: Path = Path("config/source_registry.example.json")
    quarantine_bucket: str = "vyu-local-quarantine"
    s3_region: str = "ap-south-1"
    s3_kms_key_id: str = (
        "arn:aws:kms:ap-south-1:123456789012:key/00000000-0000-0000-0000-000000000000"
    )
    presign_expiry_seconds: int = 600
    max_upload_bytes: int = MAX_UPLOAD_BYTES
    policy_version: str = "ingestion_upload_v1"

    @field_validator("max_upload_bytes")
    @classmethod
    def validate_max_upload_bytes(cls, value: int) -> int:
        if value < 1 or value > MAX_UPLOAD_BYTES:
            raise ValueError("max_upload_bytes must be between 1 and 50 MiB")
        return value

    @field_validator("presign_expiry_seconds")
    @classmethod
    def validate_presign_expiry(cls, value: int) -> int:
        if value < 60 or value > 3600:
            raise ValueError("presign_expiry_seconds must be between 60 and 3600")
        return value
