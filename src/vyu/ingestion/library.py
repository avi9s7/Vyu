from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.vyu.api.schemas.evidence_documents import (
    REPROCESS_ROUTE,
    DocumentChunkItem,
    DocumentDetailResponse,
    DocumentEventItem,
    DocumentEventListResponse,
    DocumentListResponse,
    DocumentSummary,
    DocumentVersionDetail,
    DocumentVersionSummary,
    DocumentVersionListResponse,
    IngestionJobDetailResponse,
    IngestionJobEventItem,
    ReprocessDocumentRequest,
    ReprocessDocumentResponse,
    RetentionRequest,
    RetentionRequestResponse,
)
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.authz import Action, AuthorizationPolicy, Principal, ResourceScope, Role, WorkspaceMembership
from src.vyu.db.repositories.audit import AuditRepository, NewAuditEvent
from src.vyu.ingestion.contracts import DocumentStatus, can_transition_document_status
from src.vyu.ingestion.models import Document, DocumentVersion, IngestionEvent
from src.vyu.ingestion.repository import IngestionRepository
from src.vyu.ingestion.settings import IngestionSettings
from src.vyu.jobs.contracts import IdempotencyRequest, NewJob
from src.vyu.jobs.models import OutboxEvent
from src.vyu.jobs.repository import JobRepository


