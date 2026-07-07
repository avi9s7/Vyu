from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai.types import GenerateContentResponse

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
from src.vyu.model_gateway.secrets import GoogleCredentials

STRUCTURED_OUTPUT_MODEL_PREFIXES = (
    "gemini-2.5",
    "gemini-2.0",
    "gemini-1.5",
)

T = TypeVar("T")


def supports_structured_synthesis(model_id: str) -> bool:
    normalized = model_id.strip().lower()
    return any(normalized.startswith(prefix) for prefix in STRUCTURED_OUTPUT_MODEL_PREFIXES)


@dataclass
class GoogleAdapter:
    credentials: GoogleCredentials
    provider_id: str = "google"
    settings: AdapterRetrySettings = field(default_factory=AdapterRetrySettings)
    client: genai.Client | None = None
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.perf_counter

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not supports_structured_synthesis(request.model_id):
            raise GatewayValidationError(
                "Google model is not approved for strict structured synthesis"
            )

        started = self.monotonic()
        response = self._with_retries(
            lambda: self._generate_content(request),
            operation_name="models.generate_content",
        )
        latency_ms = max(int((self.monotonic() - started) * 1000), 0)
        return _normalize_generate_content_response(request, response, latency_ms=latency_ms)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        started = self.monotonic()
        response = self._with_retries(
            lambda: self._client().models.embed_content(
                model=request.model_id,
                contents=list(request.texts),
                config={"output_dimensionality": request.dimensions},
            ),
            operation_name="models.embed_content",
        )
        latency_ms = max(int((self.monotonic() - started) * 1000), 0)
        embeddings = getattr(response, "embeddings", None) or []
        vectors = tuple(
            tuple(float(value) for value in embedding.values)
            for embedding in embeddings
        )
        metadata = getattr(response, "metadata", None)
        token_count = int(getattr(metadata, "token_count", 0) or 0) if metadata else 0
        return EmbeddingResponse.from_vectors(
            request=request,
            provider_request_id=getattr(response, "response_id", None),
            vectors=vectors,
            input_tokens=token_count,
            total_tokens=token_count,
            latency_ms=latency_ms,
        )

    def health(self) -> ProviderHealth:
        started = self.monotonic()
        status = ProviderHealthStatus.HEALTHY
        safe_code: str | None = None
        try:
            self._with_retries(
                lambda: self._client().models.list(config={"page_size": 1}),
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

    def _generate_content(self, request: ModelRequest) -> GenerateContentResponse:
        return self._client().models.generate_content(
            model=request.model_id,
            contents=request.input,
            config={
                "system_instruction": request.system_instructions,
                "temperature": request.temperature,
                "max_output_tokens": request.max_output_tokens,
                "response_mime_type": "application/json",
                "response_json_schema": dict(request.output_schema),
                "labels": {
                    "vyu_request_id": request.request_id[:64],
                    "vyu_run_id": request.run_id[:64],
                },
            },
        )

    def _client(self) -> genai.Client:
        if self.client is not None:
            return self.client
        return genai.Client(api_key=self.credentials.api_key)

    def _with_retries(self, operation: Callable[[], T], *, operation_name: str) -> T:
        attempt = 0
        while True:
            attempt += 1
            try:
                return operation()
            except genai_errors.ClientError as exc:
                if exc.code == 429:
                    if attempt >= self.settings.max_attempts:
                        headers = getattr(getattr(exc, "response", None), "headers", None)
                        raise GatewayRateLimited(
                            "Google rate limit exceeded",
                            retry_after_seconds=retry_after_from_header(headers) if headers else None,
                        ) from exc
                    headers = getattr(getattr(exc, "response", None), "headers", None)
                    delay = (
                        retry_after_from_header(headers)
                        if headers is not None
                        else None
                    ) or backoff_seconds(attempt, settings=self.settings)
                    self.sleep(delay)
                    continue
                if exc.code in {401, 403}:
                    raise GatewayAuthenticationError("Google authentication failed") from exc
                if exc.code in {400, 422}:
                    raise GatewayValidationError(f"{operation_name} rejected the request") from exc
                raise GatewayUnavailable(f"{operation_name} failed") from exc
            except genai_errors.ServerError as exc:
                if attempt >= self.settings.max_attempts:
                    raise GatewayUnavailable(f"{operation_name} unavailable") from exc
                self.sleep(backoff_seconds(attempt, settings=self.settings))
            except TimeoutError as exc:
                if attempt >= self.settings.max_attempts:
                    raise GatewayTimeout(f"{operation_name} timed out") from exc
                self.sleep(backoff_seconds(attempt, settings=self.settings))


def _normalize_generate_content_response(
    request: ModelRequest,
    response: GenerateContentResponse,
    *,
    latency_ms: int,
) -> ModelResponse:
    prompt_feedback = response.prompt_feedback
    if prompt_feedback is not None and getattr(prompt_feedback, "block_reason", None):
        raise GatewayPolicyBlocked("provider blocked the request")

    candidates = response.candidates or []
    if not candidates:
        raise GatewayMalformedResponse("provider returned no candidates")

    candidate = candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)
    if finish_reason is not None and str(finish_reason).upper() in {"SAFETY", "RECITATION"}:
        raise GatewayPolicyBlocked("provider blocked the request")
    if finish_reason is not None and str(finish_reason).upper() == "MAX_TOKENS":
        raise GatewayMalformedResponse("provider returned incomplete output")

    content = getattr(candidate, "content", None)
    parts = getattr(content, "parts", None) if content is not None else None
    text_parts: list[str] = []
    if parts:
        for part in parts:
            text = getattr(part, "text", None)
            if isinstance(text, str):
                text_parts.append(text)
    output_text = "".join(text_parts).strip()
    if not output_text:
        raise GatewayMalformedResponse("provider returned empty structured output")

    try:
        output = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise GatewayMalformedResponse("provider returned non-json output") from exc
    if not isinstance(output, dict):
        raise GatewayMalformedResponse("provider structured output must be a JSON object")

    usage = response.usage_metadata
    input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0) if usage else 0
    output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0) if usage else 0
    cached_tokens = int(getattr(usage, "cached_content_token_count", 0) or 0) if usage else 0

    return ModelResponse.from_output(
        request=request,
        provider_request_id=response.response_id,
        output=output,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=0,
        cached_tokens=cached_tokens,
        latency_ms=latency_ms,
        finish_reason=_google_finish_reason(finish_reason),
        schema_valid=True,
    )


def _google_finish_reason(finish_reason: object | None) -> str:
    if finish_reason is None:
        return "unknown"
    normalized = str(finish_reason).upper()
    if normalized == "STOP":
        return "stop"
    return str(finish_reason).lower()
