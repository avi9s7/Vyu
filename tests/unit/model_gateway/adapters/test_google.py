from __future__ import annotations

import json
import unittest
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx
from google.genai import errors as genai_errors
from google.genai.types import GenerateContentResponse

from src.vyu.model_gateway.adapters.google import GoogleAdapter
from src.vyu.model_gateway.adapters.retry import AdapterRetrySettings
from src.vyu.model_gateway.contracts import EmbeddingRequest, ModelRequest
from src.vyu.model_gateway.errors import (
    GatewayAuthenticationError,
    GatewayPolicyBlocked,
    GatewayRateLimited,
    GatewayValidationError,
)
from src.vyu.model_gateway.secrets import GoogleCredentials


def _sample_request(**overrides: object) -> ModelRequest:
    tenant_id = uuid4()
    workspace_id = uuid4()
    base = {
        "request_id": "req-google-001",
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "run_id": "run-001",
        "use_case": "grounded_synthesis",
        "provider_id": "google",
        "model_id": "gemini-2.0-flash-001",
        "prompt_template_id": "grounded_answer_v1",
        "prompt_version": "grounded_answer_v1.0",
        "system_instructions": "Return only grounded claims.",
        "input": "Summarize the evidence.",
        "output_schema": {
            "type": "object",
            "properties": {
                "answer_summary": {"type": "string"},
                "claims": {"type": "array"},
            },
            "required": ["answer_summary", "claims"],
            "additionalProperties": False,
        },
        "max_output_tokens": 512,
        "timeout_seconds": 30,
        "temperature": 0.0,
        "evidence_context_sha256": "abc123",
        "policy_version": "model-policy-v1",
    }
    base.update(overrides)
    return ModelRequest(**base)  # type: ignore[arg-type]


def _success_response() -> GenerateContentResponse:
    return GenerateContentResponse.model_validate(
        {
            "response_id": "resp_google_001",
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "answer_summary": "Supported by evidence.",
                                        "claims": [],
                                    }
                                )
                            }
                        ]
                    },
                    "finish_reason": "STOP",
                }
            ],
            "usage_metadata": {
                "prompt_token_count": 25,
                "candidates_token_count": 10,
                "cached_content_token_count": 1,
            },
        }
    )


def _blocked_response() -> GenerateContentResponse:
    return GenerateContentResponse.model_validate(
        {
            "response_id": "resp_google_blocked",
            "prompt_feedback": {"block_reason": "SAFETY"},
            "candidates": [],
        }
    )


@dataclass
class FakeModelsAPI:
    generate_handler: Any
    embed_handler: Any
    list_handler: Any
    generate_calls: list[dict[str, Any]] = field(default_factory=list)
    embed_calls: list[dict[str, Any]] = field(default_factory=list)

    def generate_content(self, **kwargs: Any) -> GenerateContentResponse:
        self.generate_calls.append(kwargs)
        return self.generate_handler(kwargs)

    def embed_content(self, **kwargs: Any) -> object:
        self.embed_calls.append(kwargs)
        return self.embed_handler(kwargs)

    def list(self, **kwargs: Any) -> object:
        return self.list_handler(kwargs)


@dataclass
class FakeGoogleClient:
    models: FakeModelsAPI


def _adapter(
    *,
    generate_handler: Any,
    embed_handler: Any | None = None,
    max_attempts: int = 3,
) -> tuple[GoogleAdapter, FakeGoogleClient]:
    client = FakeGoogleClient(
        models=FakeModelsAPI(
            generate_handler=generate_handler,
            embed_handler=embed_handler
            or (
                lambda _kwargs: type(
                    "EmbedResponse",
                    (),
                    {
                        "embeddings": [type("Embedding", (), {"values": [0.1, 0.2, 0.3]})()],
                        "metadata": type("Metadata", (), {"token_count": 4})(),
                        "response_id": "embed_google_001",
                    },
                )()
            ),
            list_handler=lambda _kwargs: object(),
        )
    )
    adapter = GoogleAdapter(
        credentials=GoogleCredentials(api_key="google-test-key"),
        client=client,  # type: ignore[arg-type]
        settings=AdapterRetrySettings(max_attempts=max_attempts),
        sleep=lambda _seconds: None,
    )
    return adapter, client


