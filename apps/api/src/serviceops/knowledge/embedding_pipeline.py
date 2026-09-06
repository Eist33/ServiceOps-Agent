"""Batch, cache, retry, and cost accounting for release embeddings."""

from __future__ import annotations

import hashlib
import math
from collections import deque
from collections.abc import Sequence
from datetime import UTC, datetime
from time import monotonic

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.config import get_settings
from serviceops.knowledge.embeddings import (
    EMBEDDING_DIMENSIONS,
    EmbeddingProvider,
    EmbeddingProviderError,
)
from serviceops.knowledge.releases import get_release, list_release_items
from serviceops.models import (
    KnowledgeChunk,
    KnowledgeChunkEmbedding,
    KnowledgeEmbeddingBatch,
    KnowledgeRelease,
)
from serviceops.shared.errors import ConflictError, NotFoundError, ValidationError

EMBEDDABLE_STRATEGIES = frozenset({"vector_v1", "hybrid_rrf_v1"})


class _RequestRateLimiter:
    """Fail closed when one batch would exceed the configured provider budget."""

    def __init__(self, requests_per_minute: int) -> None:
        self.requests_per_minute = requests_per_minute
        self._request_times: deque[float] = deque()

    def acquire(self) -> None:
        now = monotonic()
        while self._request_times and now - self._request_times[0] >= 60.0:
            self._request_times.popleft()
        if len(self._request_times) >= self.requests_per_minute:
            raise EmbeddingProviderError(
                "EMBEDDING_RATE_LIMIT_EXCEEDED",
                "embedding 批次达到 provider 请求限额，保持失败关闭",
            )
        self._request_times.append(now)


def _now() -> datetime:
    return datetime.now(UTC)


