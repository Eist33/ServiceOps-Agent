"""Require human refund approval and bind refund decisions to audits."""

import sqlalchemy as sa

from alembic import op

revision = "20260907_0015"
down_revision = "20260906_0014"
branch_labels = None
depends_on = None


ACTIVE_REFUND_STATUS = (
    "'PENDING_HUMAN_APPROVAL', 'PENDING_CONFIRMATION', 'PROCESSING', 'SUCCEEDED'"
)


def upgrade() -> None:
    op.add_column(
        "refund_requests",
        sa.Column("approved_by_operator_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "refund_requests",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_refund_requests_approved_by_operator",
        "refund_requests",
        "operators",
        ["approved_by_operator_id"],
        ["id"],
    )
    # Legacy PENDING_CONFIRMATION rows have no human approval identity/time.
    # Move them behind the new approval gate instead of allowing an old row to
    # reach the local execution adapter after this migration.
    op.execute(
        "UPDATE refund_requests SET status = 'PENDING_HUMAN_APPROVAL' "
        "WHERE status = 'PENDING_CONFIRMATION'"
    )
    op.create_index(
        "ix_refund_requests_approved_by_operator_id",
        "refund_requests",
        ["approved_by_operator_id"],
    )
    op.create_index(
        "uq_refund_requests_customer_order_active",
        "refund_requests",
        ["customer_id", "order_id"],
        unique=True,
        sqlite_where=sa.text(f"status IN ({ACTIVE_REFUND_STATUS})"),
        postgresql_where=sa.text(f"status IN ({ACTIVE_REFUND_STATUS})"),
    )
    op.create_table(
        "refund_approval_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("refund_request_id", sa.String(length=36), nullable=False),
        sa.Column("operator_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["refund_request_id"], ["refund_requests.id"]),
        sa.ForeignKeyConstraint(["operator_id"], ["operators.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "refund_request_id",
            "idempotency_key",
            name="uq_refund_approval_refund_key",
        ),
    )
    op.create_index(
        "ix_refund_approval_audits_refund_request_id",
        "refund_approval_audits",
        ["refund_request_id"],
    )
    op.create_index(
        "ix_refund_approval_audits_operator_id",
        "refund_approval_audits",
        ["operator_id"],
    )
    op.create_index(
        "ix_refund_approval_audits_refund_created",
        "refund_approval_audits",
        ["refund_request_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_refund_approval_audits_refund_created",
        table_name="refund_approval_audits",
    )
    op.drop_index(
        "ix_refund_approval_audits_operator_id",
        table_name="refund_approval_audits",
    )
    op.drop_index(
        "ix_refund_approval_audits_refund_request_id",
        table_name="refund_approval_audits",
    )
    op.drop_table("refund_approval_audits")
    op.drop_index(
        "uq_refund_requests_customer_order_active", table_name="refund_requests"
    )
    op.drop_index(
        "ix_refund_requests_approved_by_operator_id", table_name="refund_requests"
    )
    op.drop_constraint(
        "fk_refund_requests_approved_by_operator",
        "refund_requests",
        type_="foreignkey",
    )
    op.drop_column("refund_requests", "approved_at")
    op.drop_column("refund_requests", "approved_by_operator_id")
