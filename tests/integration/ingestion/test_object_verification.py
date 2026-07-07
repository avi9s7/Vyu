from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from src.vyu.api.schemas.uploads import PresignUploadRequest
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.ingestion.contracts import DocumentStatus
from src.vyu.ingestion.handler import IngestionVerifyHandler
from src.vyu.ingestion.models import Document, IngestionEvent
from src.vyu.ingestion.object_store import QuarantineObjectRef, RecordingQuarantineObjectStore
from src.vyu.ingestion.service import IngestionService, IngestionVerifyResult
from src.vyu.ingestion.settings import IngestionSettings, MAX_UPLOAD_BYTES
from src.vyu.jobs.contracts import JobRecord
from src.vyu.jobs.models import Job
from src.vyu.jobs.repository import JobRepository
from src.vyu.jobs.worker import (
    JobWorker,
    MessageDisposition,
    WorkerSettings,
    message_from_job,
)
from src.vyu.sources import ProductionSourceRecord, SourceRegistry


@dataclass
class VerificationFixture:
    scope: TenantScope
    factory: object
    service: IngestionService
    store: RecordingQuarantineObjectStore
    principal: RequestPrincipal
    ref: QuarantineObjectRef
    document_id: UUID
    version_id: UUID
    job_id: UUID


@pytest.fixture
def verification_fixture(postgres_urls: dict[str, str]) -> VerificationFixture:
    scope = TenantScope(tenant_id=uuid4(), workspace_id=uuid4())
    factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["app"]))
    )
    store = RecordingQuarantineObjectStore(
        bucket="vyu-test-quarantine",
        region="ap-south-1",
        kms_key_id="arn:aws:kms:ap-south-1:123456789012:key/00000000-0000-0000-0000-000000000000",
        expiry_seconds=600,
    )
    registry = SourceRegistry(
        [
            ProductionSourceRecord(
                source_id="internal_documents",
                display_name="Internal Documents",
                source_type="tenant_documents",
                owner="Vyu",
                license_or_terms="test",
                allowed_uses=["document_upload"],
                approval_status="approved",
            )
        ]
    )
    service = IngestionService(
        settings=IngestionSettings(env="test"),
        source_registry=registry,
        object_store=store,
    )
    principal = RequestPrincipal(
        user_id=uuid4(),
        issuer="https://test.vyu.invalid",
        subject="ingestion-test-user",
        email="ingestion@test.vyu",
        tenant_id=scope.tenant_id,
        workspace_id=scope.workspace_id,
        role="researcher",
        authentication_method="test",
    )
    body_bytes = b"%PDF-1.4 valid upload fixture"
    return _seed_upload(
        scope=scope,
        factory=factory,
        service=service,
        store=store,
        principal=principal,
        body_bytes=body_bytes,
    )


def _seed_upload(
    *,
    scope: TenantScope,
    factory: object,
    service: IngestionService,
    store: RecordingQuarantineObjectStore,
    principal: RequestPrincipal,
    body_bytes: bytes,
    filename: str = "report.pdf",
    media_type: str = "application/pdf",
) -> VerificationFixture:
    sha256 = hashlib.sha256(body_bytes).hexdigest()
    request = PresignUploadRequest(
        filename=filename,
        media_type=media_type,
        size_bytes=len(body_bytes),
        sha256=sha256,
        source_id="internal_documents",
        contains_phi=False,
    )
    with transaction(factory, scope=scope) as session:
        response = service.create_presigned_upload(
            body=request,
            principal=principal,
            request_id="req-presign",
            trace_id="trace-presign",
            session=session,
        )
    document_id = UUID(response.document_id)
    version_id = UUID(response.version_id)
    job_id = UUID(response.job_id)
    ref = QuarantineObjectRef(
        bucket=store.bucket,
        key=response.object_key,
        tenant_id=scope.tenant_id,
        workspace_id=scope.workspace_id,
        document_id=document_id,
        version_id=version_id,
        filename=filename,
        media_type=media_type,
        size_bytes=len(body_bytes),
        sha256=sha256,
    )
    return VerificationFixture(
        scope=scope,
        factory=factory,
        service=service,
        store=store,
        principal=principal,
        ref=ref,
        document_id=document_id,
        version_id=version_id,
        job_id=job_id,
    )


