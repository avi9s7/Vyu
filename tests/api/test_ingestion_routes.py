from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine

from src.vyu.api.app import create_app
from src.vyu.api.settings import ApiSettings
from tests.api.support import AuthTestContext, auth_headers, build_auth_test_client, seed_active_membership
from src.vyu.db.settings import DatabaseSettings
from src.vyu.db.session import TenantScope, build_engine, build_session_factory
from src.vyu.ingestion.contracts import DocumentStatus
from src.vyu.ingestion.library import sanitize_event_details, sanitize_version_metadata
from src.vyu.ingestion.malware import EICAR_TEST_SIGNATURE
from tests.fixtures.ingestion.builders import PUBLIC_ARTICLE_TEXT
from tests.integration.ingestion.test_object_verification import (
    _build_principal,
    _finalize,
    _run_verify,
    _seed_upload,
)


def _seed_ready_for_context(
    context: AuthTestContext,
    postgres_urls: dict[str, str],
    *,
    body: bytes | None = None,
    filename: str = "report.txt",
    media_type: str = "text/plain",
) -> tuple[str, str, str]:
    payload = body or PUBLIC_ARTICLE_TEXT.encode("utf-8")
    scope = TenantScope(tenant_id=context.tenant_id, workspace_id=context.workspace_id)
    factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )
    service = context.client.app.state.ingestion_service
    store = service.object_store
    principal = _build_principal(
        user_id=context.user_id,
        tenant_id=context.tenant_id,
        workspace_id=context.workspace_id,
        subject=context.subject,
    )
    fixture = _seed_upload(
        scope=scope,
        factory=factory,
        service=service,
        store=store,
        principal=principal,
        body_bytes=payload,
        filename=filename,
        media_type=media_type,
    )
    fixture.store.seed_object(fixture.ref, payload)
    _finalize(fixture)
    result = _run_verify(fixture)
    assert result.result is not None
    return str(fixture.document_id), str(fixture.version_id), str(fixture.job_id)


@pytest.fixture
def library_context(postgres_urls: dict[str, str]) -> AuthTestContext:
    return build_auth_test_client(postgres_urls, role="reviewer", subject="library-reviewer")


