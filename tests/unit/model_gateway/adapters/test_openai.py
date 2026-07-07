from __future__ import annotations

import json
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from openai import (
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)
from openai.types.create_embedding_response import CreateEmbeddingResponse
from openai.types.responses import Response

from src.vyu.model_gateway.adapters.openai import (
    OpenAIAdapter,
    OpenAIAdapterSettings,
    supports_structured_synthesis,
)
from src.vyu.model_gateway.contracts import EmbeddingRequest, ModelRequest
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

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "model_gateway" / "openai"


@dataclass
class FakeResponsesAPI:
    handler: Any
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> Response:
        self.calls.append(kwargs)
        return self.handler(kwargs)


@dataclass
class FakeEmbeddingsAPI:
    handler: Any
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> CreateEmbeddingResponse:
        self.calls.append(kwargs)
        return self.handler(kwargs)


@dataclass
class FakeModelsAPI:
    handler: Any
    calls: list[dict[str, Any]] = field(default_factory=list)

    def list(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return self.handler(kwargs)


@dataclass
class FakeOpenAIClient:
    responses: FakeResponsesAPI
    embeddings: FakeEmbeddingsAPI
    models: FakeModelsAPI


def _load_response(name: str) -> Response:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return Response.model_validate(payload)


def _load_embedding(name: str) -> CreateEmbeddingResponse:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return CreateEmbeddingResponse.model_validate(payload)


def _sample_request(**overrides: object) -> ModelRequest:
    tenant_id = uuid4()
    workspace_id = uuid4()
    base = {
        "request_id": "req-openai-001",
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "run_id": "run-001",
        "use_case": "grounded_synthesis",
        "provider_id": "openai",
        "model_id": "gpt-4o-2024-08-06",
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


def _sample_embedding_request(**overrides: object) -> EmbeddingRequest:
    tenant_id = uuid4()
    workspace_id = uuid4()
    base = {
        "request_id": "embed-openai-001",
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "run_id": "run-001",
        "provider_id": "openai",
        "model_id": "text-embedding-3-small",
        "texts": ("first passage", "second passage"),
        "dimensions": 1536,
        "timeout_seconds": 30,
        "policy_version": "model-policy-v1",
    }
    base.update(overrides)
    return EmbeddingRequest(**base)  # type: ignore[arg-type]


def _adapter(
    *,
    responses_handler: Any,
    embeddings_handler: Any | None = None,
    models_handler: Any | None = None,
    settings: OpenAIAdapterSettings | None = None,
    sleep: Any | None = None,
) -> tuple[OpenAIAdapter, FakeOpenAIClient]:
    client = FakeOpenAIClient(
        responses=FakeResponsesAPI(responses_handler),
        embeddings=FakeEmbeddingsAPI(
            embeddings_handler
            or (lambda _kwargs: _load_embedding("embedding_success.json"))
        ),
        models=FakeModelsAPI(models_handler or (lambda _kwargs: object())),
    )
    adapter = OpenAIAdapter(
        credentials=OpenAICredentials(api_key="sk-test-key"),
        client=client,  # type: ignore[arg-type]
        settings=settings or OpenAIAdapterSettings(max_attempts=3),
        sleep=sleep or (lambda _seconds: None),
    )
    return adapter, client


class OpenAIAdapterContractTests(unittest.TestCase):
    def test_supports_structured_synthesis_for_approved_models(self) -> None:
        self.assertTrue(supports_structured_synthesis("gpt-4o-2024-08-06"))
        self.assertFalse(supports_structured_synthesis("gpt-3.5-turbo"))

    def test_generate_success_normalizes_usage_and_request_id(self) -> None:
        adapter, client = _adapter(
            responses_handler=lambda _kwargs: _load_response("response_success.json"),
        )
        response = adapter.generate(_sample_request())

        self.assertEqual(response.provider_request_id, "resp_success_001")
        self.assertEqual(response.input_tokens, 42)
        self.assertEqual(response.output_tokens, 18)
        self.assertEqual(response.reasoning_tokens, 2)
        self.assertEqual(response.cached_tokens, 3)
        self.assertEqual(response.finish_reason, "stop")
        self.assertTrue(response.schema_valid)
        self.assertEqual(
            response.output["answer_summary"],
            "Supported by evidence.",
        )
        create_kwargs = client.responses.calls[0]
        self.assertNotIn("tools", create_kwargs)
        self.assertEqual(create_kwargs["model"], "gpt-4o-2024-08-06")
        self.assertEqual(create_kwargs["metadata"]["vyu_request_id"], "req-openai-001")
        self.assertEqual(create_kwargs["text"]["format"]["strict"], True)

    def test_generate_rejects_unapproved_model(self) -> None:
        adapter, _client = _adapter(
            responses_handler=lambda _kwargs: _load_response("response_success.json"),
        )
        with self.assertRaises(GatewayValidationError):
            adapter.generate(_sample_request(model_id="gpt-3.5-turbo"))

    def test_generate_maps_refusal_to_policy_blocked(self) -> None:
        adapter, _client = _adapter(
            responses_handler=lambda _kwargs: _load_response("response_refusal.json"),
        )
        with self.assertRaises(GatewayPolicyBlocked):
            adapter.generate(_sample_request())

    def test_generate_maps_incomplete_output_to_malformed_response(self) -> None:
        adapter, _client = _adapter(
            responses_handler=lambda _kwargs: _load_response("response_incomplete.json"),
        )
        with self.assertRaises(GatewayMalformedResponse) as ctx:
            adapter.generate(_sample_request())
        self.assertIn("incomplete", str(ctx.exception).lower())

    def test_generate_maps_invalid_json_to_malformed_response(self) -> None:
        adapter, _client = _adapter(
            responses_handler=lambda _kwargs: _load_response("response_invalid_json.json"),
        )
        with self.assertRaises(GatewayMalformedResponse):
            adapter.generate(_sample_request())

    def test_generate_maps_schema_request_failure_without_retry(self) -> None:
        attempts = {"count": 0}

        def handler(_kwargs: dict[str, Any]) -> Response:
            attempts["count"] += 1
            request = httpx.Request("POST", "https://api.openai.com/v1/responses")
            response = httpx.Response(400, request=request)
            raise BadRequestError("invalid schema", response=response, body={"error": "schema"})

        adapter, _client = _adapter(responses_handler=handler)
        with self.assertRaises(GatewayValidationError):
            adapter.generate(_sample_request())
        self.assertEqual(attempts["count"], 1)

    def test_generate_retries_rate_limit_then_succeeds(self) -> None:
        attempts = {"count": 0}
        sleeps: list[float] = []

        def handler(_kwargs: dict[str, Any]) -> Response:
            attempts["count"] += 1
            if attempts["count"] == 1:
                request = httpx.Request("POST", "https://api.openai.com/v1/responses")
                response = httpx.Response(429, request=request, headers={"retry-after": "1.5"})
                raise RateLimitError("rate limited", response=response, body=None)
            return _load_response("response_success.json")

        adapter, _client = _adapter(
            responses_handler=handler,
            sleep=sleeps.append,
        )
        response = adapter.generate(_sample_request())
        self.assertEqual(attempts["count"], 2)
        self.assertEqual(sleeps, [1.5])
        self.assertEqual(response.provider_request_id, "resp_success_001")

    def test_generate_maps_timeout_after_retries(self) -> None:
        attempts = {"count": 0}

        def handler(_kwargs: dict[str, Any]) -> Response:
            attempts["count"] += 1
            request = httpx.Request("POST", "https://api.openai.com/v1/responses")
            raise APITimeoutError(request=request)

        adapter, _client = _adapter(
            responses_handler=handler,
            settings=OpenAIAdapterSettings(max_attempts=2),
        )
        with self.assertRaises(GatewayTimeout):
            adapter.generate(_sample_request())
        self.assertEqual(attempts["count"], 2)

    def test_generate_maps_internal_server_error_to_unavailable(self) -> None:
        attempts = {"count": 0}

        def handler(_kwargs: dict[str, Any]) -> Response:
            attempts["count"] += 1
            request = httpx.Request("POST", "https://api.openai.com/v1/responses")
            response = httpx.Response(500, request=request)
            raise InternalServerError("server error", response=response, body=None)

        adapter, _client = _adapter(
            responses_handler=handler,
            settings=OpenAIAdapterSettings(max_attempts=2),
        )
        with self.assertRaises(GatewayUnavailable):
            adapter.generate(_sample_request())
        self.assertEqual(attempts["count"], 2)

    def test_generate_maps_authentication_failure_without_retry(self) -> None:
        attempts = {"count": 0}

        def handler(_kwargs: dict[str, Any]) -> Response:
            attempts["count"] += 1
            request = httpx.Request("POST", "https://api.openai.com/v1/responses")
            response = httpx.Response(401, request=request)
            raise AuthenticationError("invalid api key sk-secret-value", response=response, body=None)

        adapter, _client = _adapter(responses_handler=handler)
        with self.assertRaises(GatewayAuthenticationError) as ctx:
            adapter.generate(_sample_request())
        self.assertEqual(attempts["count"], 1)
        self.assertNotIn("sk-secret-value", str(ctx.exception))

    def test_generate_exhausted_rate_limit_raises_gateway_rate_limited(self) -> None:
        def handler(_kwargs: dict[str, Any]) -> Response:
            request = httpx.Request("POST", "https://api.openai.com/v1/responses")
            response = httpx.Response(429, request=request, headers={"retry-after": "2"})
            raise RateLimitError("rate limited", response=response, body=None)

        adapter, _client = _adapter(
            responses_handler=handler,
            settings=OpenAIAdapterSettings(max_attempts=1),
        )
        with self.assertRaises(GatewayRateLimited) as ctx:
            adapter.generate(_sample_request())
        self.assertEqual(ctx.exception.retry_after_seconds, 2.0)

    def test_embed_normalizes_vectors_and_usage(self) -> None:
        adapter, client = _adapter(
            responses_handler=lambda _kwargs: _load_response("response_success.json"),
            embeddings_handler=lambda _kwargs: _load_embedding("embedding_success.json"),
        )
        response = adapter.embed(_sample_embedding_request())

        self.assertEqual(len(response.vectors), 2)
        self.assertEqual(response.vectors[0], (0.1, 0.2, 0.3))
        self.assertEqual(response.input_tokens, 8)
        self.assertEqual(response.total_tokens, 8)
        embed_kwargs = client.embeddings.calls[0]
        self.assertEqual(embed_kwargs["model"], "text-embedding-3-small")
        self.assertEqual(embed_kwargs["dimensions"], 1536)

    def test_health_reports_authentication_failure(self) -> None:
        def models_handler(_kwargs: dict[str, Any]) -> object:
            request = httpx.Request("GET", "https://api.openai.com/v1/models")
            response = httpx.Response(401, request=request)
            raise AuthenticationError("invalid api key", response=response, body=None)

        adapter, _client = _adapter(
            responses_handler=lambda _kwargs: _load_response("response_success.json"),
            models_handler=models_handler,
        )
        health = adapter.health()
        self.assertEqual(health.status.value, "unavailable")
        self.assertEqual(health.safe_code, "authentication_error")


if __name__ == "__main__":
    unittest.main()
