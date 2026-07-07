from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from src.vyu.ingestion.chunking import ChunkDraft
from src.vyu.ingestion.contracts import DocumentStatus
from src.vyu.ingestion.models import Document, DocumentChunk, DocumentVersion, EvidenceObject, IngestionEvent


class ReadyVersionMatch:
    __slots__ = ("document_id", "version_id", "version_number")

    def __init__(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        version_number: int,
    ) -> None:
        self.document_id = document_id
        self.version_id = version_id
        self.version_number = version_number


class IngestionRepository:
    def find_ready_version_by_sha256(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        sha256: str,
    ) -> ReadyVersionMatch | None:
        row = session.execute(
            select(Document.id, DocumentVersion.id, DocumentVersion.version)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(
                Document.tenant_id == tenant_id,
                Document.workspace_id == workspace_id,
                Document.status == DocumentStatus.READY.value,
                DocumentVersion.sha256 == sha256,
            )
            .order_by(DocumentVersion.version.desc())
            .limit(1)
        ).first()
        if row is None:
            return None
        document_id, version_id, version_number = row
        return ReadyVersionMatch(
            document_id=document_id,
            version_id=version_id,
            version_number=int(version_number),
        )

    def find_document_by_external_id(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        source_id: str,
        external_id: str,
    ) -> Document | None:
        row = session.scalar(
            select(Document).where(
                Document.tenant_id == tenant_id,
                Document.workspace_id == workspace_id,
                Document.source_id == source_id,
                Document.external_id == external_id,
            )
        )
        return row if isinstance(row, Document) else None

    def next_version_number(self, session: Session, document_id: UUID) -> int:
        current = session.scalar(
            select(func.max(DocumentVersion.version)).where(
                DocumentVersion.document_id == document_id
            )
        )
        return int(current or 0) + 1

    def count_chunks(self, session: Session, document_version_id: UUID) -> int:
        count = session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_version_id == document_version_id)
        )
        return int(count or 0)

    def get_document(self, session: Session, document_id: UUID) -> Document | None:
        row = session.scalar(select(Document).where(Document.id == document_id))
        return row if isinstance(row, Document) else None

    def get_version(self, session: Session, version_id: UUID) -> DocumentVersion | None:
        row = session.scalar(select(DocumentVersion).where(DocumentVersion.id == version_id))
        return row if isinstance(row, DocumentVersion) else None

    def list_documents(
        self,
        session: Session,
        *,
        source_id: str | None,
        status: str | None,
        media_type: str | None,
        created_after: datetime | None,
        created_before: datetime | None,
        cursor_created_at: datetime | None,
        cursor_id: UUID | None,
        limit: int,
    ) -> list[Document]:
        statement = select(Document).order_by(Document.created_at.desc(), Document.id.desc())
        if source_id is not None:
            statement = statement.where(Document.source_id == source_id)
        if status is not None:
            statement = statement.where(Document.status == status)
        if created_after is not None:
            statement = statement.where(Document.created_at >= created_after)
        if created_before is not None:
            statement = statement.where(Document.created_at <= created_before)
        if media_type is not None:
            statement = statement.join(
                DocumentVersion,
                DocumentVersion.id == Document.current_version_id,
            ).where(DocumentVersion.media_type == media_type)
        if cursor_created_at is not None and cursor_id is not None:
            statement = statement.where(
                or_(
                    Document.created_at < cursor_created_at,
                    and_(
                        Document.created_at == cursor_created_at,
                        Document.id < cursor_id,
                    ),
                )
            )
        return list(session.scalars(statement.limit(limit)).all())

    def list_versions(self, session: Session, document_id: UUID) -> list[DocumentVersion]:
        rows = session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version.desc())
        ).all()
        return list(rows)

    def list_chunks(self, session: Session, document_version_id: UUID) -> list[DocumentChunk]:
        rows = session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_version_id == document_version_id)
            .order_by(DocumentChunk.ordinal.asc())
        ).all()
        return list(rows)

    def list_document_events(
        self,
        session: Session,
        *,
        document_id: UUID,
        cursor_sequence: int | None,
        limit: int,
    ) -> list[IngestionEvent]:
        statement = (
            select(IngestionEvent)
            .where(IngestionEvent.document_id == document_id)
            .order_by(IngestionEvent.sequence.asc())
        )
        if cursor_sequence is not None:
            statement = statement.where(IngestionEvent.sequence > cursor_sequence)
        return list(session.scalars(statement.limit(limit)).all())

    def list_job_events(
        self,
        session: Session,
        *,
        job_id: UUID,
        cursor_sequence: int | None,
        limit: int,
    ) -> list[IngestionEvent]:
        statement = (
            select(IngestionEvent)
            .where(IngestionEvent.job_id == job_id)
            .order_by(IngestionEvent.sequence.asc())
        )
        if cursor_sequence is not None:
            statement = statement.where(IngestionEvent.sequence > cursor_sequence)
        return list(session.scalars(statement.limit(limit)).all())

    def replace_chunks(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        document_version_id: UUID,
        chunks: tuple[ChunkDraft, ...],
        normalized_object_sha256: str,
    ) -> None:
        existing = session.scalars(
            select(DocumentChunk).where(
                DocumentChunk.document_version_id == document_version_id
            )
        ).all()
        for chunk in existing:
            session.delete(chunk)
        for draft in chunks:
            metadata = {
                **draft.metadata_json,
                "normalized_object_sha256": normalized_object_sha256,
            }
            session.add(
                DocumentChunk(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    document_version_id=document_version_id,
                    ordinal=draft.ordinal,
                    citation_id=draft.citation_id,
                    text=draft.text,
                    text_sha256=draft.text_sha256,
                    token_count=draft.token_count,
                    page_from=draft.page_from,
                    page_to=draft.page_to,
                    section=draft.section,
                    metadata_json=metadata,
                )
            )
        session.flush()

    def replace_evidence_objects(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        document_version_id: UUID,
        objects: tuple[EvidenceObject, ...],
    ) -> None:
        existing = session.scalars(
            select(EvidenceObject).where(
                EvidenceObject.document_version_id == document_version_id
            )
        ).all()
        for item in existing:
            session.delete(item)
        for item in objects:
            session.add(item)
        session.flush()
