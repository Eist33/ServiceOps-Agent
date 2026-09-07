import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from serviceops.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class EmbeddingType(TypeDecorator):
    """pgvector in PostgreSQL, JSON fallback for deterministic SQLite tests."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(1536))
        return dialect.type_descriptor(JSON())


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RESOLVED = "RESOLVED"


class TicketPriority(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class HandoffStatus(StrEnum):
    BOT_ACTIVE = "BOT_ACTIVE"
    ASSIGNED = "ASSIGNED"
    COMPLETED = "COMPLETED"


class RefundStatus(StrEnum):
    PENDING_HUMAN_APPROVAL = "PENDING_HUMAN_APPROVAL"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    FAILED = "FAILED"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80))
    session_token: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Operator(Base):
    __tablename__ = "operators"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(40), default="KNOWLEDGE_MANAGER")
    session_token: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdentityAccount(Base):
    __tablename__ = "identity_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_identity_provider_subject"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    subject: Mapped[str] = mapped_column(String(160))
    login_name: Mapped[str | None] = mapped_column(
        String(80), nullable=True, unique=True, index=True
    )
    principal_type: Mapped[str] = mapped_column(String(20), index=True)
    principal_id: Mapped[str] = mapped_column(String(36), index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    identity_account_id: Mapped[str] = mapped_column(
        ForeignKey("identity_accounts.id"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SecurityAuditEvent(Base):
    __tablename__ = "security_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    outcome: Mapped[str] = mapped_column(String(30), index=True)
    account_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    principal_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    principal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    anonymized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RetentionRun(Base):
    __tablename__ = "retention_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    policy_version: Mapped[str] = mapped_column(String(40))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    cutoffs: Mapped[dict] = mapped_column(JSON, default=dict)
    deleted_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    anonymized_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(160))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    refundable_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(40))
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped[Customer] = relationship()


class ShippingEvent(Base):
    __tablename__ = "shipping_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    location: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(240))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    order: Mapped[Order] = relationship()


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"
    __table_args__ = (
        UniqueConstraint(
            "title",
            "version",
            "section",
            name="uq_knowledge_article_version_section",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(40))
    section: Mapped[str] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType(), nullable=True)
    source_uri: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        UniqueConstraint("source_uri", name="uq_knowledge_source_uri"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_uri: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(30), default="upload")
    owner: Mapped[str] = mapped_column(String(120), default="knowledge-operations")
    trust_level: Mapped[str] = mapped_column(String(30), default="operator_reviewed")
    authorization_scope: Mapped[str] = mapped_column(String(200), default="local-demo")
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_knowledge_document_content_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_sources.id"), index=True)
    source_uri: Mapped[str] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    content_hash: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    parser_version: Mapped[str] = mapped_column(String(40))
    chunking_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED", index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(240), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    supersedes_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_documents.id"), nullable=True
    )
    tenant_scope: Mapped[str] = mapped_column(String(120), default="local-demo")
    channel_scope: Mapped[str] = mapped_column(String(80), default="*")
    product_scope: Mapped[str] = mapped_column(String(120), default="*")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    block_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_knowledge_chunk_document_index",
        ),
        Index("ix_knowledge_chunks_content_hash", "content_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    block_type: Mapped[str] = mapped_column(String(30))
    title_path: Mapped[list[str]] = mapped_column(JSON, default=list)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    source_uri: Mapped[str] = mapped_column(String(500))
    tenant_scope: Mapped[str] = mapped_column(String(120), default="local-demo", index=True)
    channel_scope: Mapped[str] = mapped_column(String(80), default="*", index=True)
    product_scope: Mapped[str] = mapped_column(String(120), default="*", index=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeRelease(Base):
    __tablename__ = "knowledge_releases"
    __table_args__ = (
        UniqueConstraint("release_version", name="uq_knowledge_release_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    release_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    parser_version: Mapped[str] = mapped_column(String(40))
    chunking_version: Mapped[str] = mapped_column(String(40))
    retrieval_strategy_version: Mapped[str] = mapped_column(String(40), default="lexical_v1")
    evaluation_dataset_version: Mapped[str] = mapped_column(String(100))
    evaluation_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_manifest: Mapped[list[dict]] = mapped_column(JSON, default=list)
    git_commit: Mapped[str] = mapped_column(String(64), default="unbound")
    created_by: Mapped[str] = mapped_column(String(120))
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rollback_release_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_releases.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_normalization_version: Mapped[str | None] = mapped_column(
        String(40), nullable=True
    )
    embedding_status: Mapped[str] = mapped_column(String(30), default="NOT_REQUIRED")
    embedding_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_embedding_batches.id"), nullable=True
    )


class KnowledgeReleaseItem(Base):
    __tablename__ = "knowledge_release_items"
    __table_args__ = (
        UniqueConstraint(
            "release_id",
            "chunk_id",
            name="uq_knowledge_release_item_chunk",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    release_id: Mapped[str] = mapped_column(ForeignKey("knowledge_releases.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("knowledge_chunks.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    source_uri: Mapped[str] = mapped_column(String(500))
    title_path: Mapped[list[str]] = mapped_column(JSON, default=list)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeEmbeddingBatch(Base):
    __tablename__ = "knowledge_embedding_batches"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_knowledge_embedding_batch_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    release_id: Mapped[str] = mapped_column(ForeignKey("knowledge_releases.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    dimensions: Mapped[int] = mapped_column(Integer)
    normalization_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    requested_count: Mapped[int] = mapped_column(Integer, default=0)
    embedded_count: Mapped[int] = mapped_column(Integer, default=0)
    reused_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(180))
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeChunkEmbedding(Base):
    __tablename__ = "knowledge_chunk_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            "provider",
            "model",
            "dimensions",
            "normalization_version",
            name="uq_knowledge_chunk_embedding_variant",
        ),
        Index("ix_knowledge_chunk_embeddings_content_hash", "content_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("knowledge_chunks.id"), index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("knowledge_embedding_batches.id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    dimensions: Mapped[int] = mapped_column(Integer)
    normalization_version: Mapped[str] = mapped_column(String(40))
    embedding: Mapped[list[float]] = mapped_column(EmbeddingType())
    status: Mapped[str] = mapped_column(String(30), default="READY", index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeRetrievalTrace(Base):
    __tablename__ = "knowledge_retrieval_traces"
    __table_args__ = (Index("ix_knowledge_retrieval_traces_created_at", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_trace_id: Mapped[str] = mapped_column(String(64), index=True)
    query_hash: Mapped[str] = mapped_column(String(64), index=True)
    query_length: Mapped[int] = mapped_column(Integer)
    strategy: Mapped[str] = mapped_column(String(40))
    release_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reranker_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reranker_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reranker_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reranker_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    reranker_cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="SUCCEEDED", index=True)
    decision: Mapped[str] = mapped_column(String(30), default="REFUSE")
    confident: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    filter_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    candidate_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeRetrievalTraceCandidate(Base):
    __tablename__ = "knowledge_retrieval_trace_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trace_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_retrieval_traces.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    release_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    release_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    lexical_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vector_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rrf_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    lexical_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    vector_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rerank_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    decision: Mapped[str] = mapped_column(String(30), default="CANDIDATE")
    exclusion_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeRetrievalFeedback(Base):
    __tablename__ = "knowledge_retrieval_feedback"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_knowledge_retrieval_feedback_idempotency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trace_id: Mapped[str] = mapped_column(ForeignKey("knowledge_retrieval_traces.id"), index=True)
    label: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="PENDING_REVIEW", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    deidentified_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120))
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evaluation_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    active_order_id: Mapped[str | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True, index=True
    )
    order_selection_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    pending_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pending_action_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_active_ticket_scope", "customer_id", "order_id", "ticket_type", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    ticket_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default=TicketStatus.OPEN.value)
    priority: Mapped[str] = mapped_column(String(10), default=TicketPriority.P2.value)
    handoff_status: Mapped[str] = mapped_column(
        String(30), default=HandoffStatus.BOT_ACTIVE.value
    )
    assignee_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    handoff_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: utcnow() + timedelta(hours=4)
    )
    reason: Mapped[str] = mapped_column(String(500))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TicketEvent(Base):
    __tablename__ = "ticket_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(String(500))
    actor: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OperationsAlertAcknowledgement(Base):
    __tablename__ = "operations_alert_acknowledgements"
    __table_args__ = (
        UniqueConstraint(
            "ticket_id",
            "alert_type",
            name="uq_operations_alert_ack_ticket_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), index=True)
    alert_type: Mapped[str] = mapped_column(String(40))
    acknowledged_by_operator_id: Mapped[str] = mapped_column(ForeignKey("operators.id"))
    acknowledged_by_name: Mapped[str] = mapped_column(String(80))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerSatisfactionFeedback(Base):
    __tablename__ = "customer_satisfaction_feedback"
    __table_args__ = (
        UniqueConstraint("ticket_id", name="uq_customer_satisfaction_ticket"),
        CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_customer_satisfaction_rating",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RefundRequest(Base):
    __tablename__ = "refund_requests"
    __table_args__ = (
        Index(
            "uq_refund_requests_customer_order_active",
            "customer_id",
            "order_id",
            unique=True,
            sqlite_where=text(
                "status IN ('PENDING_HUMAN_APPROVAL', 'PENDING_CONFIRMATION', "
                "'PROCESSING', 'SUCCEEDED')"
            ),
            postgresql_where=text(
                "status IN ('PENDING_HUMAN_APPROVAL', 'PENDING_CONFIRMATION', "
                "'PROCESSING', 'SUCCEEDED')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    refund_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), index=True)
    status: Mapped[str] = mapped_column(
        String(40), default=RefundStatus.PENDING_HUMAN_APPROVAL.value
    )
    reason: Mapped[str] = mapped_column(String(500))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(80), default="原路退回")
    version: Mapped[int] = mapped_column(default=1)
    approved_by_operator_id: Mapped[str | None] = mapped_column(
        ForeignKey("operators.id"), nullable=True, index=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RefundApprovalAudit(Base):
    __tablename__ = "refund_approval_audits"
    __table_args__ = (
        UniqueConstraint(
            "refund_request_id",
            "idempotency_key",
            name="uq_refund_approval_refund_key",
        ),
        Index(
            "ix_refund_approval_audits_refund_created",
            "refund_request_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    refund_request_id: Mapped[str] = mapped_column(
        ForeignKey("refund_requests.id"), index=True
    )
    operator_id: Mapped[str] = mapped_column(ForeignKey("operators.id"), index=True)
    decision: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ToolInvocation(Base):
    __tablename__ = "tool_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    message_id: Mapped[str] = mapped_column(String(36), index=True)
    tool_call_id: Mapped[str] = mapped_column(String(36), index=True)
    tool_name: Mapped[str] = mapped_column(String(80))
    input_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    output_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30))
    duration_ms: Mapped[int] = mapped_column(default=0)
    error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ticket_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    refund_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelInvocation(Base):
    __tablename__ = "model_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    message_id: Mapped[str] = mapped_column(String(36), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    model_name: Mapped[str] = mapped_column(String(100))
    api_style: Mapped[str] = mapped_column(String(30))
    agent_release_id: Mapped[str] = mapped_column(String(80), default="legacy-unbound")
    agent_release_version: Mapped[str] = mapped_column(String(40), default="legacy-unbound")
    prompt_version: Mapped[str] = mapped_column(String(80), default="legacy-unbound")
    tool_schema_version: Mapped[str] = mapped_column(String(80), default="legacy-unbound")
    knowledge_release_version: Mapped[str] = mapped_column(
        String(80), default="legacy-unbound"
    )
    evaluation_dataset_version: Mapped[str] = mapped_column(
        String(100), default="legacy-unbound"
    )
    context_policy_version: Mapped[str] = mapped_column(String(80), default="legacy-unbound")
    context_token_count: Mapped[int] = mapped_column(Integer, default=0)
    context_source_count: Mapped[int] = mapped_column(Integer, default=0)
    context_truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30))
    duration_ms: Mapped[int] = mapped_column(default=0)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    total_tokens: Mapped[int] = mapped_column(default=0)
    error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("scope", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(120))
    idempotency_key: Mapped[str] = mapped_column(String(160))
    resource_id: Mapped[str] = mapped_column(String(36))
    response_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
