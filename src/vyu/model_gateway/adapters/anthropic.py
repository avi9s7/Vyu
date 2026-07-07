from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from anthropic import (
    APIConnectionError,
    APITimeoutError,
    Anthropic,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)
from anthropic.types import Message

from src.vyu.model_gateway.adapters.openai_common import utc_now_iso
from src.vyu.model_gateway.adapters.retry import AdapterRetrySettings, backoff_seconds, retry_after_from_header
from src.vyu.model_gateway.contracts import (
    EmbeddingRequest,
    EmbeddingResponse,
    ModelRequest,
    ModelResponse,
    ProviderHealth,
    ProviderHealthStatus,
)
from src.vyu.model_gateway.errors import (
    GatewayAuthenticationError,
    GatewayMalformedResponse,
    GatewayPolicyBlocked,
    GatewayRateLimited,
    GatewayTimeout,
    GatewayUnavailable,
    GatewayValidationError,
)
from src.vyu.model_gateway.secrets import AnthropicCredentials

STRUCTURED_OUTPUT_MODEL_PREFIXES = (
    "claude-opus-4",
    "claude-sonnet-4",
    "claude-haiku-4",
    "claude-3-5-sonnet",
    "claude-3-7-sonnet",
)

T = TypeVar("T")


def supports_structured_synthesis(model_id: str) -> bool:
    normalized = model_id.strip().lower()
    return any(normalized.startswith(prefix) for prefix in STRUCTURED_OUTPUT_MODEL_PREFIXES)


@dataclass
class AnthropicAdapter:
    credentials: AnthropicCredentials
    provider_id: str = "anthropic"
    settings: AdapterRetrySettings = field(default_factory=AdapterRetrySettings)
    client: Anthropic | None = None
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.perf_counter

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not supports_structured_synthesis(request.model_id):
            raise GatewayValidationError(
                "Anthropic model is not approved for strict structured synthesis"
            )

        started = self.monotonic()
        response = self._with_retries(
            lambda: self._create_message(request),
            operation_name="messages.create",
        )
        latency_ms = max(int((self.monotonic() - started) * 1000), 0)
        return _normalize_message_response(request, response, latency_ms=latency_ms)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raise GatewayValidationError("Anthropic provider does not support embeddings")

    def health(self) -> ProviderHealth:
        started = self.monotonic()
        status = ProviderHealthStatus.HEALTHY
        safe_code: str | None = None
        try:
            self._with_retries(
                lambda: self._client().models.list(limit=1),
                operation_name="models.list",
            )
        except GatewayAuthenticationError:
            status = ProviderHealthStatus.UNAVAILABLE
            safe_code = "authentication_error"
        except (GatewayUnavailable, GatewayTimeout, GatewayRateLimited, GatewayValidationError):
            status = ProviderHealthStatus.DEGRADED
            safe_code = "provider_unavailable"
        latency_ms = max(int((self.monotonic() - started) * 1000), 0)
        return ProviderHealth(
            provider_id=self.provider_id,
            status=status,
            checked_at=utc_now_iso(),
            latency_ms=latency_ms,
            safe_code=safe_code,
        )

    def _create_message(self, request: ModelRequest) -> Message:
        return self._client().messages.create(
            model=request.model_id,
            max_tokens=request.max_output_tokens,
            system=request.system_instructions,
            messages=[{"role": "user", "content": request.input}],
            temperature=request.temperature,
            timeout=request.timeout_seconds,
            metadata={
                "vyu_request_id": request.request_id[:64],
                "vyu_run_id": request.run_id[:64],
            },
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": dict(request.output_schema),
                }
            },
        )

    def _client(self) -> Anthropic:
        if self.client is not None:
            return self.client
        return Anthropic(api_key=self.credentials.api_key)

    def _with_retries(self, operation: Callable[[], T], *, operation_name: str) -> T:
        attempt = 0
        while True:
            attempt += 1
            try:
                return operation()
            except RateLimitError as exc:
                if attempt >= self.settings.max_attempts:
                    raise GatewayRateLimited(
                        "Anthropic rate limit exceeded",
                        retry_after_seconds=retry_after_from_header(exc.response.headers),
                    ) from exc
                delay = retry_after_from_header(exc.response.headers) or backoff_seconds(
                    attempt,
                    settings=self.settings,
                )
                self.sleep(delay)
            except APITimeoutError as exc:
                if attempt >= self.settings.max_attempts:
                    raise GatewayTimeout(f"{operation_name} timed out") from exc
                self.sleep(backoff_seconds(attempt, settings=self.settings))
            except APIConnectionError as exc:
                if attempt >= self.settings.max_attempts:
                    raise GatewayUnavailable(f"{operation_name} connection failed") from exc
                self.sleep(backoff_seconds(attempt, settings=self.settings))
            except InternalServerError as exc:
                if attempt >= self.settings.max_attempts:
                    raise GatewayUnavailable(f"{operation_name} unavailable") from exc
                self.sleep(backoff_seconds(attempt, settings=self.settings))
            except AuthenticationError as exc:
                raise GatewayAuthenticationError("Anthropic authentication failed") from exc
            except BadRequestError as exc:
                raise GatewayValidationError(f"{operation_name} rejected the request") from exc


def _normalize_message_response(
    request: ModelRequest,
    response: Message,
    *,
    latency_ms: int,
) -> ModelResponse:
    if response.stop_reason == "refusal" or response.stop_details is not None:
        raise GatewayPolicyBlocked("provider refused the request")
    if response.stop_reason == "max_tokens":
        raise GatewayMalformedResponse("provider returned incomplete output")

    text_parts: list[str] = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
    output_text = "".join(text_parts).strip()
    if not output_text:
        raise GatewayMalformedResponse("provider returned empty structured output")

    try:
        output = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise GatewayMalformedResponse("provider returned non-json output") from exc
    if not isinstance(output, dict):
        raise GatewayMalformedResponse("provider structured output must be a JSON object")

    usage = response.usage
    cached_tokens = int(usage.cache_read_input_tokens or 0)
    return ModelResponse.from_output(
        request=request,
        provider_request_id=response.id,
        output=output,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        reasoning_tokens=0,
        cached_tokens=cached_tokens,
        latency_ms=latency_ms,
        finish_reason=_anthropic_finish_reason(response.stop_reason),
        schema_valid=True,
    )


def _anthropic_finish_reason(stop_reason: str | None) -> str:
    if stop_reason == "end_turn":
        return "stop"
    if stop_reason is None:
        return "unknown"
    return stop_reason
