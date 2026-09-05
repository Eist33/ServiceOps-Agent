"""Add provider-neutral identity accounts and revocable auth sessions.

Revision ID: 20260905_0009
Revises: 20260904_0008
Create Date: 2026-09-05
"""

import sqlalchemy as sa

from alembic import op

revision = "20260905_0009"
down_revision = "20260904_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identity_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("subject", sa.String(length=160), nullable=False),
        sa.Column("login_name", sa.String(length=80), nullable=True),
        sa.Column("principal_type", sa.String(length=20), nullable=False),
        sa.Column("principal_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "subject", name="uq_identity_provider_subject"
        ),
    )
    op.create_index(
        "ix_identity_accounts_provider", "identity_accounts", ["provider"]
    )
    op.create_index(
        "ix_identity_accounts_login_name",
        "identity_accounts",
        ["login_name"],
        unique=True,
    )
    op.create_index(
        "ix_identity_accounts_principal_type",
        "identity_accounts",
        ["principal_type"],
    )
    op.create_index(
        "ix_identity_accounts_principal_id",
        "identity_accounts",
        ["principal_id"],
    )
    op.create_index(
        "ix_identity_accounts_active", "identity_accounts", ["active"]
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("identity_account_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["identity_account_id"], ["identity_accounts.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_sessions_identity_account_id",
        "auth_sessions",
        ["identity_account_id"],
    )
    op.create_index(
        "ix_auth_sessions_token_hash",
        "auth_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_token_hash", table_name="auth_sessions")
    op.drop_index(
        "ix_auth_sessions_identity_account_id", table_name="auth_sessions"
    )
    op.drop_table("auth_sessions")
    op.drop_index("ix_identity_accounts_active", table_name="identity_accounts")
    op.drop_index(
        "ix_identity_accounts_principal_id", table_name="identity_accounts"
    )
    op.drop_index(
        "ix_identity_accounts_principal_type", table_name="identity_accounts"
    )
    op.drop_index(
        "ix_identity_accounts_login_name", table_name="identity_accounts"
    )
    op.drop_index("ix_identity_accounts_provider", table_name="identity_accounts")
    op.drop_table("identity_accounts")
