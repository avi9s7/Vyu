from __future__ import annotations

from src.vyu.ingestion.contracts import DocumentStatus
from tests.integration.ingestion.test_object_verification import (
    _document_status,
    _finalize,
    _run_verify,
    _seed_upload,
)
from tests.api.support import seed_active_membership
from src.vyu.db.session import TenantScope, build_engine, build_session_factory
from src.vyu.db.settings import DatabaseSettings
from src.vyu.ingestion.object_store import RecordingQuarantineObjectStore
from tests.integration.ingestion.test_object_verification import (
    _build_principal,
    _build_service,
)


def test_malformed_pdf_blocks_during_parsing(postgres_urls: dict[str, str]) -> None:
    migration_factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )
    tenant_id, workspace_id, user_id = seed_active_membership(
        migration_factory,
        subject="ingestion-parser-fail-user",
        role="researcher",
    )
    scope = TenantScope(tenant_id=tenant_id, workspace_id=workspace_id)
    factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )
    store = RecordingQuarantineObjectStore(
        bucket="vyu-test-quarantine",
        region="ap-south-1",
        kms_key_id="arn:aws:kms:ap-south-1:123456789012:key/00000000-0000-0000-0000-000000000000",
        expiry_seconds=600,
    )
    service = _build_service(store)
    principal = _build_principal(
        user_id=user_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        subject="ingestion-parser-fail-user",
    )
    body = b"%PDF-1.4 not a real pdf"
    fixture = _seed_upload(
        scope=scope,
        factory=factory,
        service=service,
        store=store,
        principal=principal,
        body_bytes=body,
        filename="broken.pdf",
        media_type="application/pdf",
    )
    fixture.store.seed_object(fixture.ref, body, include_checksum_metadata=False)
    _finalize(fixture)

    result = _run_verify(fixture)

    assert result.outcome == "complete"
    assert result.result is not None
    assert result.result["code"] == "parser_malformed_document"
    assert _document_status(fixture) == DocumentStatus.BLOCKED.value
