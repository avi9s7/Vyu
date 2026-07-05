from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from src.vyu.deployment.composition import DeploymentCompositionConfig
from src.vyu.deployment.smoke import DeploymentSmokeTestConfig


class DeploymentOperatorConfigError(ValueError):
    """Raised when an operator deployment config file is incomplete or unsafe."""


PLACEHOLDER_SECRET_VALUES = frozenset(
    {
        "__REPLACE_WITH_LOCAL_SECRET__",
        "CHANGE_ME",
        "REPLACE_ME",
        "REPLACE_WITH_SECRET",
        "replace-with-secret",
    }
)


@dataclass(frozen=True)
class DeploymentOperatorConfig:
    """Safe local operator config shared by composition and smoke tests.

    This class parses an explicit mapping or `.env`-style file. It does not
    read process environment variables by itself and never exposes the secret in
    `safe_summary()`.
    """

    sqlite_db_path: Path
    phase_output_dir: Path
    token_issuer: str
    token_audience: str
    tenant_id: str
    workspace_id: str
    hs256_secret: str = ""
    auth_mode: str = "hs256"
    oidc_jwks_uri: str | None = None
    oidc_jwks_path: Path | None = None
    oidc_discovery_uri: str | None = None
    oidc_allowed_algorithms: tuple[str, ...] = ("RS256",)
    oidc_jwks_cache_ttl_seconds: int = 300
    oidc_fetch_timeout_seconds: float = 2.0
    oidc_required_token_use: str | None = None
    user_id: str = "smoke-user"
    role: str = "vyu:reviewer"
    token_leeway_seconds: int = 60
    token_lifetime_seconds: int = 300
    unauthenticated_paths: tuple[str, ...] = ("/v1/health",)
    initialize_storage: bool = True
    require_email_verified: bool = False
    tenant_governance_registry_path: Path | None = None
    require_tenant_governance: bool = False
    api_key_auth_enabled: bool = False
    api_key_issuer: str = "vyu-api-key"
    identity_access_audit_enabled: bool = True
    request_id_prefix: str = "local-deployment"
    serverless_default_request_id: str = "local-serverless"
    serverless_extra_response_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        mapping: Mapping[str, object],
        *,
        allow_placeholder_secret: bool = False,
    ) -> "DeploymentOperatorConfig":
        auth_mode = str(mapping.get("VYU_AUTH_MODE", "hs256")).strip() or "hs256"
        required = [
            "VYU_SQLITE_DB",
            "VYU_PHASE_OUTPUT_DIR",
            "VYU_TOKEN_ISSUER",
            "VYU_TOKEN_AUDIENCE",
            "VYU_TENANT_ID",
            "VYU_WORKSPACE_ID",
        ]
        if auth_mode == "hs256":
            required.append("VYU_HS256_SECRET")
        missing = [key for key in required if not str(mapping.get(key, "")).strip()]
        if missing:
            raise DeploymentOperatorConfigError(
                "Missing deployment operator settings: " + ", ".join(missing)
            )
        config = cls(
            sqlite_db_path=Path(str(mapping["VYU_SQLITE_DB"])),
            phase_output_dir=Path(str(mapping["VYU_PHASE_OUTPUT_DIR"])),
            token_issuer=str(mapping["VYU_TOKEN_ISSUER"]),
            token_audience=str(mapping["VYU_TOKEN_AUDIENCE"]),
            hs256_secret=str(mapping.get("VYU_HS256_SECRET", "")),
            auth_mode=auth_mode,
            oidc_jwks_uri=_optional_string_setting(mapping, "VYU_OIDC_JWKS_URI"),
            oidc_jwks_path=_optional_path_setting(mapping, "VYU_OIDC_JWKS_FILE"),
            oidc_discovery_uri=_optional_string_setting(mapping, "VYU_OIDC_DISCOVERY_URI"),
            oidc_allowed_algorithms=_tuple_setting(
                mapping,
                "VYU_OIDC_ALLOWED_ALGORITHMS",
                ("RS256",),
            ),
            oidc_jwks_cache_ttl_seconds=_int_setting(
                mapping,
                "VYU_OIDC_JWKS_CACHE_TTL_SECONDS",
                300,
            ),
            oidc_fetch_timeout_seconds=_float_setting(
                mapping,
                "VYU_OIDC_FETCH_TIMEOUT_SECONDS",
                2.0,
            ),
            oidc_required_token_use=_optional_string_setting(
                mapping,
                "VYU_OIDC_REQUIRED_TOKEN_USE",
            ),
            tenant_id=str(mapping["VYU_TENANT_ID"]),
            workspace_id=str(mapping["VYU_WORKSPACE_ID"]),
            user_id=str(mapping.get("VYU_USER_ID", "smoke-user")),
            role=str(mapping.get("VYU_ROLE", "vyu:reviewer")),
            token_leeway_seconds=_int_setting(mapping, "VYU_TOKEN_LEEWAY_SECONDS", 60),
            token_lifetime_seconds=_int_setting(mapping, "VYU_TOKEN_LIFETIME_SECONDS", 300),
            unauthenticated_paths=_tuple_setting(
                mapping,
                "VYU_UNAUTHENTICATED_PATHS",
                ("/v1/health",),
            ),
            initialize_storage=_bool_setting(mapping, "VYU_INITIALIZE_STORAGE", True),
            require_email_verified=_bool_setting(mapping, "VYU_REQUIRE_EMAIL_VERIFIED", False),
            tenant_governance_registry_path=_optional_path_setting(
                mapping,
                "VYU_TENANT_GOVERNANCE_REGISTRY",
            ),
            require_tenant_governance=_bool_setting(mapping, "VYU_REQUIRE_TENANT_GOVERNANCE", False),
            api_key_auth_enabled=_bool_setting(mapping, "VYU_API_KEY_AUTH_ENABLED", False),
            api_key_issuer=str(mapping.get("VYU_API_KEY_ISSUER", "vyu-api-key")),
            identity_access_audit_enabled=_bool_setting(
                mapping,
                "VYU_IDENTITY_ACCESS_AUDIT_ENABLED",
                True,
            ),
            request_id_prefix=str(mapping.get("VYU_REQUEST_ID_PREFIX", "local-deployment")),
            serverless_default_request_id=str(
                mapping.get("VYU_SERVERLESS_DEFAULT_REQUEST_ID", "local-serverless")
            ),
            serverless_extra_response_headers=_header_mapping(
                mapping.get("VYU_SERVERLESS_EXTRA_RESPONSE_HEADERS", "")
            ),
        )
        config.validate(allow_placeholder_secret=allow_placeholder_secret)
        return config

    def validate(self, *, allow_placeholder_secret: bool = False) -> None:
        required = {
            "VYU_SQLITE_DB": str(self.sqlite_db_path),
            "VYU_PHASE_OUTPUT_DIR": str(self.phase_output_dir),
            "VYU_TOKEN_ISSUER": self.token_issuer,
            "VYU_TOKEN_AUDIENCE": self.token_audience,
            "VYU_TENANT_ID": self.tenant_id,
            "VYU_WORKSPACE_ID": self.workspace_id,
            "VYU_USER_ID": self.user_id,
            "VYU_ROLE": self.role,
        }
        missing = [key for key, value in required.items() if not value.strip()]
        if missing:
            raise DeploymentOperatorConfigError(
                "Missing deployment operator settings: " + ", ".join(missing)
            )
        if self.auth_mode not in {"hs256", "oidc_jwks"}:
            raise DeploymentOperatorConfigError("VYU_AUTH_MODE must be hs256 or oidc_jwks.")
        if self.auth_mode == "hs256" and not self.hs256_secret.strip():
            raise DeploymentOperatorConfigError("VYU_HS256_SECRET is required when VYU_AUTH_MODE=hs256.")
        if self.auth_mode == "oidc_jwks":
            if not (self.oidc_jwks_uri or self.oidc_jwks_path or self.oidc_discovery_uri):
                raise DeploymentOperatorConfigError(
                    "VYU_AUTH_MODE=oidc_jwks requires VYU_OIDC_JWKS_URI, "
                    "VYU_OIDC_JWKS_FILE, or VYU_OIDC_DISCOVERY_URI."
                )
            unsupported = set(self.oidc_allowed_algorithms).difference({"RS256"})
            if unsupported:
                raise DeploymentOperatorConfigError(
                    "VYU_OIDC_ALLOWED_ALGORITHMS contains unsupported values: "
                    + ", ".join(sorted(unsupported))
                )
            if self.oidc_jwks_path is not None and not self.oidc_jwks_path.exists():
                raise DeploymentOperatorConfigError(
                    f"VYU_OIDC_JWKS_FILE does not exist: {self.oidc_jwks_path}"
                )
            if self.oidc_jwks_cache_ttl_seconds < 0:
                raise DeploymentOperatorConfigError("VYU_OIDC_JWKS_CACHE_TTL_SECONDS cannot be negative.")
            if self.oidc_fetch_timeout_seconds <= 0:
                raise DeploymentOperatorConfigError("VYU_OIDC_FETCH_TIMEOUT_SECONDS must be positive.")
        if self.token_leeway_seconds < 0:
            raise DeploymentOperatorConfigError("VYU_TOKEN_LEEWAY_SECONDS cannot be negative.")
        if self.token_lifetime_seconds <= 0:
            raise DeploymentOperatorConfigError("VYU_TOKEN_LIFETIME_SECONDS must be positive.")
        if not self.unauthenticated_paths:
            raise DeploymentOperatorConfigError("VYU_UNAUTHENTICATED_PATHS cannot be empty.")
        if self.require_tenant_governance and self.tenant_governance_registry_path is None:
            raise DeploymentOperatorConfigError(
                "VYU_REQUIRE_TENANT_GOVERNANCE=true requires VYU_TENANT_GOVERNANCE_REGISTRY."
            )
        if self.api_key_auth_enabled and self.tenant_governance_registry_path is None:
            raise DeploymentOperatorConfigError(
                "VYU_API_KEY_AUTH_ENABLED=true requires VYU_TENANT_GOVERNANCE_REGISTRY."
            )
        if self.api_key_auth_enabled and not self.api_key_issuer.strip():
            raise DeploymentOperatorConfigError("VYU_API_KEY_ISSUER cannot be empty when API-key auth is enabled.")
        if self.tenant_governance_registry_path is not None and not self.tenant_governance_registry_path.exists():
            raise DeploymentOperatorConfigError(
                f"VYU_TENANT_GOVERNANCE_REGISTRY does not exist: {self.tenant_governance_registry_path}"
            )
        if (
            self.auth_mode == "hs256"
            and not allow_placeholder_secret
            and _is_placeholder_secret(self.hs256_secret)
        ):
            raise DeploymentOperatorConfigError(
                "VYU_HS256_SECRET is still a placeholder; copy the example config and set a local secret."
            )

    def to_composition_config(self) -> DeploymentCompositionConfig:
        self.validate()
        return DeploymentCompositionConfig(
            sqlite_db_path=self.sqlite_db_path,
            phase_output_dir=self.phase_output_dir,
            token_issuer=self.token_issuer,
            token_audience=self.token_audience,
            hs256_secret=self.hs256_secret,
            auth_mode=self.auth_mode,
            token_leeway_seconds=self.token_leeway_seconds,
            oidc_jwks_uri=self.oidc_jwks_uri,
            oidc_jwks_path=self.oidc_jwks_path,
            oidc_discovery_uri=self.oidc_discovery_uri,
            oidc_allowed_algorithms=self.oidc_allowed_algorithms,
            oidc_jwks_cache_ttl_seconds=self.oidc_jwks_cache_ttl_seconds,
            oidc_fetch_timeout_seconds=self.oidc_fetch_timeout_seconds,
            oidc_required_token_use=self.oidc_required_token_use,
            unauthenticated_paths=self.unauthenticated_paths,
            initialize_storage=self.initialize_storage,
            require_email_verified=self.require_email_verified,
            tenant_governance_registry_path=self.tenant_governance_registry_path,
            require_tenant_governance=self.require_tenant_governance,
            api_key_auth_enabled=self.api_key_auth_enabled,
            api_key_issuer=self.api_key_issuer,
            identity_access_audit_enabled=self.identity_access_audit_enabled,
            request_id_prefix=self.request_id_prefix,
            serverless_default_request_id=self.serverless_default_request_id,
            serverless_extra_response_headers=dict(self.serverless_extra_response_headers),
        )

    def to_smoke_test_config(self) -> DeploymentSmokeTestConfig:
        self.validate()
        return DeploymentSmokeTestConfig(
            sqlite_db_path=self.sqlite_db_path,
            phase_output_dir=self.phase_output_dir,
            token_issuer=self.token_issuer,
            token_audience=self.token_audience,
            hs256_secret=self.hs256_secret,
            auth_mode=self.auth_mode,
            oidc_jwks_uri=self.oidc_jwks_uri,
            oidc_jwks_path=self.oidc_jwks_path,
            oidc_discovery_uri=self.oidc_discovery_uri,
            oidc_allowed_algorithms=self.oidc_allowed_algorithms,
            oidc_jwks_cache_ttl_seconds=self.oidc_jwks_cache_ttl_seconds,
            oidc_fetch_timeout_seconds=self.oidc_fetch_timeout_seconds,
            oidc_required_token_use=self.oidc_required_token_use,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            user_id=self.user_id,
            role=self.role,
            token_lifetime_seconds=self.token_lifetime_seconds,
            request_id_prefix=self.request_id_prefix,
            tenant_governance_registry_path=self.tenant_governance_registry_path,
            require_tenant_governance=self.require_tenant_governance,
            api_key_auth_enabled=self.api_key_auth_enabled,
            api_key_issuer=self.api_key_issuer,
            identity_access_audit_enabled=self.identity_access_audit_enabled,
        )

    def safe_summary(self) -> dict[str, Any]:
        return {
            "sqlite_db_path": str(self.sqlite_db_path),
            "phase_output_dir": str(self.phase_output_dir),
            "token_issuer": self.token_issuer,
            "token_audience": self.token_audience,
            "hs256_secret_configured": bool(self.hs256_secret.strip()),
            "hs256_secret_placeholder": _is_placeholder_secret(self.hs256_secret),
            "auth_mode": self.auth_mode,
            "oidc_jwks_uri_configured": bool(self.oidc_jwks_uri),
            "oidc_jwks_path": str(self.oidc_jwks_path) if self.oidc_jwks_path is not None else None,
            "oidc_discovery_uri_configured": bool(self.oidc_discovery_uri),
            "oidc_allowed_algorithms": list(self.oidc_allowed_algorithms),
            "oidc_jwks_cache_ttl_seconds": self.oidc_jwks_cache_ttl_seconds,
            "oidc_fetch_timeout_seconds": self.oidc_fetch_timeout_seconds,
            "oidc_required_token_use": self.oidc_required_token_use,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "role": self.role,
            "token_leeway_seconds": self.token_leeway_seconds,
            "token_lifetime_seconds": self.token_lifetime_seconds,
            "unauthenticated_paths": list(self.unauthenticated_paths),
            "initialize_storage": self.initialize_storage,
            "require_email_verified": self.require_email_verified,
            "tenant_governance_registry_path": (
                str(self.tenant_governance_registry_path)
                if self.tenant_governance_registry_path is not None
                else None
            ),
            "require_tenant_governance": self.require_tenant_governance,
            "api_key_auth_enabled": self.api_key_auth_enabled,
            "api_key_issuer": self.api_key_issuer,
            "identity_access_audit_enabled": self.identity_access_audit_enabled,
            "request_id_prefix": self.request_id_prefix,
            "serverless_default_request_id": self.serverless_default_request_id,
            "serverless_extra_response_headers": dict(self.serverless_extra_response_headers),
        }


