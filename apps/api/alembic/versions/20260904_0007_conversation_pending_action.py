"""Persist an incomplete customer action across conversation turns.

Revision ID: 20260904_0007
Revises: 20260904_0006
Create Date: 2026-09-04
"""

import sqlalchemy as sa

from alembic import op

revision = "20260904_0007"
down_revision = "20260904_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("pending_action", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("pending_action_payload", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "pending_action_payload")
    op.drop_column("conversations", "pending_action")
