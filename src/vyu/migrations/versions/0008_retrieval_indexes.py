"""retrieval index and embedding persistence

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-07

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APPROVED_EMBEDDING_DIMENSIONS = 1536
INDEX_STATUSES = ("building", "validating", "active", "failed", "retired")


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
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "retrieval_indexes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("use_case", sa.String(length=64), nullable=False, server_default="evidence_memory"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="building"),
        sa.Column("manifest_checksum", sa.String(length=64), nullable=False),
        sa.Column("manifest_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("chunker_name", sa.String(length=128), nullable=False),
        sa.Column("chunker_version", sa.String(length=64), nullable=False),
        sa.Column("embedding_provider", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("build_git_sha", sa.String(length=64), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluation_result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("lexical_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("semantic_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
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
            f"status IN ({', '.join(repr(value) for value in INDEX_STATUSES)})",
            name="retrieval_indexes_status_valid",
        ),
        sa.CheckConstraint(
            f"embedding_dimensions = {APPROVED_EMBEDDING_DIMENSIONS}",
            name="retrieval_indexes_embedding_dimensions_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_retrieval_indexes_tenant_id"),
        "retrieval_indexes",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_retrieval_indexes_workspace_id"),
        "retrieval_indexes",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_retrieval_indexes_manifest_checksum"),
        "retrieval_indexes",
        ["manifest_checksum"],
        unique=False,
    )
    op.create_index(
        "uq_retrieval_indexes_active_scope",
        "retrieval_indexes",
        ["tenant_id", "workspace_id", "use_case"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_index_id", sa.Uuid(), nullable=False),
        sa.Column("document_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("usage_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"dimensions = {APPROVED_EMBEDDING_DIMENSIONS}",
            name="chunk_embeddings_dimensions_valid",
        ),
        sa.ForeignKeyConstraint(
            ["document_chunk_id"],
            ["document_chunks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_index_id"],
            ["retrieval_indexes.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "retrieval_index_id",
            "document_chunk_id",
            name="chunk_embeddings_index_chunk_unique",
        ),
    )
    op.execute(
        f"""
        ALTER TABLE chunk_embeddings
        ADD COLUMN embedding vector({APPROVED_EMBEDDING_DIMENSIONS}) NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE chunk_embeddings
        ADD COLUMN search_vector tsvector
        """
    )
    op.create_index(
        "ix_chunk_embeddings_cache_lookup",
        "chunk_embeddings",
        ["tenant_id", "text_sha256", "provider", "model", "dimensions"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chunk_embeddings_tenant_id"),
        "chunk_embeddings",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chunk_embeddings_workspace_id"),
        "chunk_embeddings",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chunk_embeddings_retrieval_index_id"),
        "chunk_embeddings",
        ["retrieval_index_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chunk_embeddings_document_chunk_id"),
        "chunk_embeddings",
        ["document_chunk_id"],
        unique=False,
    )

    op.create_table(
        "retrieval_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_run_key", sa.String(length=128), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=128), nullable=False),
        sa.Column("retrieval_index_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("retrieval_mode", sa.String(length=64), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("query_metadata_filter_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retriever_versions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("evaluation_suite", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_index_id"],
            ["retrieval_indexes.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("retrieval_run_key", name="retrieval_runs_retrieval_run_key_unique"),
    )
    op.create_index(
        op.f("ix_retrieval_runs_tenant_id"),
        "retrieval_runs",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_retrieval_runs_workspace_id"),
        "retrieval_runs",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_retrieval_runs_workflow_run_id"),
        "retrieval_runs",
        ["workflow_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_retrieval_runs_retrieval_index_id"),
        "retrieval_runs",
        ["retrieval_index_id"],
        unique=False,
    )

    op.create_table(
        "retrieval_hits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_run_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.String(length=128), nullable=False),
        sa.Column("passage_id", sa.String(length=255), nullable=False),
        sa.Column("document_chunk_id", sa.Uuid(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score_source", sa.String(length=64), nullable=False),
        sa.Column("score_value", sa.Float(), nullable=False),
        sa.Column("score_components_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("trace_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_run_id"],
            ["retrieval_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_retrieval_hits_tenant_id"),
        "retrieval_hits",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_retrieval_hits_workspace_id"),
        "retrieval_hits",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_retrieval_hits_retrieval_run_id"),
        "retrieval_hits",
        ["retrieval_run_id"],
        unique=False,
    )

    op.create_table(
        "retrieval_exclusions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_run_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.String(length=128), nullable=True),
        sa.Column("document_chunk_id", sa.Uuid(), nullable=True),
        sa.Column("exclusion_kind", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_run_id"],
            ["retrieval_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_retrieval_exclusions_tenant_id"),
        "retrieval_exclusions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_retrieval_exclusions_workspace_id"),
        "retrieval_exclusions",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_retrieval_exclusions_retrieval_run_id"),
        "retrieval_exclusions",
        ["retrieval_run_id"],
        unique=False,
    )

    for table in (
        "retrieval_indexes",
        "chunk_embeddings",
        "retrieval_runs",
        "retrieval_hits",
        "retrieval_exclusions",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        _tenant_workspace_scope_policy(table)


def downgrade() -> None:
    for table in (
        "retrieval_exclusions",
        "retrieval_hits",
        "retrieval_runs",
        "chunk_embeddings",
        "retrieval_indexes",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_scope ON {table}")
        op.drop_table(table)
