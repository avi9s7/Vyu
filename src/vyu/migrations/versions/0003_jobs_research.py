"""job and research schema

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-05

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JOB_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "failed",
    "blocked",
    "cancelled",
)
RESEARCH_STATUSES = (
    "queued",
    "planning",
    "searching",
    "retrieving",
    "synthesizing",
    "review_required",
    "completed",
    "failed",
    "blocked",
    "cancelled",
)


def _tenant_scope_policy(table: str) -> None:
    op.execute(
        f"""
        CREATE POLICY {table}_scope ON {table}
        USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
        """
    )


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
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
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
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(value) for value in JOB_STATUSES)})",
            name="jobs_status_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobs_tenant_id"), "jobs", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_jobs_workspace_id"), "jobs", ["workspace_id"], unique=False)
    op.create_index("ix_jobs_lease", "jobs", ["status", "available_at", "leased_until"])

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("route", sa.String(length=255), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "actor_id", "route", "key"),
    )
    op.create_index(
        op.f("ix_idempotency_keys_tenant_id"), "idempotency_keys", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"], unique=False
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.String(length=64), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=255), nullable=False),
        sa.Column(
            "payload",
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
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_outbox_events_tenant_id"), "outbox_events", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_outbox_events_workspace_id"), "outbox_events", ["workspace_id"], unique=False
    )
    op.create_index(
        "ix_outbox_events_unpublished",
        "outbox_events",
        ["created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )

    op.create_table(
        "research_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("intended_use", sa.String(length=64), nullable=False),
        sa.Column(
            "requested_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_step", sa.String(length=64), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
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
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(value) for value in RESEARCH_STATUSES)})",
            name="research_runs_status_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_research_runs_tenant_id"), "research_runs", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_research_runs_workspace_id"), "research_runs", ["workspace_id"], unique=False
    )
    op.create_index(
        op.f("ix_research_runs_created_by"), "research_runs", ["created_by"], unique=False
    )

    op.create_table(
        "research_run_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("safe_message", sa.String(length=500), nullable=False),
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
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("research_run_id", "sequence"),
    )
    op.create_index(
        op.f("ix_research_run_events_tenant_id"),
        "research_run_events",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_run_events_workspace_id"),
        "research_run_events",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_run_events_research_run_id"),
        "research_run_events",
        ["research_run_id"],
        unique=False,
    )

    rls_tenant_only = ("idempotency_keys",)
    rls_tenant_workspace = (
        "jobs",
        "outbox_events",
        "research_runs",
        "research_run_events",
    )
    for table in rls_tenant_only + rls_tenant_workspace:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    for table in rls_tenant_only:
        _tenant_scope_policy(table)
    for table in rls_tenant_workspace:
        _tenant_workspace_scope_policy(table)

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO vyu_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO vyu_app")


def downgrade() -> None:
    for table in (
        "research_run_events",
        "research_runs",
        "outbox_events",
        "idempotency_keys",
        "jobs",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_scope ON {table}")

    op.drop_index(op.f("ix_research_run_events_research_run_id"), table_name="research_run_events")
    op.drop_index(op.f("ix_research_run_events_workspace_id"), table_name="research_run_events")
    op.drop_index(op.f("ix_research_run_events_tenant_id"), table_name="research_run_events")
    op.drop_table("research_run_events")

    op.drop_index(op.f("ix_research_runs_created_by"), table_name="research_runs")
    op.drop_index(op.f("ix_research_runs_workspace_id"), table_name="research_runs")
    op.drop_index(op.f("ix_research_runs_tenant_id"), table_name="research_runs")
    op.drop_table("research_runs")

    op.drop_index("ix_outbox_events_unpublished", table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_workspace_id"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_tenant_id"), table_name="outbox_events")
    op.drop_table("outbox_events")

    op.drop_index("ix_idempotency_keys_expires_at", table_name="idempotency_keys")
    op.drop_index(op.f("ix_idempotency_keys_tenant_id"), table_name="idempotency_keys")
    op.drop_table("idempotency_keys")

    op.drop_index("ix_jobs_lease", table_name="jobs")
    op.drop_index(op.f("ix_jobs_workspace_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_tenant_id"), table_name="jobs")
    op.drop_table("jobs")
