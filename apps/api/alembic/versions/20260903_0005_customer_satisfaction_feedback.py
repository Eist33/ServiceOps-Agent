"""Add durable customer satisfaction feedback.

Revision ID: 20260903_0005
Revises: 20260903_0004
Create Date: 2026-09-03
"""

import sqlalchemy as sa

from alembic import op

revision = "20260903_0005"
down_revision = "20260903_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_satisfaction_feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_customer_satisfaction_rating",
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", name="uq_customer_satisfaction_ticket"),
    )
    op.create_index(
        "ix_customer_satisfaction_feedback_customer_id",
        "customer_satisfaction_feedback",
        ["customer_id"],
    )
    op.create_index(
        "ix_customer_satisfaction_feedback_ticket_id",
        "customer_satisfaction_feedback",
        ["ticket_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_satisfaction_feedback_ticket_id",
        table_name="customer_satisfaction_feedback",
    )
    op.drop_index(
        "ix_customer_satisfaction_feedback_customer_id",
        table_name="customer_satisfaction_feedback",
    )
    op.drop_table("customer_satisfaction_feedback")
