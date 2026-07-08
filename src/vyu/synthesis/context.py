from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.vyu.ingestion.models import Document, DocumentChunk, DocumentVersion
from src.vyu.jobs.models import ResearchRun
from src.vyu.policy.repository import PolicyRepository
from src.vyu.research_mcp.hashing import stable_hash
from src.vyu.retrieval.index_contracts import IndexManifest, IndexStatus
from src.vyu.retrieval.models import RetrievalHitRow, RetrievalIndex, RetrievalRun
from src.vyu.synthesis.contracts import (
    EVIDENCE_CONTEXT_BUILDER_VERSION,
    EVIDENCE_ITEM_BEGIN,
    EVIDENCE_ITEM_END,
    UNTRUSTED_EVIDENCE_PREAMBLE,
)


class EvidenceContextBuildError(ValueError):
    """Raised when persisted retrieval evidence cannot be converted into a safe context."""


@dataclass(frozen=True)
class EvidenceContextItem:
    citation_id: str
    title: str
    source_id: str
    source_date: str | None
    evidence_type: str | None
    evidence_quality: str | None
    is_retracted: bool
    has_correction: bool
    excerpt: str
    document_id: str
    document_version_id: UUID
    document_chunk_id: UUID
    location: str
    rank: int
    token_count: int

    def to_json(self) -> dict[str, object]:
        return {
            "citation_id": self.citation_id,
            "title": self.title,
            "source_id": self.source_id,
            "source_date": self.source_date,
            "evidence_type": self.evidence_type,
            "evidence_quality": self.evidence_quality,
            "is_retracted": self.is_retracted,
            "has_correction": self.has_correction,
            "excerpt": self.excerpt,
            "document_id": self.document_id,
            "document_version_id": str(self.document_version_id),
            "document_chunk_id": str(self.document_chunk_id),
            "location": self.location,
            "rank": self.rank,
            "token_count": self.token_count,
        }


