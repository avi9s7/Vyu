from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.vyu.retrieval.index_contracts import APPROVED_EMBEDDING_DIMENSIONS

if TYPE_CHECKING:
    from src.vyu.model_gateway.secrets import SecretResolver


class ModelGatewayConfigError(ValueError):
    """Raised when model gateway configuration is incomplete or unsafe."""


class ModelGatewaySettings(BaseSettings):
    """Non-secret model gateway settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="VYU_",
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    env: str = "local"
    generation_provider: str = "deterministic"
    generation_model: str = "vyu-deterministic-v1"
    embedding_provider: str = "deterministic"
    embedding_model: str = "vyu-deterministic-v1"
    embedding_dimensions: int = APPROVED_EMBEDDING_DIMENSIONS
    generation_timeout_seconds: int = 120
    embedding_timeout_seconds: int = 60
    max_input_tokens: int = Field(default=120_000, validation_alias="MODEL_MAX_INPUT_TOKENS")
    max_output_tokens: int = Field(default=8_192, validation_alias="MODEL_MAX_OUTPUT_TOKENS")
    max_cost_minor_per_call: int = Field(default=500, validation_alias="MODEL_MAX_COST_MINOR")
    cost_currency: str = Field(default="USD", validation_alias="MODEL_COST_CURRENCY")
    model_policy_version: str = ""
    prompt_template_id: str = ""
    prompt_version: str = ""
    providers_config_secret_arn: str = ""
    providers_secret_file: Path | None = None
    enable_fixture_adapter: bool = Field(default=False, validation_alias="MODEL_ENABLE_FIXTURE_ADAPTER")
    secret_cache_ttl_seconds: int = Field(default=300, validation_alias="MODEL_SECRET_CACHE_TTL_SECONDS")
    aws_region: str | None = None

    @field_validator("generation_timeout_seconds", "embedding_timeout_seconds")
    @classmethod
    def validate_positive_timeout(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("timeout must be positive")
        return value

    @field_validator("max_input_tokens", "max_output_tokens", "max_cost_minor_per_call")
    @classmethod
    def validate_positive_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("limit must be positive")
        return value

    @field_validator("embedding_dimensions")
    @classmethod
    def validate_embedding_dimensions(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("embedding dimensions must be positive")
        return value

    @property
    def is_deployed_environment(self) -> bool:
        return self.env in {"staging", "production", "prod"}

    def safe_summary(self) -> dict[str, object]:
        return {
            "env": self.env,
            "generation_provider": self.generation_provider,
            "generation_model": self.generation_model,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": self.embedding_dimensions,
            "generation_timeout_seconds": self.generation_timeout_seconds,
            "embedding_timeout_seconds": self.embedding_timeout_seconds,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_cost_minor_per_call": self.max_cost_minor_per_call,
            "cost_currency": self.cost_currency,
            "model_policy_version": self.model_policy_version,
            "prompt_template_id": self.prompt_template_id,
            "prompt_version": self.prompt_version,
            "providers_config_secret_arn_configured": bool(self.providers_config_secret_arn.strip()),
            "providers_secret_file": str(self.providers_secret_file) if self.providers_secret_file else None,
            "enable_fixture_adapter": self.enable_fixture_adapter,
            "secret_cache_ttl_seconds": self.secret_cache_ttl_seconds,
            "aws_region": self.aws_region,
        }


def validate_model_gateway_startup(
    settings: ModelGatewaySettings,
    *,
    resolver: SecretResolver | None = None,
    active_index_dimensions: Sequence[int] = (),
) -> None:
    """Fail closed for staging/production startup checks."""

    if not settings.is_deployed_environment:
        return

    required = {
        "VYU_GENERATION_PROVIDER": settings.generation_provider,
        "VYU_GENERATION_MODEL": settings.generation_model,
        "VYU_EMBEDDING_PROVIDER": settings.embedding_provider,
        "VYU_EMBEDDING_MODEL": settings.embedding_model,
        "VYU_MODEL_POLICY_VERSION": settings.model_policy_version,
        "VYU_PROMPT_TEMPLATE_ID": settings.prompt_template_id,
        "VYU_PROMPT_VERSION": settings.prompt_version,
    }
    missing = [key for key, value in required.items() if not str(value).strip()]
    if missing:
        raise ModelGatewayConfigError(
            "Missing model gateway settings: " + ", ".join(missing)
        )

    if settings.enable_fixture_adapter:
        raise ModelGatewayConfigError(
            "Fixture adapters are not allowed in staging or production."
        )

    if settings.generation_provider == "deterministic" or settings.embedding_provider == "deterministic":
        raise ModelGatewayConfigError(
            "Deterministic providers are not allowed in staging or production."
        )

    if not settings.providers_config_secret_arn.strip():
        raise ModelGatewayConfigError(
            "VYU_PROVIDERS_CONFIG_SECRET_ARN is required in staging or production."
        )

    conflicting_dimensions = sorted(
        {
            dimension
            for dimension in active_index_dimensions
            if dimension != settings.embedding_dimensions
        }
    )
    if conflicting_dimensions:
        raise ModelGatewayConfigError(
            "Embedding dimensions conflict with active retrieval indexes: "
            f"configured={settings.embedding_dimensions}, active={conflicting_dimensions}"
        )

    if resolver is None:
        raise ModelGatewayConfigError(
            "SecretResolver is required for staging or production startup validation."
        )

    resolver.validate_provider_credentials(settings.generation_provider)
    if settings.embedding_provider != settings.generation_provider:
        resolver.validate_provider_credentials(settings.embedding_provider)
