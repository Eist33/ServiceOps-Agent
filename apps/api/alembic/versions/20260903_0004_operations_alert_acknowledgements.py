"""Add durable operations alert acknowledgements.

Revision ID: 20260903_0004
Revises: 20260901_0003
Create Date: 2026-09-03
"""

import sqlalchemy as sa

from alembic import op

revision = "20260903_0004"
down_revision = "20260901_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations_alert_acknowledgements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("alert_type", sa.String(length=40), nullable=False),
        sa.Column("acknowledged_by_operator_id", sa.String(length=36), nullable=False),
        sa.Column("acknowledged_by_name", sa.String(length=80), nullable=False),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["acknowledged_by_operator_id"], ["operators.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ticket_id",
            "alert_type",
            name="uq_operations_alert_ack_ticket_type",
        ),
    )
    op.create_index(
        "ix_operations_alert_acknowledgements_ticket_id",
        "operations_alert_acknowledgements",
        ["ticket_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operations_alert_acknowledgements_ticket_id",
        table_name="operations_alert_acknowledgements",
    )
    op.drop_table("operations_alert_acknowledgements")