@dataclass(frozen=True)
class EvidenceContextExclusion:
    citation_id: str | None
    document_id: str | None
    document_chunk_id: UUID | None
    rank: int | None
    reason: str

    def to_json(self) -> dict[str, object]:
        return {
            "citation_id": self.citation_id,
            "document_id": self.document_id,
            "document_chunk_id": str(self.document_chunk_id) if self.document_chunk_id else None,
            "rank": self.rank,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BuiltEvidenceContext:
    builder_version: str
    research_run_id: UUID
    retrieval_run_id: UUID
    retrieval_index_id: UUID
    policy_version: str
    manifest_checksum: str
    items: tuple[EvidenceContextItem, ...]
    exclusions: tuple[EvidenceContextExclusion, ...]
    context_sha256: str
    token_count: int

    def to_canonical_json(self) -> dict[str, object]:
        return {
            "builder_version": self.builder_version,
            "research_run_id": str(self.research_run_id),
            "retrieval_run_id": str(self.retrieval_run_id),
            "retrieval_index_id": str(self.retrieval_index_id),
            "policy_version": self.policy_version,
            "manifest_checksum": self.manifest_checksum,
            "items": [item.to_json() for item in self.items],
            "exclusions": [exclusion.to_json() for exclusion in self.exclusions],
            "token_count": self.token_count,
        }

    def to_prompt_block(self) -> str:
        lines = [UNTRUSTED_EVIDENCE_PREAMBLE, ""]
        for index, item in enumerate(self.items, start=1):
            lines.extend(
                [
                    f'{EVIDENCE_ITEM_BEGIN} citation_id="{item.citation_id}" index="{index}">>>',
                    item.excerpt,
                    EVIDENCE_ITEM_END,
                    "",
                ]
            )
        return "\n".join(lines).rstrip()


@dataclass(frozen=True)
class LoadedRetrievalHit:
    rank: int
    document_id: str
    passage_id: str
    document_chunk_id: UUID | None
    score_source: str
    score_value: float


@dataclass(frozen=True)
class LoadedChunk:
    id: UUID
    citation_id: str
    text: str
    text_sha256: str
    token_count: int
    page_from: int | None
    page_to: int | None
    section: str | None
    metadata_json: dict[str, object]
    document_version_id: UUID
    document_id: UUID


@dataclass(frozen=True)
class LoadedDocument:
    id: UUID
    source_id: str
    title: str | None
    status: str


@dataclass(frozen=True)
class LoadedDocumentVersion:
    id: UUID
    version: int
    metadata_json: dict[str, object]


@dataclass(frozen=True)
class EvidenceContextInputs:
    tenant_id: UUID
    workspace_id: UUID
    research_run_id: UUID
    retrieval_run_id: UUID
    retrieval_index_id: UUID
    index_status: str
    policy_version: str
    manifest_checksum: str
    approved_source_ids: frozenset[str]
    currently_approved_source_ids: frozenset[str] | None
    hits: tuple[LoadedRetrievalHit, ...]
    chunks_by_id: dict[UUID, LoadedChunk]
    documents_by_id: dict[UUID, LoadedDocument]
    versions_by_id: dict[UUID, LoadedDocumentVersion]


class EvidenceContextBuilder:
    def __init__(self, *, policy_repository: PolicyRepository | None = None) -> None:
        self.policy_repository = policy_repository or PolicyRepository()

    def build_from_session(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        research_run_id: UUID,
        retrieval_run_id: UUID,
        max_tokens: int,
    ) -> BuiltEvidenceContext:
        inputs = self.load_inputs(
            session,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            research_run_id=research_run_id,
            retrieval_run_id=retrieval_run_id,
        )
        return build_evidence_context(inputs, max_tokens=max_tokens)

    def load_inputs(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        research_run_id: UUID,
        retrieval_run_id: UUID,
    ) -> EvidenceContextInputs:
        research_run = session.scalar(
            select(ResearchRun).where(ResearchRun.id == research_run_id)
        )
        if not isinstance(research_run, ResearchRun):
            raise EvidenceContextBuildError("research run was not found")
        if research_run.tenant_id != tenant_id or research_run.workspace_id != workspace_id:
            raise EvidenceContextBuildError("research run is outside the requested scope")

        retrieval_run = session.scalar(
            select(RetrievalRun).where(RetrievalRun.id == retrieval_run_id)
        )
        if not isinstance(retrieval_run, RetrievalRun):
            raise EvidenceContextBuildError("retrieval run was not found")
        if retrieval_run.tenant_id != tenant_id or retrieval_run.workspace_id != workspace_id:
            raise EvidenceContextBuildError("retrieval run is outside the requested scope")
        if retrieval_run.workflow_run_id != str(research_run_id):
            raise EvidenceContextBuildError("retrieval run does not belong to the research run")

        retrieval_index = session.scalar(
            select(RetrievalIndex).where(RetrievalIndex.id == retrieval_run.retrieval_index_id)
        )
        if not isinstance(retrieval_index, RetrievalIndex):
            raise EvidenceContextBuildError("retrieval index was not found")
        if retrieval_index.id != retrieval_run.retrieval_index_id:
            raise EvidenceContextBuildError("retrieval index does not match the recorded run")

        manifest = IndexManifest.from_json(dict(retrieval_index.manifest_json))
        if retrieval_index.status not in {
            IndexStatus.ACTIVE.value,
            IndexStatus.RETIRED.value,
        }:
            raise EvidenceContextBuildError("retrieval index is not ready for synthesis")

        active_policy = self.policy_repository.get_active_source_policy_version(session)
        currently_approved: frozenset[str] | None = None
        if active_policy is not None:
            currently_approved = frozenset(
                record.source_id
                for record in self.policy_repository.list_sources_for_version(
                    session,
                    active_policy.id,
                )
                if record.approval_status == "approved"
            )

        hits = tuple(
            LoadedRetrievalHit(
                rank=row.rank,
                document_id=row.document_id,
                passage_id=row.passage_id,
                document_chunk_id=row.document_chunk_id,
                score_source=row.score_source,
                score_value=row.score_value,
            )
            for row in session.scalars(
                select(RetrievalHitRow)
                .where(RetrievalHitRow.retrieval_run_id == retrieval_run.id)
                .order_by(RetrievalHitRow.rank.asc())
            ).all()
            if isinstance(row, RetrievalHitRow)
        )

        chunk_ids = {
            hit.document_chunk_id for hit in hits if hit.document_chunk_id is not None
        }
        chunks_by_id: dict[UUID, LoadedChunk] = {}
        documents_by_id: dict[UUID, LoadedDocument] = {}
        versions_by_id: dict[UUID, LoadedDocumentVersion] = {}

        if chunk_ids:
            chunk_rows = session.scalars(
                select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids))
            ).all()
            version_ids = {
                chunk.document_version_id
                for chunk in chunk_rows
                if isinstance(chunk, DocumentChunk)
            }
            version_rows = session.scalars(
                select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
            ).all()
            document_ids = {
                version.document_id for version in version_rows if isinstance(version, DocumentVersion)
            }
            document_rows = session.scalars(
                select(Document).where(Document.id.in_(document_ids))
            ).all()

            for version in version_rows:
                if isinstance(version, DocumentVersion):
                    versions_by_id[version.id] = LoadedDocumentVersion(
                        id=version.id,
                        version=version.version,
                        metadata_json=dict(version.metadata_json),
                    )
            version_document_ids = {
                version.id: version.document_id
                for version in version_rows
                if isinstance(version, DocumentVersion)
            }
            for chunk in chunk_rows:
                if isinstance(chunk, DocumentChunk):
                    document_id = version_document_ids.get(chunk.document_version_id)
                    if document_id is None:
                        raise EvidenceContextBuildError("document version was not found for chunk")
                    chunks_by_id[chunk.id] = LoadedChunk(
                        id=chunk.id,
                        citation_id=chunk.citation_id,
                        text=chunk.text,
                        text_sha256=chunk.text_sha256,
                        token_count=chunk.token_count,
                        page_from=chunk.page_from,
                        page_to=chunk.page_to,
                        section=chunk.section,
                        metadata_json=dict(chunk.metadata_json),
                        document_version_id=chunk.document_version_id,
                        document_id=document_id,
                    )
            for document in document_rows:
                if isinstance(document, Document):
                    documents_by_id[document.id] = LoadedDocument(
                        id=document.id,
                        source_id=document.source_id,
                        title=document.title,
                        status=document.status,
                    )

        return EvidenceContextInputs(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            research_run_id=research_run_id,
            retrieval_run_id=retrieval_run_id,
            retrieval_index_id=retrieval_index.id,
            index_status=retrieval_index.status,
            policy_version=manifest.policy_version,
            manifest_checksum=retrieval_index.manifest_checksum,
            approved_source_ids=frozenset(manifest.source_ids),
            currently_approved_source_ids=currently_approved,
            hits=hits,
            chunks_by_id=chunks_by_id,
            documents_by_id=documents_by_id,
            versions_by_id=versions_by_id,
        )


