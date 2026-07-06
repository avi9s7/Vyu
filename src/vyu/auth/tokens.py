from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from src.vyu.deployment.http_adapter import (
    AuthenticationError,
    BearerTokenConfig,
    Hs256BearerTokenAuthenticator,
)
from src.vyu.deployment.idp import OidcJwksBearerTokenAuthenticator, OidcJwksConfig


LOCAL_HS256_AUTH_MODE = "local_hs256"
OIDC_JWKS_AUTH_MODE = "oidc_jwks"


@dataclass(frozen=True)
class VerifiedToken:
    issuer: str
    subject: str
    audience: str
    email: str
    email_verified: bool
    tenant_id: str
    workspace_id: str
    claimed_roles: tuple[str, ...]
    authentication_method: str


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedToken:
        ...


@dataclass(frozen=True)
class Hs256TokenVerifier:
    authenticator: Hs256BearerTokenAuthenticator
    require_email_verified: bool

    def verify(self, token: str) -> VerifiedToken:
        claims = self.authenticator.authenticate({"authorization": f"Bearer {token}"})
        return _verified_from_claims(
            claims,
            authentication_method=LOCAL_HS256_AUTH_MODE,
            require_email_verified=self.require_email_verified,
        )


@dataclass(frozen=True)
class OidcJwksTokenVerifier:
    authenticator: OidcJwksBearerTokenAuthenticator
    require_email_verified: bool

    def verify(self, token: str) -> VerifiedToken:
        claims = self.authenticator.authenticate({"authorization": f"Bearer {token}"})
        return _verified_from_claims(
            claims,
            authentication_method=OIDC_JWKS_AUTH_MODE,
            require_email_verified=self.require_email_verified,
        )


def build_token_verifier(
    *,
    auth_mode: str,
    issuer: str,
    audience: str,
    hs256_secret: str | None,
    require_email_verified: bool,
    oidc_config: OidcJwksConfig | None = None,
) -> TokenVerifier:
    if auth_mode == LOCAL_HS256_AUTH_MODE:
        if not hs256_secret:
            raise ValueError("HS256 secret is required for local_hs256 auth mode.")
        return Hs256TokenVerifier(
            authenticator=Hs256BearerTokenAuthenticator(
                BearerTokenConfig(
                    issuer=issuer,
                    audience=audience,
                    hs256_secret=hs256_secret,
                )
            ),
            require_email_verified=require_email_verified,
        )
    if auth_mode == OIDC_JWKS_AUTH_MODE:
        if oidc_config is None:
            raise ValueError("OIDC JWKS configuration is required for oidc_jwks auth mode.")
        return OidcJwksTokenVerifier(
            authenticator=OidcJwksBearerTokenAuthenticator(oidc_config),
            require_email_verified=require_email_verified,
        )
    raise ValueError(f"Unsupported auth mode: {auth_mode}")


def verify_authorization_header(
    verifier: TokenVerifier,
    headers: Mapping[str, str],
) -> VerifiedToken:
    authorization = _header_value(headers, "authorization")
    if not authorization:
        raise AuthenticationError("Missing Authorization bearer token.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("Authorization header must use the Bearer scheme.")
    return verifier.verify(token.strip())


def _verified_from_claims(
    claims: Mapping[str, Any],
    *,
    authentication_method: str,
    require_email_verified: bool,
) -> VerifiedToken:
    issuer = _required_string(claims, "iss")
    subject = _required_string(claims, "sub")
    audience = _first_audience(claims.get("aud"))
    email = _optional_string(claims, "email") or f"{subject}@unknown.invalid"
    email_verified = claims.get("email_verified") is True
    if require_email_verified and not email_verified:
        raise AuthenticationError("Email verification is required.")
    tenant_id = _required_scope_claim(claims, "tenant_id")
    workspace_id = _required_scope_claim(claims, "workspace_id")
    claimed_roles = _claimed_roles(claims)
    return VerifiedToken(
        issuer=issuer,
        subject=subject,
        audience=audience,
        email=email,
        email_verified=email_verified,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        claimed_roles=claimed_roles,
        authentication_method=authentication_method,
    )


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lowered:
            return str(value)
    return None


def _required_string(claims: Mapping[str, Any], claim: str) -> str:
    value = claims.get(claim)
    if not isinstance(value, str) or not value.strip():
        raise AuthenticationError(f"Bearer token is missing {claim}.")
    return value.strip()


def _optional_string(claims: Mapping[str, Any], claim: str) -> str | None:
    value = claims.get(claim)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _first_audience(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (list, tuple, set)):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    raise AuthenticationError("Bearer token is missing aud.")


def _required_scope_claim(claims: Mapping[str, Any], name: str) -> str:
    paths = (
        f"vyu.{name}",
        f"custom:vyu_{name}",
        name,
    )
    for path in paths:
        if path in claims:
            value = claims.get(path)
        else:
            value = _nested_claim(claims, path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = claims.get("vyu")
    if isinstance(nested, Mapping):
        nested_value = nested.get(name)
        if isinstance(nested_value, str) and nested_value.strip():
            return nested_value.strip()
    raise AuthenticationError(f"Bearer token is missing scope claim for {name}.")


def _nested_claim(claims: Mapping[str, Any], path: str) -> Any:
    current: Any = claims
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _claimed_roles(claims: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for path in ("vyu.roles", "roles", "cognito:groups", "custom:vyu_roles"):
        if path in claims:
            raw = claims.get(path)
        else:
            raw = _nested_claim(claims, path)
        if isinstance(raw, str):
            values.extend(item.strip() for item in raw.split(",") if item.strip())
        elif isinstance(raw, (list, tuple, set)):
            values.extend(str(item).strip() for item in raw if str(item).strip())
    nested = claims.get("vyu")
    if isinstance(nested, Mapping):
        roles = nested.get("roles")
        if isinstance(roles, str):
            values.extend(item.strip() for item in roles.split(",") if item.strip())
        elif isinstance(roles, (list, tuple, set)):
            values.extend(str(item).strip() for item in roles if str(item).strip())
    return tuple(dict.fromkeys(values))
