from __future__ import annotations

import hashlib

from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.ingestion.contracts import DocumentStatus
from src.vyu.ingestion.malware import EICAR_TEST_SIGNATURE
from src.vyu.ingestion.object_store import RecordingQuarantineObjectStore
from tests.api.support import seed_active_membership
from tests.integration.ingestion.test_object_verification import (
    VerificationFixture,
    _build_principal,
    _build_service,
    _document_status,
    _finalize,
    _run_verify,
    _seed_upload,
)


def _fixture_with_body(
    postgres_urls: dict[str, str],
    *,
    body_bytes: bytes,
    filename: str,
    subject: str,
) -> VerificationFixture:
    migration_factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )
    tenant_id, workspace_id, user_id = seed_active_membership(
        migration_factory,
        subject=subject,
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
        subject=subject,
    )
    return _seed_upload(
        scope=scope,
        factory=factory,
        service=service,
        store=store,
        principal=principal,
        body_bytes=body_bytes,
        filename=filename,
        media_type="text/plain",
    )


def test_eicar_payload_blocks_document(postgres_urls: dict[str, str]) -> None:
    body = EICAR_TEST_SIGNATURE.encode("ascii")
    fixture = _fixture_with_body(
        postgres_urls,
        body_bytes=body,
        filename="eicar.txt",
        subject="ingestion-eicar-user",
    )
    fixture.store.seed_object(fixture.ref, body, include_checksum_metadata=False)
    _finalize(fixture)

    result = _run_verify(fixture)

    assert result.outcome == "complete"
    assert result.result is not None
    assert result.result["code"] == "malware_infected"
    assert _document_status(fixture) == DocumentStatus.BLOCKED.value


def test_synthetic_phi_blocks_document(postgres_urls: dict[str, str]) -> None:
    body = b"Patient ID: ABC-12345. Date of birth: 01/15/1980."
    fixture = _fixture_with_body(
        postgres_urls,
        body_bytes=body,
        filename="clinical-note.txt",
        subject="ingestion-phi-user",
    )
    fixture.store.seed_object(fixture.ref, body, include_checksum_metadata=False)
    _finalize(fixture)

    result = _run_verify(fixture)

    assert result.outcome == "complete"
    assert result.result is not None
    assert result.result["code"] == "phi_suspected_phi"
    assert _document_status(fixture) == DocumentStatus.BLOCKED.value


def test_clean_text_passes_screening(postgres_urls: dict[str, str]) -> None:
    body = b"Quarterly operations report without patient identifiers."
    fixture = _fixture_with_body(
        postgres_urls,
        body_bytes=body,
        filename="report.txt",
        subject="ingestion-clean-screen-user",
    )
    fixture.store.seed_object(fixture.ref, body, include_checksum_metadata=False)
    _finalize(fixture)

    result = _run_verify(fixture)

    assert result.outcome == "complete"
    assert result.result is not None
    assert result.result["code"] == "ready"
    assert _document_status(fixture) == DocumentStatus.READY.value

    with transaction(fixture.factory, scope=fixture.scope) as session:
        version = fixture.service._get_version(session, fixture.version_id)
        assert version is not None
        assert version.malware_status == "clean"
        assert version.phi_status == "non_phi"
        assert version.parser_name == "vyu_text"
        assert version.metadata_json["malware_scanner"]["content_hash"] == hashlib.sha256(body).hexdigest()
        assert fixture.service.ingestion_repository.count_chunks(session, fixture.version_id) >= 1