def build_evidence_context(
    inputs: EvidenceContextInputs,
    *,
    max_tokens: int,
) -> BuiltEvidenceContext:
    if max_tokens <= 0:
        raise EvidenceContextBuildError("max_tokens must be positive")

    included: list[EvidenceContextItem] = []
    exclusions: list[EvidenceContextExclusion] = []
    used_tokens = 0

    for hit in sorted(inputs.hits, key=lambda value: value.rank):
        exclusion = _evaluate_hit(inputs, hit)
        if exclusion is not None:
            exclusions.append(exclusion)
            continue

        assert hit.document_chunk_id is not None
        chunk = inputs.chunks_by_id[hit.document_chunk_id]
        document = inputs.documents_by_id[chunk.document_id]
        version = inputs.versions_by_id[chunk.document_version_id]
        item = _materialize_item(hit=hit, chunk=chunk, document=document, version=version)

        if item.is_retracted:
            exclusions.append(
                EvidenceContextExclusion(
                    citation_id=item.citation_id,
                    document_id=item.document_id,
                    document_chunk_id=item.document_chunk_id,
                    rank=item.rank,
                    reason="retracted_evidence",
                )
            )
            continue

        if used_tokens + item.token_count > max_tokens:
            exclusions.append(
                EvidenceContextExclusion(
                    citation_id=item.citation_id,
                    document_id=item.document_id,
                    document_chunk_id=item.document_chunk_id,
                    rank=item.rank,
                    reason="token_budget",
                )
            )
            continue

        included.append(item)
        used_tokens += item.token_count

    canonical = {
        "builder_version": EVIDENCE_CONTEXT_BUILDER_VERSION,
        "research_run_id": str(inputs.research_run_id),
        "retrieval_run_id": str(inputs.retrieval_run_id),
        "retrieval_index_id": str(inputs.retrieval_index_id),
        "policy_version": inputs.policy_version,
        "manifest_checksum": inputs.manifest_checksum,
        "items": [item.to_json() for item in included],
        "exclusions": [exclusion.to_json() for exclusion in exclusions],
        "token_count": used_tokens,
    }
    return BuiltEvidenceContext(
        builder_version=EVIDENCE_CONTEXT_BUILDER_VERSION,
        research_run_id=inputs.research_run_id,
        retrieval_run_id=inputs.retrieval_run_id,
        retrieval_index_id=inputs.retrieval_index_id,
        policy_version=inputs.policy_version,
        manifest_checksum=inputs.manifest_checksum,
        items=tuple(included),
        exclusions=tuple(exclusions),
        context_sha256=stable_hash(canonical),
        token_count=used_tokens,
    )


