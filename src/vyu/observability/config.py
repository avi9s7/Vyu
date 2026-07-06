from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VYU_", extra="ignore")

    service_name: str = "vyu"
    environment: str = "local"
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://127.0.0.1:4318"
    log_json_enabled: bool = True

    redacted_field_names: tuple[str, ...] = Field(
        default=(
            "authorization",
            "cookie",
            "set-cookie",
            "password",
            "token",
            "access_token",
            "refresh_token",
            "id_token",
            "client_secret",
            "api_key",
            "prompt",
            "document_text",
            "request_body",
            "response_body",
        )
    )
