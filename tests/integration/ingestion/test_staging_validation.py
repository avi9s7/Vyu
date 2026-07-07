from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.ingestion.contracts import DocumentStatus
from src.vyu.ingestion.models import Document, IngestionEvent
from src.vyu.ingestion.object_store import (
    RecordingQuarantineObjectStore,
    build_evidence_normalized_key,
    build_evidence_original_key,
)
from src.vyu.ingestion.staging_fixtures import (
    BLOCKED_STAGING_FIXTURES,
    CLEAN_STAGING_FIXTURES,
)
from src.vyu.ingestion.handler import IngestionVerifyHandler
from src.vyu.jobs.models import Job
from src.vyu.jobs.repository import JobRepository
from src.vyu.jobs.worker import JobWorker, MessageDisposition, WorkerSettings, message_from_job
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


def _create_fixture(
    postgres_urls: dict[str, str],
    *,
    subject: str,
    body: bytes,
    filename: str,
    media_type: str,
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
        filename=filename,
        media_type=media_type,
    )


def _process_to_ready(fixture: VerificationFixture, body: bytes) -> None:
    fixture.store.seed_object(fixture.ref, body)
    _finalize(fixture)
    result = _run_verify(fixture)
    assert result.result is not None
    assert result.result["code"] == "ready"
    assert _document_status(fixture) == DocumentStatus.READY.value


@pytest.mark.parametrize("fixture_def", CLEAN_STAGING_FIXTURES, ids=lambda item: item.name)
def test_supported_formats_reach_ready_with_chunks(
    postgres_urls: dict[str, str],
    fixture_def,
) -> None:
    fixture = _create_fixture(
        postgres_urls,
        subject=f"staging-{fixture_def.name}",
        body=fixture_def.body,
        filename=fixture_def.filename,
        media_type=fixture_def.media_type,
    )
    _process_to_ready(fixture, fixture_def.body)

    with transaction(fixture.factory, scope=fixture.scope) as session:
        version = fixture.service._get_version(session, fixture.version_id)
        assert version is not None
        assert version.parser_name is not None
        assert fixture.service.ingestion_repository.count_chunks(session, fixture.version_id) >= 1
        original_key = build_evidence_original_key(
            env=fixture.service.settings.env,
            tenant_id=fixture.ref.tenant_id,
            workspace_id=fixture.ref.workspace_id,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
            filename=fixture_def.filename,
        )
        normalized_key = build_evidence_normalized_key(
            env=fixture.service.settings.env,
            tenant_id=fixture.ref.tenant_id,
            workspace_id=fixture.ref.workspace_id,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )
        original = fixture.service.evidence_store.stored[original_key]
        normalized = fixture.service.evidence_store.stored[normalized_key]
        assert original.server_side_encryption == "aws:kms"
        assert normalized.server_side_encryption == "aws:kms"
        assert original.version_id
        assert normalized.version_id
        assert original.metadata["sha256"] == hashlib.sha256(fixture_def.body).hexdigest()


@pytest.mark.parametrize("fixture_def", BLOCKED_STAGING_FIXTURES, ids=lambda item: item.name)
def test_blocked_fixtures_remain_quarantined_without_chunks(
    postgres_urls: dict[str, str],
    fixture_def,
) -> None:
    fixture = _create_fixture(
        postgres_urls,
        subject=f"staging-blocked-{fixture_def.name}",
        body=fixture_def.body,
        filename=fixture_def.filename,
        media_type=fixture_def.media_type,
    )
    fixture.store.seed_object(fixture.ref, fixture_def.body, include_checksum_metadata=False)
    _finalize(fixture)
    result = _run_verify(fixture)

    assert result.result is not None
    assert result.result["code"] == fixture_def.expect_code
    assert _document_status(fixture) == DocumentStatus.BLOCKED.value
    with transaction(fixture.factory, scope=fixture.scope) as session:
        assert fixture.service.ingestion_repository.count_chunks(session, fixture.version_id) == 0


