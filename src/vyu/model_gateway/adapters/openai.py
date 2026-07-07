from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from openai.types.responses import Response

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
from src.vyu.model_gateway.secrets import OpenAICredentials

STRUCTURED_OUTPUT_MODEL_PREFIXES = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-5",
    "o3",
    "o4",
)

T = TypeVar("T")


@dataclass(frozen=True)
class OpenAIAdapterSettings:
    max_attempts: int = 3
    retry_base_seconds: float = 0.5
    retry_max_seconds: float = 8.0


def supports_structured_synthesis(model_id: str) -> bool:
    normalized = model_id.strip().lower()
    return any(normalized.startswith(prefix) for prefix in STRUCTURED_OUTPUT_MODEL_PREFIXES)


@dataclass
class OpenAIAdapter:
    """OpenAI Responses API generation and Embeddings API adapter."""

    credentials: OpenAICredentials
    provider_id: str = "openai"
    settings: OpenAIAdapterSettings = field(default_factory=OpenAIAdapterSettings)
    client: OpenAI | None = None
    jitter: Callable[[float, float], float] = random.uniform
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.perf_counter

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not supports_structured_synthesis(request.model_id):
            raise GatewayValidationError(
                "OpenAI model is not approved for strict structured synthesis"
            )

        started = self.monotonic()
        response = self._with_retries(
            lambda: self._create_response(request),
            operation_name="responses.create",
        )
        latency_ms = max(int((self.monotonic() - started) * 1000), 0)
        return _normalize_generation_response(request, response, latency_ms=latency_ms)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        started = self.monotonic()
        response = self._with_retries(
            lambda: self._client().embeddings.create(
                model=request.model_id,
                input=list(request.texts),
                dimensions=request.dimensions,
                timeout=request.timeout_seconds,
            ),
            operation_name="embeddings.create",
        )
        latency_ms = max(int((self.monotonic() - started) * 1000), 0)
        vectors = tuple(tuple(float(value) for value in item.embedding) for item in response.data)
        usage = response.usage
        return EmbeddingResponse.from_vectors(
            request=request,
            provider_request_id=None,
            vectors=vectors,
            input_tokens=usage.prompt_tokens,
            total_tokens=usage.total_tokens,
            latency_ms=latency_ms,
        )

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
            checked_at=_utc_now_iso(),
            latency_ms=latency_ms,
            safe_code=safe_code,
        )

    def _create_response(self, request: ModelRequest) -> Response:
        schema_name = _schema_name(request.prompt_template_id)
        return self._client().responses.create(
            model=request.model_id,
            instructions=request.system_instructions,
            input=request.input,
            max_output_tokens=request.max_output_tokens,
            temperature=request.temperature,
            timeout=request.timeout_seconds,
            metadata={
                "vyu_request_id": request.request_id[:64],
                "vyu_run_id": request.run_id[:64],
            },
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": dict(request.output_schema),
                    "strict": True,
                }
            },
        )

    def _client(self) -> OpenAI:
        if self.client is not None:
            return self.client
        return OpenAI(api_key=self.credentials.api_key)

    def _with_retries(self, operation: Callable[[], T], *, operation_name: str) -> T:
        attempt = 0
        while True:
            attempt += 1
            try:
                return operation()
            except RateLimitError as exc:
                if attempt >= self.settings.max_attempts:
                    raise _rate_limited_error(exc) from exc
                self.sleep(_retry_delay_seconds(exc, attempt=attempt, settings=self.settings))
            except APITimeoutError as exc:
                if attempt >= self.settings.max_attempts:
                    raise GatewayTimeout(f"{operation_name} timed out") from exc
                self.sleep(_backoff_seconds(attempt, settings=self.settings))
            except APIConnectionError as exc:
                if attempt >= self.settings.max_attempts:
                    raise GatewayUnavailable(f"{operation_name} connection failed") from exc
                self.sleep(_backoff_seconds(attempt, settings=self.settings))
            except InternalServerError as exc:
                if attempt >= self.settings.max_attempts:
                    raise GatewayUnavailable(f"{operation_name} unavailable") from exc
                self.sleep(_backoff_seconds(attempt, settings=self.settings))
            except AuthenticationError as exc:
                raise GatewayAuthenticationError("OpenAI authentication failed") from exc
            except BadRequestError as exc:
                raise GatewayValidationError(f"{operation_name} rejected the request") from exc
def _normalize_generation_response(
    request: ModelRequest,
    response: Response,
    *,
    latency_ms: int,
) -> ModelResponse:
    if response.status in {"failed", "cancelled"}:
        raise GatewayMalformedResponse(f"provider response status is {response.status}")
    if response.status == "incomplete" or response.incomplete_details is not None:
        raise GatewayMalformedResponse("provider returned incomplete output")

    refusals = _extract_refusals(response)
    if refusals:
        raise GatewayPolicyBlocked("provider refused the request")

    output_text = response.output_text
    if not output_text.strip():
        raise GatewayMalformedResponse("provider returned empty structured output")

    try:
        output = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise GatewayMalformedResponse("provider returned non-json output") from exc
    if not isinstance(output, dict):
        raise GatewayMalformedResponse("provider structured output must be a JSON object")

    usage = response.usage
    input_tokens = usage.input_tokens if usage is not None else 0
    output_tokens = usage.output_tokens if usage is not None else 0
    reasoning_tokens = (
        usage.output_tokens_details.reasoning_tokens
        if usage is not None and usage.output_tokens_details is not None
        else 0
    )
    cached_tokens = (
        usage.input_tokens_details.cached_tokens
        if usage is not None and usage.input_tokens_details is not None
        else 0
    )

    return ModelResponse.from_output(
        request=request,
        provider_request_id=response.id,
        output=output,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cached_tokens=cached_tokens,
        latency_ms=latency_ms,
        finish_reason=_finish_reason(response),
        schema_valid=True,
    )


def _extract_refusals(response: Response) -> list[str]:
    refusals: list[str] = []
    for item in response.output:
        if item.type != "message":
            continue
        for content in item.content:
            if content.type == "refusal":
                refusals.append(content.refusal)
    return refusals


def _finish_reason(response: Response) -> str:
    if response.status == "completed":
        return "stop"
    if response.status == "incomplete":
        return "incomplete"
    return str(response.status or "unknown")


def _schema_name(prompt_template_id: str) -> str:
    sanitized = "".join(
        character if character.isalnum() or character in {"_", "-"} else "_"
        for character in prompt_template_id.strip()
    )
    return (sanitized or "vyu_output")[:64]


def _retry_delay_seconds(
    exc: RateLimitError,
    *,
    attempt: int,
    settings: OpenAIAdapterSettings,
) -> float:
    retry_after = _retry_after_header(exc)
    if retry_after is not None:
        return retry_after
    return _backoff_seconds(attempt, settings=settings)


def _retry_after_header(exc: APIStatusError) -> float | None:
    header = exc.response.headers.get("retry-after")
    if header is None:
        return None
    try:
        return max(float(header), 0.0)
    except ValueError:
        return None


def _backoff_seconds(attempt: int, *, settings: OpenAIAdapterSettings) -> float:
    delay = min(
        settings.retry_base_seconds * (2 ** max(attempt - 1, 0)),
        settings.retry_max_seconds,
    )
    return delay


def _rate_limited_error(exc: RateLimitError) -> GatewayRateLimited:
    return GatewayRateLimited(
        "OpenAI rate limit exceeded",
        retry_after_seconds=_retry_after_header(exc),
    )


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
