from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import time
from typing import Any, Mapping

from src.vyu.deployment.composition import (
    DeploymentCompositionConfig,
    build_deployment_runtime,
)


class DeploymentSmokeTestError(ValueError):
    """Raised when local deployment smoke-test configuration is incomplete."""


@dataclass(frozen=True)
class DeploymentSmokeTestConfig:
    """Explicit config for the local deployment smoke-test command.

    The smoke test is operator-facing and local. It intentionally creates a
    short-lived HS256 token from the same explicit secret used by the local
    composition factory so it can exercise the deployment authentication path
    without starting a web server or depending on a cloud identity provider.
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
    token_lifetime_seconds: int = 300
    request_id_prefix: str = "smoke"
    tenant_governance_registry_path: Path | None = None
    require_tenant_governance: bool = False
    api_key_auth_enabled: bool = False
    api_key_issuer: str = "vyu-api-key"
    identity_access_audit_enabled: bool = True

    def validate(self) -> None:
        required = {
            "sqlite_db_path": str(self.sqlite_db_path),
            "phase_output_dir": str(self.phase_output_dir),
            "token_issuer": self.token_issuer,
            "token_audience": self.token_audience,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "role": self.role,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise DeploymentSmokeTestError(
                "Missing deployment smoke-test settings: " + ", ".join(missing)
            )
        if self.auth_mode != "hs256":
            raise DeploymentSmokeTestError(
                "The local smoke-test token generator only supports VYU_AUTH_MODE=hs256; "
                "use real IdP-issued JWTs for oidc_jwks deployment tests."
            )
        if not self.hs256_secret.strip():
            raise DeploymentSmokeTestError("hs256_secret is required for local smoke tests.")
        if self.token_lifetime_seconds <= 0:
            raise DeploymentSmokeTestError("token_lifetime_seconds must be positive.")
        if self.require_tenant_governance and self.tenant_governance_registry_path is None:
            raise DeploymentSmokeTestError(
                "require_tenant_governance requires tenant_governance_registry_path."
            )
        if self.api_key_auth_enabled and self.tenant_governance_registry_path is None:
            raise DeploymentSmokeTestError(
                "api_key_auth_enabled requires tenant_governance_registry_path."
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
            token_leeway_seconds=60,
            oidc_jwks_uri=self.oidc_jwks_uri,
            oidc_jwks_path=self.oidc_jwks_path,
            oidc_discovery_uri=self.oidc_discovery_uri,
            oidc_allowed_algorithms=self.oidc_allowed_algorithms,
            oidc_jwks_cache_ttl_seconds=self.oidc_jwks_cache_ttl_seconds,
            oidc_fetch_timeout_seconds=self.oidc_fetch_timeout_seconds,
            oidc_required_token_use=self.oidc_required_token_use,
            request_id_prefix=self.request_id_prefix,
            serverless_default_request_id=f"{self.request_id_prefix}-serverless",
            tenant_governance_registry_path=self.tenant_governance_registry_path,
            require_tenant_governance=self.require_tenant_governance,
            api_key_auth_enabled=self.api_key_auth_enabled,
            api_key_issuer=self.api_key_issuer,
            identity_access_audit_enabled=self.identity_access_audit_enabled,
        )


@dataclass(frozen=True)
class DeploymentSmokeCheck:
    name: str
    passed: bool
    expected_status_code: int
    actual_status_code: int | None
    expected_reason: str
    actual_reason: str | None
    message: str

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "expected_status_code": self.expected_status_code,
            "actual_status_code": self.actual_status_code,
            "expected_reason": self.expected_reason,
            "actual_reason": self.actual_reason,
            "message": self.message,
        }


@dataclass(frozen=True)
class DeploymentSmokeTestResult:
    status: str
    checks: tuple[DeploymentSmokeCheck, ...]
    deployment: dict[str, str]

    def to_json(self) -> dict[str, Any]:
        passed_count = sum(1 for check in self.checks if check.passed)
        return {
            "status": self.status,
            "summary": {
                "passed": passed_count,
                "failed": len(self.checks) - passed_count,
                "total": len(self.checks),
            },
            "checks": [check.to_json() for check in self.checks],
            "deployment": dict(self.deployment),
        }


def run_deployment_smoke_test(
    config: DeploymentSmokeTestConfig,
    now: int | None = None,
) -> DeploymentSmokeTestResult:
    """Run local smoke checks through the composed serverless handler."""

    config.validate()
    bundle = build_deployment_runtime(config.to_composition_config())
    issued_at = int(now if now is not None else time.time())
    token = _local_hs256_jwt(
        secret=config.hs256_secret,
        payload={
            "iss": config.token_issuer,
            "aud": config.token_audience,
            "sub": config.user_id,
            "exp": issued_at + config.token_lifetime_seconds,
            "iat": issued_at - 30,
            "email": f"{config.user_id}@example.invalid",
            "email_verified": True,
            "vyu": {
                "tenant_id": config.tenant_id,
                "workspace_id": config.workspace_id,
                "roles": [config.role],
            },
        },
    )

    checks = (
        _expect(
            name="health",
            response=bundle.serverless_handler.handle(
                {
                    "httpMethod": "GET",
                    "path": "/v1/health",
                    "headers": {"x-vyu-request-id": f"{config.request_id_prefix}-health"},
                }
            ),
            expected_status_code=200,
            expected_reason="service_healthy",
        ),
        _expect(
            name="authenticated_review_queue",
            response=bundle.serverless_handler.handle(
                {
                    "httpMethod": "GET",
                    "path": "/v1/review-queue",
                    "headers": {
                        "authorization": f"Bearer {token}",
                        "x-vyu-request-id": f"{config.request_id_prefix}-review-queue",
                    },
                    "queryStringParameters": {
                        "tenant_id": config.tenant_id,
                        "workspace_id": config.workspace_id,
                        "status": "pending",
                    },
                }
            ),
            expected_status_code=200,
            expected_reason="review_queue_loaded",
        ),
        _expect(
            name="fail_closed_bad_token",
            response=bundle.serverless_handler.handle(
                {
                    "httpMethod": "GET",
                    "path": "/v1/review-queue",
                    "headers": {
                        "authorization": "Bearer definitely.invalid.token",
                        "x-vyu-request-id": f"{config.request_id_prefix}-bad-token",
                    },
                    "queryStringParameters": {
                        "tenant_id": config.tenant_id,
                        "workspace_id": config.workspace_id,
                        "status": "pending",
                    },
                }
            ),
            expected_status_code=401,
            expected_reason="auth_token_invalid",
        ),
    )
    status = "pass" if all(check.passed for check in checks) else "fail"
    return DeploymentSmokeTestResult(
        status=status,
        checks=checks,
        deployment={
            "sqlite_db_path": str(config.sqlite_db_path),
            "phase_output_dir": str(config.phase_output_dir),
            "token_issuer": config.token_issuer,
            "token_audience": config.token_audience,
            "tenant_id": config.tenant_id,
            "workspace_id": config.workspace_id,
            "tenant_governance_registry_path": (
                str(config.tenant_governance_registry_path)
                if config.tenant_governance_registry_path is not None
                else ""
            ),
            "require_tenant_governance": str(config.require_tenant_governance).lower(),
            "api_key_auth_enabled": str(config.api_key_auth_enabled).lower(),
            "auth_mode": config.auth_mode,
        },
    )


def _expect(
    name: str,
    response: Mapping[str, object],
    expected_status_code: int,
    expected_reason: str,
) -> DeploymentSmokeCheck:
    actual_status_code = _status_code(response)
    payload = _response_payload(response)
    actual_reason = _reason(payload)
    passed = actual_status_code == expected_status_code and actual_reason == expected_reason
    message = (
        f"{name} returned expected status {expected_status_code} and reason {expected_reason}."
        if passed
        else (
            f"{name} expected status {expected_status_code} reason {expected_reason}, "
            f"got status {actual_status_code} reason {actual_reason}."
        )
    )
    return DeploymentSmokeCheck(
        name=name,
        passed=passed,
        expected_status_code=expected_status_code,
        actual_status_code=actual_status_code,
        expected_reason=expected_reason,
        actual_reason=actual_reason,
        message=message,
    )


def _status_code(response: Mapping[str, object]) -> int | None:
    value = response.get("statusCode")
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _response_payload(response: Mapping[str, object]) -> dict[str, object]:
    body = response.get("body")
    if isinstance(body, Mapping):
        return {str(key): value for key, value in body.items()}
    if not isinstance(body, str):
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, Mapping):
        return {}
    return {str(key): value for key, value in parsed.items()}


def _reason(payload: Mapping[str, object]) -> str | None:
    reason = payload.get("reason")
    if reason:
        return str(reason)
    data = payload.get("data")
    if isinstance(data, Mapping) and data.get("reason"):
        return str(data["reason"])
    error = payload.get("error")
    if isinstance(error, Mapping) and error.get("reason"):
        return str(error["reason"])
    return None


def _local_hs256_jwt(secret: str, payload: Mapping[str, object]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64_json(header)
    encoded_payload = _b64_json(payload)
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64(signature)}"


def _b64_json(payload: Mapping[str, object]) -> str:
    return _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
