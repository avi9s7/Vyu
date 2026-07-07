"""research execution persistence

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-07

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
        "research_search_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.String(length=128), nullable=False),
        sa.Column("plan_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("plan_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("research_run_id"),
    )
    op.create_index(
        op.f("ix_research_search_plans_tenant_id"),
        "research_search_plans",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_search_plans_workspace_id"),
        "research_search_plans",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_search_plans_research_run_id"),
        "research_search_plans",
        ["research_run_id"],
        unique=False,
    )

    op.create_table(
        "research_tool_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("plan_id", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("record_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("research_run_id", "request_hash"),
        sa.UniqueConstraint("call_id"),
    )
    op.create_index(
        op.f("ix_research_tool_calls_tenant_id"),
        "research_tool_calls",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_tool_calls_workspace_id"),
        "research_tool_calls",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_tool_calls_research_run_id"),
        "research_tool_calls",
        ["research_run_id"],
        unique=False,
    )

    op.create_table(
        "research_tool_replays",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "workspace_id", "request_hash"),
    )
    op.create_index(
        op.f("ix_research_tool_replays_tenant_id"),
        "research_tool_replays",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_tool_replays_workspace_id"),
        "research_tool_replays",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_tool_replays_research_run_id"),
        "research_tool_replays",
        ["research_run_id"],
        unique=False,
    )

    for table in ("research_search_plans", "research_tool_calls", "research_tool_replays"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        _tenant_workspace_scope_policy(table)


def downgrade() -> None:
    for table in ("research_tool_replays", "research_tool_calls", "research_search_plans"):
        op.execute(f"DROP POLICY IF EXISTS {table}_scope ON {table}")
        op.drop_table(table)
