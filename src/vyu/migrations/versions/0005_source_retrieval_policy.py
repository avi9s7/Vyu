"""source and research tool policy schema

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-07

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_VERSION_STATUSES = ("draft", "active", "retired")
SOURCE_APPROVAL_STATUSES = ("draft", "approved", "quarantined", "expired")
TOOL_APPROVAL_STATUSES = ("draft", "approved", "quarantined", "expired")


def upgrade() -> None:
    op.create_table(
        "source_policy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("policy_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by", sa.String(length=255), nullable=True),
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
            f"status IN ({', '.join(repr(value) for value in POLICY_VERSION_STATUSES)})",
            name="source_policy_versions_status_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_number", name="source_policy_versions_version_number_unique"),
    )
    op.create_index(
        op.f("ix_source_policy_versions_status"),
        "source_policy_versions",
        ["status"],
        unique=False,
    )

    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("record_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("approval_status", sa.String(length=32), nullable=False),
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quarantined_by", sa.String(length=255), nullable=True),
        sa.Column("quarantined_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            f"approval_status IN ({', '.join(repr(value) for value in SOURCE_APPROVAL_STATUSES)})",
            name="sources_approval_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["policy_version_id"],
            ["source_policy_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_version_id", "source_id", name="sources_policy_source_unique"),
    )
    op.create_index(op.f("ix_sources_policy_version_id"), "sources", ["policy_version_id"])
    op.create_index(op.f("ix_sources_source_id"), "sources", ["source_id"])

    op.create_table(
        "research_tool_policy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("policy_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by", sa.String(length=255), nullable=True),
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
            f"status IN ({', '.join(repr(value) for value in POLICY_VERSION_STATUSES)})",
            name="research_tool_policy_versions_status_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_number",
            name="research_tool_policy_versions_version_number_unique",
        ),
    )
    op.create_index(
        op.f("ix_research_tool_policy_versions_status"),
        "research_tool_policy_versions",
        ["status"],
        unique=False,
    )

    op.create_table(
        "research_tools",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("tool_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("record_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("approval_status", sa.String(length=32), nullable=False),
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quarantined_by", sa.String(length=255), nullable=True),
        sa.Column("quarantined_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            f"approval_status IN ({', '.join(repr(value) for value in TOOL_APPROVAL_STATUSES)})",
            name="research_tools_approval_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["policy_version_id"],
            ["research_tool_policy_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_version_id", "tool_id", name="research_tools_policy_tool_unique"),
    )
    op.create_index(
        op.f("ix_research_tools_policy_version_id"),
        "research_tools",
        ["policy_version_id"],
    )
    op.create_index(op.f("ix_research_tools_tool_id"), "research_tools", ["tool_id"])
    op.create_index(op.f("ix_research_tools_source_id"), "research_tools", ["source_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_research_tools_source_id"), table_name="research_tools")
    op.drop_index(op.f("ix_research_tools_tool_id"), table_name="research_tools")
    op.drop_index(op.f("ix_research_tools_policy_version_id"), table_name="research_tools")
    op.drop_table("research_tools")
    op.drop_index(
        op.f("ix_research_tool_policy_versions_status"),
        table_name="research_tool_policy_versions",
    )
    op.drop_table("research_tool_policy_versions")
    op.drop_index(op.f("ix_sources_source_id"), table_name="sources")
    op.drop_index(op.f("ix_sources_policy_version_id"), table_name="sources")
    op.drop_table("sources")
    op.drop_index(op.f("ix_source_policy_versions_status"), table_name="source_policy_versions")
    op.drop_table("source_policy_versions")
