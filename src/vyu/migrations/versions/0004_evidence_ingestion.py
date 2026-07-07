"""evidence ingestion schema

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-07

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DOCUMENT_STATUSES = (
    "awaiting_upload",
    "uploaded",
    "scanning",
    "blocked",
    "parsing",
    "chunking",
    "ready",
    "failed",
    "deleted",
)
MALWARE_STATUSES = ("clean", "infected", "error", "unknown")
PHI_STATUSES = ("non_phi", "suspected_phi", "unknown")


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
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
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
            f"status IN ({', '.join(repr(value) for value in DOCUMENT_STATUSES)})",
            name="documents_status_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_tenant_id"), "documents", ["tenant_id"], unique=False)
    op.create_index(
        op.f("ix_documents_workspace_id"), "documents", ["workspace_id"], unique=False
    )
    op.create_index(op.f("ix_documents_source_id"), "documents", ["source_id"], unique=False)
    op.create_index(op.f("ix_documents_status"), "documents", ["status"], unique=False)
    op.execute(
        """
        CREATE UNIQUE INDEX documents_external_id_unique
        ON documents (tenant_id, workspace_id, source_id, external_id)
        WHERE external_id IS NOT NULL
        """
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("original_bucket", sa.String(length=255), nullable=True),
        sa.Column("original_key", sa.String(length=1024), nullable=True),
        sa.Column("original_version_id", sa.String(length=255), nullable=True),
        sa.Column("normalized_bucket", sa.String(length=255), nullable=True),
        sa.Column("normalized_key", sa.String(length=1024), nullable=True),
        sa.Column("normalized_version_id", sa.String(length=255), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("media_type", sa.String(length=255), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("classification", sa.String(length=64), nullable=True),
        sa.Column("malware_status", sa.String(length=32), nullable=True),
        sa.Column("phi_status", sa.String(length=32), nullable=True),
        sa.Column("parser_name", sa.String(length=128), nullable=True),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"malware_status IS NULL OR malware_status IN ({', '.join(repr(value) for value in MALWARE_STATUSES)})",
            name="document_versions_malware_status_valid",
        ),
        sa.CheckConstraint(
            f"phi_status IS NULL OR phi_status IN ({', '.join(repr(value) for value in PHI_STATUSES)})",
            name="document_versions_phi_status_valid",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "version", name="document_versions_document_version_unique"),
    )
    op.create_index(
        op.f("ix_document_versions_tenant_id"),
        "document_versions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_versions_workspace_id"),
        "document_versions",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_versions_document_id"),
        "document_versions",
        ["document_id"],
        unique=False,
    )
    op.create_foreign_key(
        "documents_current_version_id_fkey",
        "documents",
        "document_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "evidence_objects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("key", sa.String(length=1024), nullable=False),
        sa.Column("version_id", sa.String(length=255), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evidence_objects_tenant_id"),
        "evidence_objects",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_objects_workspace_id"),
        "evidence_objects",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_objects_document_version_id"),
        "evidence_objects",
        ["document_version_id"],
        unique=False,
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("citation_id", sa.String(length=255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("page_from", sa.Integer(), nullable=True),
        sa.Column("page_to", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(length=255), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_version_id", "ordinal", name="document_chunks_version_ordinal_unique"
        ),
        sa.UniqueConstraint(
            "document_version_id",
            "citation_id",
            name="document_chunks_version_citation_unique",
        ),
    )
    op.create_index(
        op.f("ix_document_chunks_tenant_id"),
        "document_chunks",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_chunks_workspace_id"),
        "document_chunks",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_chunks_document_version_id"),
        "document_chunks",
        ["document_version_id"],
        unique=False,
    )

    op.create_table(
        "ingestion_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("safe_message", sa.String(length=500), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "sequence", name="ingestion_events_job_sequence_unique"),
    )
    op.create_index(
        op.f("ix_ingestion_events_tenant_id"),
        "ingestion_events",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingestion_events_workspace_id"),
        "ingestion_events",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingestion_events_document_id"),
        "ingestion_events",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingestion_events_job_id"), "ingestion_events", ["job_id"], unique=False
    )

    rls_tables = (
        "documents",
        "document_versions",
        "evidence_objects",
        "document_chunks",
        "ingestion_events",
    )
    for table in rls_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        _tenant_workspace_scope_policy(table)

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO vyu_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO vyu_app")


def downgrade() -> None:
    for table in (
        "ingestion_events",
        "document_chunks",
        "evidence_objects",
        "document_versions",
        "documents",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_scope ON {table}")

    op.drop_index(op.f("ix_ingestion_events_job_id"), table_name="ingestion_events")
    op.drop_index(op.f("ix_ingestion_events_document_id"), table_name="ingestion_events")
    op.drop_index(op.f("ix_ingestion_events_workspace_id"), table_name="ingestion_events")
    op.drop_index(op.f("ix_ingestion_events_tenant_id"), table_name="ingestion_events")
    op.drop_table("ingestion_events")

    op.drop_index(op.f("ix_document_chunks_document_version_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_workspace_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_tenant_id"), table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index(op.f("ix_evidence_objects_document_version_id"), table_name="evidence_objects")
    op.drop_index(op.f("ix_evidence_objects_workspace_id"), table_name="evidence_objects")
    op.drop_index(op.f("ix_evidence_objects_tenant_id"), table_name="evidence_objects")
    op.drop_table("evidence_objects")

    op.drop_constraint("documents_current_version_id_fkey", "documents", type_="foreignkey")
    op.drop_index(op.f("ix_document_versions_document_id"), table_name="document_versions")
    op.drop_index(op.f("ix_document_versions_workspace_id"), table_name="document_versions")
    op.drop_index(op.f("ix_document_versions_tenant_id"), table_name="document_versions")
    op.drop_table("document_versions")

    op.execute("DROP INDEX IF EXISTS documents_external_id_unique")
    op.drop_index(op.f("ix_documents_status"), table_name="documents")
    op.drop_index(op.f("ix_documents_source_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_workspace_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_tenant_id"), table_name="documents")
    op.drop_table("documents")
