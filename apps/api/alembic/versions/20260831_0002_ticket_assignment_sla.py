"""Add ticket handoff, assignment and SLA fields.

Revision ID: 20260831_0002
Revises: 20260831_0001
Create Date: 2026-08-31
"""

import sqlalchemy as sa

from alembic import op

revision = "20260831_0002"
down_revision = "20260831_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("priority", sa.String(length=10), nullable=False, server_default="P2"),
    )
    op.add_column(
        "tickets",
        sa.Column(
            "handoff_status",
            sa.String(length=30),
            nullable=False,
            server_default="BOT_ACTIVE",
        ),
    )
    op.add_column("tickets", sa.Column("assignee_name", sa.String(length=80), nullable=True))
    op.add_column(
        "tickets", sa.Column("handoff_requested_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("tickets", sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tickets", sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("UPDATE tickets SET sla_due_at = created_at + INTERVAL '4 hours'")
        op.alter_column("tickets", "sla_due_at", nullable=False)
    else:
        op.execute("UPDATE tickets SET sla_due_at = datetime(created_at, '+4 hours')")


def downgrade() -> None:
    op.drop_column("tickets", "sla_due_at")
    op.drop_column("tickets", "assigned_at")
    op.drop_column("tickets", "handoff_requested_at")
    op.drop_column("tickets", "assignee_name")
    op.drop_column("tickets", "handoff_status")
    op.drop_column("tickets", "priority")
