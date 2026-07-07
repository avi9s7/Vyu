from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import AuthenticationError, RateLimitError
from openai.types.create_embedding_response import CreateEmbeddingResponse
from openai.types.responses import Response

from src.vyu.model_gateway.adapters.azure_openai import AzureOpenAIAdapter
from src.vyu.model_gateway.errors import (
    GatewayAuthenticationError,
    GatewayPolicyBlocked,
)
from src.vyu.model_gateway.secrets import AzureOpenAICredentials
from tests.unit.model_gateway.adapters.test_openai import (
    _load_embedding,
    _load_response,
    _sample_embedding_request,
    _sample_request,
)


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
class FakeAzureOpenAIClient:
    responses: FakeResponsesAPI
    embeddings: FakeEmbeddingsAPI
    models: FakeModelsAPI


def _azure_adapter(
    *,
    responses_handler: Any,
    embeddings_handler: Any | None = None,
) -> tuple[AzureOpenAIAdapter, FakeAzureOpenAIClient]:
    client = FakeAzureOpenAIClient(
        responses=FakeResponsesAPI(responses_handler),
        embeddings=FakeEmbeddingsAPI(
            embeddings_handler
            or (lambda _kwargs: _load_embedding("embedding_success.json"))
        ),
        models=FakeModelsAPI(lambda _kwargs: object()),
    )
    adapter = AzureOpenAIAdapter(
        credentials=AzureOpenAICredentials(
            api_key="azure-test-key",
            endpoint="https://example.openai.azure.com",
            deployment="gpt-4o-deployment",
        ),
        client=client,  # type: ignore[arg-type]
        sleep=lambda _seconds: None,
    )
    return adapter, client


class AzureOpenAIAdapterContractTests(unittest.TestCase):
    def test_generate_uses_deployment_and_normalizes_response(self) -> None:
        adapter, client = _azure_adapter(
            responses_handler=lambda _kwargs: _load_response("response_success.json"),
        )
        response = adapter.generate(
            _sample_request(provider_id="azure_openai", model_id="gpt-4o-2024-08-06")
        )
        self.assertEqual(response.provider_request_id, "resp_success_001")
        self.assertEqual(client.responses.calls[0]["model"], "gpt-4o-deployment")
        self.assertNotIn("tools", client.responses.calls[0])

    def test_generate_maps_refusal_to_policy_blocked(self) -> None:
        adapter, _client = _azure_adapter(
            responses_handler=lambda _kwargs: _load_response("response_refusal.json"),
        )
        with self.assertRaises(GatewayPolicyBlocked):
            adapter.generate(
                _sample_request(provider_id="azure_openai", model_id="gpt-4o-2024-08-06")
            )

    def test_generate_maps_authentication_failure(self) -> None:
        def handler(_kwargs: dict[str, Any]) -> Response:
            request = httpx.Request("POST", "https://example.openai.azure.com/openai/responses")
            response = httpx.Response(401, request=request)
            raise AuthenticationError("invalid api key", response=response, body=None)

        adapter, _client = _azure_adapter(responses_handler=handler)
        with self.assertRaises(GatewayAuthenticationError):
            adapter.generate(
                _sample_request(provider_id="azure_openai", model_id="gpt-4o-2024-08-06")
            )

    def test_generate_retries_rate_limit(self) -> None:
        attempts = {"count": 0}
        sleeps: list[float] = []

        def handler(_kwargs: dict[str, Any]) -> Response:
            attempts["count"] += 1
            if attempts["count"] == 1:
                request = httpx.Request("POST", "https://example.openai.azure.com/openai/responses")
                response = httpx.Response(429, request=request, headers={"retry-after": "1"})
                raise RateLimitError("rate limited", response=response, body=None)
            return _load_response("response_success.json")

        adapter, _client = _azure_adapter(responses_handler=handler)
        adapter.sleep = sleeps.append  # type: ignore[method-assign]
        response = adapter.generate(
            _sample_request(provider_id="azure_openai", model_id="gpt-4o-2024-08-06")
        )
        self.assertEqual(response.provider_request_id, "resp_success_001")
        self.assertEqual(sleeps, [1.0])

    def test_embed_uses_deployment_name(self) -> None:
        adapter, client = _azure_adapter(
            responses_handler=lambda _kwargs: _load_response("response_success.json"),
        )
        adapter.embed(
            _sample_embedding_request(
                provider_id="azure_openai",
                model_id="text-embedding-3-small",
            )
        )
        self.assertEqual(client.embeddings.calls[0]["model"], "gpt-4o-deployment")


if __name__ == "__main__":
    unittest.main()
