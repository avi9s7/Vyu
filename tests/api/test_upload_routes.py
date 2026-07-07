from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.vyu.api.app import create_app
from src.vyu.api.settings import ApiSettings
from src.vyu.auth.resolver import apply_principal_scope
from src.vyu.auth.settings import AuthSettings
from src.vyu.db.settings import DatabaseSettings
from src.vyu.ingestion.object_store import RecordingQuarantineObjectStore
from src.vyu.ingestion.service import IngestionService
from src.vyu.ingestion.settings import IngestionSettings
from src.vyu.sources import ProductionSourceRecord, SourceRegistry
from tests.api.support import AuthTestContext, auth_headers, build_auth_test_client


def valid_upload_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "filename": "report.pdf",
        "media_type": "application/pdf",
        "size_bytes": 2048,
        "sha256": "a" * 64,
        "source_id": "internal_documents",
        "contains_phi": False,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def upload_context(postgres_urls: dict[str, str]) -> AuthTestContext:
    return build_auth_test_client(postgres_urls)


def test_presign_upload_returns_post_fields(upload_context: AuthTestContext) -> None:
    response = upload_context.client.post(
        "/v1/uploads/presign",
        headers=auth_headers(upload_context),
        json=valid_upload_payload(),
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["document_id"]
    assert payload["version_id"]
    assert payload["job_id"]
    assert payload["upload_url"]
    assert payload["upload_fields"]["key"].endswith("/report.pdf")
    assert "/quarantine/" in payload["object_key"]


def test_presign_upload_rejects_phi_attestation(upload_context: AuthTestContext) -> None:
    response = upload_context.client.post(
        "/v1/uploads/presign",
        headers=auth_headers(upload_context),
        json=valid_upload_payload(contains_phi=True),
    )
    assert response.status_code == 422


def test_presign_upload_rejects_unapproved_source(postgres_urls: dict[str, str]) -> None:
    draft_registry = SourceRegistry(
        [
            ProductionSourceRecord(
                source_id="internal_documents",
                display_name="Draft Internal",
                source_type="tenant_documents",
                owner="Vyu",
                license_or_terms="test",
                allowed_uses=["document_upload"],
                approval_status="draft",
            )
        ]
    )
    settings = IngestionSettings(env="test")
    object_store = RecordingQuarantineObjectStore(
        bucket=settings.quarantine_bucket,
        region=settings.s3_region,
        kms_key_id=settings.s3_kms_key_id,
        expiry_seconds=settings.presign_expiry_seconds,
    )
    service = IngestionService(
        settings=settings,
        source_registry=draft_registry,
        object_store=object_store,
    )
    auth_settings = AuthSettings(
        env="test",
        auth_mode="local_hs256",
        token_issuer="https://local.vyu.invalid",
        token_audience="vyu-local",
        hs256_secret="test-auth-secret",
        require_email_verified=True,
    )
    context = build_auth_test_client(postgres_urls)
    app = create_app(
        settings_override=ApiSettings(env="test", expected_migration_revision="0004"),
        database_settings_override=DatabaseSettings(database_url=postgres_urls["app"]),
        auth_settings_override=auth_settings,
        ingestion_service_override=service,
        schema_revision_override="0004",
    )
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/v1/uploads/presign",
        headers=auth_headers(context),
        json=valid_upload_payload(),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_cross_tenant_document_lookup_is_hidden(
    postgres_urls: dict[str, str],
    upload_context: AuthTestContext,
) -> None:
    create_response = upload_context.client.post(
        "/v1/uploads/presign",
        headers=auth_headers(upload_context),
        json=valid_upload_payload(),
    )
    assert create_response.status_code == 201
    document_id = UUID(create_response.json()["document_id"])

    other_context = build_auth_test_client(postgres_urls, subject="other-tenant-user")
    service = upload_context.client.app.state.ingestion_service
    with upload_context.client.app.state.session_factory.begin() as session:
        apply_principal_scope(
            session,
            tenant_id=other_context.tenant_id,
            workspace_id=other_context.workspace_id,
        )
        assert service.get_document(session, document_id) is None