def test_cross_tenant_document_lookup_is_hidden(postgres_urls: dict[str, str]) -> None:
    owner = _create_fixture(
        postgres_urls,
        subject="staging-owner",
        body=CLEAN_STAGING_FIXTURES[0].body,
        filename="report.txt",
        media_type="text/plain",
    )
    _process_to_ready(owner, CLEAN_STAGING_FIXTURES[0].body)

    migration_factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )
    other_tenant_id, other_workspace_id, _other_user_id = seed_active_membership(
        migration_factory,
        subject="staging-foreign",
        role="researcher",
    )
    other_scope = TenantScope(tenant_id=other_tenant_id, workspace_id=other_workspace_id)
    other_factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )
    with transaction(other_factory, scope=other_scope) as session:
        document = owner.service.get_document(session, owner.document_id)
        assert document is None


def test_duplicate_finalize_and_worker_delivery_are_idempotent(
    postgres_urls: dict[str, str],
) -> None:
    fixture = _create_fixture(
        postgres_urls,
        subject="staging-dup-delivery",
        body=CLEAN_STAGING_FIXTURES[0].body,
        filename="report.txt",
        media_type="text/plain",
    )
    fixture.store.seed_object(fixture.ref, CLEAN_STAGING_FIXTURES[0].body)
    _finalize(fixture)
    _finalize(fixture)

    with transaction(fixture.factory, scope=fixture.scope) as session:
        finalized_count = session.scalar(
            select(func.count())
            .select_from(IngestionEvent)
            .where(
                IngestionEvent.job_id == fixture.job_id,
                IngestionEvent.code == "upload_finalized",
            )
        )
        assert int(finalized_count or 0) == 1

    worker = JobWorker(
        repository=JobRepository(),
        settings=WorkerSettings(worker_id="staging-verify-worker"),
        handlers={"ingestion.verify": IngestionVerifyHandler(fixture.service)},
    )
    with transaction(fixture.factory, scope=fixture.scope) as session:
        job_row = session.scalar(select(Job).where(Job.id == fixture.job_id))
        assert job_row is not None
        first = worker.process_queue_message(message_from_job(job_row), session)
        second = worker.process_queue_message(message_from_job(job_row), session)
    assert first == MessageDisposition.ACK
    assert second == MessageDisposition.ACK
    assert _document_status(fixture) == DocumentStatus.READY.value

    with transaction(fixture.factory, scope=fixture.scope) as session:
        ready_count = session.scalar(
            select(func.count())
            .select_from(IngestionEvent)
            .where(
                IngestionEvent.job_id == fixture.job_id,
                IngestionEvent.code == "ready",
            )
        )
        assert int(ready_count or 0) == 1
        assert fixture.service.ingestion_repository.count_chunks(session, fixture.version_id) >= 1


def test_presigned_post_expires_and_requires_kms(postgres_urls: dict[str, str]) -> None:
    fixture = _create_fixture(
        postgres_urls,
        subject="staging-presign",
        body=CLEAN_STAGING_FIXTURES[0].body,
        filename="report.txt",
        media_type="text/plain",
    )
    post = fixture.store.posts[-1]
    assert post.expires_at > datetime.now(tz=UTC)
    assert post.expires_at <= datetime.now(tz=UTC) + timedelta(seconds=601)
    assert {"x-amz-server-side-encryption": "aws:kms"} in post.conditions
    assert post.fields["x-amz-meta-sha256"] == hashlib.sha256(CLEAN_STAGING_FIXTURES[0].body).hexdigest()


def test_exact_duplicate_does_not_create_chunks_for_new_version(
    postgres_urls: dict[str, str],
) -> None:
    first = _create_fixture(
        postgres_urls,
        subject="staging-dup-a",
        body=CLEAN_STAGING_FIXTURES[0].body,
        filename="report.txt",
        media_type="text/plain",
    )
    _process_to_ready(first, CLEAN_STAGING_FIXTURES[0].body)

    duplicate = _create_fixture(
        postgres_urls,
        subject="staging-dup-b",
        body=CLEAN_STAGING_FIXTURES[0].body,
        filename="report.txt",
        media_type="text/plain",
    )
    duplicate.store.seed_object(duplicate.ref, CLEAN_STAGING_FIXTURES[0].body)
    _finalize(duplicate)
    result = _run_verify(duplicate)

    assert result.result is not None
    assert result.result["code"] == "duplicate_exact"
    with transaction(duplicate.factory, scope=duplicate.scope) as session:
        assert duplicate.service.ingestion_repository.count_chunks(session, duplicate.version_id) == 0
        document = session.scalar(select(Document).where(Document.id == duplicate.document_id))
        assert document is not None
        assert document.current_version_id == first.version_id