def _finalize(fixture: VerificationFixture) -> None:
    with transaction(fixture.factory, scope=fixture.scope) as session:
        fixture.service.finalize_upload(
            document_id=fixture.document_id,
            version_id=fixture.version_id,
            principal=fixture.principal,
            request_id="req-finalize",
            trace_id="trace-finalize",
            session=session,
        )


def _load_job(fixture: VerificationFixture) -> JobRecord:
    repository = JobRepository()
    with transaction(fixture.factory, scope=fixture.scope) as session:
        job = repository.get_job(fixture.job_id, session)
        assert job is not None
        return job


def _run_verify(
    fixture: VerificationFixture,
    *,
    heartbeat: Callable[[], None] | None = None,
) -> IngestionVerifyResult:
    job = _load_job(fixture)
    with transaction(fixture.factory, scope=fixture.scope) as session:
        return fixture.service.run_ingestion_verify(
            job=job,
            session=session,
            heartbeat=heartbeat or (lambda: None),
        )


def _event_count(fixture: VerificationFixture, code: str) -> int:
    with transaction(fixture.factory, scope=fixture.scope) as session:
        count = session.scalar(
            select(func.count())
            .select_from(IngestionEvent)
            .where(
                IngestionEvent.job_id == fixture.job_id,
                IngestionEvent.code == code,
            )
        )
        return int(count or 0)


def _document_status(fixture: VerificationFixture) -> str:
    with transaction(fixture.factory, scope=fixture.scope) as session:
        document = session.scalar(
            select(Document).where(Document.id == fixture.document_id)
        )
        assert document is not None
        return document.status


def test_verify_valid_object(verification_fixture: VerificationFixture) -> None:
    fixture = verification_fixture
    fixture.store.seed_object(fixture.ref, b"%PDF-1.4 valid upload fixture")
    _finalize(fixture)

    result = _run_verify(fixture)

    assert result.outcome == "complete"
    assert result.result is not None
    assert result.result["code"] == "object_verified"
    assert _document_status(fixture) == DocumentStatus.SCANNING.value
    assert _event_count(fixture, "object_verified") == 1


def test_verify_missing_object_blocks_document(verification_fixture: VerificationFixture) -> None:
    fixture = verification_fixture
    _finalize(fixture)

    result = _run_verify(fixture)

    assert result.outcome == "complete"
    assert result.result is not None
    assert result.result["code"] == "object_missing"
    assert _document_status(fixture) == DocumentStatus.BLOCKED.value


def test_verify_metadata_spoof_blocks_document(verification_fixture: VerificationFixture) -> None:
    fixture = verification_fixture
    fixture.store.seed_object(
        fixture.ref,
        b"%PDF-1.4 valid upload fixture",
        metadata_overrides={"tenant-id": str(uuid4())},
    )
    _finalize(fixture)

    result = _run_verify(fixture)

    assert result.outcome == "complete"
    assert result.result is not None
    assert result.result["code"] == "scope_metadata_mismatch"
    assert _document_status(fixture) == DocumentStatus.BLOCKED.value


def test_verify_checksum_mismatch_blocks_document(verification_fixture: VerificationFixture) -> None:
    fixture = verification_fixture
    original = b"%PDF-1.4 valid upload fixture"
    tampered = original[:-1] + b"X"
    fixture.store.seed_object(
        fixture.ref,
        tampered,
        include_checksum_metadata=False,
    )
    _finalize(fixture)

    result = _run_verify(fixture)

    assert result.outcome == "complete"
    assert result.result is not None
    assert result.result["code"] == "checksum_mismatch"
    assert _document_status(fixture) == DocumentStatus.BLOCKED.value


def test_duplicate_finalize_is_idempotent(verification_fixture: VerificationFixture) -> None:
    fixture = verification_fixture
    _finalize(fixture)
    _finalize(fixture)

    assert _event_count(fixture, "upload_finalized") == 1
    assert _document_status(fixture) == DocumentStatus.UPLOADED.value