def load_deployment_operator_env(
    path: Path,
    *,
    allow_placeholder_secret: bool = False,
) -> DeploymentOperatorConfig:
    return DeploymentOperatorConfig.from_mapping(
        parse_env_text(path.read_text(encoding="utf-8")),
        allow_placeholder_secret=allow_placeholder_secret,
    )


def parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            raise DeploymentOperatorConfigError(f"Invalid env line {line_number}.")
        values[key.strip()] = _unquote(value.strip())
    return values


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _int_setting(mapping: Mapping[str, object], key: str, default: int) -> int:
    raw = mapping.get(key, default)
    try:
        return int(str(raw))
    except ValueError as exc:
        raise DeploymentOperatorConfigError(f"{key} must be an integer.") from exc


def _float_setting(mapping: Mapping[str, object], key: str, default: float) -> float:
    raw = mapping.get(key, default)
    try:
        return float(str(raw))
    except ValueError as exc:
        raise DeploymentOperatorConfigError(f"{key} must be a number.") from exc


def _optional_string_setting(mapping: Mapping[str, object], key: str) -> str | None:
    raw = mapping.get(key)
    if raw is None or not str(raw).strip():
        return None
    return str(raw).strip()


def _bool_setting(mapping: Mapping[str, object], key: str, default: bool) -> bool:
    raw = mapping.get(key)
    if raw is None:
        return default
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise DeploymentOperatorConfigError(f"{key} must be a boolean value.")


def _tuple_setting(
    mapping: Mapping[str, object],
    key: str,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    raw = mapping.get(key)
    if raw is None:
        return default
    values = tuple(item.strip() for item in str(raw).split(",") if item.strip())
    return values or default


def _optional_path_setting(mapping: Mapping[str, object], key: str) -> Path | None:
    raw = mapping.get(key)
    if raw is None or not str(raw).strip():
        return None
    return Path(str(raw))


def _header_mapping(raw: object) -> dict[str, str]:
    if raw is None or str(raw).strip() == "":
        return {}
    headers: dict[str, str] = {}
    for pair in str(raw).split(","):
        if not pair.strip():
            continue
        key, separator, value = pair.partition("=")
        if not separator or not key.strip():
            raise DeploymentOperatorConfigError(
                "VYU_SERVERLESS_EXTRA_RESPONSE_HEADERS must use key=value pairs."
            )
        headers[key.strip()] = value.strip()
    return headers


def _is_placeholder_secret(secret: str) -> bool:
    normalized = secret.strip()
    upper = normalized.upper()
    return normalized in PLACEHOLDER_SECRET_VALUES or "REPLACE" in upper or "CHANGE_ME" in upper
