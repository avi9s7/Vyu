from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol

from src.vyu.retrieval.contracts import RetrievalHit, RetrievalQuery
from src.vyu.retrieval.rrf import reciprocal_rank_fusion


class EvidenceObjectKind(StrEnum):
    DOCUMENT = "document"
    EVIDENCE_PACK = "evidence_pack"
    INDEX_SNAPSHOT = "index_snapshot"
    RETRIEVAL_TRACE = "retrieval_trace"


class RetrievalIndexKind(StrEnum):
    BM25 = "bm25"
    DENSE = "dense"
    HYBRID = "hybrid"
    PGVECTOR = "pgvector"
    QDRANT = "qdrant"


@dataclass(frozen=True)
class EvidenceObjectRecord:
    object_id: str
    tenant_id: str
    workspace_id: str
    object_uri: str
    object_kind: EvidenceObjectKind
    content_type: str
    checksum_sha256: str
    size_bytes: int
    source_id: str
    document_id: str | None = None
    evidence_pack_id: str | None = None
    retention_policy_id: str = "default_evidence_object_retention"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "object_uri": self.object_uri,
            "object_kind": self.object_kind.value,
            "content_type": self.content_type,
            "checksum_sha256": self.checksum_sha256,
            "size_bytes": self.size_bytes,
            "source_id": self.source_id,
            "document_id": self.document_id,
            "evidence_pack_id": self.evidence_pack_id,
            "retention_policy_id": self.retention_policy_id,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "EvidenceObjectRecord":
        return cls(
            object_id=str(payload["object_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            object_uri=str(payload["object_uri"]),
            object_kind=EvidenceObjectKind(str(payload["object_kind"])),
            content_type=str(payload["content_type"]),
            checksum_sha256=str(payload["checksum_sha256"]),
            size_bytes=int(payload["size_bytes"]),
            source_id=str(payload["source_id"]),
            document_id=(str(payload["document_id"]) if payload.get("document_id") is not None else None),
            evidence_pack_id=(
                str(payload["evidence_pack_id"])
                if payload.get("evidence_pack_id") is not None
                else None
            ),
            retention_policy_id=str(
                payload.get("retention_policy_id", "default_evidence_object_retention")
            ),
            created_at=str(payload["created_at"]),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class RetrievalIndexRecord:
    index_version: str
    tenant_id: str
    workspace_id: str
    index_kind: RetrievalIndexKind
    corpus_version: str
    source_ids: tuple[str, ...]
    object_uri: str
    checksum_sha256: str
    document_count: int
    passage_count: int
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    embedding_model: str | None = None
    lexical_config: dict[str, Any] = field(default_factory=dict)
    semantic_config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "index_version": self.index_version,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "index_kind": self.index_kind.value,
            "corpus_version": self.corpus_version,
            "source_ids": list(self.source_ids),
            "object_uri": self.object_uri,
            "checksum_sha256": self.checksum_sha256,
            "document_count": self.document_count,
            "passage_count": self.passage_count,
            "created_at": self.created_at,
            "embedding_model": self.embedding_model,
            "lexical_config": dict(self.lexical_config),
            "semantic_config": dict(self.semantic_config),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "RetrievalIndexRecord":
        return cls(
            index_version=str(payload["index_version"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            index_kind=RetrievalIndexKind(str(payload["index_kind"])),
            corpus_version=str(payload["corpus_version"]),
            source_ids=tuple(str(item) for item in payload.get("source_ids", [])),
            object_uri=str(payload["object_uri"]),
            checksum_sha256=str(payload["checksum_sha256"]),
            document_count=int(payload["document_count"]),
            passage_count=int(payload["passage_count"]),
            created_at=str(payload["created_at"]),
            embedding_model=(
                str(payload["embedding_model"])
                if payload.get("embedding_model") is not None
                else None
            ),
            lexical_config=dict(payload.get("lexical_config", {})),
            semantic_config=dict(payload.get("semantic_config", {})),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class RetrievalRunRecord:
    retrieval_run_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    user_id: str
    topic: str
    question: str
    retrieval_mode: str
    index_versions: tuple[str, ...]
    top_k: int
    retrieved_document_ids: tuple[str, ...]
    retrieved_passage_ids: tuple[str, ...]
    score_trace: tuple[dict[str, Any], ...]
    query_metadata_filter: dict[str, Any] = field(default_factory=dict)
    retriever_versions: dict[str, str] = field(default_factory=dict)
    latency_ms: int | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evaluation_suite: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "retrieval_run_id": self.retrieval_run_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "topic": self.topic,
            "question": self.question,
            "retrieval_mode": self.retrieval_mode,
            "index_versions": list(self.index_versions),
            "top_k": self.top_k,
            "retrieved_document_ids": list(self.retrieved_document_ids),
            "retrieved_passage_ids": list(self.retrieved_passage_ids),
            "score_trace": [dict(item) for item in self.score_trace],
            "query_metadata_filter": dict(self.query_metadata_filter),
            "retriever_versions": dict(self.retriever_versions),
            "latency_ms": self.latency_ms,
            "created_at": self.created_at,
            "evaluation_suite": self.evaluation_suite,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "RetrievalRunRecord":
        return cls(
            retrieval_run_id=str(payload["retrieval_run_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            user_id=str(payload["user_id"]),
            topic=str(payload["topic"]),
            question=str(payload["question"]),
            retrieval_mode=str(payload["retrieval_mode"]),
            index_versions=tuple(str(item) for item in payload.get("index_versions", [])),
            top_k=int(payload["top_k"]),
            retrieved_document_ids=tuple(
                str(item) for item in payload.get("retrieved_document_ids", [])
            ),
            retrieved_passage_ids=tuple(
                str(item) for item in payload.get("retrieved_passage_ids", [])
            ),
            score_trace=tuple(dict(item) for item in payload.get("score_trace", [])),
            query_metadata_filter=dict(payload.get("query_metadata_filter", {})),
            retriever_versions={
                str(key): str(value)
                for key, value in payload.get("retriever_versions", {}).items()
            },
            latency_ms=(int(payload["latency_ms"]) if payload.get("latency_ms") is not None else None),
            created_at=str(payload["created_at"]),
            evaluation_suite=(
                str(payload["evaluation_suite"])
                if payload.get("evaluation_suite") is not None
                else None
            ),
        )


class Retriever(Protocol):
    source: str

    def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        ...


class ProductionHybridRetrievalService:
    """Production-shaped BM25 + semantic + RRF runtime boundary.

    The current implementation can be backed by local deterministic retrievers for
    tests, then swapped for pgvector/Qdrant/managed BM25 providers without
    changing the persisted run contract.
    """

    def __init__(
        self,
        *,
        lexical_retriever: Retriever,
        semantic_retriever: Retriever,
        index_versions: tuple[str, ...],
        retriever_versions: dict[str, str] | None = None,
        retrieval_mode: str = "hybrid_rrf_v1",
    ) -> None:
        self.lexical_retriever = lexical_retriever
        self.semantic_retriever = semantic_retriever
        self.index_versions = index_versions
        self.retriever_versions = retriever_versions or {
            lexical_retriever.source: "local-boundary-v1",
            semantic_retriever.source: "local-boundary-v1",
            "rrf": "local-boundary-v1",
        }
        self.retrieval_mode = retrieval_mode

    def search_with_record(
        self,
        *,
        query: RetrievalQuery,
        retrieval_run_id: str,
        run_id: str,
        tenant_id: str,
        workspace_id: str,
        user_id: str,
        topic: str,
        created_at: str | None = None,
        evaluation_suite: str | None = None,
    ) -> tuple[list[RetrievalHit], RetrievalRunRecord]:
        start = time.perf_counter()
        lexical_hits = self.lexical_retriever.search(query)
        semantic_hits = self.semantic_retriever.search(query)
        hits = reciprocal_rank_fusion([lexical_hits, semantic_hits], top_k=query.top_k)
        latency_ms = int((time.perf_counter() - start) * 1000)
        record = build_retrieval_run_record(
            retrieval_run_id=retrieval_run_id,
            run_id=run_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            topic=topic,
            question=query.text,
            retrieval_mode=self.retrieval_mode,
            index_versions=self.index_versions,
            top_k=query.top_k,
            hits=hits,
            query_metadata_filter=_metadata_filter_to_json(query),
            retriever_versions=self.retriever_versions,
            latency_ms=latency_ms,
            created_at=created_at,
            evaluation_suite=evaluation_suite,
        )
        return hits, record


def build_retrieval_run_record(
    *,
    retrieval_run_id: str,
    run_id: str,
    tenant_id: str,
    workspace_id: str,
    user_id: str,
    topic: str,
    question: str,
    retrieval_mode: str,
    index_versions: tuple[str, ...],
    top_k: int,
    hits: list[RetrievalHit],
    query_metadata_filter: dict[str, Any] | None = None,
    retriever_versions: dict[str, str] | None = None,
    latency_ms: int | None = None,
    created_at: str | None = None,
    evaluation_suite: str | None = None,
) -> RetrievalRunRecord:
    return RetrievalRunRecord(
        retrieval_run_id=retrieval_run_id,
        run_id=run_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        user_id=user_id,
        topic=topic,
        question=question,
        retrieval_mode=retrieval_mode,
        index_versions=index_versions,
        top_k=top_k,
        retrieved_document_ids=tuple(hit.document_id for hit in hits),
        retrieved_passage_ids=tuple(hit.passage_id for hit in hits),
        score_trace=tuple(_hit_score_trace(hit) for hit in hits),
        query_metadata_filter=query_metadata_filter or {},
        retriever_versions=retriever_versions or {},
        latency_ms=latency_ms,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        evaluation_suite=evaluation_suite,
    )


def _hit_score_trace(hit: RetrievalHit) -> dict[str, Any]:
    return {
        "document_id": hit.document_id,
        "passage_id": hit.passage_id,
        "score_source": hit.score.source,
        "score_value": hit.score.value,
        "score_components": dict(hit.score.components),
        "retriever": hit.trace.retriever,
        "original_rank": hit.trace.original_rank,
        "post_filter_rank": hit.trace.post_filter_rank,
        "final_rank": hit.trace.final_rank,
    }


def _metadata_filter_to_json(query: RetrievalQuery) -> dict[str, Any]:
    metadata_filter = query.metadata_filter
    if metadata_filter is None:
        return {}
    return {
        "include_retracted": metadata_filter.include_retracted,
        "include_preprints": metadata_filter.include_preprints,
        "study_designs": (
            sorted(study_design.value for study_design in metadata_filter.study_designs)
            if metadata_filter.study_designs is not None
            else None
        ),
        "publication_statuses": (
            sorted(metadata_filter.publication_statuses)
            if metadata_filter.publication_statuses is not None
            else None
        ),
        "population_contains": metadata_filter.population_contains,
        "intervention": metadata_filter.intervention,
    }