def _batch_key(
    release: KnowledgeRelease,
    *,
    provider: EmbeddingProvider,
    content_hashes: Sequence[str],
) -> str:
    material = "|".join(
        (
            release.id,
            provider.provider,
            provider.model,
            str(provider.dimensions),
            provider.normalization_version,
            *content_hashes,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _load_release_chunks(
    db: Session,
    release_id: str,
) -> tuple[KnowledgeRelease, list[KnowledgeChunk]]:
    release = get_release(db, release_id)
    if release.retrieval_strategy_version not in EMBEDDABLE_STRATEGIES:
        raise ValidationError(
            "EMBEDDING_NOT_REQUIRED",
            "lexical_v1 快照不需要 embedding；请显式创建 vector_v1 或 hybrid_rrf_v1 快照",
        )
    if release.status not in {"APPROVED", "PUBLISHED"}:
        raise ValidationError("KNOWLEDGE_RELEASE_NOT_APPROVED", "只有已审核快照才能生成 embedding")
    items = list_release_items(db, release_id)
    chunks: list[KnowledgeChunk] = []
    for item in items:
        chunk = db.get(KnowledgeChunk, item.chunk_id)
        if chunk is None:
            raise NotFoundError("知识快照引用的切块不存在")
        if chunk.content_hash != item.content_hash:
            raise ConflictError(
                "EMBEDDING_CONTENT_HASH_MISMATCH",
                "快照切块内容哈希不一致，拒绝生成 embedding",
            )
        chunks.append(chunk)
    if not chunks:
        raise ValidationError("KNOWLEDGE_RELEASE_EMPTY", "知识快照没有可向量化的切块")
    return release, chunks


def _allocate(total: int, weights: Sequence[int]) -> list[int]:
    if not weights:
        return []
    total_weight = max(1, sum(weights))
    values = [math.floor(total * weight / total_weight) for weight in weights]
    remainder = total - sum(values)
    for index in range(max(0, remainder)):
        values[index % len(values)] += 1
    return values


def embed_knowledge_release(
    db: Session,
    release_id: str,
    *,
    provider: EmbeddingProvider,
    batch_size: int | None = None,
) -> KnowledgeEmbeddingBatch:
    """Generate or reuse embeddings for an approved vector/hybrid release.

    The idempotency key binds release, provider metadata, and every content
    hash.  Provider failures commit a FAILED batch and leave the release
    unpublishable; no caller can accidentally treat a partial batch as ready.
    """

    release, chunks = _load_release_chunks(db, release_id)
    settings = get_settings()
    effective_batch_size = batch_size or settings.embedding_batch_size
    if effective_batch_size < 1 or effective_batch_size > 128:
        raise ValidationError("EMBEDDING_BATCH_SIZE_INVALID", "embedding 批大小必须在 1 到 128 之间")
    if settings.embedding_requests_per_minute < 1:
        raise ValidationError(
            "EMBEDDING_RATE_LIMIT_INVALID",
            "embedding 每分钟请求上限必须至少为 1",
        )
    if provider.dimensions != EMBEDDING_DIMENSIONS:
        raise EmbeddingProviderError(
            "EMBEDDING_DIMENSION_UNSUPPORTED",
            f"当前索引只支持 {EMBEDDING_DIMENSIONS} 维 embedding",
        )
    if not provider.model.strip() or not provider.provider.strip():
        raise EmbeddingProviderError("EMBEDDING_PROVIDER_METADATA_INVALID", "embedding provider 元数据不完整")

    content_hashes = [chunk.content_hash for chunk in chunks]
    key = _batch_key(release, provider=provider, content_hashes=content_hashes)
    batch = db.scalar(
        select(KnowledgeEmbeddingBatch).where(KnowledgeEmbeddingBatch.idempotency_key == key)
    )
    if batch is None:
        batch = KnowledgeEmbeddingBatch(
            release_id=release.id,
            provider=provider.provider,
            model=provider.model,
            dimensions=provider.dimensions,
            normalization_version=provider.normalization_version,
            status="PENDING",
            requested_count=len(chunks),
            idempotency_key=key,
        )
        db.add(batch)
        db.flush()
    elif batch.status == "READY":
        return batch
    elif (
        batch.provider != provider.provider
        or batch.model != provider.model
        or batch.dimensions != provider.dimensions
        or batch.normalization_version != provider.normalization_version
    ):
        raise ConflictError("EMBEDDING_BATCH_METADATA_CONFLICT", "幂等 embedding 批的 provider 元数据不一致")

    release.embedding_provider = provider.provider
    release.embedding_model = provider.model
    release.embedding_dimensions = provider.dimensions
    release.embedding_normalization_version = provider.normalization_version
    release.embedding_status = "RUNNING"
    release.embedding_batch_id = batch.id
    batch.status = "RUNNING"
    batch.error_code = None
    batch.error_message = None
    batch.requested_count = len(chunks)
    batch.updated_at = _now()
    db.flush()

    pending: list[KnowledgeChunk] = []
    for chunk in chunks:
        existing = db.scalar(
            select(KnowledgeChunkEmbedding).where(
                KnowledgeChunkEmbedding.chunk_id == chunk.id,
                KnowledgeChunkEmbedding.provider == provider.provider,
                KnowledgeChunkEmbedding.model == provider.model,
                KnowledgeChunkEmbedding.dimensions == provider.dimensions,
                KnowledgeChunkEmbedding.normalization_version == provider.normalization_version,
            )
        )
        if existing is not None:
            if existing.content_hash != chunk.content_hash:
                raise ConflictError(
                    "EMBEDDING_CONTENT_HASH_MISMATCH",
                    "已有 embedding 与当前切块内容哈希不一致",
                )
            if existing.status == "READY" and len(existing.embedding) == provider.dimensions:
                batch.reused_count += 1
                continue
        pending.append(chunk)

    max_retries = max(0, settings.embedding_max_retries)
    rate_limiter = _RequestRateLimiter(settings.embedding_requests_per_minute)
    try:
        for start in range(0, len(pending), effective_batch_size):
            group = pending[start : start + effective_batch_size]
            texts = [chunk.content for chunk in group]
            result = None
            last_error: EmbeddingProviderError | None = None
            for _attempt in range(max_retries + 1):
                batch.attempts += 1
                try:
                    rate_limiter.acquire()
                    result = provider.embed(texts)
                    break
                except EmbeddingProviderError as error:
                    last_error = error
            if result is None:
                assert last_error is not None
                raise last_error
            if (
                result.provider != provider.provider
                or result.model != provider.model
                or result.dimensions != provider.dimensions
                or result.normalization_version != provider.normalization_version
            ):
                raise EmbeddingProviderError(
                    "EMBEDDING_RESPONSE_METADATA_MISMATCH",
                    "embedding 返回的 provider 元数据不一致",
                )
            token_weights = [max(1, math.ceil(len(chunk.content) / 4)) for chunk in group]
            token_values = _allocate(result.input_tokens, token_weights)
            cost_values = _allocate(result.cost_micros, token_weights)
            for chunk, vector, tokens, cost in zip(
                group,
                result.vectors,
                token_values,
                cost_values,
                strict=True,
            ):
                row = db.scalar(
                    select(KnowledgeChunkEmbedding).where(
                        KnowledgeChunkEmbedding.chunk_id == chunk.id,
                        KnowledgeChunkEmbedding.provider == provider.provider,
                        KnowledgeChunkEmbedding.model == provider.model,
                        KnowledgeChunkEmbedding.dimensions == provider.dimensions,
                        KnowledgeChunkEmbedding.normalization_version == provider.normalization_version,
                    )
                )
                if row is None:
                    row = KnowledgeChunkEmbedding(
                        chunk_id=chunk.id,
                        batch_id=batch.id,
                        content_hash=chunk.content_hash,
                        provider=provider.provider,
                        model=provider.model,
                        dimensions=provider.dimensions,
                        normalization_version=provider.normalization_version,
                        embedding=list(vector),
                        status="READY",
                        input_tokens=tokens,
                        cost_micros=cost,
                        attempt_count=batch.attempts,
                    )
                    db.add(row)
                else:
                    row.batch_id = batch.id
                    row.content_hash = chunk.content_hash
                    row.embedding = list(vector)
                    row.status = "READY"
                    row.input_tokens = tokens
                    row.cost_micros = cost
                    row.attempt_count = batch.attempts
                    row.error_code = None
                    row.error_message = None
                    row.updated_at = _now()
                batch.embedded_count += 1
            batch.input_tokens += result.input_tokens
            batch.cost_micros += result.cost_micros
            db.flush()
        batch.status = "READY"
        batch.failed_count = 0
        batch.updated_at = _now()
        release.embedding_status = "READY"
        db.commit()
        db.refresh(batch)
        return batch
    except EmbeddingProviderError as error:
        batch.status = "FAILED"
        batch.failed_count = len(pending)
        batch.error_code = error.code
        batch.error_message = error.message[:240]
        batch.updated_at = _now()
        release.embedding_status = "FAILED"
        db.commit()
        raise
    except Exception:
        db.rollback()
        raise


def get_embedding_batch(db: Session, batch_id: str) -> KnowledgeEmbeddingBatch:
    batch = db.get(KnowledgeEmbeddingBatch, batch_id)
    if batch is None:
        raise NotFoundError("embedding 批不存在")
    return batch


def list_embedding_batches(db: Session, release_id: str | None = None) -> list[KnowledgeEmbeddingBatch]:
    statement = select(KnowledgeEmbeddingBatch).order_by(KnowledgeEmbeddingBatch.created_at.desc())
    if release_id:
        statement = statement.where(KnowledgeEmbeddingBatch.release_id == release_id)
    return list(db.scalars(statement))
