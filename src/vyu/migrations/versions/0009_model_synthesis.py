"""model synthesis persistence

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-08

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MODEL_POLICY_STATUSES = ("draft", "active", "retired")
PROMPT_TEMPLATE_STATUSES = ("draft", "active", "retired")
MODEL_CALL_STATUSES = ("pending", "succeeded", "failed", "blocked")
ANSWER_STATUSES = ("draft", "approved", "blocked", "failed")
CLAIM_SUPPORT_STATUSES = ("supported", "mixed", "unsupported")


def _tenant_workspace_scope_policy(table: str) -> None:
    op.execute(
        f"""
        CREATE POLICY {table}_scope ON {table}
        USING (
            tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
            AND workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
            AND workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid
        )
        """
    )


def upgrade() -> None:
    op.create_table(
        "model_policy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("allowed_providers_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("allowed_models_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("use_cases_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("limits_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fallback_rules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(value) for value in MODEL_POLICY_STATUSES)})",
            name="model_policy_versions_status_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_number", name="model_policy_versions_version_number_unique"),
        sa.UniqueConstraint("sha256", name="model_policy_versions_sha256_unique"),
    )

    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("use_case", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("output_schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(value) for value in PROMPT_TEMPLATE_STATUSES)})",
            name="prompt_templates_status_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="prompt_templates_name_version_unique"),
        sa.UniqueConstraint("sha256", name="prompt_templates_sha256_unique"),
    )
    op.create_index(op.f("ix_prompt_templates_name"), "prompt_templates", ["name"], unique=False)
    op.create_index(op.f("ix_prompt_templates_use_case"), "prompt_templates", ["use_case"], unique=False)

    op.create_table(
        "model_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("prompt_template_id", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("response_sha256", sa.String(length=64), nullable=True),
        sa.Column("evidence_context_sha256", sa.String(length=64), nullable=False),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("safe_error_code", sa.String(length=64), nullable=True),
        sa.Column("usage_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_minor", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(value) for value in MODEL_CALL_STATUSES)})",
            name="model_calls_status_valid",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "request_sha256", name="model_calls_tenant_request_unique"),
    )
    op.create_index(op.f("ix_model_calls_tenant_id"), "model_calls", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_model_calls_workspace_id"), "model_calls", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_model_calls_run_id"), "model_calls", ["run_id"], unique=False)
    op.create_index(op.f("ix_model_calls_job_id"), "model_calls", ["job_id"], unique=False)

    op.create_table(
        "answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_run_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("uncertainty", sa.Text(), nullable=True),
        sa.Column("limitations_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_call_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("evidence_context_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(value) for value in ANSWER_STATUSES)})",
            name="answers_status_valid",
        ),
        sa.ForeignKeyConstraint(["model_call_id"], ["model_calls.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["retrieval_run_id"], ["retrieval_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "research_run_id",
            "version",
            name="answers_scope_version_unique",
        ),
    )
    op.create_index(op.f("ix_answers_tenant_id"), "answers", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_answers_workspace_id"), "answers", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_answers_research_run_id"), "answers", ["research_run_id"], unique=False)
    op.create_index(op.f("ix_answers_retrieval_run_id"), "answers", ["retrieval_run_id"], unique=False)
    op.create_index(op.f("ix_answers_model_call_id"), "answers", ["model_call_id"], unique=False)

    op.create_table(
        "answer_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("support_status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"support_status IN ({', '.join(repr(value) for value in CLAIM_SUPPORT_STATUSES)})",
            name="answer_claims_support_status_valid",
        ),
        sa.ForeignKeyConstraint(["answer_id"], ["answers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("answer_id", "ordinal", name="answer_claims_answer_ordinal_unique"),
    )
    op.create_index(op.f("ix_answer_claims_tenant_id"), "answer_claims", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_answer_claims_workspace_id"), "answer_claims", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_answer_claims_answer_id"), "answer_claims", ["answer_id"], unique=False)

    op.create_table(
        "claim_citations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("citation_id", sa.String(length=255), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=True),
        sa.Column("chunk_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["claim_id"], ["answer_claims.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_claim_citations_tenant_id"), "claim_citations", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_claim_citations_workspace_id"), "claim_citations", ["workspace_id"], unique=False
    )
    op.create_index(
        op.f("ix_claim_citations_claim_id"), "claim_citations", ["claim_id"], unique=False
    )

    for table in ("model_calls", "answers", "answer_claims", "claim_citations"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        _tenant_workspace_scope_policy(table)


def downgrade() -> None:
    for table in ("claim_citations", "answer_claims", "answers", "model_calls"):
        op.execute(f"DROP POLICY IF EXISTS {table}_scope ON {table}")
        op.drop_table(table)
    op.drop_table("prompt_templates")
    op.drop_table("model_policy_versions")
