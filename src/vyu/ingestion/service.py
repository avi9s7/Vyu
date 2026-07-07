from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.vyu.api.schemas.uploads import PresignUploadRequest, PresignUploadResponse
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.authz import Action, AuthorizationPolicy, Principal, ResourceScope, Role, WorkspaceMembership
from src.vyu.db.repositories.audit import AuditRepository, NewAuditEvent
from src.vyu.ingestion.chunking import CHUNKER_NAME, CHUNKER_VERSION, chunk_parsed_document
from src.vyu.ingestion.classifiers import RulesSensitiveDataClassifier, SensitiveDataClassifier
from src.vyu.ingestion.contracts import DocumentStatus, MalwareStatus, PhiStatus, can_transition_document_status
from src.vyu.ingestion.malware import EicarRulesMalwareScanner, MalwareScanner
from src.vyu.ingestion.metrics import IngestionMetricsRecorder
from src.vyu.ingestion.models import Document, DocumentVersion, EvidenceObject, IngestionEvent
from src.vyu.ingestion.normalization import build_normalized_document_bytes
from src.vyu.ingestion.object_store import (
    CHUNKING_TERMINAL_CODES,
    EvidenceObjectRef,
    EvidenceObjectStore,
    ObjectNotFoundError,
    PromotionError,
    QuarantineObjectHead,
    QuarantineObjectRef,
    QuarantineObjectStore,
    RecordingEvidenceObjectStore,
    RecordingQuarantineObjectStore,
    PARSING_TERMINAL_CODES,
    SCREENING_TERMINAL_CODES,
    VERIFY_BLOCK_CODES,
    VERIFY_TERMINAL_CODES,
    build_evidence_normalized_key,
    build_evidence_original_key,
    build_quarantine_key,
    metadata_value,
    stream_sha256_hex,
)
from src.vyu.ingestion.parsers.base import ParsedDocument
from src.vyu.ingestion.parsers.isolated import parse_in_process, run_isolated_parse
from src.vyu.ingestion.repository import IngestionRepository
from src.vyu.ingestion.sampling import bounded_text_sample
from src.vyu.ingestion.settings import IngestionSettings
from src.vyu.ingestion.validation import UploadValidationError, validate_upload_request
from src.vyu.jobs.contracts import JobRecord, NewJob
from src.vyu.jobs.models import OutboxEvent
from src.vyu.jobs.repository import JobRepository
from src.vyu.sources import SourceRegistry


