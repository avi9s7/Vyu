from __future__ import annotations

import json

import httpx

from scripts.deploy_smoke import run_deploy_smoke


def test_deploy_smoke_passes_with_mocked_https_responses() -> None:
    search_id = "11111111-1111-1111-1111-111111111111"
    job_id = "22222222-2222-2222-2222-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/health/live":
            return httpx.Response(
                200,
                json={"status": "ok"},
                headers={
                    "x-request-id": "req-live",
                    "strict-transport-security": "max-age=63072000",
                    "x-content-type-options": "nosniff",
                    "x-frame-options": "DENY",
                },
            )
        if path == "/v1/health/ready":
            return httpx.Response(200, json={"status": "ready"})
        if path == "/v1/version":
            return httpx.Response(
                200,
                json={
                    "service": "vyu-api",
                    "environment": "staging",
                    "git_sha": "abc123",
                    "image_digest": "sha256:deadbeef",
                    "schema_revision": "0003",
                },
            )
        if path == "/v1/research/searches" and request.method == "GET":
            return httpx.Response(
                401,
                json={"status": "error", "error": {"code": "authentication_failed"}},
            )
        if path == "/v1/me":
            return httpx.Response(
                200,
                json={
                    "user_id": "user-1",
                    "tenant_id": "tenant-1",
                    "workspace_id": "workspace-1",
                    "role": "reviewer",
                    "authentication_method": "local_hs256",
                },
            )
        if path == "/v1/research/searches" and request.method == "POST":
            return httpx.Response(
                202,
                json={
                    "status": "queued",
                    "search_id": search_id,
                    "job_id": job_id,
                    "links": {
                        "self": f"/v1/research/searches/{search_id}",
                        "events": f"/v1/research/searches/{search_id}/events",
                    },
                },
            )
        if path == f"/v1/research/searches/{search_id}":
            return httpx.Response(
                200,
                json={
                    "search_id": search_id,
                    "job_id": job_id,
                    "status": "queued",
                },
            )
        if path == f"/v1/research/searches/{search_id}/events":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "sequence": 1,
                            "event_type": "research_search_accepted",
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"status": "error"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://staging.example.com")
    result = run_deploy_smoke(
        base_url="https://staging.example.com",
        bearer_token="test-token",
        research_payload={
            "question": "question",
            "source_ids": ["pubmed"],
            "only_approved_sources": True,
        },
        idempotency_key="deploy-smoke-test",
        expected_git_sha="abc123",
        expected_schema_revision="0003",
        expected_image_digest="sha256:deadbeef",
        client=client,
    )

    payload = result.to_json()
    assert payload["status"] == "pass"
    assert all(check["passed"] for check in payload["checks"])
    serialized = json.dumps(payload)
    assert "test-token" not in serialized
