from __future__ import annotations

import json
import unittest
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx
from anthropic import AuthenticationError, RateLimitError
from anthropic.types import Message

from src.vyu.model_gateway.adapters.anthropic import AnthropicAdapter
from src.vyu.model_gateway.adapters.retry import AdapterRetrySettings
from src.vyu.model_gateway.contracts import EmbeddingRequest, ModelRequest
from src.vyu.model_gateway.errors import (
    GatewayAuthenticationError,
    GatewayPolicyBlocked,
    GatewayRateLimited,
    GatewayValidationError,
)
from src.vyu.model_gateway.secrets import AnthropicCredentials


def _sample_request(**overrides: object) -> ModelRequest:
    tenant_id = uuid4()
    workspace_id = uuid4()
    base = {
        "request_id": "req-anthropic-001",
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "run_id": "run-001",
        "use_case": "grounded_synthesis",
        "provider_id": "anthropic",
        "model_id": "claude-sonnet-4-20250514",
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


def _success_message() -> Message:
    return Message.model_validate(
        {
            "id": "msg_success_001",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-20250514",
            "stop_reason": "end_turn",
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"answer_summary": "Supported by evidence.", "claims": []}
                    ),
                }
            ],
            "usage": {
                "input_tokens": 30,
                "output_tokens": 12,
                "cache_read_input_tokens": 2,
            },
        }
    )


def _refusal_message() -> Message:
    return Message.model_validate(
        {
            "id": "msg_refusal_001",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-20250514",
            "stop_reason": "refusal",
            "stop_details": {"type": "refusal"},
            "content": [{"type": "text", "text": "I cannot answer that request."}],
            "usage": {"input_tokens": 10, "output_tokens": 4},
        }
    )


@dataclass
class FakeMessagesAPI:
    handler: Any
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> Message:
        self.calls.append(kwargs)
        return self.handler(kwargs)


@dataclass
class FakeModelsAPI:
    handler: Any

    def list(self, **kwargs: Any) -> object:
        return self.handler(kwargs)


@dataclass
class FakeAnthropicClient:
    messages: FakeMessagesAPI
    models: FakeModelsAPI


def _adapter(messages_handler: Any, *, max_attempts: int = 3) -> tuple[AnthropicAdapter, FakeAnthropicClient]:
    client = FakeAnthropicClient(
        messages=FakeMessagesAPI(messages_handler),
        models=FakeModelsAPI(lambda _kwargs: object()),
    )
    adapter = AnthropicAdapter(
        credentials=AnthropicCredentials(api_key="sk-ant-test"),
        client=client,  # type: ignore[arg-type]
        settings=AdapterRetrySettings(max_attempts=max_attempts),
        sleep=lambda _seconds: None,
    )
    return adapter, client


class AnthropicAdapterContractTests(unittest.TestCase):
    def test_generate_success_normalizes_usage_and_request_id(self) -> None:
        adapter, client = _adapter(lambda _kwargs: _success_message())
        response = adapter.generate(_sample_request())
        self.assertEqual(response.provider_request_id, "msg_success_001")
        self.assertEqual(response.input_tokens, 30)
        self.assertEqual(response.output_tokens, 12)
        self.assertEqual(response.cached_tokens, 2)
        self.assertNotIn("tools", client.messages.calls[0])
        self.assertEqual(client.messages.calls[0]["output_config"]["format"]["type"], "json_schema")

    def test_generate_maps_refusal_to_policy_blocked(self) -> None:
        adapter, _client = _adapter(lambda _kwargs: _refusal_message())
        with self.assertRaises(GatewayPolicyBlocked):
            adapter.generate(_sample_request())

    def test_generate_rejects_unapproved_model(self) -> None:
        adapter, _client = _adapter(lambda _kwargs: _success_message())
        with self.assertRaises(GatewayValidationError):
            adapter.generate(_sample_request(model_id="claude-2.0"))

    def test_embed_is_not_supported(self) -> None:
        adapter, _client = _adapter(lambda _kwargs: _success_message())
        with self.assertRaises(GatewayValidationError):
            adapter.embed(
                EmbeddingRequest(
                    request_id="embed-001",
                    tenant_id=uuid4(),
                    workspace_id=uuid4(),
                    run_id="run-001",
                    provider_id="anthropic",
                    model_id="claude-sonnet-4-20250514",
                    texts=("text",),
                    dimensions=1536,
                    timeout_seconds=30,
                    policy_version="model-policy-v1",
                )
            )

    def test_generate_maps_authentication_failure(self) -> None:
        def handler(_kwargs: dict[str, Any]) -> Message:
            request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            response = httpx.Response(401, request=request)
            raise AuthenticationError("invalid api key", response=response, body=None)

        adapter, _client = _adapter(handler)
        with self.assertRaises(GatewayAuthenticationError):
            adapter.generate(_sample_request())

    def test_generate_retries_rate_limit(self) -> None:
        attempts = {"count": 0}
        sleeps: list[float] = []

        def handler(_kwargs: dict[str, Any]) -> Message:
            attempts["count"] += 1
            if attempts["count"] == 1:
                request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
                response = httpx.Response(429, request=request, headers={"retry-after": "2"})
                raise RateLimitError("rate limited", response=response, body=None)
            return _success_message()

        adapter, _client = _adapter(handler)
        adapter.sleep = sleeps.append  # type: ignore[method-assign]
        response = adapter.generate(_sample_request())
        self.assertEqual(response.provider_request_id, "msg_success_001")
        self.assertEqual(sleeps, [2.0])

    def test_generate_exhausted_rate_limit_raises_gateway_rate_limited(self) -> None:
        def handler(_kwargs: dict[str, Any]) -> Message:
            request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            response = httpx.Response(429, request=request, headers={"retry-after": "3"})
            raise RateLimitError("rate limited", response=response, body=None)

        adapter, _client = _adapter(handler, max_attempts=1)
        with self.assertRaises(GatewayRateLimited) as ctx:
            adapter.generate(_sample_request())
        self.assertEqual(ctx.exception.retry_after_seconds, 3.0)


if __name__ == "__main__":
    unittest.main()
