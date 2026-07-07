from __future__ import annotations

import unittest
from uuid import uuid4

from src.vyu.model_gateway.contracts import (
    EmbeddingRequest,
    EmbeddingResponse,
    ModelPolicy,
    ModelRequest,
    ModelResponse,
    ProviderHealth,
    ProviderHealthStatus,
    count_schema_properties,
)


class ModelGatewayContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenant_id = uuid4()
        self.workspace_id = uuid4()

    def test_model_request_hash_is_stable(self) -> None:
        request = self._sample_request()
        self.assertEqual(request.request_sha256(), request.request_sha256())

    def test_model_response_records_hashes(self) -> None:
        request = self._sample_request()
        response = ModelResponse.from_output(
            request=request,
            provider_request_id="req-123",
            output={"answer_summary": "Evidence supports aspirin use."},
            input_tokens=10,
            output_tokens=5,
            latency_ms=12,
            finish_reason="stop",
            schema_valid=True,
        )
        self.assertEqual(request.request_sha256(), response.request_sha256)
        self.assertTrue(response.response_sha256)

    def test_embedding_request_and_response_hashes(self) -> None:
        request = EmbeddingRequest(
            request_id="embed-1",
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            run_id="run-1",
            provider_id="deterministic",
            model_id="vyu-deterministic-v1",
            texts=("aspirin", "efficacy"),
            dimensions=1536,
            timeout_seconds=30,
            policy_version="model-policy-v1",
        )
        response = EmbeddingResponse.from_vectors(
            request=request,
            provider_request_id="embed-req-1",
            vectors=([0.1, 0.2], [0.3, 0.4]),
            input_tokens=4,
            total_tokens=4,
            latency_ms=3,
        )
        self.assertEqual(request.request_sha256(), response.request_sha256)
        self.assertEqual(("aspirin", "efficacy"), request.texts)
        self.assertEqual(2, len(response.vectors))

    def test_model_policy_allows_approved_combination(self) -> None:
        policy = ModelPolicy(
            policy_version="model-policy-v1",
            allowed_providers=frozenset({"openai"}),
            allowed_models=frozenset({"gpt-test"}),
            allowed_use_cases=frozenset({"grounded_synthesis"}),
            allowed_prompt_versions=frozenset({"prompt-v1"}),
        )
        self.assertTrue(
            policy.allows(
                provider_id="openai",
                model_id="gpt-test",
                use_case="grounded_synthesis",
                prompt_version="prompt-v1",
            )
        )
        self.assertFalse(
            policy.allows(
                provider_id="openai",
                model_id="gpt-test",
                use_case="grounded_synthesis",
                prompt_version="prompt-v2",
            )
        )

    def test_count_schema_properties_includes_nested_fields(self) -> None:
        total = count_schema_properties(
            {
                "type": "object",
                "properties": {
                    "answer_summary": {"type": "string"},
                    "claims": {
                        "type": "object",
                        "properties": {
                            "claim_text": {"type": "string"},
                            "citation_ids": {"type": "array"},
                        },
                    },
                },
            }
        )
        self.assertEqual(4, total)

    def test_provider_health_contract(self) -> None:
        health = ProviderHealth(
            provider_id="openai",
            status=ProviderHealthStatus.HEALTHY,
            checked_at="2026-07-08T00:00:00+00:00",
            latency_ms=25,
        )
        self.assertEqual(ProviderHealthStatus.HEALTHY, health.status)

    def _sample_request(self) -> ModelRequest:
        return ModelRequest(
            request_id="req-1",
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            run_id="run-1",
            use_case="grounded_synthesis",
            provider_id="openai",
            model_id="gpt-test",
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
        )


if __name__ == "__main__":
    unittest.main()
