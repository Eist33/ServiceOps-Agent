"""Add knowledge operator identity and article version uniqueness.

Revision ID: 20260901_0003
Revises: 20260831_0002
Create Date: 2026-09-01
"""

import sqlalchemy as sa

from alembic import op

revision = "20260901_0003"
down_revision = "20260831_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operators",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "role",
            sa.String(length=40),
            nullable=False,
            server_default="KNOWLEDGE_MANAGER",
        ),
        sa.Column("session_token", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operators_session_token", "operators", ["session_token"], unique=True)
    op.create_unique_constraint(
        "uq_knowledge_article_version_section",
        "knowledge_articles",
        ["title", "version", "section"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_knowledge_article_version_section",
        "knowledge_articles",
        type_="unique",
    )
    op.drop_index("ix_operators_session_token", table_name="operators")
    op.drop_table("operators")
