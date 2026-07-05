from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Mapping

from src.vyu.authn import IdentityMapper, IdentityMappingConfig
from src.vyu.authz import TenantGovernanceRegistry, TenantGovernanceRepository
from src.vyu.deployment.api_service import DeploymentApiServiceShell
from src.vyu.deployment.http_adapter import (
    ApiKeyAuthConfig,
    BearerTokenConfig,
    CompositeDeploymentAuthenticator,
    Hs256BearerTokenAuthenticator,
    TenantGovernanceApiKeyAuthenticator,
    ServiceDeploymentHttpAdapter,
)
from src.vyu.deployment.idp import OIDC_AUTH_MODE, OidcJwksBearerTokenAuthenticator, OidcJwksConfig
from src.vyu.deployment.serverless_handler import (
    ServerlessDeploymentHandler,
    ServerlessHandlerConfig,
)
from src.vyu.entrypoints.report_export_routes import (
    PhaseOutputReportArtifactStore,
    ReportExportRouteRuntime,
)
from src.vyu.entrypoints.review_queue_routes import ReviewQueueRouteRuntime
from src.vyu.entrypoints.service_routes import ServiceRouteRuntime
from src.vyu.entrypoints.tenant_governance_admin_routes import TenantGovernanceAdminRouteRuntime
from src.vyu.storage import ProductionAuditEvent, ProductionStorage


class DeploymentCompositionError(ValueError):
    """Raised when local deployment composition config is incomplete."""


