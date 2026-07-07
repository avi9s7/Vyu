from __future__ import annotations

import hashlib
from dataclasses import replace
from uuid import UUID

from sqlalchemy import select

from src.vyu.api.schemas.uploads import PresignUploadRequest
from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.ingestion.contracts import DocumentStatus
from src.vyu.ingestion.models import Document, DocumentVersion
from src.vyu.ingestion.object_store import (
    RecordingQuarantineObjectStore,
    build_evidence_normalized_key,
    build_evidence_original_key,
)
from tests.api.support import seed_active_membership
from tests.fixtures.ingestion.builders import PUBLIC_ARTICLE_TEXT
from tests.integration.ingestion.test_object_verification import (
    VerificationFixture,
    _build_principal,
    _build_service,
    _finalize,
    _run_verify,
    _seed_upload,
)


def _process_fixture(fixture: VerificationFixture, body: bytes) -> None:
    fixture.store.seed_object(fixture.ref, body)
    _finalize(fixture)
    result = _run_verify(fixture)
    assert result.result is not None
    assert result.result["code"] == "ready"


def test_exact_duplicate_reuses_ready_version(postgres_urls: dict[str, str]) -> None:
    first = _seed_ready_upload(postgres_urls, subject="dedup-user-a")
    body = PUBLIC_ARTICLE_TEXT.encode("utf-8")
    duplicate = _create_fixture(postgres_urls, subject="dedup-user-b", body=body)
    duplicate.store.seed_object(duplicate.ref, body)
    _finalize(duplicate)

    result = _run_verify(duplicate)

    assert result.result is not None
    assert result.result["code"] == "duplicate_exact"
    assert result.result["canonical_version_id"] == str(first.version_id)
    with transaction(duplicate.factory, scope=duplicate.scope) as session:
        document = session.scalar(select(Document).where(Document.id == duplicate.document_id))
        assert document is not None
        assert document.status == DocumentStatus.READY.value
        assert document.current_version_id == first.version_id
        assert duplicate.service.ingestion_repository.count_chunks(session, duplicate.version_id) == 0


def test_external_id_creates_next_version(postgres_urls: dict[str, str]) -> None:
    first_body = PUBLIC_ARTICLE_TEXT.encode("utf-8")
    fixture = _create_fixture(postgres_urls, subject="version-user", body=first_body)
    with transaction(fixture.factory, scope=fixture.scope) as session:
        document = session.scalar(select(Document).where(Document.id == fixture.document_id))
        assert document is not None
        document.external_id = "ops-report-001"
    _process_fixture(fixture, first_body)

    second_body = b"Updated quarterly operations report without patient identifiers."
    request = PresignUploadRequest(
        filename="report.txt",
        media_type="text/plain",
        size_bytes=len(second_body),
        sha256=hashlib.sha256(second_body).hexdigest(),
        source_id="internal_documents",
        external_id="ops-report-001",
        contains_phi=False,
    )
    with transaction(fixture.factory, scope=fixture.scope) as session:
        response = fixture.service.create_presigned_upload(
            body=request,
            principal=fixture.principal,
            request_id="req-presign-v2",
            trace_id="trace-presign-v2",
            session=session,
        )
    second_fixture = _build_second_fixture(fixture, response=response, body=second_body)
    _process_fixture(second_fixture, second_body)

    with transaction(fixture.factory, scope=fixture.scope) as session:
        versions = session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == fixture.document_id)
            .order_by(DocumentVersion.version)
        ).all()
        assert [version.version for version in versions] == [1, 2]
        document = session.scalar(select(Document).where(Document.id == fixture.document_id))
        assert document is not None
        assert document.current_version_id == second_fixture.version_id


def test_promotion_failure_recovers_on_retry(postgres_urls: dict[str, str]) -> None:
    body = PUBLIC_ARTICLE_TEXT.encode("utf-8")
    fixture = _create_fixture(postgres_urls, subject="promotion-retry-user", body=body)
    fixture.store.seed_object(fixture.ref, body)
    _finalize(fixture)

    original_key = build_evidence_original_key(
        env=fixture.service.settings.env,
        tenant_id=fixture.ref.tenant_id,
        workspace_id=fixture.ref.workspace_id,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
        filename="report.txt",
    )
    normalized_key = build_evidence_normalized_key(
        env=fixture.service.settings.env,
        tenant_id=fixture.ref.tenant_id,
        workspace_id=fixture.ref.workspace_id,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )
    fixture.service.evidence_store.blocked_dest_keys.add(original_key)
    fixture.service.evidence_store.blocked_dest_keys.add(normalized_key)

    failed = _run_verify(fixture)
    assert failed.outcome == "retry"
    assert failed.error_code == "promotion_failed"

    fixture.service.evidence_store.blocked_dest_keys.clear()
    recovered = _run_verify(fixture)
    assert recovered.outcome == "complete"
    assert recovered.result is not None
    assert recovered.result["code"] == "ready"


def _seed_ready_upload(
    postgres_urls: dict[str, str],
    *,
    subject: str,
    body: bytes | None = None,
) -> VerificationFixture:
    payload = body or PUBLIC_ARTICLE_TEXT.encode("utf-8")
    fixture = _create_fixture(postgres_urls, subject=subject, body=payload)
    _process_fixture(fixture, payload)
    return fixture


def _create_fixture(
    postgres_urls: dict[str, str],
    *,
    subject: str,
    body: bytes,
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
        body_bytes=body,
    )


def _build_second_fixture(
    fixture: VerificationFixture,
    *,
    response: object,
    body: bytes,
) -> VerificationFixture:
    from src.vyu.api.schemas.uploads import PresignUploadResponse

    assert isinstance(response, PresignUploadResponse)
    version_id = UUID(response.version_id)
    ref = replace(
        fixture.ref,
        document_id=fixture.document_id,
        version_id=version_id,
        sha256=hashlib.sha256(body).hexdigest(),
        size_bytes=len(body),
        key=response.object_key,
    )
    return VerificationFixture(
        scope=fixture.scope,
        factory=fixture.factory,
        service=fixture.service,
        store=fixture.store,
        principal=fixture.principal,
        ref=ref,
        document_id=fixture.document_id,
        version_id=version_id,
        job_id=UUID(response.job_id),
    )