def _evaluate_hit(
    inputs: EvidenceContextInputs,
    hit: LoadedRetrievalHit,
) -> EvidenceContextExclusion | None:
    if hit.document_chunk_id is None:
        return EvidenceContextExclusion(
            citation_id=hit.passage_id,
            document_id=hit.document_id,
            document_chunk_id=None,
            rank=hit.rank,
            reason="missing_chunk",
        )

    chunk = inputs.chunks_by_id.get(hit.document_chunk_id)
    if chunk is None:
        return EvidenceContextExclusion(
            citation_id=hit.passage_id,
            document_id=hit.document_id,
            document_chunk_id=hit.document_chunk_id,
            rank=hit.rank,
            reason="chunk_not_found",
        )

    if _sha256_text(chunk.text) != chunk.text_sha256:
        raise EvidenceContextBuildError("chunk hash mismatch for persisted retrieval evidence")

    document = inputs.documents_by_id.get(chunk.document_id)
    if document is None:
        return EvidenceContextExclusion(
            citation_id=chunk.citation_id,
            document_id=hit.document_id,
            document_chunk_id=chunk.id,
            rank=hit.rank,
            reason="document_not_found",
        )

    if document.status != "ready":
        return EvidenceContextExclusion(
            citation_id=chunk.citation_id,
            document_id=hit.document_id,
            document_chunk_id=chunk.id,
            rank=hit.rank,
            reason="document_not_ready",
        )

    if document.source_id not in inputs.approved_source_ids:
        return EvidenceContextExclusion(
            citation_id=chunk.citation_id,
            document_id=hit.document_id,
            document_chunk_id=chunk.id,
            rank=hit.rank,
            reason="source_not_in_index_policy",
        )

    if (
        inputs.currently_approved_source_ids is not None
        and document.source_id not in inputs.currently_approved_source_ids
    ):
        return EvidenceContextExclusion(
            citation_id=chunk.citation_id,
            document_id=hit.document_id,
            document_chunk_id=chunk.id,
            rank=hit.rank,
            reason="source_revoked_after_run",
        )

    if inputs.versions_by_id.get(chunk.document_version_id) is None:
        return EvidenceContextExclusion(
            citation_id=chunk.citation_id,
            document_id=hit.document_id,
            document_chunk_id=chunk.id,
            rank=hit.rank,
            reason="document_version_not_found",
        )

    return None


def _materialize_item(
    *,
    hit: LoadedRetrievalHit,
    chunk: LoadedChunk,
    document: LoadedDocument,
    version: LoadedDocumentVersion,
) -> EvidenceContextItem:
    metadata = dict(chunk.metadata_json)
    version_metadata = dict(version.metadata_json)
    is_retracted = _flag_is_true(metadata.get("retraction_status"), expected="retracted") or _flag_is_true(
        metadata.get("is_retracted")
    ) or _flag_is_true(version_metadata.get("retraction_status"), expected="retracted")
    has_correction = _flag_is_true(metadata.get("has_correction")) or _flag_is_true(
        version_metadata.get("has_correction")
    )
    return EvidenceContextItem(
        citation_id=chunk.citation_id,
        title=document.title or hit.document_id,
        source_id=document.source_id,
        source_date=_string_or_none(metadata.get("source_date") or version_metadata.get("published_at")),
        evidence_type=_string_or_none(metadata.get("evidence_type") or version_metadata.get("evidence_type")),
        evidence_quality=_string_or_none(
            metadata.get("evidence_quality") or version_metadata.get("evidence_quality")
        ),
        is_retracted=is_retracted,
        has_correction=has_correction,
        excerpt=chunk.text,
        document_id=hit.document_id,
        document_version_id=version.id,
        document_chunk_id=chunk.id,
        location=_format_location(chunk),
        rank=hit.rank,
        token_count=chunk.token_count,
    )


def _format_location(chunk: LoadedChunk) -> str:
    if chunk.section:
        return chunk.section
    if chunk.page_from is not None and chunk.page_to is not None:
        if chunk.page_from == chunk.page_to:
            return f"page {chunk.page_from}"
        return f"pages {chunk.page_from}-{chunk.page_to}"
    if chunk.page_from is not None:
        return f"page {chunk.page_from}"
    return "unknown"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _flag_is_true(value: object, *, expected: str | None = None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    normalized = str(value).strip().lower()
    if expected is not None:
        return normalized == expected
    return normalized in {"1", "true", "yes", "on"}
