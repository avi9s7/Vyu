from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping, Protocol, Sequence
from uuid import UUID

from src.vyu.research_mcp.hashing import stable_hash


class ProviderHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ModelPolicy:
    policy_version: str
    allowed_providers: frozenset[str]
    allowed_models: frozenset[str]
    allowed_use_cases: frozenset[str]
    allowed_prompt_versions: frozenset[str]
    max_input_tokens: int = 120_000
    max_output_tokens: int = 8_192
    max_context_bytes: int = 512_000
    max_output_schema_properties: int = 64

    def allows(
        self,
        *,
        provider_id: str,
        model_id: str,
        use_case: str,
        prompt_version: str,
    ) -> bool:
        return (
            provider_id in self.allowed_providers
            and model_id in self.allowed_models
            and use_case in self.allowed_use_cases
            and prompt_version in self.allowed_prompt_versions
        )


@dataclass(frozen=True)
class ModelRequest:
    request_id: str
    tenant_id: UUID
    workspace_id: UUID
    run_id: str
    use_case: str
    provider_id: str
    model_id: str
    prompt_template_id: str
    prompt_version: str
    system_instructions: str
    input: str
    output_schema: dict[str, Any]
    max_output_tokens: int
    timeout_seconds: int
    temperature: float
    evidence_context_sha256: str
    policy_version: str
    contains_phi: bool = False

    def request_sha256(self) -> str:
        return stable_hash(
            {
                "request_id": self.request_id,
                "tenant_id": str(self.tenant_id),
                "workspace_id": str(self.workspace_id),
                "run_id": self.run_id,
                "use_case": self.use_case,
                "provider_id": self.provider_id,
                "model_id": self.model_id,
                "prompt_template_id": self.prompt_template_id,
                "prompt_version": self.prompt_version,
                "system_instructions": self.system_instructions,
                "input": self.input,
                "output_schema": self.output_schema,
                "max_output_tokens": self.max_output_tokens,
                "timeout_seconds": self.timeout_seconds,
                "temperature": self.temperature,
                "evidence_context_sha256": self.evidence_context_sha256,
                "policy_version": self.policy_version,
                "contains_phi": self.contains_phi,
            }
        )


@dataclass(frozen=True)
class ModelResponse:
    provider_id: str
    model_id: str
    provider_request_id: str | None
    output: dict[str, Any]
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cached_tokens: int
    latency_ms: int
    finish_reason: str
    request_sha256: str
    response_sha256: str
    schema_valid: bool
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_output(
        cls,
        *,
        request: ModelRequest,
        provider_request_id: str | None,
        output: dict[str, Any],
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int = 0,
        cached_tokens: int = 0,
        latency_ms: int,
        finish_reason: str,
        schema_valid: bool,
    ) -> "ModelResponse":
        response_sha256 = stable_hash(output)
        return cls(
            provider_id=request.provider_id,
            model_id=request.model_id,
            provider_request_id=provider_request_id,
            output=output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_tokens=cached_tokens,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            request_sha256=request.request_sha256(),
            response_sha256=response_sha256,
            schema_valid=schema_valid,
        )


@dataclass(frozen=True)
class EmbeddingRequest:
    request_id: str
    tenant_id: UUID
    workspace_id: UUID
    run_id: str
    provider_id: str
    model_id: str
    texts: tuple[str, ...]
    dimensions: int
    timeout_seconds: int
    policy_version: str
    contains_phi: bool = False

    def text_hashes(self) -> tuple[str, ...]:
        import hashlib

        return tuple(hashlib.sha256(text.encode("utf-8")).hexdigest() for text in self.texts)

    def request_sha256(self) -> str:
        return stable_hash(
            {
                "request_id": self.request_id,
                "tenant_id": str(self.tenant_id),
                "workspace_id": str(self.workspace_id),
                "run_id": self.run_id,
                "provider_id": self.provider_id,
                "model_id": self.model_id,
                "text_hashes": list(self.text_hashes()),
                "dimensions": self.dimensions,
                "timeout_seconds": self.timeout_seconds,
                "policy_version": self.policy_version,
                "contains_phi": self.contains_phi,
            }
        )


@dataclass(frozen=True)
class EmbeddingResponse:
    provider_id: str
    model_id: str
    provider_request_id: str | None
    text_hashes: tuple[str, ...]
    vectors: tuple[tuple[float, ...], ...]
    dimensions: int
    input_tokens: int
    total_tokens: int
    latency_ms: int
    request_sha256: str
    response_sha256: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_vectors(
        cls,
        *,
        request: EmbeddingRequest,
        provider_request_id: str | None,
        vectors: Sequence[Sequence[float]],
        input_tokens: int,
        total_tokens: int,
        latency_ms: int,
    ) -> "EmbeddingResponse":
        vector_payload = [list(vector) for vector in vectors]
        return cls(
            provider_id=request.provider_id,
            model_id=request.model_id,
            provider_request_id=provider_request_id,
            text_hashes=request.text_hashes(),
            vectors=tuple(tuple(float(value) for value in vector) for vector in vectors),
            dimensions=request.dimensions,
            input_tokens=input_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            request_sha256=request.request_sha256(),
            response_sha256=stable_hash(vector_payload),
        )


@dataclass(frozen=True)
class ProviderHealth:
    provider_id: str
    status: ProviderHealthStatus
    checked_at: str
    latency_ms: int | None = None
    safe_code: str | None = None


class GenerationAdapter(Protocol):
    provider_id: str

    def generate(self, request: ModelRequest) -> ModelResponse:
        ...


class EmbeddingAdapter(Protocol):
    provider_id: str

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        ...


class ProviderAdapter(Protocol):
    provider_id: str

    def health(self) -> ProviderHealth:
        ...


def count_schema_properties(schema: Mapping[str, Any]) -> int:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return 0
    total = len(properties)
    for value in properties.values():
        if isinstance(value, dict) and value.get("type") == "object":
            nested = value.get("properties")
            if isinstance(nested, dict):
                total += len(nested)
    return total
