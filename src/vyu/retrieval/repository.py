from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from src.vyu.retrieval.embeddings import EmbeddingBatch
from src.vyu.retrieval.index_contracts import (
    DEFAULT_RETRIEVAL_USE_CASE,
    IndexActivationError,
    IndexEvaluationResult,
    IndexManifest,
    IndexRecord,
    IndexStatus,
    manifest_checksum,
)
from src.vyu.retrieval.models import (
    ChunkEmbedding,
    RetrievalExclusion,
    RetrievalHitRow,
    RetrievalIndex,
    RetrievalRun,
)


class RetrievalIndexRepository:
    def get_by_checksum(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        manifest_checksum_value: str,
    ) -> IndexRecord | None:
        row = session.scalar(
            select(RetrievalIndex).where(
                RetrievalIndex.tenant_id == tenant_id,
                RetrievalIndex.workspace_id == workspace_id,
                RetrievalIndex.manifest_checksum == manifest_checksum_value,
            )
        )
        if not isinstance(row, RetrievalIndex):
            return None
        return _index_record_from_row(row)

    def get_active_index(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        use_case: str = DEFAULT_RETRIEVAL_USE_CASE,
    ) -> IndexRecord | None:
        row = session.scalar(
            select(RetrievalIndex).where(
                RetrievalIndex.tenant_id == tenant_id,
                RetrievalIndex.workspace_id == workspace_id,
                RetrievalIndex.use_case == use_case,
                RetrievalIndex.status == IndexStatus.ACTIVE.value,
            )
        )
        if not isinstance(row, RetrievalIndex):
            return None
        return _index_record_from_row(row)

    def create_index(
        self,
        session: Session,
        *,
        manifest: IndexManifest,
        document_count: int,
        chunk_count: int,
        status: IndexStatus = IndexStatus.BUILDING,
    ) -> IndexRecord:
        manifest.validate_dimensions()
        checksum = manifest_checksum(manifest)
        existing = self.get_by_checksum(
            session,
            tenant_id=manifest.tenant_id,
            workspace_id=manifest.workspace_id,
            manifest_checksum_value=checksum,
        )
        if existing is not None:
            return existing
        row = RetrievalIndex(
            id=uuid4(),
            tenant_id=manifest.tenant_id,
            workspace_id=manifest.workspace_id,
            use_case=manifest.use_case,
            status=status.value,
            manifest_checksum=checksum,
            manifest_json=manifest.to_json(),
            chunker_name=manifest.chunker_name,
            chunker_version=manifest.chunker_version,
            embedding_provider=manifest.embedding_provider,
            embedding_model=manifest.embedding_model,
            embedding_dimensions=manifest.embedding_dimensions,
            policy_version=manifest.policy_version,
            build_git_sha=manifest.build_git_sha,
            document_count=document_count,
            chunk_count=chunk_count,
            lexical_config_json=dict(manifest.lexical_config),
            semantic_config_json=dict(manifest.semantic_config),
        )
        session.add(row)
        session.flush()
        return _index_record_from_row(row)

    def update_status(
        self,
        session: Session,
        *,
        index_id: UUID,
        status: IndexStatus,
        evaluation_result: IndexEvaluationResult | None = None,
    ) -> IndexRecord:
        row = session.scalar(select(RetrievalIndex).where(RetrievalIndex.id == index_id))
        if not isinstance(row, RetrievalIndex):
            raise KeyError(f"unknown retrieval index: {index_id}")
        row.status = status.value
        if evaluation_result is not None:
            row.evaluation_result_json = evaluation_result.to_json()
        session.flush()
        return _index_record_from_row(row)

    def activate_index(
        self,
        session: Session,
        *,
        index_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        use_case: str = DEFAULT_RETRIEVAL_USE_CASE,
    ) -> IndexRecord:
        row = session.scalar(
            select(RetrievalIndex).where(
                RetrievalIndex.id == index_id,
                RetrievalIndex.tenant_id == tenant_id,
                RetrievalIndex.workspace_id == workspace_id,
            )
        )
        if not isinstance(row, RetrievalIndex):
            raise KeyError(f"unknown retrieval index: {index_id}")
        if row.status != IndexStatus.VALIDATING.value:
            raise IndexActivationError(
                f"index {index_id} must be validating before activation (status={row.status})"
            )
        evaluation_payload = row.evaluation_result_json
        if not isinstance(evaluation_payload, dict) or not bool(evaluation_payload.get("passed")):
            raise IndexActivationError(f"index {index_id} failed evaluation gate")
        session.execute(
            update(RetrievalIndex)
            .where(
                RetrievalIndex.tenant_id == tenant_id,
                RetrievalIndex.workspace_id == workspace_id,
                RetrievalIndex.use_case == use_case,
                RetrievalIndex.status == IndexStatus.ACTIVE.value,
            )
            .values(status=IndexStatus.RETIRED.value)
        )
        activated_at = datetime.now(timezone.utc)
        row.status = IndexStatus.ACTIVE.value
        row.activated_at = activated_at
        session.flush()
        return _index_record_from_row(row)

    def lookup_cached_embeddings(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        text_hashes: tuple[str, ...],
        provider: str,
        model: str,
        dimensions: int,
    ) -> dict[str, ChunkEmbedding]:
        if not text_hashes:
            return {}
        rows = session.scalars(
            select(ChunkEmbedding).where(
                ChunkEmbedding.tenant_id == tenant_id,
                ChunkEmbedding.text_sha256.in_(text_hashes),
                ChunkEmbedding.provider == provider,
                ChunkEmbedding.model == model,
                ChunkEmbedding.dimensions == dimensions,
            )
        ).all()
        return {
            row.text_sha256: row
            for row in rows
            if isinstance(row, ChunkEmbedding)
        }

    def save_embedding_batch(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        retrieval_index_id: UUID,
        document_chunk_id: UUID,
        batch: EmbeddingBatch,
        vector_index: int,
        chunk_text: str | None = None,
    ) -> ChunkEmbedding:
        vector = batch.vectors[vector_index]
        linked = session.scalar(
            select(ChunkEmbedding).where(
                ChunkEmbedding.retrieval_index_id == retrieval_index_id,
                ChunkEmbedding.document_chunk_id == document_chunk_id,
            )
        )
        if isinstance(linked, ChunkEmbedding):
            return linked
        cached = session.scalar(
            select(ChunkEmbedding).where(
                ChunkEmbedding.tenant_id == tenant_id,
                ChunkEmbedding.text_sha256 == vector.text_sha256,
                ChunkEmbedding.provider == batch.provider,
                ChunkEmbedding.model == batch.model,
                ChunkEmbedding.dimensions == batch.dimensions,
            )
            .order_by(ChunkEmbedding.created_at.desc())
            .limit(1)
        )
        if isinstance(cached, ChunkEmbedding):
            row = ChunkEmbedding(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                retrieval_index_id=retrieval_index_id,
                document_chunk_id=document_chunk_id,
                text_sha256=vector.text_sha256,
                provider=batch.provider,
                model=batch.model,
                dimensions=batch.dimensions,
                embedding=list(cached.embedding),
                search_vector=cached.search_vector,
                provider_request_id=batch.provider_request_id,
                latency_ms=batch.latency_ms,
                usage_json=batch.usage.to_json(),
            )
            session.add(row)
            session.flush()
            return row
        row = ChunkEmbedding(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            retrieval_index_id=retrieval_index_id,
            document_chunk_id=document_chunk_id,
            text_sha256=vector.text_sha256,
            provider=batch.provider,
            model=batch.model,
            dimensions=batch.dimensions,
            embedding=list(vector.values),
            provider_request_id=batch.provider_request_id,
            latency_ms=batch.latency_ms,
            usage_json=batch.usage.to_json(),
        )
        session.add(row)
        session.flush()
        if chunk_text is not None:
            session.execute(
                text(
                    """
                    UPDATE chunk_embeddings
                    SET search_vector = to_tsvector('english', :chunk_text)
                    WHERE id = :embedding_id
                    """
                ),
                {"chunk_text": chunk_text, "embedding_id": row.id},
            )
            session.flush()
        return row

    def link_cached_embedding(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        retrieval_index_id: UUID,
        document_chunk_id: UUID,
        cached: ChunkEmbedding,
        chunk_text: str,
    ) -> ChunkEmbedding:
        linked = session.scalar(
            select(ChunkEmbedding).where(
                ChunkEmbedding.retrieval_index_id == retrieval_index_id,
                ChunkEmbedding.document_chunk_id == document_chunk_id,
            )
        )
        if isinstance(linked, ChunkEmbedding):
            return linked
        row = ChunkEmbedding(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            retrieval_index_id=retrieval_index_id,
            document_chunk_id=document_chunk_id,
            text_sha256=cached.text_sha256,
            provider=cached.provider,
            model=cached.model,
            dimensions=cached.dimensions,
            embedding=list(cached.embedding),
            search_vector=cached.search_vector,
            provider_request_id=cached.provider_request_id,
            latency_ms=cached.latency_ms,
            usage_json=dict(cached.usage_json),
        )
        session.add(row)
        session.flush()
        if row.search_vector is None:
            session.execute(
                text(
                    """
                    UPDATE chunk_embeddings
                    SET search_vector = to_tsvector('english', :chunk_text)
                    WHERE id = :embedding_id
                    """
                ),
                {"chunk_text": chunk_text, "embedding_id": row.id},
            )
            session.flush()
        return row

    def save_retrieval_run(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        retrieval_run_key: str,
        workflow_run_id: str,
        retrieval_index_id: UUID,
        user_id: str,
        topic: str,
        question: str,
        retrieval_mode: str,
        top_k: int,
        query_metadata_filter: dict[str, object],
        retriever_versions: dict[str, str],
        latency_ms: int | None,
        evaluation_suite: str | None,
        hits: tuple[RetrievalHitDraft, ...],
        exclusions: tuple[RetrievalExclusionDraft, ...] = (),
    ) -> RetrievalRun:
        existing = session.scalar(
            select(RetrievalRun).where(RetrievalRun.retrieval_run_key == retrieval_run_key)
        )
        if isinstance(existing, RetrievalRun):
            return existing
        row = RetrievalRun(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            retrieval_run_key=retrieval_run_key,
            workflow_run_id=workflow_run_id,
            retrieval_index_id=retrieval_index_id,
            user_id=user_id,
            topic=topic,
            question=question,
            retrieval_mode=retrieval_mode,
            top_k=top_k,
            query_metadata_filter_json=dict(query_metadata_filter),
            retriever_versions_json=dict(retriever_versions),
            latency_ms=latency_ms,
            evaluation_suite=evaluation_suite,
        )
        session.add(row)
        session.flush()
        for hit in hits:
            session.add(
                RetrievalHitRow(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    retrieval_run_id=row.id,
                    document_id=hit.document_id,
                    passage_id=hit.passage_id,
                    document_chunk_id=hit.document_chunk_id,
                    rank=hit.rank,
                    score_source=hit.score_source,
                    score_value=hit.score_value,
                    score_components_json=dict(hit.score_components),
                    trace_json=dict(hit.trace),
                )
            )
        for exclusion in exclusions:
            session.add(
                RetrievalExclusion(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    retrieval_run_id=row.id,
                    document_id=exclusion.document_id,
                    document_chunk_id=exclusion.document_chunk_id,
                    exclusion_kind=exclusion.exclusion_kind,
                    reason=exclusion.reason,
                    details_json=dict(exclusion.details),
                )
            )
        session.flush()
        return row


def _index_record_from_row(row: RetrievalIndex) -> IndexRecord:
    manifest = IndexManifest.from_json(dict(row.manifest_json))
    evaluation_result: IndexEvaluationResult | None = None
    if isinstance(row.evaluation_result_json, dict) and row.evaluation_result_json:
        evaluation_result = IndexEvaluationResult.from_json(dict(row.evaluation_result_json))
    return IndexRecord(
        index_id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        use_case=row.use_case,
        status=IndexStatus(row.status),
        manifest=manifest,
        manifest_checksum=row.manifest_checksum,
        document_count=row.document_count,
        chunk_count=row.chunk_count,
        evaluation_result=evaluation_result,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
        activated_at=row.activated_at.isoformat() if row.activated_at is not None else None,
    )


@dataclass(frozen=True)
class RetrievalHitDraft:
    document_id: str
    passage_id: str
    document_chunk_id: UUID | None
    rank: int
    score_source: str
    score_value: float
    score_components: dict[str, float]
    trace: dict[str, object]


@dataclass(frozen=True)
class RetrievalExclusionDraft:
    exclusion_kind: str
    reason: str
    document_id: str | None = None
    document_chunk_id: UUID | None = None
    details: dict[str, object] | None = None
