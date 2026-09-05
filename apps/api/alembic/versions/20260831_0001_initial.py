"""Create the original ServiceOps MVP schema.

Revision ID: 20260831_0001
Revises:
Create Date: 2026-08-31

This migration intentionally contains a frozen schema snapshot. Importing the
current ORM metadata here would make a fresh database include later changes
before their own migrations run.
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "20260831_0001"
down_revision = None
branch_labels = None
depends_on = None


class EmbeddingType(sa.TypeDecorator):
    impl = sa.JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(1536))
        return dialect.type_descriptor(sa.JSON())


def _initial_metadata() -> sa.MetaData:
    metadata = sa.MetaData()
    customers = sa.Table(
        "customers",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("session_token", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_customers_session_token", customers.c.session_token, unique=True)

    orders = sa.Table(
        "orders",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_number", sa.String(40), nullable=False),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("product_name", sa.String(160), nullable=False),
        sa.Column("paid_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("refundable_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_orders_order_number", orders.c.order_number, unique=True)
    sa.Index("ix_orders_customer_id", orders.c.customer_id)

    shipping_events = sa.Table(
        "shipping_events",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("location", sa.String(160), nullable=False),
        sa.Column("description", sa.String(240), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_shipping_events_order_id", shipping_events.c.order_id)
    sa.Index("ix_shipping_events_occurred_at", shipping_events.c.occurred_at)

    knowledge_articles = sa.Table(
        "knowledge_articles",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("section", sa.String(80), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("embedding", EmbeddingType(), nullable=True),
        sa.Column("source_uri", sa.String(500), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_knowledge_articles_active", knowledge_articles.c.active)

    conversations = sa.Table(
        "conversations",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_conversations_customer_id", conversations.c.customer_id)

    messages = sa.Table(
        "messages",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_messages_conversation_id", messages.c.conversation_id)

    tickets = sa.Table(
        "tickets",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ticket_number", sa.String(40), nullable=False),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("ticket_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_tickets_ticket_number", tickets.c.ticket_number, unique=True)
    sa.Index("ix_tickets_customer_id", tickets.c.customer_id)
    sa.Index("ix_tickets_order_id", tickets.c.order_id)
    sa.Index("ix_tickets_conversation_id", tickets.c.conversation_id)
    sa.Index(
        "ix_active_ticket_scope",
        tickets.c.customer_id,
        tickets.c.order_id,
        tickets.c.ticket_type,
        tickets.c.status,
    )

    ticket_events = sa.Table(
        "ticket_events",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_ticket_events_ticket_id", ticket_events.c.ticket_id)

    refund_requests = sa.Table(
        "refund_requests",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("refund_number", sa.String(40), nullable=False),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_refund_requests_refund_number", refund_requests.c.refund_number, unique=True)
    sa.Index("ix_refund_requests_customer_id", refund_requests.c.customer_id)
    sa.Index("ix_refund_requests_order_id", refund_requests.c.order_id)
    sa.Index("ix_refund_requests_ticket_id", refund_requests.c.ticket_id)

    tool_invocations = sa.Table(
        "tool_invocations",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trace_id", sa.String(36), nullable=False),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("message_id", sa.String(36), nullable=False),
        sa.Column("tool_call_id", sa.String(36), nullable=False),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column("input_summary", sa.JSON(), nullable=False),
        sa.Column("output_summary", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(80), nullable=True),
        sa.Column("order_id", sa.String(36), nullable=True),
        sa.Column("ticket_id", sa.String(36), nullable=True),
        sa.Column("refund_request_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_tool_invocations_trace_id", tool_invocations.c.trace_id)
    sa.Index("ix_tool_invocations_conversation_id", tool_invocations.c.conversation_id)
    sa.Index("ix_tool_invocations_message_id", tool_invocations.c.message_id)
    sa.Index("ix_tool_invocations_tool_call_id", tool_invocations.c.tool_call_id)

    sa.Table(
        "idempotency_records",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope", sa.String(120), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope", "idempotency_key"),
    )
    return metadata


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _initial_metadata().create_all(bind=bind)


def downgrade() -> None:
    _initial_metadata().drop_all(bind=op.get_bind())
