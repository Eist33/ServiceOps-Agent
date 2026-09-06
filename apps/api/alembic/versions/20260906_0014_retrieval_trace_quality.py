"""Add retrieval traces, candidate scores, and reviewed quality feedback."""

import sqlalchemy as sa

from alembic import op

revision = "20260906_0014"
down_revision = "20260906_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_retrieval_traces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("request_trace_id", sa.String(length=64), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("query_length", sa.Integer(), nullable=False),
        sa.Column("strategy", sa.String(length=40), nullable=False),
        sa.Column("release_version", sa.String(length=80), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("provider_model", sa.String(length=120), nullable=True),
        sa.Column("reranker_provider", sa.String(length=80), nullable=True),
        sa.Column("reranker_model", sa.String(length=120), nullable=True),
        sa.Column("reranker_version", sa.String(length=80), nullable=True),
        sa.Column("reranker_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reranker_cost_micros", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="SUCCEEDED"),
        sa.Column("decision", sa.String(length=30), nullable=False, server_default="REFUSE"),
        sa.Column("confident", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fallback_reason", sa.String(length=100), nullable=True),
        sa.Column("filter_summary", sa.JSON(), nullable=False),
        sa.Column("candidate_counts", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_retrieval_traces_request_trace_id",
        "knowledge_retrieval_traces",
        ["request_trace_id"],
    )
    op.create_index(
        "ix_knowledge_retrieval_traces_query_hash",
        "knowledge_retrieval_traces",
        ["query_hash"],
    )
    op.create_index(
        "ix_knowledge_retrieval_traces_created_at",
        "knowledge_retrieval_traces",
        ["created_at"],
    )
    op.create_index(
        "ix_knowledge_retrieval_traces_status",
        "knowledge_retrieval_traces",
        ["status"],
    )

    op.create_table(
        "knowledge_retrieval_trace_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("trace_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("release_id", sa.String(length=36), nullable=True),
        sa.Column("release_version", sa.String(length=80), nullable=True),
        sa.Column("source_uri", sa.String(length=500), nullable=True),
        sa.Column("lexical_rank", sa.Integer(), nullable=True),
        sa.Column("vector_rank", sa.Integer(), nullable=True),
        sa.Column("rrf_score", sa.Float(), nullable=True),
        sa.Column("lexical_score", sa.Float(), nullable=True),
        sa.Column("vector_score", sa.Float(), nullable=True),
        sa.Column("rerank_score", sa.Float(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("decision", sa.String(length=30), nullable=False, server_default="CANDIDATE"),
        sa.Column("exclusion_reason", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["trace_id"], ["knowledge_retrieval_traces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_retrieval_trace_candidates_trace_id",
        "knowledge_retrieval_trace_candidates",
        ["trace_id"],
    )
    op.create_index(
        "ix_knowledge_retrieval_trace_candidates_chunk_id",
        "knowledge_retrieval_trace_candidates",
        ["chunk_id"],
    )

    op.create_table(
        "knowledge_retrieval_feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("trace_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("deidentified_note", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("review_note", sa.String(length=500), nullable=True),
        sa.Column("evaluation_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["trace_id"], ["knowledge_retrieval_traces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_knowledge_retrieval_feedback_idempotency"),
    )
    op.create_index(
        "ix_knowledge_retrieval_feedback_trace_id",
        "knowledge_retrieval_feedback",
        ["trace_id"],
    )
    op.create_index(
        "ix_knowledge_retrieval_feedback_status",
        "knowledge_retrieval_feedback",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_retrieval_feedback_status", table_name="knowledge_retrieval_feedback")
    op.drop_index("ix_knowledge_retrieval_feedback_trace_id", table_name="knowledge_retrieval_feedback")
    op.drop_table("knowledge_retrieval_feedback")
    op.drop_index(
        "ix_knowledge_retrieval_trace_candidates_chunk_id",
        table_name="knowledge_retrieval_trace_candidates",
    )
    op.drop_index(
        "ix_knowledge_retrieval_trace_candidates_trace_id",
        table_name="knowledge_retrieval_trace_candidates",
    )
    op.drop_table("knowledge_retrieval_trace_candidates")
    op.drop_index("ix_knowledge_retrieval_traces_status", table_name="knowledge_retrieval_traces")
    op.drop_index("ix_knowledge_retrieval_traces_created_at", table_name="knowledge_retrieval_traces")
    op.drop_index("ix_knowledge_retrieval_traces_query_hash", table_name="knowledge_retrieval_traces")
    op.drop_index(
        "ix_knowledge_retrieval_traces_request_trace_id",
        table_name="knowledge_retrieval_traces",
    )
    op.drop_table("knowledge_retrieval_traces")
