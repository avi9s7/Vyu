from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from src.vyu.retrieval.index_contracts import (
    APPROVED_EMBEDDING_DIMENSIONS,
    EmbeddingDimensionMismatchError,
)


@dataclass(frozen=True)
class EmbeddingUsage:
    prompt_tokens: int
    total_tokens: int

    def to_json(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "total_tokens": self.total_tokens,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "EmbeddingUsage":
        return cls(
            prompt_tokens=int(payload.get("prompt_tokens", 0)),
            total_tokens=int(payload.get("total_tokens", 0)),
        )


@dataclass(frozen=True)
class EmbeddingVector:
    text_sha256: str
    values: tuple[float, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "text_sha256": self.text_sha256,
            "values": list(self.values),
        }


@dataclass(frozen=True)
class EmbeddingBatch:
    provider: str
    model: str
    provider_version: str
    dimensions: int
    input_hashes: tuple[str, ...]
    vectors: tuple[EmbeddingVector, ...]
    usage: EmbeddingUsage
    latency_ms: int
    provider_request_id: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "provider_version": self.provider_version,
            "dimensions": self.dimensions,
            "input_hashes": list(self.input_hashes),
            "vectors": [vector.to_json() for vector in self.vectors],
            "usage": self.usage.to_json(),
            "latency_ms": self.latency_ms,
            "provider_request_id": self.provider_request_id,
        }


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embedding_cache_key(
    *,
    text_sha256_value: str,
    provider: str,
    model: str,
    dimensions: int,
) -> str:
    return stable_embedding_cache_key(text_sha256_value, provider, model, dimensions)


def stable_embedding_cache_key(
    text_sha256_value: str,
    provider: str,
    model: str,
    dimensions: int,
) -> str:
    return hashlib.sha256(
        f"{text_sha256_value}:{provider}:{model}:{dimensions}".encode("utf-8")
    ).hexdigest()


def validate_embedding_dimensions(dimensions: int) -> None:
    if dimensions != APPROVED_EMBEDDING_DIMENSIONS:
        raise EmbeddingDimensionMismatchError(
            f"embedding dimensions {dimensions} do not match approved "
            f"dimension {APPROVED_EMBEDDING_DIMENSIONS}"
        )


class EmbeddingProvider(Protocol):
    provider: str
    provider_version: str

    def embed(
        self,
        texts: Sequence[str],
        *,
        model: str,
        dimensions: int = APPROVED_EMBEDDING_DIMENSIONS,
    ) -> EmbeddingBatch:
        ...


@dataclass
class DeterministicEmbeddingProvider:
    """Test and replay adapter that derives stable vectors from text hashes."""

    provider: str = "deterministic"
    provider_version: str = "1.0.0"
    default_model: str = "vyu-deterministic-v1"

    def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        dimensions: int = APPROVED_EMBEDDING_DIMENSIONS,
    ) -> EmbeddingBatch:
        validate_embedding_dimensions(dimensions)
        resolved_model = model or self.default_model
        started = time.perf_counter()
        input_hashes = tuple(text_sha256(text) for text in texts)
        vectors: list[EmbeddingVector] = []
        for text_hash in input_hashes:
            values = _deterministic_vector(text_hash, dimensions)
            vectors.append(EmbeddingVector(text_sha256=text_hash, values=values))
        latency_ms = int((time.perf_counter() - started) * 1000)
        token_estimate = sum(max(1, len(text.split())) for text in texts)
        return EmbeddingBatch(
            provider=self.provider,
            model=resolved_model,
            provider_version=self.provider_version,
            dimensions=dimensions,
            input_hashes=input_hashes,
            vectors=tuple(vectors),
            usage=EmbeddingUsage(prompt_tokens=token_estimate, total_tokens=token_estimate),
            latency_ms=latency_ms,
            provider_request_id=f"deterministic-{input_hashes[0][:12]}" if input_hashes else None,
        )


def _deterministic_vector(text_hash: str, dimensions: int) -> tuple[float, ...]:
    values: list[float] = []
    seed = text_hash
    while len(values) < dimensions:
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        for offset in range(0, len(digest), 8):
            chunk = digest[offset : offset + 8]
            if len(chunk) < 8:
                break
            value = (int(chunk, 16) / float(0xFFFFFFFF)) * 2.0 - 1.0
            values.append(value)
            if len(values) >= dimensions:
                break
        seed = digest
    norm = sum(value * value for value in values) ** 0.5 or 1.0
    return tuple(value / norm for value in values)