@dataclass(frozen=True)
class DeploymentCompositionConfig:
    sqlite_db_path: Path
    phase_output_dir: Path
    token_issuer: str
    token_audience: str
    hs256_secret: str = ""
    auth_mode: str = "hs256"
    token_leeway_seconds: int = 60
    oidc_jwks_uri: str | None = None
    oidc_jwks_path: Path | None = None
    oidc_discovery_uri: str | None = None
    oidc_allowed_algorithms: tuple[str, ...] = ("RS256",)
    oidc_jwks_cache_ttl_seconds: int = 300
    oidc_fetch_timeout_seconds: float = 2.0
    oidc_required_token_use: str | None = None
    unauthenticated_paths: tuple[str, ...] = ("/v1/health",)
    initialize_storage: bool = True
    require_email_verified: bool = False
    tenant_governance_registry_path: Path | None = None
    require_tenant_governance: bool = False
    api_key_auth_enabled: bool = False
    api_key_issuer: str = "vyu-api-key"
    identity_access_audit_enabled: bool = True
    request_id_prefix: str = "vyu-deployment"
    serverless_default_request_id: str = "serverless-request"
    serverless_extra_response_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        mapping: Mapping[str, object],
    ) -> "DeploymentCompositionConfig":
        auth_mode = str(mapping.get("VYU_AUTH_MODE", "hs256")).strip() or "hs256"
        required = {
            "VYU_SQLITE_DB": "sqlite_db_path",
            "VYU_PHASE_OUTPUT_DIR": "phase_output_dir",
            "VYU_TOKEN_ISSUER": "token_issuer",
            "VYU_TOKEN_AUDIENCE": "token_audience",
        }
        if auth_mode == "hs256":
            required["VYU_HS256_SECRET"] = "hs256_secret"
        missing = [key for key in required if not str(mapping.get(key, "")).strip()]
        if missing:
            raise DeploymentCompositionError(
                "Missing deployment composition settings: " + ", ".join(missing)
            )
        return cls(
            sqlite_db_path=Path(str(mapping["VYU_SQLITE_DB"])),
            phase_output_dir=Path(str(mapping["VYU_PHASE_OUTPUT_DIR"])),
            token_issuer=str(mapping["VYU_TOKEN_ISSUER"]),
            token_audience=str(mapping["VYU_TOKEN_AUDIENCE"]),
            hs256_secret=str(mapping.get("VYU_HS256_SECRET", "")),
            auth_mode=auth_mode,
            token_leeway_seconds=_int_setting(mapping, "VYU_TOKEN_LEEWAY_SECONDS", 60),
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
            request_id_prefix=str(mapping.get("VYU_REQUEST_ID_PREFIX", "vyu-deployment")),
            serverless_default_request_id=str(
                mapping.get("VYU_SERVERLESS_DEFAULT_REQUEST_ID", "serverless-request")
            ),
            serverless_extra_response_headers=_header_mapping(
                mapping.get("VYU_SERVERLESS_EXTRA_RESPONSE_HEADERS", "")
            ),
        )

    def validate(self) -> None:
        if not self.token_issuer.strip():
            raise DeploymentCompositionError("token_issuer is required.")
        if not self.token_audience.strip():
            raise DeploymentCompositionError("token_audience is required.")
        if self.auth_mode not in {"hs256", OIDC_AUTH_MODE}:
            raise DeploymentCompositionError("auth_mode must be hs256 or oidc_jwks.")
        if self.auth_mode == "hs256" and not self.hs256_secret.strip():
            raise DeploymentCompositionError("hs256_secret is required.")
        if self.token_leeway_seconds < 0:
            raise DeploymentCompositionError("token_leeway_seconds cannot be negative.")
        if not self.unauthenticated_paths:
            raise DeploymentCompositionError("At least one unauthenticated path is required.")
        if self.auth_mode == OIDC_AUTH_MODE:
            try:
                OidcJwksConfig(
                    issuer=self.token_issuer,
                    audience=self.token_audience,
                    jwks_uri=self.oidc_jwks_uri,
                    jwks_path=self.oidc_jwks_path,
                    discovery_uri=self.oidc_discovery_uri,
                    allowed_algorithms=frozenset(self.oidc_allowed_algorithms),
                    leeway_seconds=self.token_leeway_seconds,
                    jwks_cache_ttl_seconds=self.oidc_jwks_cache_ttl_seconds,
                    fetch_timeout_seconds=self.oidc_fetch_timeout_seconds,
                    unauthenticated_paths=frozenset(self.unauthenticated_paths),
                    required_token_use=self.oidc_required_token_use,
                ).validate()
            except ValueError as exc:
                raise DeploymentCompositionError(str(exc)) from exc
        if self.require_tenant_governance and self.tenant_governance_registry_path is None:
            raise DeploymentCompositionError(
                "Tenant governance is required but VYU_TENANT_GOVERNANCE_REGISTRY is not configured."
            )
        if self.api_key_auth_enabled and self.tenant_governance_registry_path is None:
            raise DeploymentCompositionError(
                "API-key authentication requires VYU_TENANT_GOVERNANCE_REGISTRY."
            )
        if self.api_key_auth_enabled and not self.api_key_issuer.strip():
            raise DeploymentCompositionError("api_key_issuer is required when API-key auth is enabled.")
        if self.tenant_governance_registry_path is not None and not self.tenant_governance_registry_path.exists():
            raise DeploymentCompositionError(
                f"Tenant governance registry does not exist: {self.tenant_governance_registry_path}"
            )


@dataclass(frozen=True)
class DeploymentRuntimeBundle:
    config: DeploymentCompositionConfig
    storage: ProductionStorage
    review_queue_runtime: ReviewQueueRouteRuntime
    report_export_runtime: ReportExportRouteRuntime
    tenant_governance_repository: TenantGovernanceRepository | None
    identity_mapper: IdentityMapper
    tenant_governance_admin_runtime: TenantGovernanceAdminRouteRuntime | None
    service_runtime: ServiceRouteRuntime
    authenticator: CompositeDeploymentAuthenticator | Hs256BearerTokenAuthenticator | OidcJwksBearerTokenAuthenticator
    deployment_adapter: ServiceDeploymentHttpAdapter
    api_shell: DeploymentApiServiceShell
    serverless_handler: ServerlessDeploymentHandler