def test_duplicate_verify_does_not_repeat_scan(verification_fixture: VerificationFixture) -> None:
    fixture = verification_fixture
    fixture.store.seed_object(fixture.ref, b"%PDF-1.4 valid upload fixture")
    _finalize(fixture)

    first = _run_verify(fixture)
    second = _run_verify(fixture)

    assert first.result is not None
    assert first.result["code"] == "object_verified"
    assert second.result is not None
    assert second.result.get("idempotent") is True
    assert _event_count(fixture, "object_verified") == 1


def test_verify_before_finalize_retries(verification_fixture: VerificationFixture) -> None:
    fixture = verification_fixture
    fixture.store.seed_object(fixture.ref, b"%PDF-1.4 valid upload fixture")

    result = _run_verify(fixture)

    assert result.outcome == "retry"
    assert result.error_code == "upload_not_finalized"
    assert _document_status(fixture) == DocumentStatus.AWAITING_UPLOAD.value


def test_verify_streams_large_object_without_metadata_checksum(
    postgres_urls: dict[str, str],
) -> None:
    scope = TenantScope(tenant_id=uuid4(), workspace_id=uuid4())
    factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["app"]))
    )
    store = RecordingQuarantineObjectStore(
        bucket="vyu-test-quarantine",
        region="ap-south-1",
        kms_key_id="arn:aws:kms:ap-south-1:123456789012:key/00000000-0000-0000-0000-000000000000",
        expiry_seconds=600,
    )
    registry = SourceRegistry(
        [
            ProductionSourceRecord(
                source_id="internal_documents",
                display_name="Internal Documents",
                source_type="tenant_documents",
                owner="Vyu",
                license_or_terms="test",
                allowed_uses=["document_upload"],
                approval_status="approved",
            )
        ]
    )
    service = IngestionService(
        settings=IngestionSettings(env="test"),
        source_registry=registry,
        object_store=store,
    )
    principal = RequestPrincipal(
        user_id=uuid4(),
        issuer="https://test.vyu.invalid",
        subject="ingestion-test-user",
        email="ingestion@test.vyu",
        tenant_id=scope.tenant_id,
        workspace_id=scope.workspace_id,
        role="researcher",
        authentication_method="test",
    )
    body_bytes = b"x" * MAX_UPLOAD_BYTES
    fixture = _seed_upload(
        scope=scope,
        factory=factory,
        service=service,
        store=store,
        principal=principal,
        body_bytes=body_bytes,
        filename="large.bin",
        media_type="application/octet-stream",
    )
    fixture.store.seed_object(
        fixture.ref,
        body_bytes,
        include_checksum_metadata=False,
    )
    _finalize(fixture)

    heartbeats = 0

    def heartbeat() -> None:
        nonlocal heartbeats
        heartbeats += 1

    result = _run_verify(fixture, heartbeat=heartbeat)

    assert result.outcome == "complete"
    assert result.result is not None
    assert result.result["code"] == "object_verified"
    assert heartbeats >= 1
    assert _document_status(fixture) == DocumentStatus.SCANNING.value


def test_worker_processes_ingestion_verify_job(verification_fixture: VerificationFixture) -> None:
    fixture = verification_fixture
    fixture.store.seed_object(fixture.ref, b"%PDF-1.4 valid upload fixture")
    _finalize(fixture)
    worker = JobWorker(
        repository=JobRepository(),
        settings=WorkerSettings(worker_id="verify-worker"),
        handlers={"ingestion.verify": IngestionVerifyHandler(fixture.service)},
    )
    with transaction(fixture.factory, scope=fixture.scope) as session:
        job_row = session.scalar(select(Job).where(Job.id == fixture.job_id))
        assert job_row is not None
        disposition = worker.process_queue_message(message_from_job(job_row), session)
    assert disposition == MessageDisposition.ACK
    assert _document_status(fixture) == DocumentStatus.SCANNING.value
    assert _event_count(fixture, "object_verified") == 1