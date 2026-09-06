"""Add stage-3 embedding batches, pgvector storage, and retrieval scopes.

The vector index is created only on PostgreSQL.  SQLite remains a deterministic
unit-test backend and stores vectors as JSON without pretending to be a
production vector database.
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "20260906_0013"
down_revision = "20260906_0012"
branch_labels = None
depends_on = None


class EmbeddingType(sa.TypeDecorator):
    impl = sa.JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(1536))
        return dialect.type_descriptor(sa.JSON())


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("tenant_scope", sa.String(length=120), nullable=False, server_default="local-demo"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("channel_scope", sa.String(length=80), nullable=False, server_default="*"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("product_scope", sa.String(length=120), nullable=False, server_default="*"),
    )
    op.add_column("knowledge_documents", sa.Column("valid_from", sa.DateTime(timezone=True)))
    op.add_column("knowledge_documents", sa.Column("valid_until", sa.DateTime(timezone=True)))
    op.add_column(
        "knowledge_chunks",
        sa.Column("tenant_scope", sa.String(length=120), nullable=False, server_default="local-demo"),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("channel_scope", sa.String(length=80), nullable=False, server_default="*"),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("product_scope", sa.String(length=120), nullable=False, server_default="*"),
    )
    op.create_index("ix_knowledge_chunks_tenant_scope", "knowledge_chunks", ["tenant_scope"])
    op.create_index("ix_knowledge_chunks_channel_scope", "knowledge_chunks", ["channel_scope"])
    op.create_index("ix_knowledge_chunks_product_scope", "knowledge_chunks", ["product_scope"])

    op.add_column(
        "knowledge_releases",
        sa.Column("embedding_provider", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "knowledge_releases",
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "knowledge_releases",
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
    )
    op.add_column(
        "knowledge_releases",
        sa.Column("embedding_normalization_version", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "knowledge_releases",
        sa.Column("embedding_status", sa.String(length=30), nullable=False, server_default="NOT_REQUIRED"),
    )
    op.add_column(
        "knowledge_releases",
        sa.Column("embedding_batch_id", sa.String(length=36), nullable=True),
    )

    op.create_table(
        "knowledge_embedding_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("release_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("normalization_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("requested_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reused_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["release_id"], ["knowledge_releases.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_knowledge_embedding_batch_key"),
    )
    op.create_index(
        "ix_knowledge_embedding_batches_release_id",
        "knowledge_embedding_batches",
        ["release_id"],
    )
    op.create_index(
        "ix_knowledge_embedding_batches_status",
        "knowledge_embedding_batches",
        ["status"],
    )
    op.create_foreign_key(
        "fk_knowledge_release_embedding_batch",
        "knowledge_releases",
        "knowledge_embedding_batches",
        ["embedding_batch_id"],
        ["id"],
    )

    op.create_table(
        "knowledge_chunk_embeddings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("normalization_version", sa.String(length=40), nullable=False),
        sa.Column("embedding", EmbeddingType(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="READY"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["knowledge_embedding_batches.id"]),
        sa.ForeignKeyConstraint(["chunk_id"], ["knowledge_chunks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chunk_id",
            "provider",
            "model",
            "dimensions",
            "normalization_version",
            name="uq_knowledge_chunk_embedding_variant",
        ),
    )
    op.create_index(
        "ix_knowledge_chunk_embeddings_chunk_id",
        "knowledge_chunk_embeddings",
        ["chunk_id"],
    )
    op.create_index(
        "ix_knowledge_chunk_embeddings_batch_id",
        "knowledge_chunk_embeddings",
        ["batch_id"],
    )
    op.create_index(
        "ix_knowledge_chunk_embeddings_content_hash",
        "knowledge_chunk_embeddings",
        ["content_hash"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_index(
            "ix_knowledge_chunk_embeddings_vector",
            "knowledge_chunk_embeddings",
            ["embedding"],
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("ix_knowledge_chunk_embeddings_vector", table_name="knowledge_chunk_embeddings")
    op.drop_index("ix_knowledge_chunk_embeddings_content_hash", table_name="knowledge_chunk_embeddings")
    op.drop_index("ix_knowledge_chunk_embeddings_batch_id", table_name="knowledge_chunk_embeddings")
    op.drop_index("ix_knowledge_chunk_embeddings_chunk_id", table_name="knowledge_chunk_embeddings")
    op.drop_table("knowledge_chunk_embeddings")
    op.drop_constraint(
        "fk_knowledge_release_embedding_batch",
        "knowledge_releases",
        type_="foreignkey",
    )
    op.drop_index("ix_knowledge_embedding_batches_status", table_name="knowledge_embedding_batches")
    op.drop_index("ix_knowledge_embedding_batches_release_id", table_name="knowledge_embedding_batches")
    op.drop_table("knowledge_embedding_batches")
    op.drop_column("knowledge_releases", "embedding_batch_id")
    op.drop_column("knowledge_releases", "embedding_status")
    op.drop_column("knowledge_releases", "embedding_normalization_version")
    op.drop_column("knowledge_releases", "embedding_dimensions")
    op.drop_column("knowledge_releases", "embedding_model")
    op.drop_column("knowledge_releases", "embedding_provider")
    op.drop_index("ix_knowledge_chunks_product_scope", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_channel_scope", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_tenant_scope", table_name="knowledge_chunks")
    op.drop_column("knowledge_chunks", "product_scope")
    op.drop_column("knowledge_chunks", "channel_scope")
    op.drop_column("knowledge_chunks", "tenant_scope")
    op.drop_column("knowledge_documents", "valid_until")
    op.drop_column("knowledge_documents", "valid_from")
    op.drop_column("knowledge_documents", "product_scope")
    op.drop_column("knowledge_documents", "channel_scope")
    op.drop_column("knowledge_documents", "tenant_scope")
