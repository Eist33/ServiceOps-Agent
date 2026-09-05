"""Add security audit and retention run records for the 9B-4 lifecycle.

Revision ID: 20260905_0010
Revises: 20260905_0009
Create Date: 2026-09-05
"""

import sqlalchemy as sa

from alembic import op

revision = "20260905_0010"
down_revision = "20260905_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("principal_type", sa.String(length=20), nullable=True),
        sa.Column("principal_id", sa.String(length=36), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_security_audit_events_event_type",
        "security_audit_events",
        ["event_type"],
    )
    op.create_index(
        "ix_security_audit_events_outcome",
        "security_audit_events",
        ["outcome"],
    )
    op.create_index(
        "ix_security_audit_events_account_id",
        "security_audit_events",
        ["account_id"],
    )
    op.create_table(
        "retention_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("policy_version", sa.String(length=40), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("cutoffs", sa.JSON(), nullable=False),
        sa.Column("deleted_counts", sa.JSON(), nullable=False),
        sa.Column("anonymized_counts", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retention_runs_as_of", "retention_runs", ["as_of"])
    op.create_index("ix_retention_runs_status", "retention_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_retention_runs_status", table_name="retention_runs")
    op.drop_index("ix_retention_runs_as_of", table_name="retention_runs")
    op.drop_table("retention_runs")
    op.drop_index(
        "ix_security_audit_events_account_id", table_name="security_audit_events"
    )
    op.drop_index(
        "ix_security_audit_events_outcome", table_name="security_audit_events"
    )
    op.drop_index(
        "ix_security_audit_events_event_type", table_name="security_audit_events"
    )
    op.drop_table("security_audit_events")
