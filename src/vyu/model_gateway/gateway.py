from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping

from src.vyu.model_gateway.contracts import (
    EmbeddingAdapter,
    EmbeddingRequest,
    EmbeddingResponse,
    GenerationAdapter,
    ModelPolicy,
    ModelRequest,
    ModelResponse,
    ProviderAdapter,
    ProviderHealth,
    ProviderHealthStatus,
    count_schema_properties,
)
from src.vyu.model_gateway.errors import (
    GatewayMalformedResponse,
    GatewayPolicyBlocked,
    GatewayValidationError,
)


@dataclass
class ModelGateway:
    """Provider-neutral gateway that validates policy before adapter calls."""

    policy: ModelPolicy
    generation_adapters: Mapping[str, GenerationAdapter] = field(default_factory=dict)
    embedding_adapters: Mapping[str, EmbeddingAdapter] = field(default_factory=dict)
    health_adapters: Mapping[str, ProviderAdapter] = field(default_factory=dict)

    def generate(self, request: ModelRequest) -> ModelResponse:
        self._validate_generation_request(request)
        adapter = self._generation_adapter(request.provider_id)
        response = adapter.generate(request)
        if not response.schema_valid:
            raise GatewayMalformedResponse("provider returned schema-invalid output")
        if response.request_sha256 != request.request_sha256():
            raise GatewayMalformedResponse("provider response request hash mismatch")
        return response

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self._validate_embedding_request(request)
        adapter = self._embedding_adapter(request.provider_id)
        response = adapter.embed(request)
        if response.request_sha256 != request.request_sha256():
            raise GatewayMalformedResponse("provider embedding request hash mismatch")
        if len(response.vectors) != len(request.texts):
            raise GatewayMalformedResponse("provider embedding vector count mismatch")
        return response

    def health(self, provider_id: str) -> ProviderHealth:
        adapter = self.health_adapters.get(provider_id)
        if adapter is None:
            generation = self.generation_adapters.get(provider_id)
            if generation is not None:
                return ProviderHealth(
                    provider_id=provider_id,
                    status=ProviderHealthStatus.HEALTHY,
                    checked_at=datetime.now(timezone.utc).isoformat(),
                    latency_ms=0,
                )
            raise GatewayValidationError(f"unknown provider: {provider_id}")
        return adapter.health()

    def _validate_generation_request(self, request: ModelRequest) -> None:
        if request.contains_phi:
            raise GatewayPolicyBlocked("generation requests must not contain PHI")
        if not self.policy.allows(
            provider_id=request.provider_id,
            model_id=request.model_id,
            use_case=request.use_case,
            prompt_version=request.prompt_version,
        ):
            raise GatewayPolicyBlocked("provider, model, use case, or prompt is not approved")
        if request.max_output_tokens > self.policy.max_output_tokens:
            raise GatewayValidationError("max_output_tokens exceeds policy limit")
        if len(request.input.encode("utf-8")) > self.policy.max_context_bytes:
            raise GatewayValidationError("input exceeds policy context size")
        if count_schema_properties(request.output_schema) > self.policy.max_output_schema_properties:
            raise GatewayValidationError("output schema exceeds property limit")
        if not request.output_schema:
            raise GatewayValidationError("output schema is required")

    def _validate_embedding_request(self, request: EmbeddingRequest) -> None:
        if request.contains_phi:
            raise GatewayPolicyBlocked("embedding requests must not contain PHI")
        if request.provider_id not in self.policy.allowed_providers:
            raise GatewayPolicyBlocked("embedding provider is not approved")
        if request.model_id not in self.policy.allowed_models:
            raise GatewayPolicyBlocked("embedding model is not approved")
        if not request.texts:
            raise GatewayValidationError("at least one embedding text is required")
        if request.dimensions <= 0:
            raise GatewayValidationError("embedding dimensions must be positive")

    def _generation_adapter(self, provider_id: str) -> GenerationAdapter:
        adapter = self.generation_adapters.get(provider_id)
        if adapter is None:
            raise GatewayValidationError(f"no generation adapter registered for {provider_id}")
        return adapter

    def _embedding_adapter(self, provider_id: str) -> EmbeddingAdapter:
        adapter = self.embedding_adapters.get(provider_id)
        if adapter is None:
            raise GatewayValidationError(f"no embedding adapter registered for {provider_id}")
        return adapter
