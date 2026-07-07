from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.vyu.api.schemas.uploads import PresignUploadRequest, PresignUploadResponse
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.authz import Action, AuthorizationPolicy, Principal, ResourceScope, Role, WorkspaceMembership
from src.vyu.db.repositories.audit import AuditRepository, NewAuditEvent
from src.vyu.ingestion.contracts import DocumentStatus
from src.vyu.ingestion.models import Document, DocumentVersion, IngestionEvent
from src.vyu.ingestion.object_store import (
    QuarantineObjectRef,
    QuarantineObjectStore,
    RecordingQuarantineObjectStore,
    build_quarantine_key,
)
from src.vyu.ingestion.settings import IngestionSettings
from src.vyu.ingestion.validation import UploadValidationError, validate_upload_request
from src.vyu.jobs.contracts import NewJob
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
