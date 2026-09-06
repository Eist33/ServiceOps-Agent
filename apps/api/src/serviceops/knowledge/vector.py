"""Stage-3 pgvector candidate retrieval with deterministic SQLite fallback."""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, or_, select
from sqlalchemy.orm import Session

from serviceops.knowledge.embeddings import (
    EMBEDDING_DIMENSIONS,
    EmbeddingProvider,
    EmbeddingProviderError,
)
from serviceops.models import (
    KnowledgeChunk,
    KnowledgeChunkEmbedding,
    KnowledgeRelease,
    KnowledgeReleaseItem,
)
from serviceops.shared.errors import NotFoundError, ValidationError

VECTOR_STRATEGIES = frozenset({"vector_v1", "hybrid_rrf_v1"})
MIN_VECTOR_RELEVANCE = 0.55


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = tuple(float(value) for value in left)
    right_values = tuple(float(value) for value in right)
    if len(left_values) != len(right_values) or not left_values:
        raise EmbeddingProviderError("EMBEDDING_DIMENSION_MISMATCH", "向量维度不一致")
    left_norm = math.sqrt(sum(value * value for value in left_values))
    right_norm = math.sqrt(sum(value * value for value in right_values))
    if left_norm <= 0 or right_norm <= 0:
        raise EmbeddingProviderError("EMBEDDING_VECTOR_INVALID", "检索向量不能是零向量")
    return sum(a * b for a, b in zip(left_values, right_values, strict=True)) / (
        left_norm * right_norm
    )


def _scope_filters(
    *,
    tenant_scope: str,
    channel_scope: str,
    product_scope: str,
    now: datetime,
) -> list:
    if not tenant_scope.strip() or not channel_scope.strip() or not product_scope.strip():
        raise ValidationError("RETRIEVAL_SCOPE_REQUIRED", "检索必须明确租户、渠道和产品范围")
    return [
        or_(KnowledgeChunk.tenant_scope == tenant_scope, KnowledgeChunk.tenant_scope == "*"),
        or_(KnowledgeChunk.channel_scope == channel_scope, KnowledgeChunk.channel_scope == "*"),
        or_(KnowledgeChunk.product_scope == product_scope, KnowledgeChunk.product_scope == "*"),
        or_(KnowledgeChunk.valid_from.is_(None), KnowledgeChunk.valid_from <= now),
        or_(KnowledgeChunk.valid_until.is_(None), KnowledgeChunk.valid_until > now),
    ]


def _latest_published_release(
    db: Session,
    *,
    strategy: str,
    require_embedding: bool = True,
) -> KnowledgeRelease:
    filters = [
        KnowledgeRelease.status == "PUBLISHED",
        KnowledgeRelease.retrieval_strategy_version == strategy,
    ]
    if require_embedding:
        filters.append(KnowledgeRelease.embedding_status == "READY")
    release = db.scalar(
        select(KnowledgeRelease)
        .where(*filters)
        .order_by(KnowledgeRelease.published_at.desc(), KnowledgeRelease.created_at.desc())
    )
    if release is None:
        raise NotFoundError("没有可用于向量检索的已发布 embedding 快照")
    return release


def search_vector_candidates(
    db: Session,
    query: str,
    *,
    provider: EmbeddingProvider,
    strategy: str = "vector_v1",
    tenant_scope: str,
    channel_scope: str = "*",
    product_scope: str = "*",
    now: datetime | None = None,
    limit: int = 5,
) -> list[dict]:
    if strategy not in VECTOR_STRATEGIES:
        raise ValidationError("RETRIEVAL_STRATEGY_UNSUPPORTED", "当前只支持 vector_v1 或 hybrid_rrf_v1")
    if not query.strip():
        raise ValidationError("RETRIEVAL_QUERY_REQUIRED", "检索问题不能为空")
    release = _latest_published_release(db, strategy=strategy)
    if (
        release.embedding_provider != provider.provider
        or release.embedding_model != provider.model
        or release.embedding_dimensions != provider.dimensions
        or release.embedding_normalization_version != provider.normalization_version
    ):
        raise EmbeddingProviderError(
            "EMBEDDING_MODEL_MISMATCH",
            "查询 provider 与已发布 embedding 快照不一致",
        )
    if provider.dimensions != EMBEDDING_DIMENSIONS:
        raise EmbeddingProviderError(
            "EMBEDDING_DIMENSION_UNSUPPORTED",
            f"当前索引只支持 {EMBEDDING_DIMENSIONS} 维 embedding",
        )
    query_result = provider.embed([query])
    query_vector = query_result.vectors[0]
    current_time = now or datetime.now(UTC)
    filters = [
        KnowledgeRelease.id == release.id,
        KnowledgeChunkEmbedding.provider == provider.provider,
        KnowledgeChunkEmbedding.model == provider.model,
        KnowledgeChunkEmbedding.dimensions == provider.dimensions,
        KnowledgeChunkEmbedding.normalization_version == provider.normalization_version,
        KnowledgeChunkEmbedding.status == "READY",
        *_scope_filters(
            tenant_scope=tenant_scope,
            channel_scope=channel_scope,
            product_scope=product_scope,
            now=current_time,
        ),
    ]
    statement = (
        select(KnowledgeChunk, KnowledgeRelease, KnowledgeChunkEmbedding)
        .join(KnowledgeReleaseItem, KnowledgeReleaseItem.chunk_id == KnowledgeChunk.id)
        .join(KnowledgeRelease, KnowledgeRelease.id == KnowledgeReleaseItem.release_id)
        .join(
            KnowledgeChunkEmbedding,
            KnowledgeChunkEmbedding.chunk_id == KnowledgeChunk.id,
        )
        .where(*filters)
    )
    bind = db.get_bind()
    if bind is None:
        raise ValidationError("RETRIEVAL_DATABASE_UNAVAILABLE", "检索数据库不可用")
    if bind.dialect.name == "postgresql":
        distance = cast(
            KnowledgeChunkEmbedding.embedding,
            Vector(EMBEDDING_DIMENSIONS),
        ).cosine_distance(list(query_vector))
        rows = list(db.execute(statement.order_by(distance.asc()).limit(max(1, limit))).all())
    else:
        rows = list(db.execute(statement).all())

    candidates: list[dict] = []
    for chunk, matched_release, stored in rows:
        if stored.content_hash != chunk.content_hash or len(stored.embedding) != provider.dimensions:
            raise EmbeddingProviderError(
                "EMBEDDING_CONTENT_HASH_MISMATCH",
                "检索 embedding 与切块内容不一致",
            )
        score = cosine_similarity(query_vector, stored.embedding)
        candidates.append(
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "release_id": matched_release.id,
                "release_version": matched_release.release_version,
                "content": chunk.content,
                "source_uri": chunk.source_uri,
                "title_path": chunk.title_path,
                "page_number": chunk.page_number,
                "relevance": round(score, 6),
                "vector_score": round(score, 6),
                "lexical_score": None,
                "hybrid_score": None,
            }
        )
    candidates = [
        candidate
        for candidate in candidates
        if candidate["vector_score"] >= MIN_VECTOR_RELEVANCE
    ]
    candidates.sort(key=lambda item: item["vector_score"], reverse=True)
    for rank, candidate in enumerate(candidates, start=1):
        candidate["vector_rank"] = rank
        candidate["lexical_rank"] = None
        candidate["rrf_score"] = None
        candidate["rerank_score"] = None
        candidate["final_score"] = candidate["vector_score"]
        candidate["selected"] = False
        candidate["decision"] = "VECTOR_CANDIDATE"
    return candidates[: max(1, limit)]
