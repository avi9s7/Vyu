from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from src.vyu.db.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin
from src.vyu.retrieval.index_contracts import APPROVED_EMBEDDING_DIMENSIONS, IndexStatus
from src.vyu.retrieval.vector_type import PgVector

INDEX_STATUS_SQL = ", ".join(repr(value.value) for value in IndexStatus)


class RetrievalIndex(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "retrieval_indexes"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({INDEX_STATUS_SQL})",
            name="retrieval_indexes_status_valid",
        ),
        CheckConstraint(
            f"embedding_dimensions = {APPROVED_EMBEDDING_DIMENSIONS}",
            name="retrieval_indexes_embedding_dimensions_valid",
        ),
        Index(
            "uq_retrieval_indexes_active_scope",
            "tenant_id",
            "workspace_id",
            "use_case",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    use_case: Mapped[str] = mapped_column(String(64), nullable=False, default="evidence_memory")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=IndexStatus.BUILDING.value)
    manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    manifest_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    chunker_name: Mapped[str] = mapped_column(String(128), nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    build_git_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluation_result_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    lexical_config_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    semantic_config_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChunkEmbedding(UuidPrimaryKeyMixin, Base):
    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "retrieval_index_id",
            "document_chunk_id",
            name="chunk_embeddings_index_chunk_unique",
        ),
        CheckConstraint(
            f"dimensions = {APPROVED_EMBEDDING_DIMENSIONS}",
            name="chunk_embeddings_dimensions_valid",
        ),
        Index(
            "ix_chunk_embeddings_cache_lookup",
            "tenant_id",
            "text_sha256",
            "provider",
            "model",
            "dimensions",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    retrieval_index_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("retrieval_indexes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_chunk_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        PgVector(APPROVED_EMBEDDING_DIMENSIONS),
        nullable=False,
    )
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RetrievalRun(UuidPrimaryKeyMixin, Base):
    __tablename__ = "retrieval_runs"
    __table_args__ = (UniqueConstraint("retrieval_run_key", name="retrieval_runs_retrieval_run_key_unique"),)

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    retrieval_run_key: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_run_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    retrieval_index_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("retrieval_indexes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    query_metadata_filter_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    retriever_versions_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluation_suite: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RetrievalHitRow(UuidPrimaryKeyMixin, Base):
    __tablename__ = "retrieval_hits"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    retrieval_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("retrieval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[str] = mapped_column(String(128), nullable=False)
    passage_id: Mapped[str] = mapped_column(String(255), nullable=False)
    document_chunk_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score_source: Mapped[str] = mapped_column(String(64), nullable=False)
    score_value: Mapped[float] = mapped_column(Float, nullable=False)
    score_components_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    trace_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RetrievalExclusion(UuidPrimaryKeyMixin, Base):
    __tablename__ = "retrieval_exclusions"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    retrieval_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("retrieval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    document_chunk_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    exclusion_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    details_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
