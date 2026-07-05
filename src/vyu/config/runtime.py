from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class RuntimeSettings:
    environment: str = "local"
    tenant_mode: str = "single_tenant"
    connector_timeout_seconds: float = 10.0
    connector_max_retries: int = 2
    connector_rate_limit_per_minute: int = 60
    enable_live_connectors: bool = False
    ncbi_tool: str = "vyu-poc"
    ncbi_email: str = ""
    ncbi_api_key: str | None = None

    @classmethod
    def from_environment(cls) -> "RuntimeSettings":
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "RuntimeSettings":
        return cls(
            environment=values.get("VYU_ENV", cls.environment),
            tenant_mode=values.get("VYU_TENANT_MODE", cls.tenant_mode),
            connector_timeout_seconds=float(
                values.get("VYU_CONNECTOR_TIMEOUT_SECONDS", cls.connector_timeout_seconds)
            ),
            connector_max_retries=int(
                values.get("VYU_CONNECTOR_MAX_RETRIES", cls.connector_max_retries)
            ),
            connector_rate_limit_per_minute=int(
                values.get(
                    "VYU_CONNECTOR_RATE_LIMIT_PER_MINUTE",
                    cls.connector_rate_limit_per_minute,
                )
            ),
            enable_live_connectors=_parse_bool(
                values.get("VYU_ENABLE_LIVE_CONNECTORS", str(cls.enable_live_connectors))
            ),
            ncbi_tool=values.get("VYU_NCBI_TOOL", cls.ncbi_tool),
            ncbi_email=values.get("VYU_NCBI_EMAIL", cls.ncbi_email),
            ncbi_api_key=values.get("VYU_NCBI_API_KEY") or None,
        )


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
