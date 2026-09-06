"""Add stage-2 document ingestion, chunks, and immutable knowledge releases.

Revision ID: 20260906_0012
Revises: 20260906_0011
Create Date: 2026-09-06
"""

import sqlalchemy as sa

from alembic import op

revision = "20260906_0012"
down_revision = "20260906_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_uri", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False, server_default="upload"),
        sa.Column(
            "owner",
            sa.String(length=120),
            nullable=False,
            server_default="knowledge-operations",
        ),
        sa.Column(
            "trust_level",
            sa.String(length=30),
            nullable=False,
            server_default="operator_reviewed",
        ),
        sa.Column(
            "authorization_scope",
            sa.String(length=200),
            nullable=False,
            server_default="local-demo",
        ),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_uri", name="uq_knowledge_source_uri"),
    )
    op.create_index(
        "ix_knowledge_sources_active",
        "knowledge_sources",
        ["active"],
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("source_uri", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("parser_version", sa.String(length=40), nullable=False),
        sa.Column("chunking_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="RECEIVED"),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.String(length=240), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("supersedes_document_id", sa.String(length=36), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("block_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["knowledge_sources.id"]),
        sa.ForeignKeyConstraint(["supersedes_document_id"], ["knowledge_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash", name="uq_knowledge_document_content_hash"),
        sa.UniqueConstraint("idempotency_key", name="uq_knowledge_documents_idempotency_key"),
    )
    op.create_index("ix_knowledge_documents_source_id", "knowledge_documents", ["source_id"])
    op.create_index("ix_knowledge_documents_status", "knowledge_documents", ["status"])
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("block_type", sa.String(length=30), nullable=False),
        sa.Column("title_path", sa.JSON(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("source_uri", sa.String(length=500), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_knowledge_chunk_document_index",
        ),
    )
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
    op.create_index("ix_knowledge_chunks_content_hash", "knowledge_chunks", ["content_hash"])
    op.create_table(
        "knowledge_releases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("release_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("parser_version", sa.String(length=40), nullable=False),
        sa.Column("chunking_version", sa.String(length=40), nullable=False),
        sa.Column(
            "retrieval_strategy_version",
            sa.String(length=40),
            nullable=False,
            server_default="lexical_v1",
        ),
        sa.Column("evaluation_dataset_version", sa.String(length=100), nullable=False),
        sa.Column("evaluation_report", sa.JSON(), nullable=True),
        sa.Column("source_manifest", sa.JSON(), nullable=False),
        sa.Column("git_commit", sa.String(length=64), nullable=False, server_default="unbound"),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("approved_by", sa.String(length=120), nullable=True),
        sa.Column("rollback_release_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["rollback_release_id"], ["knowledge_releases.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_version", name="uq_knowledge_release_version"),
    )
    op.create_index("ix_knowledge_releases_status", "knowledge_releases", ["status"])
    op.create_table(
        "knowledge_release_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("release_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_uri", sa.String(length=500), nullable=False),
        sa.Column("title_path", sa.JSON(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["knowledge_chunks.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"]),
        sa.ForeignKeyConstraint(["release_id"], ["knowledge_releases.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "release_id",
            "chunk_id",
            name="uq_knowledge_release_item_chunk",
        ),
    )
    op.create_index("ix_knowledge_release_items_release_id", "knowledge_release_items", ["release_id"])
    op.create_index("ix_knowledge_release_items_document_id", "knowledge_release_items", ["document_id"])
    op.create_index("ix_knowledge_release_items_chunk_id", "knowledge_release_items", ["chunk_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_release_items_chunk_id", table_name="knowledge_release_items")
    op.drop_index("ix_knowledge_release_items_document_id", table_name="knowledge_release_items")
    op.drop_index("ix_knowledge_release_items_release_id", table_name="knowledge_release_items")
    op.drop_table("knowledge_release_items")
    op.drop_index("ix_knowledge_releases_status", table_name="knowledge_releases")
    op.drop_table("knowledge_releases")
    op.drop_index("ix_knowledge_chunks_content_hash", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_documents_status", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_source_id", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index("ix_knowledge_sources_active", table_name="knowledge_sources")
    op.drop_table("knowledge_sources")
