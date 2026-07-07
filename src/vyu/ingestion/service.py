from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.vyu.api.schemas.uploads import PresignUploadRequest, PresignUploadResponse
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.authz import Action, AuthorizationPolicy, Principal, ResourceScope, Role, WorkspaceMembership
from src.vyu.db.repositories.audit import AuditRepository, NewAuditEvent
from src.vyu.ingestion.contracts import DocumentStatus, can_transition_document_status
from src.vyu.ingestion.models import Document, DocumentVersion, IngestionEvent
from src.vyu.ingestion.object_store import (
    QuarantineObjectHead,
    QuarantineObjectRef,
    QuarantineObjectStore,
    RecordingQuarantineObjectStore,
    VERIFY_TERMINAL_CODES,
    build_quarantine_key,
    metadata_value,
    stream_sha256_hex,
)
from src.vyu.ingestion.settings import IngestionSettings
from src.vyu.ingestion.validation import UploadValidationError, validate_upload_request
from src.vyu.jobs.contracts import JobRecord, NewJob
from src.vyu.jobs.models import Job, OutboxEvent
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
    authorization_policy: AuthorizationPolicy = AuthorizationPolicy()
    job_repository: JobRepository = JobRepository()

    @classmethod
    def from_settings(cls, settings: IngestionSettings) -> IngestionService:
        registry = SourceRegistry.read(settings.source_registry_path)
        object_store = RecordingQuarantineObjectStore(
            bucket=settings.quarantine_bucket,
            region=settings.s3_region,
            kms_key_id=settings.s3_kms_key_id,
            expiry_seconds=settings.presign_expiry_seconds,
        )
        return cls(settings=settings, source_registry=registry, object_store=object_store)

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

        session.add(
            Document(
                id=document_id,
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
                source_id=body.source_id,
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
                version=1,
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

        job_id = self._latest_job_id_for_version(session, document_id, version_id)
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

        terminal_event = self._get_terminal_verify_event(session, job.id)
        if terminal_event is not None:
            return IngestionVerifyResult(
                outcome="complete",
                result={
                    "status": terminal_event.status,
                    "code": terminal_event.code,
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
        return IngestionVerifyResult(
            outcome="complete",
            result={"status": DocumentStatus.SCANNING.value, "code": "object_verified"},
        )

    def _get_version(self, session: Session, version_id: UUID) -> DocumentVersion | None:
        row = session.scalar(select(DocumentVersion).where(DocumentVersion.id == version_id))
        return row if isinstance(row, DocumentVersion) else None

    def _latest_job_id_for_version(
        self,
        session: Session,
        document_id: UUID,
        version_id: UUID,
    ) -> UUID | None:
        del document_id
        row = session.scalar(
            select(Job.id)
            .where(
                Job.kind == "ingestion.verify",
                Job.payload["version_id"].as_string() == str(version_id),
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
