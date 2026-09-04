"""Persist the active order selected for a conversation.

Revision ID: 20260904_0006
Revises: 20260903_0005
Create Date: 2026-09-04
"""

import sqlalchemy as sa

from alembic import op

revision = "20260904_0006"
down_revision = "20260903_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("active_order_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "order_selection_pending",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_foreign_key(
        "fk_conversations_active_order_id_orders",
        "conversations",
        "orders",
        ["active_order_id"],
        ["id"],
    )
    op.create_index(
        "ix_conversations_active_order_id",
        "conversations",
        ["active_order_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_active_order_id", table_name="conversations")
    op.drop_constraint(
        "fk_conversations_active_order_id_orders",
        "conversations",
        type_="foreignkey",
    )
    op.drop_column("conversations", "order_selection_pending")
    op.drop_column("conversations", "active_order_id")
