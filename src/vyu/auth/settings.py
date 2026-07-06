from __future__ import annotations

from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.vyu.auth.tokens import LOCAL_HS256_AUTH_MODE, OIDC_JWKS_AUTH_MODE


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VYU_",
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    auth_mode: Literal["local_hs256", "oidc_jwks"] = "local_hs256"
    token_issuer: str = "https://local.vyu.invalid"
    token_audience: str = "vyu-local"
    hs256_secret: str = "local-dev-only-secret"
    require_email_verified: bool = True
    oidc_jwks_uri: str | None = None
    oidc_jwks_path: str | None = None
    oidc_discovery_uri: str | None = None
    oidc_required_token_use: str | None = None

    @field_validator("auth_mode", mode="before")
    @classmethod
    def normalize_auth_mode(cls, value: object) -> Literal["local_hs256", "oidc_jwks"]:
        if value in {"hs256", LOCAL_HS256_AUTH_MODE, "local_hs256"}:
            return "local_hs256"
        if value in {OIDC_JWKS_AUTH_MODE, "oidc_jwks"}:
            return "oidc_jwks"
        raise ValueError(f"Unsupported auth mode: {value!r}")

    @model_validator(mode="after")
    def reject_local_auth_outside_local(self) -> AuthSettings:
        if self.env in {"staging", "production"} and self.auth_mode == LOCAL_HS256_AUTH_MODE:
            raise ValueError("local_hs256 auth mode is not allowed in staging or production.")
        if self.auth_mode == OIDC_JWKS_AUTH_MODE and not (
            self.oidc_jwks_uri or self.oidc_jwks_path or self.oidc_discovery_uri
        ):
            raise ValueError("oidc_jwks auth mode requires JWKS or discovery configuration.")
        return self
