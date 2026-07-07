from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    AzureOpenAI,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)
from openai.types.responses import Response

from src.vyu.model_gateway.adapters.openai_common import (
    normalize_openai_generation_response,
    schema_name,
    supports_openai_structured_synthesis,
    utc_now_iso,
)
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
    GatewayRateLimited,
    GatewayTimeout,
    GatewayUnavailable,
    GatewayValidationError,
)
from src.vyu.model_gateway.secrets import AzureOpenAICredentials

T = TypeVar("T")


@dataclass(frozen=True)
class AzureOpenAIAdapterSettings(AdapterRetrySettings):
    api_version: str = "2024-10-21"


def supports_structured_synthesis(model_id: str) -> bool:
    return supports_openai_structured_synthesis(model_id)


@dataclass
class AzureOpenAIAdapter:
    """Azure OpenAI adapter using the official OpenAI-compatible SDK surface."""

    credentials: AzureOpenAICredentials
    provider_id: str = "azure_openai"
    settings: AzureOpenAIAdapterSettings = field(default_factory=AzureOpenAIAdapterSettings)
    client: AzureOpenAI | None = None
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.perf_counter

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not supports_structured_synthesis(request.model_id):
            raise GatewayValidationError(
                "Azure OpenAI model is not approved for strict structured synthesis"
            )

        started = self.monotonic()
        response = self._with_retries(
            lambda: self._create_response(request),
            operation_name="responses.create",
        )
        latency_ms = max(int((self.monotonic() - started) * 1000), 0)
        return normalize_openai_generation_response(request, response, latency_ms=latency_ms)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        started = self.monotonic()
        response = self._with_retries(
            lambda: self._client().embeddings.create(
                model=self._deployment_name(request.model_id),
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
            checked_at=utc_now_iso(),
            latency_ms=latency_ms,
            safe_code=safe_code,
        )

    def _create_response(self, request: ModelRequest) -> Response:
        return self._client().responses.create(
            model=self._deployment_name(request.model_id),
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
                    "name": schema_name(request.prompt_template_id),
                    "schema": dict(request.output_schema),
                    "strict": True,
                }
            },
        )

    def _deployment_name(self, model_id: str) -> str:
        if self.credentials.deployment and self.credentials.deployment.strip():
            return self.credentials.deployment.strip()
        return model_id

    def _client(self) -> AzureOpenAI:
        if self.client is not None:
            return self.client
        return AzureOpenAI(
            api_version=self.settings.api_version,
            azure_endpoint=self.credentials.endpoint,
            api_key=self.credentials.api_key,
        )

    def _with_retries(self, operation: Callable[[], T], *, operation_name: str) -> T:
        attempt = 0
        while True:
            attempt += 1
            try:
                return operation()
            except RateLimitError as exc:
                if attempt >= self.settings.max_attempts:
                    raise GatewayRateLimited(
                        "Azure OpenAI rate limit exceeded",
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
                raise GatewayAuthenticationError("Azure OpenAI authentication failed") from exc
            except BadRequestError as exc:
                raise GatewayValidationError(f"{operation_name} rejected the request") from exc
