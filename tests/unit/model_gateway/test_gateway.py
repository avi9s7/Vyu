from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from uuid import uuid4

from src.vyu.model_gateway.contracts import (
    EmbeddingRequest,
    EmbeddingResponse,
    ModelPolicy,
    ModelRequest,
    ModelResponse,
    ProviderHealth,
    ProviderHealthStatus,
)
from src.vyu.model_gateway.errors import (
    GatewayMalformedResponse,
    GatewayPolicyBlocked,
    GatewayValidationError,
)
from src.vyu.model_gateway.gateway import ModelGateway


@dataclass
class FakeGenerationAdapter:
    provider_id: str = "deterministic"
    calls: list[ModelRequest] = field(default_factory=list)
    fail_schema: bool = False

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        return ModelResponse.from_output(
            request=request,
            provider_request_id="fake-provider-req",
            output={"answer_summary": "Supported by evidence."},
            input_tokens=12,
            output_tokens=6,
            latency_ms=9,
            finish_reason="stop",
            schema_valid=not self.fail_schema,
        )


@dataclass
class FakeEmbeddingAdapter:
    provider_id: str = "deterministic"
    calls: list[EmbeddingRequest] = field(default_factory=list)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self.calls.append(request)
        vectors = tuple((0.1, 0.2, 0.3) for _ in request.texts)
        return EmbeddingResponse.from_vectors(
            request=request,
            provider_request_id="fake-embed-req",
            vectors=vectors,
            input_tokens=len(request.texts),
            total_tokens=len(request.texts),
            latency_ms=4,
        )


@dataclass
class FakeProviderAdapter:
    provider_id: str = "deterministic"

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.provider_id,
            status=ProviderHealthStatus.HEALTHY,
            checked_at="2026-07-08T00:00:00+00:00",
            latency_ms=10,
        )


def _policy() -> ModelPolicy:
    return ModelPolicy(
        policy_version="model-policy-v1",
        allowed_providers=frozenset({"deterministic", "openai"}),
        allowed_models=frozenset({"vyu-deterministic-v1"}),
        allowed_use_cases=frozenset({"grounded_synthesis"}),
        allowed_prompt_versions=frozenset({"prompt-v1"}),
        max_output_tokens=1000,
        max_context_bytes=10_000,
        max_output_schema_properties=8,
    )


class ModelGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenant_id = uuid4()
        self.workspace_id = uuid4()
        self.generation = FakeGenerationAdapter()
        self.embedding = FakeEmbeddingAdapter()
        self.health = FakeProviderAdapter()
        self.gateway = ModelGateway(
            policy=_policy(),
            generation_adapters={self.generation.provider_id: self.generation},
            embedding_adapters={self.embedding.provider_id: self.embedding},
            health_adapters={self.health.provider_id: self.health},
        )

    def test_generate_routes_to_adapter_after_validation(self) -> None:
        response = self.gateway.generate(self._sample_request())
        self.assertEqual(1, len(self.generation.calls))
        self.assertTrue(response.schema_valid)
        self.assertEqual("fake-provider-req", response.provider_request_id)

    def test_generate_blocks_phi_before_adapter_call(self) -> None:
        request = self._sample_request(contains_phi=True)
        with self.assertRaises(GatewayPolicyBlocked):
            self.gateway.generate(request)
        self.assertEqual([], self.generation.calls)

    def test_generate_blocks_unapproved_model_before_adapter_call(self) -> None:
        request = self._sample_request(model_id="blocked-model")
        with self.assertRaises(GatewayPolicyBlocked):
            self.gateway.generate(request)
        self.assertEqual([], self.generation.calls)

    def test_generate_rejects_schema_invalid_response_without_fallback(self) -> None:
        self.generation.fail_schema = True
        with self.assertRaises(GatewayMalformedResponse):
            self.gateway.generate(self._sample_request())
        self.assertEqual(1, len(self.generation.calls))

    def test_embed_normalizes_usage_and_hashes(self) -> None:
        request = EmbeddingRequest(
            request_id="embed-1",
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            run_id="run-1",
            provider_id="deterministic",
            model_id="vyu-deterministic-v1",
            texts=("aspirin",),
            dimensions=1536,
            timeout_seconds=30,
            policy_version="model-policy-v1",
        )
        response = self.gateway.embed(request)
        self.assertEqual(1, len(self.embedding.calls))
        self.assertEqual(request.request_sha256(), response.request_sha256)
        self.assertEqual(1, len(response.vectors))

    def test_health_returns_provider_status(self) -> None:
        health = self.gateway.health("deterministic")
        self.assertEqual(ProviderHealthStatus.HEALTHY, health.status)

    def test_unknown_provider_raises_validation_error(self) -> None:
        with self.assertRaises(GatewayValidationError):
            self.gateway.generate(
                self._sample_request(provider_id="openai", model_id="vyu-deterministic-v1")
            )

    def _sample_request(
        self,
        *,
        provider_id: str = "deterministic",
        model_id: str = "vyu-deterministic-v1",
        contains_phi: bool = False,
    ) -> ModelRequest:
        return ModelRequest(
            request_id="req-1",
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            run_id="run-1",
            use_case="grounded_synthesis",
            provider_id=provider_id,
            model_id=model_id,
            prompt_template_id="grounded_answer_v1",
            prompt_version="prompt-v1",
            system_instructions="Answer using only provided evidence.",
            input='{"question":"aspirin efficacy"}',
            output_schema={"type": "object", "properties": {"answer_summary": {"type": "string"}}},
            max_output_tokens=500,
            timeout_seconds=30,
            temperature=0.0,
            evidence_context_sha256="abc123",
            policy_version="model-policy-v1",
            contains_phi=contains_phi,
        )


if __name__ == "__main__":
    unittest.main()
