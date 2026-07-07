from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

PLACEHOLDER_SECRET_VALUES = frozenset(
    {
        "__REPLACE_WITH_LOCAL_SECRET__",
        "CHANGE_ME",
        "REPLACE_ME",
        "REPLACE_WITH_SECRET",
        "replace-with-secret",
        "sk-placeholder-replace-before-deploy",
        "sk-ant-placeholder-replace-before-deploy",
    }
)

PROVIDER_SECRET_KEYS: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "azure_openai": ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"),
    "google": ("GOOGLE_API_KEY",),
}


class SecretResolutionError(RuntimeError):
    """Raised when provider credentials cannot be resolved safely."""


class SecretsManagerClient(Protocol):
    def get_secret_value(self, *, SecretId: str, VersionId: str | None = None) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class OpenAICredentials:
    api_key: str

    def __repr__(self) -> str:
        return "OpenAICredentials(api_key=<redacted>)"


@dataclass(frozen=True)
class AnthropicCredentials:
    api_key: str

    def __repr__(self) -> str:
        return "AnthropicCredentials(api_key=<redacted>)"


@dataclass(frozen=True)
class AzureOpenAICredentials:
    api_key: str
    endpoint: str
    deployment: str | None = None

    def __repr__(self) -> str:
        return "AzureOpenAICredentials(api_key=<redacted>, endpoint=<redacted>)"


@dataclass(frozen=True)
class GoogleCredentials:
    api_key: str

    def __repr__(self) -> str:
        return "GoogleCredentials(api_key=<redacted>)"


ProviderCredentials = OpenAICredentials | AnthropicCredentials | AzureOpenAICredentials | GoogleCredentials


@dataclass(frozen=True)
class SecretRotationRunbook:
    """Operator workflow for rotating provider credentials without downtime."""

    environment: str
    secret_id: str

    def steps(self) -> tuple[str, ...]:
        return (
            f"Put a new secret value for {self.secret_id} in {self.environment}.",
            "Confirm AWSCURRENT points to the new secret version.",
            "Force a new ECS deployment for api and worker services.",
            "Run health and synthesis evaluation smoke checks.",
            "Revoke or disable the previous provider credential at the vendor.",
        )


@dataclass
class _SecretCacheEntry:
    payload: Mapping[str, str]
    version_id: str | None
    loaded_at_monotonic: float


class SecretResolver:
    """Resolve provider credentials from Secrets Manager with bounded cache refresh."""

    def __init__(
        self,
        *,
        secret_arn: str,
        cache_ttl_seconds: int = 300,
        client: SecretsManagerClient | None = None,
        local_secret_file: Path | None = None,
        now: Any | None = None,
    ) -> None:
        self._secret_arn = secret_arn.strip()
        self._cache_ttl_seconds = cache_ttl_seconds
        self._client = client
        self._local_secret_file = local_secret_file
        self._now = time.monotonic if now is None else now
        self._cache: _SecretCacheEntry | None = None

    def credentials_for(self, provider_id: str) -> ProviderCredentials:
        payload = self._current_payload()
        return _credentials_from_payload(provider_id, payload)

    def validate_provider_credentials(self, provider_id: str) -> None:
        credentials = self.credentials_for(provider_id)
        _validate_resolved_credentials(provider_id, credentials)

    def invalidate_cache(self) -> None:
        self._cache = None

    def current_secret_version_id(self) -> str | None:
        entry = self._load_cache_entry(force_refresh=True)
        return entry.version_id

    def _current_payload(self) -> Mapping[str, str]:
        entry = self._load_cache_entry()
        return entry.payload

    def _load_cache_entry(self, *, force_refresh: bool = False) -> _SecretCacheEntry:
        now = self._now()
        if (
            not force_refresh
            and self._cache is not None
            and (now - self._cache.loaded_at_monotonic) < self._cache_ttl_seconds
        ):
            return self._cache

        if self._local_secret_file is not None:
            entry = _load_local_secret_file(self._local_secret_file)
        else:
            entry = _load_secret_manager_payload(
                client=self._client,
                secret_arn=self._secret_arn,
            )
        self._cache = _SecretCacheEntry(
            payload=entry.payload,
            version_id=entry.version_id,
            loaded_at_monotonic=now,
        )
        return self._cache


@dataclass(frozen=True)
class _LoadedSecretPayload:
    payload: Mapping[str, str]
    version_id: str | None = None


