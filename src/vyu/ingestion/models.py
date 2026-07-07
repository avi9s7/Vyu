from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.vyu.db.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin
from src.vyu.ingestion.contracts import DOCUMENT_STATUSES, MALWARE_STATUSES, PHI_STATUSES

DOCUMENT_STATUS_SQL = ", ".join(repr(value) for value in DOCUMENT_STATUSES)
MALWARE_STATUS_SQL = ", ".join(repr(value) for value in MALWARE_STATUSES)
PHI_STATUS_SQL = ", ".join(repr(value) for value in PHI_STATUSES)


class Document(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({DOCUMENT_STATUS_SQL})",
            name="documents_status_valid",
        ),
        Index("ix_documents_source_id", "source_id"),
        Index("ix_documents_status", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="awaiting_upload")
    current_version_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)


class DocumentVersion(UuidPrimaryKeyMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="document_versions_document_version_unique"),
        CheckConstraint(
            f"malware_status IS NULL OR malware_status IN ({MALWARE_STATUS_SQL})",
            name="document_versions_malware_status_valid",
        ),
        CheckConstraint(
            f"phi_status IS NULL OR phi_status IN ({PHI_STATUS_SQL})",
            name="document_versions_phi_status_valid",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    original_bucket: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    original_version_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_bucket: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    normalized_version_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    malware_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phi_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    parser_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class IngestionEvent(UuidPrimaryKeyMixin, Base):
    __tablename__ = "ingestion_events"
    __table_args__ = (
        UniqueConstraint("job_id", "sequence", name="ingestion_events_job_sequence_unique"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class EvidenceObject(UuidPrimaryKeyMixin, Base):
    __tablename__ = "evidence_objects"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    key: Mapped[str] = mapped_column(String(1024), nullable=False)
    version_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DocumentChunk(UuidPrimaryKeyMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id",
            "ordinal",
            name="document_chunks_version_ordinal_unique",
        ),
        UniqueConstraint(
            "document_version_id",
            "citation_id",
            name="document_chunks_version_citation_unique",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    citation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
