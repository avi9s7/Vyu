from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.vyu.ingestion.contracts import DocumentStatus
from src.vyu.ingestion.models import Document, DocumentVersion
from src.vyu.retrieval.index_contracts import DocumentVersionRef


@dataclass(frozen=True)
class ReadyDocumentSnapshot:
    document_versions: tuple[DocumentVersionRef, ...]
    document_count: int
    source_ids: tuple[str, ...]


def snapshot_ready_documents(
    session: Session,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    source_ids: tuple[str, ...] | None = None,
) -> ReadyDocumentSnapshot:
    statement = (
        select(
            Document.id,
            Document.source_id,
            Document.current_version_id,
            DocumentVersion.version,
        )
        .join(
            DocumentVersion,
            DocumentVersion.id == Document.current_version_id,
        )
        .where(
            Document.tenant_id == tenant_id,
            Document.workspace_id == workspace_id,
            Document.status == DocumentStatus.READY.value,
            Document.current_version_id.is_not(None),
        )
        .order_by(Document.created_at.asc(), Document.id.asc())
    )
    if source_ids:
        statement = statement.where(Document.source_id.in_(source_ids))
    rows = session.execute(statement).all()
    refs: list[DocumentVersionRef] = []
    seen_sources: set[str] = set()
    for document_id, source_id, version_id, version_number in rows:
        if version_id is None:
            continue
        refs.append(
            DocumentVersionRef(
                document_id=str(document_id),
                version_number=int(version_number),
                document_version_id=str(version_id),
            )
        )
        seen_sources.add(str(source_id))
    resolved_sources = source_ids or tuple(sorted(seen_sources))
    return ReadyDocumentSnapshot(
        document_versions=tuple(refs),
        document_count=len(refs),
        source_ids=resolved_sources,
    )