def build_deployment_runtime(config: DeploymentCompositionConfig) -> DeploymentRuntimeBundle:
    config.validate()
    storage = ProductionStorage(Path(config.sqlite_db_path))
    if config.initialize_storage:
        storage.initialize()

    request_id_factory = SequentialRequestIdFactory(config.request_id_prefix)
    review_queue_runtime = ReviewQueueRouteRuntime(storage=storage)
    report_export_runtime = ReportExportRouteRuntime(
        storage=storage,
        artifact_store=PhaseOutputReportArtifactStore(Path(config.phase_output_dir)),
    )
    tenant_governance_repository = _tenant_governance_repository(config)
    accepted_issuers = {config.token_issuer}
    if config.api_key_auth_enabled:
        accepted_issuers.add(config.api_key_issuer)
    identity_mapper = IdentityMapper(
        IdentityMappingConfig(
            trusted_issuers=frozenset(accepted_issuers),
            accepted_audiences=frozenset({config.token_audience}),
            require_email_verified=config.require_email_verified,
            tenant_governance=tenant_governance_repository,
        )
    )
    audit_sink = (
        ProductionIdentityAuditSink(storage)
        if config.identity_access_audit_enabled
        else None
    )
    tenant_governance_admin_runtime = (
        TenantGovernanceAdminRouteRuntime(
            repository=tenant_governance_repository,
            audit_sink=audit_sink,
        )
        if tenant_governance_repository is not None
        else None
    )
    service_runtime = ServiceRouteRuntime(
        review_queue_runtime=review_queue_runtime,
        report_export_runtime=report_export_runtime,
        request_id_factory=request_id_factory,
        identity_mapper=identity_mapper,
        tenant_governance_admin_runtime=tenant_governance_admin_runtime,
        identity_audit_sink=audit_sink,
    )
    bearer_authenticator = _bearer_authenticator(config)
    if config.api_key_auth_enabled:
        if tenant_governance_repository is None:
            raise DeploymentCompositionError("API-key authentication requires tenant governance repository.")
        authenticator = CompositeDeploymentAuthenticator(
            bearer_authenticator=bearer_authenticator,
            api_key_authenticator=TenantGovernanceApiKeyAuthenticator(
                repository=tenant_governance_repository,
                config=ApiKeyAuthConfig(
                    issuer=config.api_key_issuer,
                    audience=config.token_audience,
                    unauthenticated_paths=frozenset(config.unauthenticated_paths),
                ),
            ),
            unauthenticated_paths=frozenset(config.unauthenticated_paths),
        )
    else:
        authenticator = bearer_authenticator
    deployment_adapter = ServiceDeploymentHttpAdapter(
        service_runtime=service_runtime,
        authenticator=authenticator,
        request_id_factory=request_id_factory,
    )
    api_shell = DeploymentApiServiceShell(deployment_adapter)
    serverless_handler = ServerlessDeploymentHandler(
        service_shell=api_shell,
        config=ServerlessHandlerConfig(
            default_request_id=config.serverless_default_request_id,
            extra_response_headers=dict(config.serverless_extra_response_headers),
        ),
    )
    return DeploymentRuntimeBundle(
        config=config,
        storage=storage,
        review_queue_runtime=review_queue_runtime,
        report_export_runtime=report_export_runtime,
        tenant_governance_repository=tenant_governance_repository,
        identity_mapper=identity_mapper,
        tenant_governance_admin_runtime=tenant_governance_admin_runtime,
        service_runtime=service_runtime,
        authenticator=authenticator,
        deployment_adapter=deployment_adapter,
        api_shell=api_shell,
        serverless_handler=serverless_handler,
    )


