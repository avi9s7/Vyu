from __future__ import annotations

import json

import httpx

from scripts.reprocess_document import ReprocessPlan, build_reprocess_plan, run_reprocess_document


def test_reprocess_document_dry_run_with_mocked_api() -> None:
    document_id = "11111111-1111-1111-1111-111111111111"
    version_id = "22222222-2222-2222-2222-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == f"/v1/evidence-documents/{document_id}":
            return httpx.Response(
                200,
                json={
                    "document_id": document_id,
                    "status": "ready",
                    "current_version_id": version_id,
                },
            )
        if request.method == "POST":
            raise AssertionError("dry-run must not call reprocess endpoint")
        return httpx.Response(404)

    plan = ReprocessPlan(
        environment="staging",
        tenant_id="33333333-3333-3333-3333-333333333333",
        workspace_id="44444444-4444-4444-4444-444444444444",
        document_id=document_id,
        version_id=None,
        reason="Parser upgrade validation",
        actor="operator@example.com",
        target_parser_version="1.0.1",
        target_chunker_version="1.0.0",
        mode="dry-run",
        idempotency_key="reprocess-test",
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = run_reprocess_document(
            base_url="https://api.staging.example.com",
            bearer_token="token",
            plan=plan,
            client=client,
        )

    assert result.status == "planned"
    assert result.version_id == version_id
    assert result.job_id is None


def test_reprocess_document_apply_posts_idempotent_request() -> None:
    document_id = "11111111-1111-1111-1111-111111111111"
    version_id = "22222222-2222-2222-2222-222222222222"
    job_id = "55555555-5555-5555-5555-555555555555"
    new_version_id = "66666666-6666-6666-6666-666666666666"
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "document_id": document_id,
                    "status": "ready",
                    "current_version_id": version_id,
                },
            )
        if request.method == "POST":
            captured["idempotency_key"] = request.headers.get("Idempotency-Key", "")
            captured["body"] = request.content.decode("utf-8")
            return httpx.Response(
                202,
                json={
                    "document_id": document_id,
                    "version_id": new_version_id,
                    "job_id": job_id,
                    "status": "accepted",
                    "idempotent": False,
                },
            )
        return httpx.Response(404)

    plan = ReprocessPlan(
        environment="staging",
        tenant_id="33333333-3333-3333-3333-333333333333",
        workspace_id="44444444-4444-4444-4444-444444444444",
        document_id=document_id,
        version_id=version_id,
        reason="Parser upgrade",
        actor="operator@example.com",
        target_parser_version="1.0.1",
        target_chunker_version="1.0.0",
        mode="apply",
        idempotency_key="reprocess-apply",
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = run_reprocess_document(
            base_url="https://api.staging.example.com",
            bearer_token="token",
            plan=plan,
            client=client,
        )

    assert result.status == "accepted"
    assert result.job_id == job_id
    assert captured["idempotency_key"] == "reprocess-apply"
    body = json.loads(captured["body"])
    assert body["version_id"] == version_id
    assert body["target_parser_version"] == "1.0.1"


def test_build_reprocess_plan_generates_deterministic_idempotency_key() -> None:
    import argparse

    args = argparse.Namespace(
        environment="staging",
        base_url="https://api.staging.example.com",
        tenant_id="tenant",
        workspace_id="workspace",
        document_id="document",
        version_id="",
        reason="reason",
        actor="actor",
        target_parser_version="1.0.0",
        target_chunker_version="1.0.0",
        mode="dry-run",
        idempotency_key="",
    )
    first = build_reprocess_plan(args)
    second = build_reprocess_plan(args)
    assert first.idempotency_key == second.idempotency_key
    assert first.idempotency_key.startswith("reprocess-")
