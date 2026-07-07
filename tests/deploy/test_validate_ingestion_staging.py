from __future__ import annotations

from scripts.validate_ingestion_staging import presign_upload
from src.vyu.ingestion.staging_fixtures import CLEAN_STAGING_FIXTURES
import httpx


def test_presign_upload_posts_expected_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = request.json()
        return httpx.Response(
            201,
            json={
                "document_id": "doc-1",
                "version_id": "ver-1",
                "job_id": "job-1",
                "upload_url": "https://s3.local/upload",
                "upload_fields": {"key": "k"},
                "expires_at": "2026-07-07T12:00:00Z",
                "object_key": "k",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        payload = presign_upload(
            client,
            origin="https://api.staging.example.com",
            headers={"Authorization": "Bearer token"},
            fixture=CLEAN_STAGING_FIXTURES[0],
            source_id="internal_documents",
        )

    assert captured["path"] == "/v1/uploads/presign"
    assert payload["document_id"] == "doc-1"
    body = captured["json"]
    assert isinstance(body, dict)
    assert body["contains_phi"] is False
