"""Add metadata-only model invocation audit records.

Revision ID: 20260904_0008
Revises: 20260904_0007
Create Date: 2026-09-04
"""

import sqlalchemy as sa

from alembic import op

revision = "20260904_0008"
down_revision = "20260904_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_invocations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("api_style", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(length=80), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_model_invocations_trace_id",
        "model_invocations",
        ["trace_id"],
    )
    op.create_index(
        "ix_model_invocations_conversation_id",
        "model_invocations",
        ["conversation_id"],
    )
    op.create_index(
        "ix_model_invocations_message_id",
        "model_invocations",
        ["message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_invocations_message_id", table_name="model_invocations")
    op.drop_index("ix_model_invocations_conversation_id", table_name="model_invocations")
    op.drop_index("ix_model_invocations_trace_id", table_name="model_invocations")
    op.drop_table("model_invocations")