class IngestionServiceError(Exception):
    def __init__(self, *, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class FinalizeUploadResult:
    document_id: str
    version_id: str
    status: str
    idempotent: bool


@dataclass(frozen=True)
class IngestionVerifyResult:
    outcome: str
    result: dict[str, object] | None = None
    error_code: str | None = None
    retryable: bool = False


@dataclass(frozen=True)
class IngestionService:
    settings: IngestionSettings
    source_registry: SourceRegistry
    object_store: QuarantineObjectStore
    evidence_store: EvidenceObjectStore
    ingestion_repository: IngestionRepository = field(default_factory=IngestionRepository)
    malware_scanner: MalwareScanner = field(default_factory=EicarRulesMalwareScanner)
    sensitive_classifier: SensitiveDataClassifier = field(default_factory=RulesSensitiveDataClassifier)
    authorization_policy: AuthorizationPolicy = AuthorizationPolicy()
    job_repository: JobRepository = JobRepository()
    metrics: IngestionMetricsRecorder = field(default_factory=IngestionMetricsRecorder)

    @classmethod
    def from_settings(cls, settings: IngestionSettings) -> IngestionService:
        registry = SourceRegistry.read(settings.source_registry_path)
        object_store = RecordingQuarantineObjectStore(
            bucket=settings.quarantine_bucket,
            region=settings.s3_region,
            kms_key_id=settings.s3_kms_key_id,
            expiry_seconds=settings.presign_expiry_seconds,
        )
        evidence_store = RecordingEvidenceObjectStore(
            bucket=settings.evidence_bucket,
            kms_key_id=settings.s3_kms_key_id,
        )
        return cls(
            settings=settings,
            source_registry=registry,
            object_store=object_store,
            evidence_store=evidence_store,
        )

    def create_presigned_upload(
        self,
        *,
        body: PresignUploadRequest,
        principal: RequestPrincipal,
        request_id: str,
        trace_id: str,
        session: Session,
    ) -> PresignUploadResponse:
        self._require_upload_permission(principal)
        try:
            validated = validate_upload_request(
                filename=body.filename,
                media_type=body.media_type,
                size_bytes=body.size_bytes,
                sha256=body.sha256,
                contains_phi=body.contains_phi,
                max_upload_bytes=self.settings.max_upload_bytes,
            )
        except UploadValidationError as exc:
            raise IngestionServiceError(
                code="validation_error",
                message=str(exc),
                status_code=422,
            ) from exc

        self._validate_source(
            source_id=body.source_id,
            principal=principal,
        )

        document_id = uuid4()
        version_number = 1
        existing_document: Document | None = None
        if body.external_id:
            existing_document = self.ingestion_repository.find_document_by_external_id(
                session,
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
                source_id=body.source_id,
                external_id=body.external_id,
            )
            if existing_document is not None:
                document_id = existing_document.id
                version_number = self.ingestion_repository.next_version_number(
                    session,
                    document_id,
                )
                existing_document.status = DocumentStatus.AWAITING_UPLOAD.value

        version_id = uuid4()
        job_id = uuid4()
        outbox_id = uuid4()
        audit_id = uuid4()
        event_id = uuid4()
        now = datetime.now(tz=UTC)
        object_key = build_quarantine_key(
            env=self.settings.env,
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            document_id=document_id,
            version_id=version_id,
            filename=validated.filename,
        )
        object_ref = QuarantineObjectRef(
            bucket=self.settings.quarantine_bucket,
            key=object_key,
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            document_id=document_id,
            version_id=version_id,
            filename=validated.filename,
            media_type=validated.media_type,
            size_bytes=validated.size_bytes,
            sha256=validated.sha256,
        )
        presigned = self.object_store.create_presigned_upload(object_ref)
        request_sha256 = normalized_request_sha256(body)

        if existing_document is None:
            session.add(
                Document(
                    id=document_id,
                    tenant_id=principal.tenant_id,
                    workspace_id=principal.workspace_id,
                    source_id=body.source_id,
                    external_id=body.external_id,
                    status=DocumentStatus.AWAITING_UPLOAD.value,
                    created_by=principal.user_id,
                )
            )
        session.add(
            DocumentVersion(
                id=version_id,
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
                document_id=document_id,
                version=version_number,
                original_bucket=self.settings.quarantine_bucket,
                original_key=object_key,
                sha256=validated.sha256,
                size_bytes=validated.size_bytes,
                media_type=validated.media_type,
                filename=validated.filename,
            )
        )
        self.job_repository.create_job(
            NewJob(
                id=job_id,
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
                kind="ingestion.verify",
                payload={
                    "document_id": str(document_id),
                    "version_id": str(version_id),
                    "policy_version": self.settings.policy_version,
                },
            ),
            session,
        )
        session.add(
            OutboxEvent(
                id=outbox_id,
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
                topic="jobs",
                aggregate_type="job",
                aggregate_id=str(job_id),
                payload={
                    "schema_version": 1,
                    "message_id": str(outbox_id),
                    "job_id": str(job_id),
                    "tenant_id": str(principal.tenant_id),
                    "workspace_id": str(principal.workspace_id),
                    "kind": "ingestion.verify",
                    "attempt": 0,
                    "created_at": now.isoformat(),
                },
            )
        )
        session.add(
            IngestionEvent(
                id=event_id,
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
                document_id=document_id,
                job_id=job_id,
                sequence=1,
                status=DocumentStatus.AWAITING_UPLOAD.value,
                code="presign_issued",
                safe_message="Upload URL issued.",
                details={"version_id": str(version_id)},
            )
        )
        AuditRepository(session).append(
            NewAuditEvent(
                id=audit_id,
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
                actor_type="user",
                actor_id=principal.subject,
                request_id=request_id,
                trace_id=trace_id,
                event_type="upload_presign_issued",
                resource_type="document",
                resource_id=str(document_id),
                outcome="success",
                payload_sha256=request_sha256,
                details={
                    "job_id": str(job_id),
                    "version_id": str(version_id),
                    "source_id": body.source_id,
                },
            )
        )
        session.flush()
        self.metrics.record_upload()
        return PresignUploadResponse(
            document_id=str(document_id),
            version_id=str(version_id),
            job_id=str(job_id),
            upload_url=presigned.url,
            upload_fields=presigned.fields,
            expires_at=presigned.expires_at.isoformat(),
            object_key=object_key,
        )

    def get_document(self, session: Session, document_id: UUID) -> Document | None:
        row = session.scalar(select(Document).where(Document.id == document_id))
        return row if isinstance(row, Document) else None

    def finalize_upload(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        principal: RequestPrincipal,
        request_id: str,
        trace_id: str,
        session: Session,
    ) -> FinalizeUploadResult:
        self._require_upload_permission(principal)
        document = self.get_document(session, document_id)
        version = self._get_version(session, version_id)
        if document is None or version is None or version.document_id != document_id:
            raise IngestionServiceError(
                code="document_not_found",
                message="Document or version was not found.",
                status_code=404,
            )
        if document.tenant_id != principal.tenant_id or document.workspace_id != principal.workspace_id:
            raise IngestionServiceError(
                code="document_not_found",
                message="Document or version was not found.",
                status_code=404,
            )

        if document.status != DocumentStatus.AWAITING_UPLOAD.value:
            if document.status in {
                DocumentStatus.UPLOADED.value,
                DocumentStatus.SCANNING.value,
                DocumentStatus.PARSING.value,
                DocumentStatus.CHUNKING.value,
                DocumentStatus.READY.value,
                DocumentStatus.BLOCKED.value,
                DocumentStatus.FAILED.value,
            }:
                return FinalizeUploadResult(
                    document_id=str(document_id),
                    version_id=str(version_id),
                    status=document.status,
                    idempotent=True,
                )
            raise IngestionServiceError(
                code="invalid_document_status",
                message="Document cannot be finalized in its current state.",
                status_code=409,
            )

        if not can_transition_document_status(document.status, DocumentStatus.UPLOADED.value):
            raise IngestionServiceError(
                code="invalid_document_status",
                message="Document cannot be finalized in its current state.",
                status_code=409,
            )

        job_id = self._job_id_for_document(session, document_id)
        document.status = DocumentStatus.UPLOADED.value
        sequence = self._next_event_sequence(session, job_id) if job_id is not None else 2
        if job_id is not None:
            session.add(
                IngestionEvent(
                    id=uuid4(),
                    tenant_id=document.tenant_id,
                    workspace_id=document.workspace_id,
                    document_id=document_id,
                    job_id=job_id,
                    sequence=sequence,
                    status=DocumentStatus.UPLOADED.value,
                    code="upload_finalized",
                    safe_message="Upload finalized.",
                    details={"version_id": str(version_id)},
                )
            )
        AuditRepository(session).append(
            NewAuditEvent(
                id=uuid4(),
                tenant_id=document.tenant_id,
                workspace_id=document.workspace_id,
                actor_type="user",
                actor_id=principal.subject,
                request_id=request_id,
                trace_id=trace_id,
                event_type="upload_finalized",
                resource_type="document",
                resource_id=str(document_id),
                outcome="success",
                payload_sha256=hashlib.sha256(
                    f"{document_id}:{version_id}".encode("utf-8")
                ).hexdigest(),
                details={"version_id": str(version_id)},
            )
        )
        session.flush()
        self.metrics.record_upload_bytes(version.size_bytes)
        return FinalizeUploadResult(
            document_id=str(document_id),
            version_id=str(version_id),
            status=document.status,
            idempotent=False,
        )

    def run_ingestion_verify(
        self,
        *,
        job: JobRecord,
        session: Session,
        heartbeat: Callable[[], None],
    ) -> IngestionVerifyResult:
        document_id = UUID(str(job.payload["document_id"]))
        version_id = UUID(str(job.payload["version_id"]))

        chunking_terminal = self._get_terminal_chunking_event(session, job.id)
        if chunking_terminal is not None:
            return IngestionVerifyResult(
                outcome="complete",
                result={
                    "status": chunking_terminal.status,
                    "code": chunking_terminal.code,
                    "idempotent": True,
                },
            )

        parsing_terminal = self._get_terminal_parsing_event(session, job.id)
        if parsing_terminal is not None:
            if parsing_terminal.code != "parsing_passed":
                return IngestionVerifyResult(
                    outcome="complete",
                    result={
                        "status": parsing_terminal.status,
                        "code": parsing_terminal.code,
                        "idempotent": True,
                    },
                )
            document = self.get_document(session, document_id)
            version = self._get_version(session, version_id)
            if document is None or version is None or version.document_id != document_id:
                return IngestionVerifyResult(
                    outcome="terminal_failure",
                    error_code="document_not_found",
                )
            parsed = self._load_parsed_document(version)
            if parsed is None:
                return IngestionVerifyResult(
                    outcome="terminal_failure",
                    error_code="parsed_document_missing",
                )
            return self._run_chunk_and_promote(
                session=session,
                document=document,
                version=version,
                parsed=parsed,
                job_id=job.id,
                heartbeat=heartbeat,
            )

        screening_terminal = self._get_terminal_screening_event(session, job.id)
        if screening_terminal is not None:
            if screening_terminal.code != "screening_passed":
                return IngestionVerifyResult(
                    outcome="complete",
                    result={
                        "status": screening_terminal.status,
                        "code": screening_terminal.code,
                        "idempotent": True,
                    },
                )
            document = self.get_document(session, document_id)
            version = self._get_version(session, version_id)
            if document is None or version is None or version.document_id != document_id:
                return IngestionVerifyResult(
                    outcome="terminal_failure",
                    error_code="document_not_found",
                )
            return self._run_document_parsing(
                session=session,
                document=document,
                version=version,
                job_id=job.id,
                heartbeat=heartbeat,
            )

        verify_terminal = self._get_terminal_verify_event(session, job.id)
        if verify_terminal is not None and verify_terminal.code in VERIFY_BLOCK_CODES:
            return IngestionVerifyResult(
                outcome="complete",
                result={
                    "status": verify_terminal.status,
                    "code": verify_terminal.code,
                    "idempotent": True,
                },
            )

        document = self.get_document(session, document_id)
        version = self._get_version(session, version_id)
        if document is None or version is None or version.document_id != document_id:
            return IngestionVerifyResult(
                outcome="terminal_failure",
                error_code="document_not_found",
            )

        if verify_terminal is not None and verify_terminal.code == "object_verified":
            return self._run_security_screening(
                session=session,
                document=document,
                version=version,
                job_id=job.id,
                heartbeat=heartbeat,
            )

        if document.status == DocumentStatus.AWAITING_UPLOAD.value:
            return IngestionVerifyResult(
                outcome="retry",
                error_code="upload_not_finalized",
                retryable=True,
            )

        if document.status == DocumentStatus.BLOCKED.value:
            return IngestionVerifyResult(
                outcome="complete",
                result={"status": "blocked", "idempotent": True},
            )

        if document.status not in {
            DocumentStatus.UPLOADED.value,
            DocumentStatus.SCANNING.value,
        }:
            return IngestionVerifyResult(
                outcome="terminal_failure",
                error_code="invalid_document_status",
            )

        if document.status == DocumentStatus.UPLOADED.value:
            if not can_transition_document_status(
                document.status,
                DocumentStatus.SCANNING.value,
            ):
                return IngestionVerifyResult(
                    outcome="terminal_failure",
                    error_code="invalid_document_status",
                )
            document.status = DocumentStatus.SCANNING.value
            self._append_ingestion_event(
                session=session,
                document=document,
                job_id=job.id,
                status=DocumentStatus.SCANNING.value,
                code="verify_started",
                safe_message="Object verification started.",
                details={"version_id": str(version_id)},
            )
            session.flush()

        heartbeat()
        object_ref = self._ref_from_version(version)
        head = self.object_store.head_object(object_ref)
        if head is None:
            return self._block_after_verify_failure(
                session=session,
                document=document,
                version=version,
                job_id=job.id,
                code="object_missing",
                safe_message="Uploaded object was not found.",
                request_id=str(job.id),
                trace_id=str(job.id),
            )

        mismatch_code = self._validate_object_head(head, object_ref, version)
        if mismatch_code is not None:
            return self._block_after_verify_failure(
                session=session,
                document=document,
                version=version,
                job_id=job.id,
                code=mismatch_code,
                safe_message="Uploaded object failed integrity checks.",
                request_id=str(job.id),
                trace_id=str(job.id),
            )

        if head.checksum_sha256:
            if head.checksum_sha256.lower() != (version.sha256 or "").lower():
                return self._block_after_verify_failure(
                    session=session,
                    document=document,
                    version=version,
                    job_id=job.id,
                    code="checksum_mismatch",
                    safe_message="Uploaded object checksum did not match.",
                    request_id=str(job.id),
                    trace_id=str(job.id),
                )
        else:
            computed = self._stream_object_sha256(object_ref, heartbeat=heartbeat)
            if computed.lower() != (version.sha256 or "").lower():
                return self._block_after_verify_failure(
                    session=session,
                    document=document,
                    version=version,
                    job_id=job.id,
                    code="checksum_mismatch",
                    safe_message="Uploaded object checksum did not match.",
                    request_id=str(job.id),
                    trace_id=str(job.id),
                )

        self._append_ingestion_event(
            session=session,
            document=document,
            job_id=job.id,
            status=DocumentStatus.SCANNING.value,
            code="object_verified",
            safe_message="Uploaded object passed integrity checks.",
            details={"version_id": str(version_id)},
        )
        AuditRepository(session).append(
            NewAuditEvent(
                id=uuid4(),
                tenant_id=document.tenant_id,
                workspace_id=document.workspace_id,
                actor_type="system",
                actor_id="ingestion.verify",
                request_id=str(job.id),
                trace_id=str(job.id),
                event_type="upload_object_verified",
                resource_type="document",
                resource_id=str(document_id),
                outcome="success",
                payload_sha256=version.sha256 or "",
                details={"version_id": str(version_id), "job_id": str(job.id)},
            )
        )
        session.flush()
        return self._run_security_screening(
            session=session,
            document=document,
            version=version,
            job_id=job.id,
            heartbeat=heartbeat,
        )

    def _get_terminal_screening_event(
        self,
        session: Session,
        job_id: UUID,
    ) -> IngestionEvent | None:
        row = session.scalar(
            select(IngestionEvent)
            .where(
                IngestionEvent.job_id == job_id,
                IngestionEvent.code.in_(tuple(SCREENING_TERMINAL_CODES)),
            )
            .order_by(IngestionEvent.sequence.desc())
            .limit(1)
        )
        return row if isinstance(row, IngestionEvent) else None

    def _get_terminal_parsing_event(
        self,
        session: Session,
        job_id: UUID,
    ) -> IngestionEvent | None:
        row = session.scalar(
            select(IngestionEvent)
            .where(
                IngestionEvent.job_id == job_id,
                IngestionEvent.code.in_(tuple(PARSING_TERMINAL_CODES)),
            )
            .order_by(IngestionEvent.sequence.desc())
            .limit(1)
        )
        return row if isinstance(row, IngestionEvent) else None

    def _get_terminal_chunking_event(
        self,
        session: Session,
        job_id: UUID,
    ) -> IngestionEvent | None:
        row = session.scalar(
            select(IngestionEvent)
            .where(
                IngestionEvent.job_id == job_id,
                IngestionEvent.code.in_(tuple(CHUNKING_TERMINAL_CODES)),
            )
            .order_by(IngestionEvent.sequence.desc())
            .limit(1)
        )
        return row if isinstance(row, IngestionEvent) else None

    def _run_security_screening(
        self,
        *,
        session: Session,
        document: Document,
        version: DocumentVersion,
        job_id: UUID,
        heartbeat: Callable[[], None],
    ) -> IngestionVerifyResult:
        if document.status not in {
            DocumentStatus.SCANNING.value,
            DocumentStatus.UPLOADED.value,
        }:
            return IngestionVerifyResult(
                outcome="terminal_failure",
                error_code="invalid_document_status",
            )
        if document.status == DocumentStatus.UPLOADED.value:
            document.status = DocumentStatus.SCANNING.value
            session.flush()

        object_ref = self._ref_from_version(version)
        heartbeat()
        scan_started = time.perf_counter()
        object_bytes = self._read_object_bytes(object_ref)
        malware_result = self.malware_scanner.scan(
            BytesIO(object_bytes),
            filename=version.filename or "upload.bin",
        )
        version.malware_status = malware_result.status.value
        version.metadata_json = {
            **version.metadata_json,
            "malware_scanner": {
                "name": malware_result.scanner_name,
                "version": malware_result.scanner_version,
                "definition_timestamp": malware_result.definition_timestamp,
                "content_hash": malware_result.content_hash,
                "finding_categories": list(malware_result.finding_categories),
            },
        }
        if malware_result.status is not MalwareStatus.CLEAN:
            self.metrics.record_scan_latency_ms(IngestionMetricsRecorder.elapsed_ms(scan_started))
            self.metrics.record_malware_infected()
            code = f"malware_{malware_result.status.value}"
            return self._block_after_screening_failure(
                session=session,
                document=document,
                version=version,
                job_id=job_id,
                code=code,
                safe_message="Malware screening blocked the upload.",
                request_id=str(job_id),
                trace_id=str(job_id),
            )

        heartbeat()
        text_sample = bounded_text_sample(iter([object_bytes]))
        classification = self.sensitive_classifier.classify(
            text_sample,
            {
                "filename": version.filename or "",
                "media_type": version.media_type or "",
            },
        )
        version.phi_status = classification.status.value
        version.metadata_json = {
            **version.metadata_json,
            "phi_classifier": {
                "name": classification.classifier_name,
                "version": classification.classifier_version,
                "definition_timestamp": classification.definition_timestamp,
                "content_hash": classification.content_hash,
                "finding_categories": list(classification.finding_categories),
            },
        }
        if classification.status is not PhiStatus.NON_PHI:
            self.metrics.record_scan_latency_ms(IngestionMetricsRecorder.elapsed_ms(scan_started))
            if classification.status is PhiStatus.UNKNOWN:
                self.metrics.record_phi_unknown()
            else:
                self.metrics.record_phi_blocked()
            code = f"phi_{classification.status.value}"
            return self._block_after_screening_failure(
                session=session,
                document=document,
                version=version,
                job_id=job_id,
                code=code,
                safe_message="Sensitive-data screening blocked the upload.",
                request_id=str(job_id),
                trace_id=str(job_id),
            )

        self.metrics.record_scan_latency_ms(IngestionMetricsRecorder.elapsed_ms(scan_started))
        self._append_ingestion_event(
            session=session,
            document=document,
            job_id=job_id,
            status=DocumentStatus.SCANNING.value,
            code="screening_passed",
            safe_message="Malware and sensitive-data screening passed.",
            details={"version_id": str(version.id)},
        )
        AuditRepository(session).append(
            NewAuditEvent(
                id=uuid4(),
                tenant_id=document.tenant_id,
                workspace_id=document.workspace_id,
                actor_type="system",
                actor_id="ingestion.verify",
                request_id=str(job_id),
                trace_id=str(job_id),
                event_type="upload_screening_passed",
                resource_type="document",
                resource_id=str(document.id),
                outcome="success",
                payload_sha256=version.sha256 or "",
                details={"version_id": str(version.id), "job_id": str(job_id)},
            )
        )
        session.flush()
        return self._run_document_parsing(
            session=session,
            document=document,
            version=version,
            job_id=job_id,
            heartbeat=heartbeat,
        )

    def _read_object_bytes(self, ref: QuarantineObjectRef) -> bytes:
        if ref.bucket == self.settings.evidence_bucket:
            evidence_ref = EvidenceObjectRef(
                bucket=ref.bucket,
                key=ref.key,
                tenant_id=ref.tenant_id,
                workspace_id=ref.workspace_id,
                document_id=ref.document_id,
                version_id=ref.version_id,
                object_type="original",
                sha256=ref.sha256,
                media_type=ref.media_type,
            )
            return b"".join(self.evidence_store.iter_object_chunks(evidence_ref))
        try:
            return b"".join(self.object_store.iter_object_chunks(ref))
        except ObjectNotFoundError:
            if ref.bucket == self.settings.quarantine_bucket:
                raise
            evidence_ref = EvidenceObjectRef(
                bucket=ref.bucket,
                key=ref.key,
                tenant_id=ref.tenant_id,
                workspace_id=ref.workspace_id,
                document_id=ref.document_id,
                version_id=ref.version_id,
                object_type="original",
                sha256=ref.sha256,
                media_type=ref.media_type,
            )
            return b"".join(self.evidence_store.iter_object_chunks(evidence_ref))

    def _block_after_screening_failure(
        self,
        *,
        session: Session,
        document: Document,
        version: DocumentVersion,
        job_id: UUID,
        code: str,
        safe_message: str,
        request_id: str,
        trace_id: str,
    ) -> IngestionVerifyResult:
        self.metrics.record_scan_error()
        self.metrics.record_quarantine_age_seconds(
            IngestionMetricsRecorder.age_seconds_since(document.created_at)
        )
        if can_transition_document_status(document.status, DocumentStatus.BLOCKED.value):
            document.status = DocumentStatus.BLOCKED.value
        self._append_ingestion_event(
            session=session,
            document=document,
            job_id=job_id,
            status=DocumentStatus.BLOCKED.value,
            code=code,
            safe_message=safe_message,
            details={"version_id": str(version.id)},
        )
        AuditRepository(session).append(
            NewAuditEvent(
                id=uuid4(),
                tenant_id=document.tenant_id,
                workspace_id=document.workspace_id,
                actor_type="system",
                actor_id="ingestion.verify",
                request_id=request_id,
                trace_id=trace_id,
                event_type="upload_screening_blocked",
                resource_type="document",
                resource_id=str(document.id),
                outcome="blocked",
                payload_sha256=version.sha256 or "",
                details={"version_id": str(version.id), "code": code},
            )
        )
        session.flush()
        return IngestionVerifyResult(
            outcome="complete",
            result={"status": DocumentStatus.BLOCKED.value, "code": code},
        )

    def _run_document_parsing(
        self,
        *,
        session: Session,
        document: Document,
        version: DocumentVersion,
        job_id: UUID,
        heartbeat: Callable[[], None],
    ) -> IngestionVerifyResult:
        if document.status not in {
            DocumentStatus.SCANNING.value,
            DocumentStatus.PARSING.value,
        }:
            return IngestionVerifyResult(
                outcome="terminal_failure",
                error_code="invalid_document_status",
            )
        if document.status == DocumentStatus.SCANNING.value:
            if not can_transition_document_status(
                document.status,
                DocumentStatus.PARSING.value,
            ):
                return IngestionVerifyResult(
                    outcome="terminal_failure",
                    error_code="invalid_document_status",
                )
            document.status = DocumentStatus.PARSING.value
            self._append_ingestion_event(
                session=session,
                document=document,
                job_id=job_id,
                status=DocumentStatus.PARSING.value,
                code="parsing_started",
                safe_message="Document parsing started.",
                details={"version_id": str(version.id)},
            )
            session.flush()

        filename = version.filename or "upload.bin"
        media_type = version.media_type or "application/octet-stream"
        heartbeat()
        object_bytes = self._read_object_bytes(self._ref_from_version(version))
        try:
            if self.settings.use_isolated_parser:
                parse_result = run_isolated_parse(
                    object_bytes,
                    filename=filename,
                    media_type=media_type,
                    timeout_seconds=self.settings.parse_timeout_seconds,
                )
            else:
                parse_result = parse_in_process(
                    object_bytes,
                    filename=filename,
                    media_type=media_type,
                )
        except ValueError:
            return self._block_after_parsing_failure(
                session=session,
                document=document,
                version=version,
                job_id=job_id,
                code="parser_unsupported_format",
                safe_message="Unsupported document format.",
                request_id=str(job_id),
                trace_id=str(job_id),
            )

        if not parse_result.succeeded or parse_result.document is None:
            failure = parse_result.failure
            failure_code = failure.code if failure is not None else "malformed_document"
            return self._block_after_parsing_failure(
                session=session,
                document=document,
                version=version,
                job_id=job_id,
                code=f"parser_{failure_code}",
                safe_message="Document parsing blocked the upload.",
                request_id=str(job_id),
                trace_id=str(job_id),
            )

        parsed = parse_result.document
        version.parser_name = parse_result.parser_name
        version.parser_version = parse_result.parser_version
        version.page_count = len(parsed.pages) if parsed.pages else 0
        version.metadata_json = {
            **version.metadata_json,
            "parsed_document": parsed.to_metadata_summary(),
            "parsed_document_full": parsed.to_dict(),
        }
        if parsed.title and not document.title:
            document.title = parsed.title[:500]

        self._append_ingestion_event(
            session=session,
            document=document,
            job_id=job_id,
            status=DocumentStatus.PARSING.value,
            code="parsing_passed",
            safe_message="Document parsing completed.",
            details={"version_id": str(version.id)},
        )
        AuditRepository(session).append(
            NewAuditEvent(
                id=uuid4(),
                tenant_id=document.tenant_id,
                workspace_id=document.workspace_id,
                actor_type="system",
                actor_id="ingestion.verify",
                request_id=str(job_id),
                trace_id=str(job_id),
                event_type="upload_parsing_passed",
                resource_type="document",
                resource_id=str(document.id),
                outcome="success",
                payload_sha256=version.sha256 or "",
                details={
                    "version_id": str(version.id),
                    "parser_name": parse_result.parser_name,
                    "parser_version": parse_result.parser_version,
                },
            )
        )
        session.flush()
        return self._run_chunk_and_promote(
            session=session,
            document=document,
            version=version,
            parsed=parsed,
            job_id=job_id,
            heartbeat=heartbeat,
        )

    def _load_parsed_document(self, version: DocumentVersion) -> ParsedDocument | None:
        payload = version.metadata_json.get("parsed_document_full")
        if isinstance(payload, dict):
            return ParsedDocument.from_dict(payload)
        return None

    def _run_chunk_and_promote(
        self,
        *,
        session: Session,
        document: Document,
        version: DocumentVersion,
        parsed: ParsedDocument,
        job_id: UUID,
        heartbeat: Callable[[], None],
    ) -> IngestionVerifyResult:
        sha256 = version.sha256 or ""
        duplicate = self.ingestion_repository.find_ready_version_by_sha256(
            session,
            tenant_id=document.tenant_id,
            workspace_id=document.workspace_id,
            sha256=sha256,
        )
        if duplicate is not None and duplicate.version_id != version.id:
            document.status = DocumentStatus.READY.value
            document.current_version_id = duplicate.version_id
            version.metadata_json = {
                **version.metadata_json,
                "duplicate_of_version_id": str(duplicate.version_id),
            }
            self._append_ingestion_event(
                session=session,
                document=document,
                job_id=job_id,
                status=DocumentStatus.READY.value,
                code="duplicate_exact",
                safe_message="Exact duplicate reused an existing ready version.",
                details={
                    "version_id": str(version.id),
                    "canonical_version_id": str(duplicate.version_id),
                },
            )
            session.flush()
            self.metrics.record_duplicate()
            return IngestionVerifyResult(
                outcome="complete",
                result={
                    "status": DocumentStatus.READY.value,
                    "code": "duplicate_exact",
                    "canonical_version_id": str(duplicate.version_id),
                },
            )

        if document.status == DocumentStatus.PARSING.value:
            if not can_transition_document_status(
                document.status,
                DocumentStatus.CHUNKING.value,
            ):
                return IngestionVerifyResult(
                    outcome="terminal_failure",
                    error_code="invalid_document_status",
                )
            document.status = DocumentStatus.CHUNKING.value
            self._append_ingestion_event(
                session=session,
                document=document,
                job_id=job_id,
                status=DocumentStatus.CHUNKING.value,
                code="chunking_started",
                safe_message="Chunking and promotion started.",
                details={"version_id": str(version.id)},
            )
            session.flush()
        elif document.status != DocumentStatus.CHUNKING.value:
            return IngestionVerifyResult(
                outcome="terminal_failure",
                error_code="invalid_document_status",
            )

        heartbeat()
        normalized_body, normalized_sha256 = build_normalized_document_bytes(
            parsed,
            parser_name=version.parser_name or "unknown",
            parser_version=version.parser_version or "unknown",
            chunker_name=CHUNKER_NAME,
            chunker_version=CHUNKER_VERSION,
        )
        normalized_key = build_evidence_normalized_key(
            env=self.settings.env,
            tenant_id=version.tenant_id,
            workspace_id=version.workspace_id,
            document_id=version.document_id,
            version_id=version.id,
        )
        normalized_ref = EvidenceObjectRef(
            bucket=self.settings.evidence_bucket,
            key=normalized_key,
            tenant_id=version.tenant_id,
            workspace_id=version.workspace_id,
            document_id=version.document_id,
            version_id=version.id,
            object_type="normalized",
            sha256=normalized_sha256,
            media_type="application/json",
        )
        original_key = build_evidence_original_key(
            env=self.settings.env,
            tenant_id=version.tenant_id,
            workspace_id=version.workspace_id,
            document_id=version.document_id,
            version_id=version.id,
            filename=version.filename or "upload.bin",
        )
        original_ref = EvidenceObjectRef(
            bucket=self.settings.evidence_bucket,
            key=original_key,
            tenant_id=version.tenant_id,
            workspace_id=version.workspace_id,
            document_id=version.document_id,
            version_id=version.id,
            object_type="original",
            sha256=sha256,
            media_type=version.media_type or "application/octet-stream",
        )
        quarantine_ref = self._ref_from_version(version)

        try:
            normalized_version_id = self.evidence_store.put_object(
                normalized_ref,
                normalized_body,
            )
            original_version_id = self.evidence_store.copy_from_quarantine(
                quarantine_ref,
                original_ref,
                quarantine_store=self.object_store,
            )
        except PromotionError:
            return self._fail_after_promotion_error(
                session=session,
                document=document,
                version=version,
                job_id=job_id,
                code="promotion_failed",
                safe_message="Evidence promotion failed.",
            )

        normalized_head = self.evidence_store.head_object(normalized_ref)
        original_head = self.evidence_store.head_object(original_ref)
        if (
            normalized_head is None
            or original_head is None
            or normalized_head.checksum_sha256 != normalized_sha256
            or original_head.checksum_sha256 != sha256
        ):
            return self._fail_after_promotion_error(
                session=session,
                document=document,
                version=version,
                job_id=job_id,
                code="promotion_failed",
                safe_message="Evidence destination verification failed.",
            )

        chunk_drafts = chunk_parsed_document(
            parsed,
            document_id=document.id,
            version_number=version.version,
            target_tokens=self.settings.chunk_target_tokens,
            max_tokens=self.settings.chunk_max_tokens,
            overlap_tokens=self.settings.chunk_overlap_tokens,
        )
        self.ingestion_repository.replace_chunks(
            session,
            tenant_id=document.tenant_id,
            workspace_id=document.workspace_id,
            document_version_id=version.id,
            chunks=chunk_drafts,
            normalized_object_sha256=normalized_sha256,
        )
        version.normalized_bucket = self.settings.evidence_bucket
        version.normalized_key = normalized_key
        version.normalized_version_id = normalized_version_id
        version.original_bucket = self.settings.evidence_bucket
        version.original_key = original_key
        version.original_version_id = original_version_id
        version.metadata_json = {
            **version.metadata_json,
            "normalized_object_sha256": normalized_sha256,
            "chunker_name": CHUNKER_NAME,
            "chunker_version": CHUNKER_VERSION,
        }

        evidence_objects = (
            EvidenceObject(
                id=uuid4(),
                tenant_id=document.tenant_id,
                workspace_id=document.workspace_id,
                document_version_id=version.id,
                object_type="normalized",
                bucket=self.settings.evidence_bucket,
                key=normalized_key,
                version_id=normalized_version_id,
                sha256=normalized_sha256,
                media_type="application/json",
                metadata_json={
                    "parser_name": version.parser_name,
                    "parser_version": version.parser_version,
                    "chunker_name": CHUNKER_NAME,
                    "chunker_version": CHUNKER_VERSION,
                },
            ),
            EvidenceObject(
                id=uuid4(),
                tenant_id=document.tenant_id,
                workspace_id=document.workspace_id,
                document_version_id=version.id,
                object_type="original",
                bucket=self.settings.evidence_bucket,
                key=original_key,
                version_id=original_version_id,
                sha256=sha256,
                media_type=version.media_type,
                metadata_json={},
            ),
        )
        self.ingestion_repository.replace_evidence_objects(
            session,
            tenant_id=document.tenant_id,
            workspace_id=document.workspace_id,
            document_version_id=version.id,
            objects=evidence_objects,
        )

        document.status = DocumentStatus.READY.value
        document.current_version_id = version.id
        self._append_ingestion_event(
            session=session,
            document=document,
            job_id=job_id,
            status=DocumentStatus.READY.value,
            code="ready",
            safe_message="Document is ready for retrieval.",
            details={"version_id": str(version.id), "chunk_count": len(chunk_drafts)},
        )
        AuditRepository(session).append(
            NewAuditEvent(
                id=uuid4(),
                tenant_id=document.tenant_id,
                workspace_id=document.workspace_id,
                actor_type="system",
                actor_id="ingestion.verify",
                request_id=str(job_id),
                trace_id=str(job_id),
                event_type="upload_ready",
                resource_type="document",
                resource_id=str(document.id),
                outcome="success",
                payload_sha256=version.sha256 or "",
                details={
                    "version_id": str(version.id),
                    "chunk_count": len(chunk_drafts),
                },
            )
        )
        self.metrics.record_ready_latency_ms(
            IngestionMetricsRecorder.age_seconds_since(document.created_at) * 1000
        )
        session.flush()
        return IngestionVerifyResult(
            outcome="complete",
            result={"status": DocumentStatus.READY.value, "code": "ready"},
        )

    def _fail_after_promotion_error(
        self,
        *,
        session: Session,
        document: Document,
        version: DocumentVersion,
        job_id: UUID,
        code: str,
        safe_message: str,
    ) -> IngestionVerifyResult:
        self._append_ingestion_event(
            session=session,
            document=document,
            job_id=job_id,
            status=document.status,
            code=code,
            safe_message=safe_message,
            details={"version_id": str(version.id)},
        )
        session.flush()
        return IngestionVerifyResult(
            outcome="retry",
            error_code=code,
            retryable=True,
        )

    def _block_after_parsing_failure(
        self,
        *,
        session: Session,
        document: Document,
        version: DocumentVersion,
        job_id: UUID,
        code: str,
        safe_message: str,
        request_id: str,
        trace_id: str,
    ) -> IngestionVerifyResult:
        self.metrics.record_parser_failure(media_type=version.media_type or "unknown")
        self.metrics.record_quarantine_age_seconds(
            IngestionMetricsRecorder.age_seconds_since(document.created_at)
        )
        if can_transition_document_status(document.status, DocumentStatus.BLOCKED.value):
            document.status = DocumentStatus.BLOCKED.value
        self._append_ingestion_event(
            session=session,
            document=document,
            job_id=job_id,
            status=DocumentStatus.BLOCKED.value,
            code=code,
            safe_message=safe_message,
            details={"version_id": str(version.id)},
        )
        AuditRepository(session).append(
            NewAuditEvent(
                id=uuid4(),
                tenant_id=document.tenant_id,
                workspace_id=document.workspace_id,
                actor_type="system",
                actor_id="ingestion.verify",
                request_id=request_id,
                trace_id=trace_id,
                event_type="upload_parsing_blocked",
                resource_type="document",
                resource_id=str(document.id),
                outcome="blocked",
                payload_sha256=version.sha256 or "",
                details={"version_id": str(version.id), "code": code},
            )
        )
        session.flush()
        return IngestionVerifyResult(
            outcome="complete",
            result={"status": DocumentStatus.BLOCKED.value, "code": code},
        )

    def _get_version(self, session: Session, version_id: UUID) -> DocumentVersion | None:
        row = session.scalar(select(DocumentVersion).where(DocumentVersion.id == version_id))
        return row if isinstance(row, DocumentVersion) else None

    def _job_id_for_document(self, session: Session, document_id: UUID) -> UUID | None:
        row = session.scalar(
            select(IngestionEvent.job_id)
            .where(
                IngestionEvent.document_id == document_id,
                IngestionEvent.code == "presign_issued",
            )
            .limit(1)
        )
        return row if isinstance(row, UUID) else None

    def _next_event_sequence(self, session: Session, job_id: UUID) -> int:
        current = session.scalar(
            select(func.max(IngestionEvent.sequence)).where(IngestionEvent.job_id == job_id)
        )
        return int(current or 0) + 1

    def _get_terminal_verify_event(
        self,
        session: Session,
        job_id: UUID,
    ) -> IngestionEvent | None:
        row = session.scalar(
            select(IngestionEvent)
            .where(
                IngestionEvent.job_id == job_id,
                IngestionEvent.code.in_(tuple(VERIFY_TERMINAL_CODES)),
            )
            .order_by(IngestionEvent.sequence.desc())
            .limit(1)
        )
        return row if isinstance(row, IngestionEvent) else None

    def _ref_from_version(self, version: DocumentVersion) -> QuarantineObjectRef:
        return QuarantineObjectRef(
            bucket=version.original_bucket or self.settings.quarantine_bucket,
            key=version.original_key or "",
            tenant_id=version.tenant_id,
            workspace_id=version.workspace_id,
            document_id=version.document_id,
            version_id=version.id,
            filename=version.filename or "upload.bin",
            media_type=version.media_type or "application/octet-stream",
            size_bytes=int(version.size_bytes or 0),
            sha256=version.sha256 or "",
        )

    def _validate_object_head(
        self,
        head: QuarantineObjectHead,
        ref: QuarantineObjectRef,
        version: DocumentVersion,
    ) -> str | None:
        if head.bucket != ref.bucket or head.key != ref.key:
            return "scope_metadata_mismatch"
        if head.content_length <= 0:
            return "size_mismatch"
        if head.content_length != int(version.size_bytes or 0):
            return "size_mismatch"
        if head.server_side_encryption != "aws:kms":
            return "encryption_missing"
        if head.ssekms_key_id != self.settings.s3_kms_key_id:
            return "encryption_missing"
        if head.content_type != version.media_type:
            return "content_type_mismatch"
        expected_scope = {
            "tenant-id": str(ref.tenant_id),
            "workspace-id": str(ref.workspace_id),
            "document-id": str(ref.document_id),
            "version-id": str(ref.version_id),
        }
        for key, expected in expected_scope.items():
            if metadata_value(head.metadata, key) != expected:
                return "scope_metadata_mismatch"
        return None

    def _stream_object_sha256(
        self,
        ref: QuarantineObjectRef,
        *,
        heartbeat: Callable[[], None],
        chunk_size: int = 1024 * 1024,
    ) -> str:
        def _iter_with_heartbeat():
            for index, chunk in enumerate(
                self.object_store.iter_object_chunks(ref, chunk_size=chunk_size)
            ):
                if index % 8 == 0:
                    heartbeat()
                yield chunk

        return stream_sha256_hex(_iter_with_heartbeat())

    def _block_after_verify_failure(
        self,
        *,
        session: Session,
        document: Document,
        version: DocumentVersion,
        job_id: UUID,
        code: str,
        safe_message: str,
        request_id: str,
        trace_id: str,
    ) -> IngestionVerifyResult:
        if can_transition_document_status(document.status, DocumentStatus.BLOCKED.value):
            document.status = DocumentStatus.BLOCKED.value
        self._append_ingestion_event(
            session=session,
            document=document,
            job_id=job_id,
            status=DocumentStatus.BLOCKED.value,
            code=code,
            safe_message=safe_message,
            details={"version_id": str(version.id)},
        )
        AuditRepository(session).append(
            NewAuditEvent(
                id=uuid4(),
                tenant_id=document.tenant_id,
                workspace_id=document.workspace_id,
                actor_type="system",
                actor_id="ingestion.verify",
                request_id=request_id,
                trace_id=trace_id,
                event_type="upload_object_blocked",
                resource_type="document",
                resource_id=str(document.id),
                outcome="blocked",
                payload_sha256=version.sha256 or "",
                details={"version_id": str(version.id), "code": code},
            )
        )
        session.flush()
        return IngestionVerifyResult(
            outcome="complete",
            result={"status": DocumentStatus.BLOCKED.value, "code": code},
        )

    def _append_ingestion_event(
        self,
        *,
        session: Session,
        document: Document,
        job_id: UUID,
        status: str,
        code: str,
        safe_message: str,
        details: dict[str, object],
    ) -> None:
        session.add(
            IngestionEvent(
                id=uuid4(),
                tenant_id=document.tenant_id,
                workspace_id=document.workspace_id,
                document_id=document.id,
                job_id=job_id,
                sequence=self._next_event_sequence(session, job_id),
                status=status,
                code=code,
                safe_message=safe_message,
                details=details,
            )
        )

    def _require_upload_permission(self, principal: RequestPrincipal) -> None:
        try:
            role = Role(principal.role)
        except ValueError as exc:
            raise IngestionServiceError(
                code="authorization_failed",
                message="Upload permission is required.",
                status_code=403,
            ) from exc
        auth_principal = Principal(
            user_id=str(principal.user_id),
            memberships=(
                WorkspaceMembership(
                    tenant_id=str(principal.tenant_id),
                    workspace_id=str(principal.workspace_id),
                    roles=(role,),
                ),
            ),
        )
        try:
            self.authorization_policy.require(
                auth_principal,
                Action.UPLOAD_DOCUMENT,
                ResourceScope(
                    tenant_id=str(principal.tenant_id),
                    workspace_id=str(principal.workspace_id),
                ),
            )
        except PermissionError as exc:
            raise IngestionServiceError(
                code="authorization_failed",
                message=str(exc),
                status_code=403,
            ) from exc

    def _validate_source(self, *, source_id: str, principal: RequestPrincipal) -> None:
        try:
            self.source_registry.require_approved(
                source_id,
                intended_use="document_upload",
                tenant_id=str(principal.tenant_id),
                workspace_id=str(principal.workspace_id),
            )
        except KeyError as exc:
            raise IngestionServiceError(
                code="validation_error",
                message=f"Unknown source ID: {source_id}",
                status_code=422,
            ) from exc
        except PermissionError as exc:
            raise IngestionServiceError(
                code="validation_error",
                message=str(exc),
                status_code=422,
            ) from exc


def normalized_request_sha256(body: PresignUploadRequest) -> str:
    payload = json.dumps(
        body.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
