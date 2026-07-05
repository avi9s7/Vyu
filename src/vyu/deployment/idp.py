from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import time
from typing import Any, Callable, Mapping
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.vyu.deployment.http_adapter import AuthenticationError, _audiences


OIDC_AUTH_MODE = "oidc_jwks"
SUPPORTED_OIDC_ALGORITHMS = frozenset({"RS256"})
_SHA256_DIGESTINFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


@dataclass(frozen=True)
class OidcJwksConfig:
    """Configuration for externally issued OIDC JWT validation.

    The implementation is intentionally provider-neutral and AWS-friendly:
    operators can point it at an Amazon Cognito user-pool JWKS endpoint, an
    Okta/Azure AD/Entra JWKS endpoint, or a checked-in/mounted JWKS file. SAML
    enterprise connections should be federated through Cognito or another OIDC
    broker so Vyu receives a signed OIDC JWT at the application boundary.
    """

    issuer: str
    audience: str
    jwks_uri: str | None = None
    jwks_path: Path | None = None
    discovery_uri: str | None = None
    allowed_algorithms: frozenset[str] = frozenset({"RS256"})
    leeway_seconds: int = 60
    jwks_cache_ttl_seconds: int = 300
    fetch_timeout_seconds: float = 2.0
    unauthenticated_paths: frozenset[str] = frozenset({"/v1/health"})
    required_token_use: str | None = None

    def validate(self) -> None:
        if not self.issuer.strip():
            raise ValueError("OIDC issuer is required.")
        if not self.audience.strip():
            raise ValueError("OIDC audience is required.")
        if not (self.jwks_uri or self.jwks_path or self.discovery_uri):
            raise ValueError(
                "OIDC JWKS configuration requires jwks_uri, jwks_path, or discovery_uri."
            )
        unsupported = self.allowed_algorithms.difference(SUPPORTED_OIDC_ALGORITHMS)
        if unsupported:
            raise ValueError(
                "OIDC allowed algorithms include unsupported values: "
                + ", ".join(sorted(unsupported))
            )
        if self.leeway_seconds < 0:
            raise ValueError("OIDC leeway_seconds cannot be negative.")
        if self.jwks_cache_ttl_seconds < 0:
            raise ValueError("OIDC jwks_cache_ttl_seconds cannot be negative.")
        if self.fetch_timeout_seconds <= 0:
            raise ValueError("OIDC fetch_timeout_seconds must be positive.")
        if self.jwks_path is not None and not self.jwks_path.exists():
            raise ValueError(f"OIDC JWKS file does not exist: {self.jwks_path}")


class JwksProvider:
    def keys(self) -> tuple[dict[str, Any], ...]:
        raise NotImplementedError


class StaticFileJwksProvider(JwksProvider):
    def __init__(self, path: Path):
        self.path = Path(path)

    def keys(self) -> tuple[dict[str, Any], ...]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthenticationError("OIDC JWKS file could not be read.") from exc
        return _parse_jwks(payload)


class HttpJwksProvider(JwksProvider):
    def __init__(
        self,
        *,
        jwks_uri: str | None,
        discovery_uri: str | None,
        cache_ttl_seconds: int,
        fetch_timeout_seconds: float,
        clock: Callable[[], float] | None = None,
        fetch_json: Callable[[str, float], Mapping[str, object]] | None = None,
    ) -> None:
        self.jwks_uri = jwks_uri
        self.discovery_uri = discovery_uri
        self.cache_ttl_seconds = cache_ttl_seconds
        self.fetch_timeout_seconds = fetch_timeout_seconds
        self.clock = clock or time.time
        self.fetch_json = fetch_json or _fetch_json
        self._cached_keys: tuple[dict[str, Any], ...] | None = None
        self._cache_expires_at = 0.0
        self._resolved_jwks_uri: str | None = None

    def keys(self) -> tuple[dict[str, Any], ...]:
        now = self.clock()
        if self._cached_keys is not None and now < self._cache_expires_at:
            return self._cached_keys
        jwks_uri = self._jwks_uri()
        try:
            payload = self.fetch_json(jwks_uri, self.fetch_timeout_seconds)
        except Exception as exc:  # pragma: no cover - concrete network failures vary.
            raise AuthenticationError("OIDC JWKS endpoint could not be fetched.") from exc
        parsed = _parse_jwks(payload)
        self._cached_keys = parsed
        self._cache_expires_at = now + self.cache_ttl_seconds
        return parsed

    def _jwks_uri(self) -> str:
        if self.jwks_uri:
            return self.jwks_uri
        if self._resolved_jwks_uri:
            return self._resolved_jwks_uri
        if not self.discovery_uri:
            raise AuthenticationError("OIDC JWKS URI is not configured.")
        try:
            metadata = self.fetch_json(self.discovery_uri, self.fetch_timeout_seconds)
        except Exception as exc:  # pragma: no cover - concrete network failures vary.
            raise AuthenticationError("OIDC discovery document could not be fetched.") from exc
        jwks_uri = metadata.get("jwks_uri")
        if not isinstance(jwks_uri, str) or not jwks_uri.strip():
            raise AuthenticationError("OIDC discovery document is missing jwks_uri.")
        self._resolved_jwks_uri = jwks_uri.strip()
        return self._resolved_jwks_uri


class CompositeJwksProvider(JwksProvider):
    def __init__(self, providers: tuple[JwksProvider, ...]):
        if not providers:
            raise ValueError("At least one JWKS provider is required.")
        self.providers = providers

    def keys(self) -> tuple[dict[str, Any], ...]:
        keys: list[dict[str, Any]] = []
        for provider in self.providers:
            keys.extend(provider.keys())
        return tuple(keys)


