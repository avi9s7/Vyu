from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.vyu.db.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin
from src.vyu.policy.contracts import (
    POLICY_VERSION_STATUSES,
    SOURCE_APPROVAL_STATUSES,
    TOOL_APPROVAL_STATUSES,
)

POLICY_VERSION_STATUS_SQL = ", ".join(repr(value) for value in POLICY_VERSION_STATUSES)
SOURCE_APPROVAL_STATUS_SQL = ", ".join(repr(value) for value in SOURCE_APPROVAL_STATUSES)
TOOL_APPROVAL_STATUS_SQL = ", ".join(repr(value) for value in TOOL_APPROVAL_STATUSES)


class SourcePolicyVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_policy_versions"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({POLICY_VERSION_STATUS_SQL})",
            name="source_policy_versions_status_valid",
        ),
        UniqueConstraint("version_number", name="source_policy_versions_version_number_unique"),
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SourcePolicyRecord(UuidPrimaryKeyMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("policy_version_id", "source_id", name="sources_policy_source_unique"),
        CheckConstraint(
            f"approval_status IN ({SOURCE_APPROVAL_STATUS_SQL})",
            name="sources_approval_status_valid",
        ),
    )

    policy_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("source_policy_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    record_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False)
    quarantined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quarantined_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quarantined_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchToolPolicyVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_tool_policy_versions"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({POLICY_VERSION_STATUS_SQL})",
            name="research_tool_policy_versions_status_valid",
        ),
        UniqueConstraint(
            "version_number",
            name="research_tool_policy_versions_version_number_unique",
        ),
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ResearchToolPolicyRecord(UuidPrimaryKeyMixin, Base):
    __tablename__ = "research_tools"
    __table_args__ = (
        UniqueConstraint("policy_version_id", "tool_id", name="research_tools_policy_tool_unique"),
        CheckConstraint(
            f"approval_status IN ({TOOL_APPROVAL_STATUS_SQL})",
            name="research_tools_approval_status_valid",
        ),
    )

    policy_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("research_tool_policy_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    record_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False)
    quarantined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quarantined_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quarantined_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