class GoogleAdapterContractTests(unittest.TestCase):
    def test_generate_success_normalizes_usage_and_request_id(self) -> None:
        adapter, client = _adapter(generate_handler=lambda _kwargs: _success_response())
        response = adapter.generate(_sample_request())
        self.assertEqual(response.provider_request_id, "resp_google_001")
        self.assertEqual(response.input_tokens, 25)
        self.assertEqual(response.output_tokens, 10)
        self.assertEqual(response.cached_tokens, 1)
        config = client.models.generate_calls[0]["config"]
        self.assertEqual(config["response_mime_type"], "application/json")
        self.assertIn("response_json_schema", config)

    def test_generate_maps_safety_block_to_policy_blocked(self) -> None:
        adapter, _client = _adapter(generate_handler=lambda _kwargs: _blocked_response())
        with self.assertRaises(GatewayPolicyBlocked):
            adapter.generate(_sample_request())

    def test_generate_rejects_unapproved_model(self) -> None:
        adapter, _client = _adapter(generate_handler=lambda _kwargs: _success_response())
        with self.assertRaises(GatewayValidationError):
            adapter.generate(_sample_request(model_id="gemini-1.0-pro"))

    def test_generate_maps_authentication_failure(self) -> None:
        def handler(_kwargs: dict[str, Any]) -> GenerateContentResponse:
            request = httpx.Request("POST", "https://generativelanguage.googleapis.com")
            response = httpx.Response(401, request=request, json={"error": {"code": 401}})
            raise genai_errors.ClientError(401, {"error": {"code": 401}}, response)

        adapter, _client = _adapter(generate_handler=handler)
        with self.assertRaises(GatewayAuthenticationError):
            adapter.generate(_sample_request())

    def test_generate_retries_rate_limit(self) -> None:
        attempts = {"count": 0}
        sleeps: list[float] = []

        def handler(_kwargs: dict[str, Any]) -> GenerateContentResponse:
            attempts["count"] += 1
            if attempts["count"] == 1:
                request = httpx.Request("POST", "https://generativelanguage.googleapis.com")
                response = httpx.Response(
                    429,
                    request=request,
                    headers={"retry-after": "1.5"},
                    json={"error": {"code": 429}},
                )
                raise genai_errors.ClientError(429, {"error": {"code": 429}}, response)
            return _success_response()

        adapter, _client = _adapter(generate_handler=handler)
        adapter.sleep = sleeps.append  # type: ignore[method-assign]
        response = adapter.generate(_sample_request())
        self.assertEqual(response.provider_request_id, "resp_google_001")
        self.assertEqual(sleeps, [1.5])

    def test_generate_exhausted_rate_limit_raises_gateway_rate_limited(self) -> None:
        def handler(_kwargs: dict[str, Any]) -> GenerateContentResponse:
            request = httpx.Request("POST", "https://generativelanguage.googleapis.com")
            response = httpx.Response(
                429,
                request=request,
                headers={"retry-after": "4"},
                json={"error": {"code": 429}},
            )
            raise genai_errors.ClientError(429, {"error": {"code": 429}}, response)

        adapter, _client = _adapter(generate_handler=handler, max_attempts=1)
        with self.assertRaises(GatewayRateLimited) as ctx:
            adapter.generate(_sample_request())
        self.assertEqual(ctx.exception.retry_after_seconds, 4.0)

    def test_embed_normalizes_vectors(self) -> None:
        adapter, client = _adapter(generate_handler=lambda _kwargs: _success_response())
        response = adapter.embed(
            EmbeddingRequest(
                request_id="embed-google-001",
                tenant_id=uuid4(),
                workspace_id=uuid4(),
                run_id="run-001",
                provider_id="google",
                model_id="text-embedding-004",
                texts=("first passage",),
                dimensions=1536,
                timeout_seconds=30,
                policy_version="model-policy-v1",
            )
        )
        self.assertEqual(response.vectors[0], (0.1, 0.2, 0.3))
        self.assertEqual(client.models.embed_calls[0]["model"], "text-embedding-004")


if __name__ == "__main__":
    unittest.main()
