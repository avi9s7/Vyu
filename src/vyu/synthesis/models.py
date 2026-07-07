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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.vyu.db.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin
from src.vyu.synthesis.contracts import (
    ANSWER_STATUSES,
    CLAIM_SUPPORT_STATUSES,
    MODEL_CALL_STATUSES,
    MODEL_POLICY_VERSION_STATUSES,
    PROMPT_TEMPLATE_STATUSES,
)

MODEL_POLICY_STATUS_SQL = ", ".join(repr(value) for value in MODEL_POLICY_VERSION_STATUSES)
PROMPT_TEMPLATE_STATUS_SQL = ", ".join(repr(value) for value in PROMPT_TEMPLATE_STATUSES)
MODEL_CALL_STATUS_SQL = ", ".join(repr(value) for value in MODEL_CALL_STATUSES)
ANSWER_STATUS_SQL = ", ".join(repr(value) for value in ANSWER_STATUSES)
CLAIM_SUPPORT_STATUS_SQL = ", ".join(repr(value) for value in CLAIM_SUPPORT_STATUSES)


class ModelPolicyVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_policy_versions"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({MODEL_POLICY_STATUS_SQL})",
            name="model_policy_versions_status_valid",
        ),
        UniqueConstraint("version_number", name="model_policy_versions_version_number_unique"),
        UniqueConstraint("sha256", name="model_policy_versions_sha256_unique"),
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    allowed_providers_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    allowed_models_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    use_cases_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    limits_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    fallback_rules_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class PromptTemplate(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({PROMPT_TEMPLATE_STATUS_SQL})",
            name="prompt_templates_status_valid",
        ),
        UniqueConstraint("name", "version", name="prompt_templates_name_version_unique"),
        UniqueConstraint("sha256", name="prompt_templates_sha256_unique"),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    use_case: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    template: Mapped[str] = mapped_column(Text, nullable=False)
    output_schema_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class ModelCall(UuidPrimaryKeyMixin, Base):
    __tablename__ = "model_calls"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({MODEL_CALL_STATUS_SQL})",
            name="model_calls_status_valid",
        ),
        UniqueConstraint("tenant_id", "request_sha256", name="model_calls_tenant_request_unique"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    job_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_template_id: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    response_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_context_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    safe_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usage_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Answer(UuidPrimaryKeyMixin, Base):
    __tablename__ = "answers"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({ANSWER_STATUS_SQL})",
            name="answers_status_valid",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "research_run_id",
            "version",
            name="answers_scope_version_unique",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    research_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    retrieval_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("retrieval_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    uncertainty: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    model_call_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("model_calls.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_context_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class AnswerClaim(UuidPrimaryKeyMixin, Base):
    __tablename__ = "answer_claims"
    __table_args__ = (
        CheckConstraint(
            f"support_status IN ({CLAIM_SUPPORT_STATUS_SQL})",
            name="answer_claims_support_status_valid",
        ),
        UniqueConstraint("answer_id", "ordinal", name="answer_claims_answer_ordinal_unique"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    answer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("answers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    support_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ClaimCitation(UuidPrimaryKeyMixin, Base):
    __tablename__ = "claim_citations"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    claim_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("answer_claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    citation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    document_version_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    chunk_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
