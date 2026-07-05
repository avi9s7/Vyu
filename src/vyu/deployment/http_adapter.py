from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import time
from typing import Callable, Mapping, Protocol

from src.vyu.authz import TenantGovernanceRepository
from src.vyu.entrypoints.service_routes import (
    ServiceRouteRequest,
    ServiceRouteResponse,
    ServiceRouteRuntime,
)


class AuthenticationError(ValueError):
    """Raised when a deployment request cannot be authenticated."""


@dataclass(frozen=True)
class DeploymentHttpRequest:
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    json_body: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DeploymentHttpResponse:
    status_code: int
    body: dict[str, object]
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BearerTokenConfig:
    issuer: str
    audience: str
    hs256_secret: str
    leeway_seconds: int = 60
    unauthenticated_paths: frozenset[str] = frozenset({"/v1/health"})


@dataclass(frozen=True)
class ApiKeyAuthConfig:
    issuer: str
    audience: str
    unauthenticated_paths: frozenset[str] = frozenset({"/v1/health"})
    header_name: str = "x-vyu-api-key"


@dataclass(frozen=True)
class CompositeAuthenticatorConfig:
    unauthenticated_paths: frozenset[str] = frozenset({"/v1/health"})


class BearerTokenAuthenticator(Protocol):
    def authenticate(self, headers: Mapping[str, str]) -> dict[str, object]:
        ...


class ServiceRouteHandler(Protocol):
    def handle(self, request: ServiceRouteRequest) -> ServiceRouteResponse:
        ...


