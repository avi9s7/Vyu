import json
import tempfile
import unittest
from pathlib import Path

import httpx

from src.vyu.connectors.audit import JsonlTransportAuditSink
from src.vyu.connectors.http import (
    ConnectorHttpClient,
    HttpClientConfig,
    HttpClientError,
    request_hash,
    response_hash,
)
from src.vyu.connectors.pubmed_live import PubMedHttpTransport, PubMedReplayTransport
from src.vyu.connectors.rate_limit import StaticRateLimiter
from src.vyu.connectors.replay import ReplayFixtureStore, build_fixture, normalized_payload_hash
from src.vyu.connectors.runtime import ConnectorRuntime, RetryPolicy


class ConnectorHttpClientTests(unittest.TestCase):
    def test_get_returns_json_for_successful_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual("vyu-test", request.headers.get("user-agent"))
            return httpx.Response(200, json={"ok": True}, request=request)

        with ConnectorHttpClient(
            config=HttpClientConfig(user_agent="vyu-test"),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ) as client:
            response = client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={"db": "pubmed"},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"ok": True}, response.json())

    def test_timeout_maps_to_retryable_error(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("read timed out")

        client = ConnectorHttpClient(
            config=HttpClientConfig(),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        with self.assertRaises(HttpClientError) as ctx:
            client.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi")
        self.assertEqual("timeout", ctx.exception.error_code)

    def test_rate_limit_maps_to_retryable_error_with_retry_after(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                headers={"Retry-After": "2.5"},
                request=request,
            )

        client = ConnectorHttpClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        with self.assertRaises(HttpClientError) as ctx:
            client.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi")
        self.assertEqual("rate_limited", ctx.exception.error_code)
        self.assertEqual(2.5, ctx.exception.retry_after_seconds)

    def test_non_retryable_400_raises_client_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, request=request)

        client = ConnectorHttpClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        with self.assertRaises(HttpClientError) as ctx:
            client.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi")
        self.assertEqual("client_error", ctx.exception.error_code)
        self.assertEqual(400, ctx.exception.status_code)

    def test_unapproved_host_is_blocked(self):
        client = ConnectorHttpClient()
        with self.assertRaises(HttpClientError) as ctx:
            client.get("https://evil.example/entrez/eutils/esearch.fcgi")
        self.assertEqual("host_not_allowed", ctx.exception.error_code)

    def test_redirect_to_unapproved_host_is_blocked(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith("https://eutils.ncbi.nlm.nih.gov"):
                return httpx.Response(
                    302,
                    headers={"Location": "https://evil.example/redirect"},
                    request=request,
                )
            return httpx.Response(200, json={"ok": True}, request=request)

        client = ConnectorHttpClient(
            config=HttpClientConfig(follow_redirects=True),
            client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
        )
        with self.assertRaises(HttpClientError) as ctx:
            client.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi")
        self.assertEqual("host_not_allowed", ctx.exception.error_code)

    def test_oversized_response_is_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"x" * 20, request=request)

        client = ConnectorHttpClient(
            config=HttpClientConfig(max_response_bytes=10),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        with self.assertRaises(HttpClientError) as ctx:
            client.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi")
        self.assertEqual("oversized_response", ctx.exception.error_code)

    def test_invalid_json_raises_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not-json", request=request)

        client = ConnectorHttpClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        response = client.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi")
        with self.assertRaises(HttpClientError) as ctx:
            response.json()
        self.assertEqual("invalid_json", ctx.exception.error_code)


class ConnectorRuntimeHttpRetryTests(unittest.TestCase):
    def test_runtime_retries_429_then_succeeds(self):
        attempts = 0

        def operation() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise HttpClientError(
                    "rate_limited",
                    status_code=429,
                    retry_after_seconds=0.0,
                )
            return "ok"

        runtime = ConnectorRuntime(
            retry_policy=RetryPolicy(max_attempts=4, backoff_seconds=0),
            rate_limiter=StaticRateLimiter(max_calls=10, window_seconds=60),
            sleep=lambda _seconds: None,
            randomizer=lambda: 0.0,
        )
        result = runtime.run("pubmed", "search", operation)
        self.assertEqual("ok", result.value)
        self.assertEqual(3, result.attempts)

    def test_runtime_does_not_retry_non_retryable_400(self):
        def operation() -> str:
            raise HttpClientError("client_error", status_code=400)

        runtime = ConnectorRuntime(
            retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=0),
            rate_limiter=StaticRateLimiter(max_calls=10, window_seconds=60),
            sleep=lambda _seconds: None,
        )
        with self.assertRaises(HttpClientError):
            runtime.run("pubmed", "search", operation)


class PubMedTransportValidationTests(unittest.TestCase):
    def test_missing_email_or_tool_rejected(self):
        with self.assertRaises(ValueError):
            PubMedHttpTransport(tool="", email="dev@example.com")
        with self.assertRaises(ValueError):
            PubMedHttpTransport(tool="vyu", email="")

    def test_transport_audit_records_hashes_without_query_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "transport.jsonl"
            audit_sink = JsonlTransportAuditSink(audit_path)

            def opener(url, timeout):
                del url, timeout
                return json.dumps({"esearchresult": {"idlist": ["1", "1"]}}).encode("utf-8")

            transport = PubMedHttpTransport(
                tool="vyu-test",
                email="dev@example.com",
                opener=opener,
                transport_audit_sink=audit_sink,
            )
            payload = transport(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                {"mode": "search", "db": "pubmed", "term": "secret-query", "retmax": 2},
            )

            self.assertEqual(["1", "1"], payload["ids"])
            records = audit_sink.read_records()
            self.assertEqual(1, len(records))
            self.assertNotIn("secret-query", json.dumps(records))
            self.assertTrue(records[0]["request_hash"])
            self.assertTrue(records[0]["response_hash"])


class ReplayFixtureTests(unittest.TestCase):
    def test_replay_fixture_hash_mismatch_is_detected(self):
        fixture = build_fixture(
            source="pubmed",
            mode="search",
            url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "pubmed", "term": "migraine"},
            response_payload={"esearchresult": {"idlist": ["123"]}},
            normalized={"ids": ["123"]},
            license_note="PubMed replay fixture",
        )
        tampered = fixture.to_json()
        tampered["response_hash"] = "0" * 64
        with self.assertRaises(ValueError):
            from src.vyu.connectors.replay import ReplayFixture

            ReplayFixture.from_json(tampered).validate_hashes()

    def test_replay_store_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReplayFixtureStore(Path(tmp))
            fixture = build_fixture(
                source="pubmed",
                mode="search",
                url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={"db": "pubmed", "term": "migraine"},
                response_payload={"esearchresult": {"idlist": ["123"]}},
                normalized={"ids": ["123"]},
            )
            store.write(fixture)
            loaded = store.load("pubmed", "search")
            self.assertEqual(fixture.request_hash, loaded.request_hash)
            self.assertEqual(fixture.normalized, loaded.normalized)

    def test_normalized_payload_hash_is_stable(self):
        first = normalized_payload_hash({"ids": ["123"]})
        second = normalized_payload_hash({"ids": ["123"]})
        self.assertEqual(first, second)

    def test_request_and_response_hashes_are_stable(self):
        params = {"db": "pubmed", "term": "migraine"}
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        body = b'{"esearchresult":{"idlist":["123"]}}'
        self.assertEqual(request_hash("GET", url, params), request_hash("GET", url, params))
        self.assertEqual(response_hash(200, body), response_hash(200, body))


class PubMedReplayTransportTests(unittest.TestCase):
    def test_legacy_fixture_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path = Path(tmp) / "pubmed_replay.json"
            fixture_path.write_text(
                json.dumps({"search": {"ids": ["12345"]}}),
                encoding="utf-8",
            )
            transport = PubMedReplayTransport(fixture_path)
            payload = transport(
                "https://example.com",
                {"mode": "search", "db": "pubmed", "term": "VX-101"},
            )
            self.assertEqual({"ids": ["12345"]}, payload)


if __name__ == "__main__":
    unittest.main()
