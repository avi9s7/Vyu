"""connector rate limit windows

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-07

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connector_rate_windows",
        sa.Column("source_key", sa.String(length=128), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("source_key", "window_start"),
    )


def downgrade() -> None:
    op.drop_table("connector_rate_windows")