def _load_local_secret_file(path: Path) -> _LoadedSecretPayload:
    if not path.exists():
        raise SecretResolutionError(f"provider secret file does not exist: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecretResolutionError("provider secret file is not valid JSON") from exc
    return _LoadedSecretPayload(payload=_normalize_secret_mapping(raw))


def _load_secret_manager_payload(
    *,
    client: SecretsManagerClient | None,
    secret_arn: str,
) -> _LoadedSecretPayload:
    if not secret_arn:
        raise SecretResolutionError("provider secret ARN is not configured")
    if client is None:
        raise SecretResolutionError("Secrets Manager client is not configured")

    try:
        response = client.get_secret_value(SecretId=secret_arn)
    except Exception as exc:
        raise SecretResolutionError(_safe_secret_error("unable to load provider secret", exc)) from exc

    secret_string = response.get("SecretString")
    if not isinstance(secret_string, str) or not secret_string.strip():
        raise SecretResolutionError("provider secret payload is missing")

    try:
        raw = json.loads(secret_string)
    except json.JSONDecodeError as exc:
        raise SecretResolutionError("provider secret payload is not valid JSON") from exc

    return _LoadedSecretPayload(
        payload=_normalize_secret_mapping(raw),
        version_id=str(response.get("VersionId")) if response.get("VersionId") else None,
    )


def _normalize_secret_mapping(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise SecretResolutionError("provider secret payload must be a JSON object")
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise SecretResolutionError("provider secret payload keys must be strings")
        if not isinstance(value, str):
            raise SecretResolutionError(f"provider secret value for {key} must be a string")
        normalized[key] = value
    return normalized


def _credentials_from_payload(provider_id: str, payload: Mapping[str, str]) -> ProviderCredentials:
    keys = PROVIDER_SECRET_KEYS.get(provider_id)
    if keys is None:
        raise SecretResolutionError(f"unsupported provider for secret resolution: {provider_id}")

    if provider_id == "openai":
        api_key = _required_secret_value(payload, keys[0], provider_id=provider_id)
        return OpenAICredentials(api_key=api_key)
    if provider_id == "anthropic":
        api_key = _required_secret_value(payload, keys[0], provider_id=provider_id)
        return AnthropicCredentials(api_key=api_key)
    if provider_id == "azure_openai":
        api_key = _required_secret_value(payload, keys[0], provider_id=provider_id)
        endpoint = _required_secret_value(payload, keys[1], provider_id=provider_id)
        deployment = payload.get("AZURE_OPENAI_DEPLOYMENT")
        return AzureOpenAICredentials(
            api_key=api_key,
            endpoint=endpoint,
            deployment=deployment.strip() if isinstance(deployment, str) and deployment.strip() else None,
        )
    if provider_id == "google":
        api_key = _required_secret_value(payload, keys[0], provider_id=provider_id)
        return GoogleCredentials(api_key=api_key)
    raise SecretResolutionError(f"unsupported provider for secret resolution: {provider_id}")


def _required_secret_value(
    payload: Mapping[str, str],
    key: str,
    *,
    provider_id: str,
) -> str:
    value = payload.get(key, "").strip()
    if not value:
        raise SecretResolutionError(
            f"missing provider credential for {provider_id}: {key}"
        )
    if _is_placeholder_secret(value):
        raise SecretResolutionError(
            f"provider credential for {provider_id} is still a placeholder"
        )
    return value


def _validate_resolved_credentials(provider_id: str, credentials: ProviderCredentials) -> None:
    if isinstance(credentials, OpenAICredentials):
        _assert_non_placeholder(credentials.api_key, provider_id=provider_id, field="api_key")
    elif isinstance(credentials, AnthropicCredentials):
        _assert_non_placeholder(credentials.api_key, provider_id=provider_id, field="api_key")
    elif isinstance(credentials, AzureOpenAICredentials):
        _assert_non_placeholder(credentials.api_key, provider_id=provider_id, field="api_key")
        _assert_non_placeholder(credentials.endpoint, provider_id=provider_id, field="endpoint")
    elif isinstance(credentials, GoogleCredentials):
        _assert_non_placeholder(credentials.api_key, provider_id=provider_id, field="api_key")


def _assert_non_placeholder(value: str, *, provider_id: str, field: str) -> None:
    if _is_placeholder_secret(value):
        raise SecretResolutionError(
            f"provider credential for {provider_id}.{field} is still a placeholder"
        )


def _is_placeholder_secret(secret: str) -> bool:
    normalized = secret.strip()
    if not normalized:
        return True
    upper = normalized.upper()
    if normalized in PLACEHOLDER_SECRET_VALUES:
        return True
    return "REPLACE" in upper or "CHANGE_ME" in upper or "PLACEHOLDER" in upper


def _safe_secret_error(prefix: str, exc: Exception) -> str:
    message = str(exc)
    for token in _secret_like_tokens(message):
        message = message.replace(token, "<redacted>")
    return f"{prefix}: {message}"


def _secret_like_tokens(message: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for part in message.split():
        if part.startswith("sk-") or part.startswith("sk_ant") or len(part) >= 24:
            tokens.append(part)
    return tuple(tokens)