class OidcJwksBearerTokenAuthenticator:
    """Validate enterprise OIDC bearer JWTs using RS256 and JWKS."""

    def __init__(
        self,
        config: OidcJwksConfig,
        *,
        jwks_provider: JwksProvider | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.clock = clock or time.time
        self.jwks_provider = jwks_provider or _provider_from_config(config, self.clock)

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
        algorithm = header.get("alg")
        if not isinstance(algorithm, str) or algorithm not in self.config.allowed_algorithms:
            raise AuthenticationError("Bearer token algorithm is not allowed.")
        if algorithm != "RS256":
            raise AuthenticationError("Bearer token algorithm is not implemented.")

        key = self._select_key(header)
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        signature = _decode_segment(encoded_signature, "signature")
        if not _verify_rs256_signature(signing_input, signature, key):
            raise AuthenticationError("Bearer token signature is invalid.")

        self._validate_registered_claims(payload)
        return _normalized_oidc_claims(dict(payload), self.config.audience)

    def _select_key(self, header: Mapping[str, object]) -> Mapping[str, object]:
        token_kid = header.get("kid")
        token_alg = header.get("alg")
        keys = self.jwks_provider.keys()
        matches: list[Mapping[str, object]] = []
        for key in keys:
            if key.get("kty") != "RSA":
                continue
            if key.get("use") not in (None, "sig"):
                continue
            if key.get("alg") not in (None, token_alg):
                continue
            if token_kid is not None and key.get("kid") != token_kid:
                continue
            matches.append(key)
        if not matches and token_kid is not None:
            raise AuthenticationError("Bearer token key id is not present in JWKS.")
        if not matches:
            raise AuthenticationError("No usable RSA signing key is present in JWKS.")
        if token_kid is None and len(matches) != 1:
            raise AuthenticationError("Bearer token key id is required when JWKS has multiple keys.")
        return matches[0]

    def _validate_registered_claims(self, payload: Mapping[str, object]) -> None:
        if payload.get("iss") != self.config.issuer:
            raise AuthenticationError("Bearer token issuer is not trusted.")

        audiences = _oidc_audiences(payload)
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

        if self.config.required_token_use is not None:
            token_use = payload.get("token_use")
            if token_use != self.config.required_token_use:
                raise AuthenticationError("Bearer token token_use is not accepted.")


def _provider_from_config(
    config: OidcJwksConfig,
    clock: Callable[[], float],
) -> JwksProvider:
    providers: list[JwksProvider] = []
    if config.jwks_path is not None:
        providers.append(StaticFileJwksProvider(config.jwks_path))
    if config.jwks_uri or config.discovery_uri:
        providers.append(
            HttpJwksProvider(
                jwks_uri=config.jwks_uri,
                discovery_uri=config.discovery_uri,
                cache_ttl_seconds=config.jwks_cache_ttl_seconds,
                fetch_timeout_seconds=config.fetch_timeout_seconds,
                clock=clock,
            )
        )
    return CompositeJwksProvider(tuple(providers))


def _parse_jwks(payload: Mapping[str, object]) -> tuple[dict[str, Any], ...]:
    keys = payload.get("keys")
    if not isinstance(keys, list):
        raise AuthenticationError("OIDC JWKS must contain a keys array.")
    parsed = tuple(dict(key) for key in keys if isinstance(key, Mapping))
    if not parsed:
        raise AuthenticationError("OIDC JWKS does not contain any keys.")
    return parsed


def _fetch_json(uri: str, timeout_seconds: float) -> Mapping[str, object]:
    request = Request(uri, headers={"accept": "application/json", "user-agent": "vyu-oidc-jwks"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310 - operator-configured IdP URL.
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AuthenticationError("OIDC JSON endpoint returned invalid content.") from exc
    if not isinstance(payload, Mapping):
        raise AuthenticationError("OIDC JSON endpoint must return a JSON object.")
    return dict(payload)


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


def _verify_rs256_signature(
    signing_input: bytes,
    signature: bytes,
    key: Mapping[str, object],
) -> bool:
    modulus = _required_jwk_int(key, "n")
    exponent = _required_jwk_int(key, "e")
    key_size = (modulus.bit_length() + 7) // 8
    if len(signature) != key_size:
        return False
    signature_int = int.from_bytes(signature, "big")
    encoded_message = pow(signature_int, exponent, modulus).to_bytes(key_size, "big")
    expected_digest_info = _SHA256_DIGESTINFO_PREFIX + hashlib.sha256(signing_input).digest()
    expected_padding_length = key_size - len(expected_digest_info) - 3
    if expected_padding_length < 8:
        return False
    expected = b"\x00\x01" + (b"\xff" * expected_padding_length) + b"\x00" + expected_digest_info
    return hmac.compare_digest(encoded_message, expected)


def _required_jwk_int(key: Mapping[str, object], name: str) -> int:
    value = key.get(name)
    if not isinstance(value, str) or not value.strip():
        raise AuthenticationError(f"OIDC RSA JWK is missing {name}.")
    return int.from_bytes(_decode_segment(value, f"jwk.{name}"), "big")


def _oidc_audiences(payload: Mapping[str, object]) -> tuple[str, ...]:
    values = list(_audiences(payload.get("aud")))
    for fallback_claim in ("client_id", "azp"):
        value = payload.get(fallback_claim)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return tuple(dict.fromkeys(values))


def _normalized_oidc_claims(payload: dict[str, object], accepted_audience: str) -> dict[str, object]:
    if not _audiences(payload.get("aud")) and accepted_audience in _oidc_audiences(payload):
        payload["aud"] = accepted_audience
    return payload


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