class EvidenceLibraryError(Exception):
    def __init__(self, *, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class EvidenceLibraryNotFound(EvidenceLibraryError):
    def __init__(self) -> None:
        super().__init__(
            code="document_not_found",
            message="Document was not found.",
            status_code=404,
        )


class EvidenceLibraryJobNotFound(EvidenceLibraryError):
    def __init__(self) -> None:
        super().__init__(
            code="job_not_found",
            message="Ingestion job was not found.",
            status_code=404,
        )


_SENSITIVE_METADATA_KEYS = frozenset({"parsed_document_full"})
_SENSITIVE_DETAIL_KEYS = frozenset({"object_key", "quarantine_key", "upload_fields"})


@dataclass(frozen=True)
class EvidenceLibraryService:
    settings: IngestionSettings
    repository: IngestionRepository = field(default_factory=IngestionRepository)
    authorization_policy: AuthorizationPolicy = field(default_factory=AuthorizationPolicy)
    job_repository: JobRepository = field(default_factory=JobRepository)

    def list_documents(
        self,
        *,
        principal: RequestPrincipal,
        session: Session,
        source_id: str | None,
        status: str | None,
        media_type: str | None,
        created_after: datetime | None,
        created_before: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> DocumentListResponse:
        self._require_read(principal)
        page_size = min(max(limit, 1), self.settings.max_page_size)
        cursor_created_at: datetime | None = None
        cursor_id: UUID | None = None
        if cursor is not None:
            cursor_created_at, cursor_id = decode_document_cursor(cursor)
        rows = self.repository.list_documents(
            session,
            source_id=source_id,
            status=status,
            media_type=media_type,
            created_after=created_after,
            created_before=created_before,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
            limit=page_size + 1,
        )
        has_more = len(rows) > page_size
        page_rows = rows[:page_size]
        items = [self._to_summary(session, row) for row in page_rows]
        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            next_cursor = encode_document_cursor(last.created_at, last.id)
        return DocumentListResponse(items=items, next_cursor=next_cursor)

    def get_document(
        self,
        *,
        principal: RequestPrincipal,
        session: Session,
        document_id: UUID,
    ) -> DocumentDetailResponse:
        self._require_read(principal)
        document = self.repository.get_document(session, document_id)
        if document is None:
            raise EvidenceLibraryNotFound()
        current_version = (
            self.repository.get_version(session, document.current_version_id)
            if document.current_version_id is not None
            else None
        )
        return DocumentDetailResponse(
            document_id=str(document.id),
            source_id=document.source_id,
            external_id=document.external_id,
            title=document.title,
            status=document.status,
            current_version_id=str(document.current_version_id)
            if document.current_version_id is not None
            else None,
            created_at=document.created_at.isoformat(),
            updated_at=document.updated_at.isoformat(),
            current_version=self._to_version_summary(current_version) if current_version else None,
            block_summary=self._block_summary(session, document),
        )

    def list_versions(
        self,
        *,
        principal: RequestPrincipal,
        session: Session,
        document_id: UUID,
    ) -> DocumentVersionListResponse:
        self._require_read(principal)
        if self.repository.get_document(session, document_id) is None:
            raise EvidenceLibraryNotFound()
        versions = self.repository.list_versions(session, document_id)
        return DocumentVersionListResponse(
            items=[self._to_version_summary(version) for version in versions]
        )

    def get_version(
        self,
        *,
        principal: RequestPrincipal,
        session: Session,
        document_id: UUID,
        version_id: UUID,
    ) -> DocumentVersionDetail:
        self._require_read(principal)
        document = self.repository.get_document(session, document_id)
        version = self.repository.get_version(session, version_id)
        if document is None or version is None or version.document_id != document_id:
            raise EvidenceLibraryNotFound()
        chunks: list[DocumentChunkItem] = []
        if document.status == DocumentStatus.READY.value and document.current_version_id == version.id:
            for chunk in self.repository.list_chunks(session, version.id):
                chunks.append(
                    DocumentChunkItem(
                        ordinal=chunk.ordinal,
                        citation_id=chunk.citation_id,
                        text=chunk.text,
                        token_count=chunk.token_count,
                        page_from=chunk.page_from,
                        page_to=chunk.page_to,
                        section=chunk.section,
                    )
                )
        return DocumentVersionDetail(
            version_id=str(version.id),
            version=version.version,
            sha256=version.sha256,
            size_bytes=int(version.size_bytes or 0),
            media_type=version.media_type,
            filename=version.filename,
            parser_name=version.parser_name,
            parser_version=version.parser_version,
            page_count=version.page_count,
            malware_status=version.malware_status,
            phi_status=version.phi_status,
            created_at=version.created_at.isoformat(),
            metadata=sanitize_version_metadata(version.metadata_json),
            chunks=chunks,
        )

    def list_document_events(
        self,
        *,
        principal: RequestPrincipal,
        session: Session,
        document_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> DocumentEventListResponse:
        self._require_read(principal)
        if self.repository.get_document(session, document_id) is None:
            raise EvidenceLibraryNotFound()
        page_size = min(max(limit, 1), self.settings.max_page_size)
        cursor_sequence = int(cursor) if cursor is not None else None
        rows = self.repository.list_document_events(
            session,
            document_id=document_id,
            cursor_sequence=cursor_sequence,
            limit=page_size + 1,
        )
        has_more = len(rows) > page_size
        page_rows = rows[:page_size]
        items = [self._to_event_item(row) for row in page_rows]
        next_cursor = str(page_rows[-1].sequence) if has_more and page_rows else None
        return DocumentEventListResponse(items=items, next_cursor=next_cursor)

    def get_ingestion_job(
        self,
        *,
        principal: RequestPrincipal,
        session: Session,
        job_id: UUID,
    ) -> IngestionJobDetailResponse:
        self._require_read(principal)
        job = self.job_repository.get_job(job_id, session)
        if job is None:
            raise EvidenceLibraryJobNotFound()
        events = self.repository.list_job_events(
            session,
            job_id=job_id,
            cursor_sequence=None,
            limit=self.settings.max_page_size,
        )
        payload = {
            key: value
            for key, value in job.payload.items()
            if key in {"document_id", "version_id", "policy_version"}
        }
        return IngestionJobDetailResponse(
            job_id=str(job.id),
            kind=job.kind,
            status=job.status,
            attempt=job.attempt,
            payload=payload,
            result=dict(job.result) if job.result else None,
            error_code=job.error_code,
            created_at=job.created_at.isoformat(),
            updated_at=job.updated_at.isoformat(),
            events=[
                IngestionJobEventItem(
                    sequence=event.sequence,
                    status=event.status,
                    code=event.code,
                    safe_message=event.safe_message,
                    created_at=event.created_at.isoformat(),
                )
                for event in events
            ],
        )

    def reprocess_document(
        self,
        *,
        principal: RequestPrincipal,
        session: Session,
        document_id: UUID,
        body: ReprocessDocumentRequest,
        idempotency_key: str,
        request_id: str,
        trace_id: str,
    ) -> ReprocessDocumentResponse:
        self._require_manage(principal)
        document = self.repository.get_document(session, document_id)
        if document is None:
            raise EvidenceLibraryNotFound()
        source_version_id = body.version_id or document.current_version_id
        if source_version_id is None:
            raise EvidenceLibraryError(
                code="version_not_found",
                message="No version is available to reprocess.",
                status_code=404,
            )
        source_version = self.repository.get_version(session, source_version_id)
        if source_version is None or source_version.document_id != document_id:
            raise EvidenceLibraryError(
                code="version_not_found",
                message="Source version was not found.",
                status_code=404,
            )
        request_sha256 = hashlib.sha256(
            json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()

        def create_resource() -> tuple[str, str, int]:
            new_version_id = uuid4()
            new_job_id = uuid4()
            outbox_id = uuid4()
            version_number = self.repository.next_version_number(session, document_id)
            session.add(
                DocumentVersion(
                    id=new_version_id,
                    tenant_id=document.tenant_id,
                    workspace_id=document.workspace_id,
                    document_id=document_id,
                    version=version_number,
                    original_bucket=source_version.original_bucket,
                    original_key=source_version.original_key,
                    original_version_id=source_version.original_version_id,
                    sha256=source_version.sha256,
                    size_bytes=source_version.size_bytes,
                    media_type=source_version.media_type,
                    filename=source_version.filename,
                    metadata_json={
                        "reprocess_from_version_id": str(source_version.id),
                        "target_parser_version": body.target_parser_version,
                        "target_chunker_version": body.target_chunker_version,
                    },
                )
            )
            self.job_repository.create_job(
                NewJob(
                    id=new_job_id,
                    tenant_id=document.tenant_id,
                    workspace_id=document.workspace_id,
                    kind="ingestion.verify",
                    payload={
                        "document_id": str(document_id),
                        "version_id": str(new_version_id),
                        "policy_version": self.settings.policy_version,
                        "reprocess": True,
                    },
                ),
                session,
            )
            session.add(
                OutboxEvent(
                    id=outbox_id,
                    tenant_id=document.tenant_id,
                    workspace_id=document.workspace_id,
                    topic="jobs",
                    aggregate_type="job",
                    aggregate_id=str(new_job_id),
                    payload={
                        "schema_version": 1,
                        "message_id": str(outbox_id),
                        "job_id": str(new_job_id),
                        "tenant_id": str(document.tenant_id),
                        "workspace_id": str(document.workspace_id),
                        "kind": "ingestion.verify",
                        "attempt": 0,
                        "created_at": datetime.now(tz=UTC).isoformat(),
                    },
                )
            )
            if document.status != DocumentStatus.READY.value and can_transition_document_status(
                document.status,
                DocumentStatus.SCANNING.value,
            ):
                document.status = DocumentStatus.SCANNING.value
            session.add(
                IngestionEvent(
                    id=uuid4(),
                    tenant_id=document.tenant_id,
                    workspace_id=document.workspace_id,
                    document_id=document_id,
                    job_id=new_job_id,
                    sequence=1,
                    status=DocumentStatus.SCANNING.value,
                    code="reprocess_requested",
                    safe_message="Document reprocess requested.",
                    details={"version_id": str(new_version_id)},
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
                    event_type="document_reprocess_requested",
                    resource_type="document",
                    resource_id=str(document_id),
                    outcome="success",
                    payload_sha256=request_sha256,
                    details={
                        "source_version_id": str(source_version.id),
                        "new_version_id": str(new_version_id),
                        "job_id": str(new_job_id),
                    },
                )
            )
            session.flush()
            return ("ingestion_reprocess", f"{new_version_id}|{new_job_id}", 202)

        result = self.job_repository.get_or_create_idempotent(
            IdempotencyRequest(
                tenant_id=document.tenant_id,
                actor_id=principal.subject,
                route=REPROCESS_ROUTE.format(document_id=document_id),
                key=idempotency_key,
                request_sha256=request_sha256,
                expires_at=datetime.now(tz=UTC) + timedelta(hours=24),
            ),
            create_resource,
            session,
        )
        version_id, job_id = result.resource_id.split("|", 1)
        return ReprocessDocumentResponse(
            document_id=str(document_id),
            version_id=version_id,
            job_id=job_id,
            status="accepted",
            idempotent=not result.created,
        )

    def request_retention(
        self,
        *,
        principal: RequestPrincipal,
        session: Session,
        document_id: UUID,
        body: RetentionRequest,
        request_id: str,
        trace_id: str,
    ) -> RetentionRequestResponse:
        self._require_manage(principal)
        document = self.repository.get_document(session, document_id)
        if document is None:
            raise EvidenceLibraryNotFound()
        if not can_transition_document_status(document.status, DocumentStatus.DELETED.value):
            raise EvidenceLibraryError(
                code="invalid_document_status",
                message="Document cannot be scheduled for retention in its current state.",
                status_code=409,
            )
        document.status = DocumentStatus.DELETED.value
        job_id = self._latest_job_id(session, document_id)
        if job_id is not None:
            sequence = session.scalar(
                select(func.max(IngestionEvent.sequence)).where(IngestionEvent.job_id == job_id)
            )
            session.add(
                IngestionEvent(
                    id=uuid4(),
                    tenant_id=document.tenant_id,
                    workspace_id=document.workspace_id,
                    document_id=document_id,
                    job_id=job_id,
                    sequence=int(sequence or 0) + 1,
                    status=DocumentStatus.DELETED.value,
                    code="retention_requested",
                    safe_message="Retention was requested for the document.",
                    details={"reason": body.reason},
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
                event_type="document_retention_requested",
                resource_type="document",
                resource_id=str(document_id),
                outcome="success",
                payload_sha256=hashlib.sha256(body.reason.encode("utf-8")).hexdigest(),
                details={"reason": body.reason},
            )
        )
        session.flush()
        return RetentionRequestResponse(
            document_id=str(document_id),
            status=document.status,
        )

    def _to_summary(self, session: Session, document: Document) -> DocumentSummary:
        current_version = (
            self.repository.get_version(session, document.current_version_id)
            if document.current_version_id is not None
            else None
        )
        return DocumentSummary(
            document_id=str(document.id),
            source_id=document.source_id,
            external_id=document.external_id,
            title=document.title,
            status=document.status,
            media_type=current_version.media_type if current_version else None,
            created_at=document.created_at.isoformat(),
            updated_at=document.updated_at.isoformat(),
        )

    def _to_version_summary(self, version: DocumentVersion) -> DocumentVersionSummary:
        return DocumentVersionSummary(
            version_id=str(version.id),
            version=version.version,
            sha256=version.sha256,
            size_bytes=int(version.size_bytes or 0),
            media_type=version.media_type,
            filename=version.filename,
            parser_name=version.parser_name,
            parser_version=version.parser_version,
            page_count=version.page_count,
            malware_status=version.malware_status,
            phi_status=version.phi_status,
            created_at=version.created_at.isoformat(),
        )

    def _to_event_item(self, event: IngestionEvent) -> DocumentEventItem:
        return DocumentEventItem(
            sequence=event.sequence,
            status=event.status,
            code=event.code,
            safe_message=event.safe_message,
            created_at=event.created_at.isoformat(),
            details=sanitize_event_details(event.details),
        )

    def _block_summary(self, session: Session, document: Document) -> dict[str, str] | None:
        if document.status != DocumentStatus.BLOCKED.value:
            return None
        job_id = self._latest_job_id(session, document.id)
        if job_id is None:
            return None
        row = session.scalar(
            select(IngestionEvent)
            .where(
                IngestionEvent.job_id == job_id,
                IngestionEvent.status == DocumentStatus.BLOCKED.value,
            )
            .order_by(IngestionEvent.sequence.desc())
            .limit(1)
        )
        if not isinstance(row, IngestionEvent):
            return None
        return {
            "code": row.code or "blocked",
            "safe_message": row.safe_message or "Document is blocked.",
        }

    def _latest_job_id(self, session: Session, document_id: UUID) -> UUID | None:
        row = session.scalar(
            select(IngestionEvent.job_id)
            .where(
                IngestionEvent.document_id == document_id,
                IngestionEvent.code == "presign_issued",
            )
            .limit(1)
        )
        return row if isinstance(row, UUID) else None

    def _require_read(self, principal: RequestPrincipal) -> None:
        self._require_action(principal, Action.READ_ARTIFACT)

    def _require_manage(self, principal: RequestPrincipal) -> None:
        self._require_action(principal, Action.MANAGE_WORKSPACE)

    def _require_action(self, principal: RequestPrincipal, action: Action) -> None:
        try:
            role = Role(principal.role)
        except ValueError as exc:
            raise EvidenceLibraryError(
                code="authorization_failed",
                message="Authorization failed.",
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
                action,
                ResourceScope(
                    tenant_id=str(principal.tenant_id),
                    workspace_id=str(principal.workspace_id),
                ),
            )
        except PermissionError as exc:
            raise EvidenceLibraryError(
                code="authorization_failed",
                message=str(exc),
                status_code=403,
            ) from exc


def encode_document_cursor(created_at: datetime, document_id: UUID) -> str:
    return f"{created_at.isoformat()}|{document_id}"


def decode_document_cursor(cursor: str) -> tuple[datetime, UUID]:
    created_at_raw, document_id_raw = cursor.split("|", 1)
    return datetime.fromisoformat(created_at_raw), UUID(document_id_raw)


def sanitize_version_metadata(metadata: dict[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in metadata.items():
        if key in _SENSITIVE_METADATA_KEYS:
            continue
        if key.endswith("_key") or "quarantine" in key.lower():
            continue
        if isinstance(value, dict):
            sanitized[key] = {
                inner_key: inner_value
                for inner_key, inner_value in value.items()
                if inner_key not in {"finding_values", "matched_text"}
            }
        else:
            sanitized[key] = value
    return sanitized


def sanitize_event_details(details: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in details.items()
        if key not in _SENSITIVE_DETAIL_KEYS and "quarantine" not in key.lower()
    }