class Hs256BearerTokenAuthenticator:
    """Validate HS256 bearer JWTs using only the Python standard library."""

    def __init__(
        self,
        config: BearerTokenConfig,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not config.hs256_secret:
            raise ValueError("HS256 secret is required.")
        if not config.issuer:
            raise ValueError("Trusted issuer is required.")
        if not config.audience:
            raise ValueError("Accepted audience is required.")
        self.config = config
        self.clock = clock or time.time

    def authenticate(self, headers: Mapping[str, str]) -> dict[str, object]:
        normalized_headers = {str(key).lower(): str(value) for key, value in headers.items()}
        authorization = normalized_headers.get("authorization")
        if not authorization:
            raise AuthenticationError("Missing Authorization bearer token.")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise AuthenticationError("Authorization header must use the Bearer scheme.")
        return self._verify_jwt(token.strip())

    def _verify_jwt(self, token: str) -> dict[str, object]:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthenticationError("Bearer token is not a three-part JWT.")
        encoded_header, encoded_payload, encoded_signature = parts
        header = _decode_json_segment(encoded_header, "header")
        payload = _decode_json_segment(encoded_payload, "payload")
        if header.get("alg") != "HS256":
            raise AuthenticationError("Bearer token algorithm is not allowed.")

        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected = _sign_hs256(signing_input, self.config.hs256_secret)
        actual = _decode_segment(encoded_signature, "signature")
        if not hmac.compare_digest(expected, actual):
            raise AuthenticationError("Bearer token signature is invalid.")

        self._validate_registered_claims(payload)
        return dict(payload)

    def _validate_registered_claims(self, payload: Mapping[str, object]) -> None:
        issuer = payload.get("iss")
        if issuer != self.config.issuer:
            raise AuthenticationError("Bearer token issuer is not trusted.")

        audiences = _audiences(payload.get("aud"))
        if self.config.audience not in audiences:
            raise AuthenticationError("Bearer token audience is not accepted.")

        now = int(self.clock())
        leeway = self.config.leeway_seconds
        exp = _numeric_claim(payload, "exp", required=True)
        if now > exp + leeway:
            raise AuthenticationError("Bearer token is expired.")

        nbf = _numeric_claim(payload, "nbf", required=False)
        if nbf is not None and now + leeway < nbf:
            raise AuthenticationError("Bearer token is not valid yet.")

        iat = _numeric_claim(payload, "iat", required=False)
        if iat is not None and now + leeway < iat:
            raise AuthenticationError("Bearer token was issued in the future.")


class TenantGovernanceApiKeyAuthenticator:
    """Authenticate service-account API keys through tenant governance records."""

    def __init__(
        self,
        repository: TenantGovernanceRepository,
        config: ApiKeyAuthConfig,
    ) -> None:
        if not config.issuer:
            raise ValueError("API-key issuer is required.")
        if not config.audience:
            raise ValueError("API-key audience is required.")
        if not config.header_name.strip():
            raise ValueError("API-key header name is required.")
        self.repository = repository
        self.config = config

    def authenticate(self, headers: Mapping[str, str]) -> dict[str, object]:
        normalized_headers = {str(key).lower(): str(value) for key, value in headers.items()}
        raw_api_key = normalized_headers.get(self.config.header_name.lower())
        if raw_api_key is None:
            raise AuthenticationError("Missing Vyu API key.")
        decision = self.repository.authenticate_api_key(
            raw_api_key,
            issuer=self.config.issuer,
            audience=self.config.audience,
        )
        if not decision.allowed or decision.claims is None:
            raise AuthenticationError(f"API key authentication failed: {decision.reason}.")
        return dict(decision.claims)


class CompositeDeploymentAuthenticator:
    """Authenticate with API key when present, otherwise with bearer JWT."""

    def __init__(
        self,
        bearer_authenticator: BearerTokenAuthenticator,
        api_key_authenticator: TenantGovernanceApiKeyAuthenticator | None = None,
        unauthenticated_paths: frozenset[str] = frozenset({"/v1/health"}),
    ) -> None:
        self.bearer_authenticator = bearer_authenticator
        self.api_key_authenticator = api_key_authenticator
        self.config = CompositeAuthenticatorConfig(unauthenticated_paths=unauthenticated_paths)

    def authenticate(self, headers: Mapping[str, str]) -> dict[str, object]:
        normalized_headers = {str(key).lower(): str(value) for key, value in headers.items()}
        if self.api_key_authenticator is not None:
            api_key_header = self.api_key_authenticator.config.header_name.lower()
            if normalized_headers.get(api_key_header):
                return self.api_key_authenticator.authenticate(normalized_headers)
        return self.bearer_authenticator.authenticate(normalized_headers)


class ServiceDeploymentHttpAdapter:
    """Deployment boundary from HTTP-shaped requests to ServiceRouteRuntime."""

    def __init__(
        self,
        service_runtime: ServiceRouteRuntime | ServiceRouteHandler,
        authenticator: BearerTokenAuthenticator,
        request_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.service_runtime = service_runtime
        self.authenticator = authenticator
        self.request_id_factory = request_id_factory or (lambda: "deployment-http")

    def handle(self, request: DeploymentHttpRequest) -> DeploymentHttpResponse:
        headers = {str(key).lower(): str(value) for key, value in request.headers.items()}
        request_id = headers.get("x-vyu-request-id") or self.request_id_factory()
        audit_correlation_id = headers.get("x-vyu-audit-correlation-id") or request_id
        headers["x-vyu-request-id"] = request_id
        headers["x-vyu-audit-correlation-id"] = audit_correlation_id

        try:
            identity_claims = (
                {}
                if request.path in _unauthenticated_paths(self.authenticator)
                else self.authenticator.authenticate(headers)
            )
        except AuthenticationError as exc:
            return _deployment_error(
                status_code=401,
                request_id=request_id,
                audit_correlation_id=audit_correlation_id,
                reason="auth_token_invalid",
                detail=str(exc),
                method=request.method.upper(),
                path=request.path,
            )

        response = self.service_runtime.handle(
            ServiceRouteRequest(
                method=request.method.upper(),
                path=request.path,
                headers=headers,
                query={str(key): str(value) for key, value in request.query.items()},
                json_body=dict(request.json_body),
                identity_claims=dict(identity_claims),
            )
        )
        return DeploymentHttpResponse(
            status_code=response.status_code,
            body=dict(response.body),
            headers=dict(getattr(response, "headers", {})),
        )


def _deployment_error(
    status_code: int,
    request_id: str,
    audit_correlation_id: str,
    reason: str,
    detail: str,
    method: str,
    path: str,
) -> DeploymentHttpResponse:
    return DeploymentHttpResponse(
        status_code=status_code,
        body={
            "request_id": request_id,
            "audit_correlation_id": audit_correlation_id,
            "status": "error",
            "reason": reason,
            "error": {"reason": reason, "detail": detail},
            "data": {
                "reason": reason,
                "detail": detail,
                "method": method,
                "path": path,
            },
        },
        headers={
            "x-vyu-request-id": request_id,
            "x-vyu-audit-correlation-id": audit_correlation_id,
        },
    )


def _unauthenticated_paths(authenticator: BearerTokenAuthenticator) -> frozenset[str]:
    config = getattr(authenticator, "config", None)
    paths = getattr(config, "unauthenticated_paths", frozenset())
    return frozenset(str(path) for path in paths)


def _decode_json_segment(encoded: str, name: str) -> dict[str, object]:
    try:
        decoded = _decode_segment(encoded, name)
        payload = json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthenticationError(f"Bearer token {name} is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise AuthenticationError(f"Bearer token {name} must be a JSON object.")
    return dict(payload)


def _decode_segment(encoded: str, name: str) -> bytes:
    try:
        padding = "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode((encoded + padding).encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise AuthenticationError(f"Bearer token {name} is not valid base64url.") from exc


def _sign_hs256(signing_input: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()


def _audiences(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if str(item))
    return ()


def _numeric_claim(
    payload: Mapping[str, object],
    claim: str,
    required: bool,
) -> int | None:
    value = payload.get(claim)
    if value is None:
        if required:
            raise AuthenticationError(f"Bearer token is missing {claim}.")
        return None
    if isinstance(value, bool):
        raise AuthenticationError(f"Bearer token {claim} must be numeric.")
    if isinstance(value, (int, float)):
        return int(value)
    raise AuthenticationError(f"Bearer token {claim} must be numeric.")