def test_list_and_get_ready_document(
    library_context: AuthTestContext,
    postgres_urls: dict[str, str],
) -> None:
    document_id, version_id, job_id = _seed_ready_for_context(library_context, postgres_urls)

    list_response = library_context.client.get(
        "/v1/evidence-documents",
        headers=auth_headers(library_context),
        params={"status": "ready"},
    )
    assert list_response.status_code == 200
    ids = {item["document_id"] for item in list_response.json()["items"]}
    assert document_id in ids

    detail_response = library_context.client.get(
        f"/v1/evidence-documents/{document_id}",
        headers=auth_headers(library_context),
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == DocumentStatus.READY.value
    assert detail["current_version_id"] == version_id

    version_response = library_context.client.get(
        f"/v1/evidence-documents/{document_id}/versions/{version_id}",
        headers=auth_headers(library_context),
    )
    assert version_response.status_code == 200
    version = version_response.json()
    assert version["parser_name"] == "vyu_text"
    assert len(version["chunks"]) >= 1
    assert "parsed_document_full" not in version["metadata"]

    job_response = library_context.client.get(
        f"/v1/ingestion-jobs/{job_id}",
        headers=auth_headers(library_context),
    )
    assert job_response.status_code == 200
    job = job_response.json()
    assert job["kind"] == "ingestion.verify"
    assert "quarantine" not in json.dumps(job)


def test_cross_tenant_document_lookup_is_hidden(
    postgres_urls: dict[str, str],
) -> None:
    owner = build_auth_test_client(postgres_urls, role="reviewer", subject="library-tenant-a")
    document_id, _version_id, _job_id = _seed_ready_for_context(owner, postgres_urls)
    other = build_auth_test_client(postgres_urls, role="reviewer", subject="library-tenant-b")
    response = other.client.get(
        f"/v1/evidence-documents/{document_id}",
        headers=auth_headers(other),
    )
    assert response.status_code == 404


def test_blocked_document_returns_safe_block_summary(
    library_context: AuthTestContext,
    postgres_urls: dict[str, str],
) -> None:
    scope = TenantScope(
        tenant_id=library_context.tenant_id,
        workspace_id=library_context.workspace_id,
    )
    factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )
    service = library_context.client.app.state.ingestion_service
    store = service.object_store
    principal = _build_principal(
        user_id=library_context.user_id,
        tenant_id=library_context.tenant_id,
        workspace_id=library_context.workspace_id,
        subject=library_context.subject,
    )
    body = EICAR_TEST_SIGNATURE.encode("ascii")
    fixture = _seed_upload(
        scope=scope,
        factory=factory,
        service=service,
        store=store,
        principal=principal,
        body_bytes=body,
        filename="eicar.txt",
        media_type="text/plain",
    )
    fixture.store.seed_object(fixture.ref, body, include_checksum_metadata=False)
    _finalize(fixture)
    result = _run_verify(fixture)
    assert result.result is not None
    assert result.result["code"] == "malware_infected"

    response = library_context.client.get(
        f"/v1/evidence-documents/{fixture.document_id}",
        headers=auth_headers(library_context),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == DocumentStatus.BLOCKED.value
    assert payload["block_summary"]["code"] == "malware_infected"


def test_reprocess_requires_workspace_admin(postgres_urls: dict[str, str]) -> None:
    migration_factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )
    tenant_id, workspace_id, _reviewer_id = seed_active_membership(
        migration_factory,
        subject="library-reprocess-reviewer",
        role="researcher",
    )
    seed_active_membership(
        migration_factory,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        subject="library-reprocess-admin",
        role="workspace_admin",
    )
    reviewer = build_auth_test_client(
        postgres_urls,
        role="researcher",
        subject="library-reprocess-reviewer",
    )
    admin = build_auth_test_client(
        postgres_urls,
        role="workspace_admin",
        subject="library-reprocess-admin",
    )
    document_id, _version_id, _job_id = _seed_ready_for_context(reviewer, postgres_urls)
    body = {
        "target_parser_version": "1.0.0",
        "target_chunker_version": "1.0.0",
    }
    denied = reviewer.client.post(
        f"/v1/evidence-documents/{document_id}/reprocess",
        headers=auth_headers(reviewer, idempotency_key="reprocess-deny"),
        json=body,
    )
    assert denied.status_code == 403

    accepted = admin.client.post(
        f"/v1/evidence-documents/{document_id}/reprocess",
        headers=auth_headers(admin, idempotency_key="reprocess-allow"),
        json=body,
    )
    assert accepted.status_code == 202
    payload = accepted.json()
    assert payload["job_id"]
    assert payload["version_id"]

    duplicate = admin.client.post(
        f"/v1/evidence-documents/{document_id}/reprocess",
        headers=auth_headers(admin, idempotency_key="reprocess-allow"),
        json=body,
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["idempotent"] is True


def test_retention_request_marks_document_deleted(postgres_urls: dict[str, str]) -> None:
    admin = build_auth_test_client(
        postgres_urls,
        role="workspace_admin",
        subject="library-retention-admin",
    )
    document_id, _version_id, _job_id = _seed_ready_for_context(admin, postgres_urls)
    response = admin.client.post(
        f"/v1/evidence-documents/{document_id}/retention-request",
        headers=auth_headers(admin),
        json={"reason": "Pilot cleanup after validation."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == DocumentStatus.DELETED.value


def test_openapi_contains_evidence_routes() -> None:
    app = create_app(
        settings_override=ApiSettings(env="test", expected_migration_revision="0004"),
        engine_override=create_engine("sqlite+pysqlite:///:memory:"),
        schema_revision_override="0004",
    )
    paths = app.openapi()["paths"]
    assert "/v1/evidence-documents" in paths
    assert "/v1/ingestion-jobs/{job_id}" in paths


def test_sanitize_metadata_redacts_sensitive_fields() -> None:
    metadata = {
        "parsed_document": {"title": "Safe"},
        "parsed_document_full": {"sections": [{"text": "secret"}]},
        "original_key": "env/t/ws/quarantine/doc/v/file.txt",
        "malware_scanner": {"finding_categories": ["eicar_test_signature"]},
    }
    sanitized = sanitize_version_metadata(metadata)
    assert "parsed_document_full" not in sanitized
    assert "original_key" not in sanitized
    assert sanitized["parsed_document"] == {"title": "Safe"}


def test_sanitize_event_details_redacts_quarantine_fields() -> None:
    details = sanitize_event_details(
        {"version_id": "abc", "object_key": "secret", "quarantine_key": "secret"}
    )
    assert details == {"version_id": "abc"}
