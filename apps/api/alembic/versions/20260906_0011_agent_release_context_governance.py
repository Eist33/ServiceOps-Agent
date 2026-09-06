"""Bind model audit records to Agent releases and context policy versions.

Revision ID: 20260906_0011
Revises: 20260905_0010
Create Date: 2026-09-06
"""

import sqlalchemy as sa

from alembic import op

revision = "20260906_0011"
down_revision = "20260905_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = (
        sa.Column(
            "agent_release_id",
            sa.String(length=80),
            nullable=False,
            server_default="legacy-unbound",
        ),
        sa.Column(
            "agent_release_version",
            sa.String(length=40),
            nullable=False,
            server_default="legacy-unbound",
        ),
        sa.Column(
            "prompt_version",
            sa.String(length=80),
            nullable=False,
            server_default="legacy-unbound",
        ),
        sa.Column(
            "tool_schema_version",
            sa.String(length=80),
            nullable=False,
            server_default="legacy-unbound",
        ),
        sa.Column(
            "knowledge_release_version",
            sa.String(length=80),
            nullable=False,
            server_default="legacy-unbound",
        ),
        sa.Column(
            "evaluation_dataset_version",
            sa.String(length=100),
            nullable=False,
            server_default="legacy-unbound",
        ),
        sa.Column(
            "context_policy_version",
            sa.String(length=80),
            nullable=False,
            server_default="legacy-unbound",
        ),
        sa.Column("context_token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("context_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("context_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    for column in columns:
        op.add_column("model_invocations", column)


def downgrade() -> None:
    for name in (
        "context_truncated",
        "context_source_count",
        "context_token_count",
        "context_policy_version",
        "evaluation_dataset_version",
        "knowledge_release_version",
        "tool_schema_version",
        "prompt_version",
        "agent_release_version",
        "agent_release_id",
    ):
        op.drop_column("model_invocations", name)
