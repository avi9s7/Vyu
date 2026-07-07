from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.vyu.retrieval.contracts import MetadataFilter, RetrievalQuery
from src.vyu.retrieval.embeddings import EmbeddingProvider
from src.vyu.retrieval.index_contracts import IndexRecord
from src.vyu.retrieval.repository import RetrievalExclusionDraft, RetrievalHitDraft, RetrievalIndexRepository
from src.vyu.retrieval.rrf import reciprocal_rank_fusion_by_passage
from src.vyu.retrieval.settings import RetrievalSettings


@dataclass(frozen=True)
class ChunkCandidate:
    document_id: str
    passage_id: str
    document_chunk_id: UUID
    document_title: str | None
    source_id: str
    text: str
    score: float
    score_source: str
    original_rank: int


@dataclass(frozen=True)
class HybridRetrievalResult:
    hits: tuple[RetrievalHitDraft, ...]
    exclusions: tuple[RetrievalExclusionDraft, ...]
    lexical_latency_ms: int
    vector_latency_ms: int
    fusion_latency_ms: int
    query_hash: str
    abstention_reason: str | None = None


class PostgresHybridRetrievalService:
    def __init__(
        self,
        *,
        settings: RetrievalSettings | None = None,
        index_repository: RetrievalIndexRepository | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.settings = settings or RetrievalSettings()
        self.index_repository = index_repository or RetrievalIndexRepository()
        from src.vyu.retrieval.embeddings import DeterministicEmbeddingProvider

        self.embedding_provider = embedding_provider or DeterministicEmbeddingProvider(
            provider=self.settings.embedding_provider,
            default_model=self.settings.embedding_model,
        )

    def search(
        self,
        session: Session,
        *,
        query: RetrievalQuery,
        active_index: IndexRecord,
        tenant_id: UUID,
        workspace_id: UUID,
        metadata_filter: MetadataFilter | None = None,
    ) -> HybridRetrievalResult:
        query_hash = hashlib.sha256(query.text.encode("utf-8")).hexdigest()
        lexical_started = time.perf_counter()
        lexical = self._lexical_search(
            session,
            query_text=query.text,
            index_id=active_index.index_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            pool_size=self.settings.lexical_pool_size,
        )
        lexical_latency_ms = int((time.perf_counter() - lexical_started) * 1000)

        vector_started = time.perf_counter()
        vector = self._vector_search(
            session,
            query_text=query.text,
            index_id=active_index.index_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            dimensions=active_index.manifest.embedding_dimensions,
            model=active_index.manifest.embedding_model,
            pool_size=self.settings.vector_pool_size,
        )
        vector_latency_ms = int((time.perf_counter() - vector_started) * 1000)

        fusion_started = time.perf_counter()
        fused = reciprocal_rank_fusion_by_passage(
            [lexical, vector],
            top_k=self.settings.final_top_k,
            rank_constant=self.settings.rrf_rank_constant,
        )
        hits: list[RetrievalHitDraft] = []
        exclusions: list[RetrievalExclusionDraft] = []
        for rank, candidate in enumerate(fused, start=1):
            if metadata_filter is not None and not self._metadata_allows(candidate, metadata_filter):
                exclusions.append(
                    RetrievalExclusionDraft(
                        exclusion_kind="metadata_filter",
                        reason="metadata_filter_rejected",
                        document_id=candidate.document_id,
                        document_chunk_id=candidate.document_chunk_id,
                    )
                )
                continue
            hits.append(
                RetrievalHitDraft(
                    document_id=candidate.document_id,
                    passage_id=candidate.passage_id,
                    document_chunk_id=candidate.document_chunk_id,
                    rank=rank,
                    score_source="rrf",
                    score_value=candidate.score,
                    score_components={
                        candidate.score_source: candidate.score,
                    },
                    trace={
                        "retriever": "hybrid_rrf_v1",
                        "original_rank": candidate.original_rank,
                        "post_filter_rank": rank,
                        "final_rank": rank,
                        "query_hash": query_hash,
                    },
                )
            )
        fusion_latency_ms = int((time.perf_counter() - fusion_started) * 1000)
        abstention_reason = "no_matching_chunks" if not hits else None
        return HybridRetrievalResult(
            hits=tuple(hits[: query.top_k]),
            exclusions=tuple(exclusions),
            lexical_latency_ms=lexical_latency_ms,
            vector_latency_ms=vector_latency_ms,
            fusion_latency_ms=fusion_latency_ms,
            query_hash=query_hash,
            abstention_reason=abstention_reason,
        )

    def _lexical_search(
        self,
        session: Session,
        *,
        query_text: str,
        index_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        pool_size: int,
    ) -> list[ChunkCandidate]:
        rows = session.execute(
            text(
                """
                SELECT
                    d.id::text AS document_id,
                    dc.citation_id AS passage_id,
                    dc.id AS document_chunk_id,
                    d.title AS document_title,
                    d.source_id AS source_id,
                    dc.text AS text,
                    ts_rank_cd(ce.search_vector, websearch_to_tsquery('english', :query_text)) AS score
                FROM chunk_embeddings ce
                JOIN document_chunks dc ON dc.id = ce.document_chunk_id
                JOIN document_versions dv ON dv.id = dc.document_version_id
                JOIN documents d ON d.id = dv.document_id
                WHERE ce.retrieval_index_id = :index_id
                  AND ce.tenant_id = :tenant_id
                  AND ce.workspace_id = :workspace_id
                  AND ce.search_vector @@ websearch_to_tsquery('english', :query_text)
                ORDER BY score DESC, dc.citation_id ASC
                LIMIT :pool_size
                """
            ),
            {
                "query_text": query_text,
                "index_id": index_id,
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "pool_size": pool_size,
            },
        ).mappings()
        candidates: list[ChunkCandidate] = []
        for rank, row in enumerate(rows, start=1):
            candidates.append(
                ChunkCandidate(
                    document_id=str(row["document_id"]),
                    passage_id=str(row["passage_id"]),
                    document_chunk_id=UUID(str(row["document_chunk_id"])),
                    document_title=row["document_title"],
                    source_id=str(row["source_id"]),
                    text=str(row["text"]),
                    score=float(row["score"] or 0.0),
                    score_source="lexical",
                    original_rank=rank,
                )
            )
        return candidates

    def _vector_search(
        self,
        session: Session,
        *,
        query_text: str,
        index_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        dimensions: int,
        model: str,
        pool_size: int,
    ) -> list[ChunkCandidate]:
        batch = self.embedding_provider.embed([query_text], model=model, dimensions=dimensions)
        vector_literal = "[" + ",".join(str(value) for value in batch.vectors[0].values) + "]"
        rows = session.execute(
            text(
                """
                SELECT
                    d.id::text AS document_id,
                    dc.citation_id AS passage_id,
                    dc.id AS document_chunk_id,
                    d.title AS document_title,
                    d.source_id AS source_id,
                    dc.text AS text,
                    1 - (ce.embedding <=> CAST(:query_vector AS vector)) AS score
                FROM chunk_embeddings ce
                JOIN document_chunks dc ON dc.id = ce.document_chunk_id
                JOIN document_versions dv ON dv.id = dc.document_version_id
                JOIN documents d ON d.id = dv.document_id
                WHERE ce.retrieval_index_id = :index_id
                  AND ce.tenant_id = :tenant_id
                  AND ce.workspace_id = :workspace_id
                ORDER BY ce.embedding <=> CAST(:query_vector AS vector) ASC, dc.citation_id ASC
                LIMIT :pool_size
                """
            ),
            {
                "query_vector": vector_literal,
                "index_id": index_id,
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "pool_size": pool_size,
            },
        ).mappings()
        candidates: list[ChunkCandidate] = []
        for rank, row in enumerate(rows, start=1):
            candidates.append(
                ChunkCandidate(
                    document_id=str(row["document_id"]),
                    passage_id=str(row["passage_id"]),
                    document_chunk_id=UUID(str(row["document_chunk_id"])),
                    document_title=row["document_title"],
                    source_id=str(row["source_id"]),
                    text=str(row["text"]),
                    score=float(row["score"] or 0.0),
                    score_source="vector",
                    original_rank=rank,
                )
            )
        return candidates

    @staticmethod
    def _metadata_allows(candidate: ChunkCandidate, metadata_filter: MetadataFilter) -> bool:
        del metadata_filter
        return True