def _bearer_authenticator(config: DeploymentCompositionConfig):
    if config.auth_mode == OIDC_AUTH_MODE:
        return OidcJwksBearerTokenAuthenticator(
            OidcJwksConfig(
                issuer=config.token_issuer,
                audience=config.token_audience,
                jwks_uri=config.oidc_jwks_uri,
                jwks_path=config.oidc_jwks_path,
                discovery_uri=config.oidc_discovery_uri,
                allowed_algorithms=frozenset(config.oidc_allowed_algorithms),
                leeway_seconds=config.token_leeway_seconds,
                jwks_cache_ttl_seconds=config.oidc_jwks_cache_ttl_seconds,
                fetch_timeout_seconds=config.oidc_fetch_timeout_seconds,
                unauthenticated_paths=frozenset(config.unauthenticated_paths),
                required_token_use=config.oidc_required_token_use,
            )
        )
    return Hs256BearerTokenAuthenticator(
        BearerTokenConfig(
            issuer=config.token_issuer,
            audience=config.token_audience,
            hs256_secret=config.hs256_secret,
            leeway_seconds=config.token_leeway_seconds,
            unauthenticated_paths=frozenset(config.unauthenticated_paths),
        )
    )


def _tenant_governance_repository(
    config: DeploymentCompositionConfig,
) -> TenantGovernanceRepository | None:
    if config.tenant_governance_registry_path is None:
        if config.require_tenant_governance:
            raise DeploymentCompositionError("Tenant governance is required but no registry path was configured.")
        return None
    try:
        # Validate that the file is parseable before accepting the deployment graph.
        TenantGovernanceRegistry.read(config.tenant_governance_registry_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise DeploymentCompositionError(
            f"Tenant governance registry is not valid: {config.tenant_governance_registry_path}"
        ) from exc
    return TenantGovernanceRepository(config.tenant_governance_registry_path)


class ProductionIdentityAuditSink:
    def __init__(self, storage: ProductionStorage):
        self.storage = storage
        self._next = 1

    def __call__(self, event: Mapping[str, object]) -> None:
        event_type = str(event.get("event_type", "identity_access_decision"))
        run_id = str(
            event.get("audit_correlation_id")
            or event.get("request_id")
            or "identity-access"
        )
        event_id = f"{run_id}:{event_type}:{self._next:06d}"
        self._next += 1
        payload = dict(event)
        payload.setdefault("audit_sink", "production_storage")
        try:
            self.storage.append_audit_event(
                ProductionAuditEvent(
                    event_id=event_id,
                    run_id=run_id,
                    event_type=event_type,
                    payload=payload,
                    created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                )
            )
        except ValueError:
            # A duplicate audit id must not make a request fail after the access
            # decision has already been enforced. Operators can inspect the
            # existing event by run_id.
            return


class SequentialRequestIdFactory:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix.strip() or "vyu-deployment"
        self._next = 1

    def __call__(self) -> str:
        value = f"{self.prefix}-{self._next:06d}"
        self._next += 1
        return value


def _int_setting(mapping: Mapping[str, object], key: str, default: int) -> int:
    raw = mapping.get(key, default)
    try:
        return int(str(raw))
    except ValueError as exc:
        raise DeploymentCompositionError(f"{key} must be an integer.") from exc


def _bool_setting(mapping: Mapping[str, object], key: str, default: bool) -> bool:
    raw = mapping.get(key)
    if raw is None:
        return default
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise DeploymentCompositionError(f"{key} must be a boolean value.")


def _float_setting(mapping: Mapping[str, object], key: str, default: float) -> float:
    raw = mapping.get(key, default)
    try:
        return float(str(raw))
    except ValueError as exc:
        raise DeploymentCompositionError(f"{key} must be a number.") from exc


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


def _optional_string_setting(mapping: Mapping[str, object], key: str) -> str | None:
    raw = mapping.get(key)
    if raw is None or not str(raw).strip():
        return None
    return str(raw).strip()


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
            raise DeploymentCompositionError(
                "VYU_SERVERLESS_EXTRA_RESPONSE_HEADERS must use key=value pairs."
            )
        headers[key.strip()] = value.strip()
    return headers
