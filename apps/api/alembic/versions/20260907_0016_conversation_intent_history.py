"""Persist current conversation intent and auditable intent changes."""

import sqlalchemy as sa

from alembic import op

revision = "20260907_0016"
down_revision = "20260907_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("current_intent", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "ix_conversations_current_intent",
        "conversations",
        ["current_intent"],
    )
    op.create_table(
        "conversation_intent_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("intent", sa.String(length=40), nullable=False),
        sa.Column("previous_intent", sa.String(length=40), nullable=True),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_ticket_id", sa.String(length=36), nullable=True),
        sa.Column("related_ticket_id", sa.String(length=36), nullable=True),
        sa.Column("related_refund_id", sa.String(length=36), nullable=True),
        sa.Column("detail", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "message_id",
            "intent",
            name="uq_conversation_intent_message",
        ),
    )
    op.create_index(
        "ix_conversation_intent_events_conversation_id",
        "conversation_intent_events",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_intent_events_message_id",
        "conversation_intent_events",
        ["message_id"],
    )
    op.create_index(
        "ix_conversation_intent_events_source_ticket_id",
        "conversation_intent_events",
        ["source_ticket_id"],
    )
    op.create_index(
        "ix_conversation_intent_events_related_ticket_id",
        "conversation_intent_events",
        ["related_ticket_id"],
    )
    op.create_index(
        "ix_conversation_intent_events_related_refund_id",
        "conversation_intent_events",
        ["related_refund_id"],
    )
    op.create_index(
        "ix_conversation_intent_events_conversation_created",
        "conversation_intent_events",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_intent_events_conversation_created",
        table_name="conversation_intent_events",
    )
    op.drop_index(
        "ix_conversation_intent_events_related_refund_id",
        table_name="conversation_intent_events",
    )
    op.drop_index(
        "ix_conversation_intent_events_related_ticket_id",
        table_name="conversation_intent_events",
    )
    op.drop_index(
        "ix_conversation_intent_events_source_ticket_id",
        table_name="conversation_intent_events",
    )
    op.drop_index(
        "ix_conversation_intent_events_message_id",
        table_name="conversation_intent_events",
    )
    op.drop_index(
        "ix_conversation_intent_events_conversation_id",
        table_name="conversation_intent_events",
    )
    op.drop_table("conversation_intent_events")
    op.drop_index("ix_conversations_current_intent", table_name="conversations")
    op.drop_column("conversations", "current_intent")
