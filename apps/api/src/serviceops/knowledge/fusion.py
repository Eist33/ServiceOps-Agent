"""Stage-3 lexical/vector candidate fusion; Stage-4 tracing stays at the boundary."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.knowledge.service import (
    _concept_denominator,
    _concepts,
    _tokens,
    search_knowledge_base,
)
from serviceops.knowledge.vector import (
    _latest_published_release,
    _scope_filters,
    search_vector_candidates,
)
from serviceops.models import KnowledgeChunk, KnowledgeRelease, KnowledgeReleaseItem
from serviceops.shared.errors import DomainError

RRF_K = 60
MIN_LEXICAL_RELEVANCE = 0.55
MIN_HYBRID_SCORE = 1 / (RRF_K + 1) / 2


def search_chunk_lexical_candidates(
    db: Session,
    query: str,
    *,
    strategy: str = "hybrid_rrf_v1",
    tenant_scope: str,
    channel_scope: str = "*",
    product_scope: str = "*",
    now: datetime | None = None,
    limit: int = 20,
) -> list[dict]:
    """Run the stage-3 lexical channel over the published chunk snapshot."""

    if not query.strip():
        return []
    release = _latest_published_release(db, strategy=strategy, require_embedding=False)
    current_time = now or datetime.now(UTC)
    statement = (
        select(KnowledgeChunk, KnowledgeRelease)
        .join(KnowledgeReleaseItem, KnowledgeReleaseItem.chunk_id == KnowledgeChunk.id)
        .join(KnowledgeRelease, KnowledgeRelease.id == KnowledgeReleaseItem.release_id)
        .where(
            KnowledgeRelease.id == release.id,
            *_scope_filters(
                tenant_scope=tenant_scope,
                channel_scope=channel_scope,
                product_scope=product_scope,
                now=current_time,
            ),
        )
    )
    query_tokens = _tokens(query)
    query_concepts = _concepts(query)
    ranked: list[tuple[float, KnowledgeChunk, KnowledgeRelease]] = []
    for chunk, matched_release in db.execute(statement).all():
        evidence = " ".join(chunk.title_path) + " " + chunk.content
        evidence_tokens = _tokens(evidence)
        evidence_concepts = _concepts(evidence)
        matched_concepts = query_concepts & evidence_concepts
        concept_coverage = len(matched_concepts) / _concept_denominator(query_concepts)
        token_coverage = len(query_tokens & evidence_tokens) / max(1, min(8, len(query_tokens)))
        score = min(0.99, 0.72 * concept_coverage + 0.28 * token_coverage)
        if score >= MIN_LEXICAL_RELEVANCE:
            ranked.append((score, chunk, matched_release))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
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
            "vector_score": None,
            "lexical_score": round(score, 6),
            "hybrid_score": None,
            "lexical_rank": rank,
            "vector_rank": None,
            "rrf_score": None,
            "rerank_score": None,
            "final_score": round(score, 6),
            "selected": False,
            "decision": "LEXICAL_CANDIDATE",
        }
        for rank, (score, chunk, matched_release) in enumerate(
            ranked[: max(1, limit)], start=1
        )
    ]


def _legacy_fallback(
    db: Session,
    query: str,
    *,
    tenant_scope: str,
    channel_scope: str,
    product_scope: str,
    now: datetime,
    limit: int,
    reason: str,
) -> dict:
    # The stage-0 articles have no tenant/channel/product metadata.  Restrict
    # this compatibility path to the explicit local demo scope so a provider
    # outage can never leak baseline data across an unbound tenant.
    if tenant_scope != "local-demo" or channel_scope != "*" or product_scope != "*":
        return {
            "strategy": "lexical_v1",
            "confident": False,
            "score": 0.0,
            "results": [],
            "fallback": True,
            "fallback_reason": reason,
            "release_version": None,
            "provider": None,
        }
    result = search_knowledge_base(db, query, now=now, limit=limit)
    results = [
        {
            "chunk_id": f"legacy-article:{item['article_id']}",
            "document_id": "legacy-knowledge-article",
            "release_id": "legacy-lexical-v1",
            "release_version": item["version"],
            "content": item["content"],
            "source_uri": item["source_uri"],
            "title_path": [item["section"], item["title"]],
            "page_number": None,
            "relevance": item["relevance"],
            "vector_score": None,
            "lexical_score": item["relevance"],
            "hybrid_score": None,
        }
        for item in result["results"]
    ]
    return {
        "strategy": "lexical_v1",
        "confident": result["confident"],
        "score": result["score"],
        "results": results,
        "fallback": True,
        "fallback_reason": reason,
        "release_version": results[0]["release_version"] if results else None,
        "provider": None,
    }


def _merge_candidates(lexical: list[dict], vector: list[dict], *, limit: int) -> list[dict]:
    merged: dict[str, dict] = {}
    for rank, candidate in enumerate(lexical, start=1):
        item = merged.setdefault(candidate["chunk_id"], dict(candidate))
        item["lexical_score"] = candidate["lexical_score"]
        item["lexical_rank"] = rank
        item["hybrid_score"] = (item.get("hybrid_score") or 0.0) + 0.5 / (RRF_K + rank)
    for rank, candidate in enumerate(vector, start=1):
        item = merged.setdefault(candidate["chunk_id"], dict(candidate))
        item.update(
            {
                "vector_score": candidate["vector_score"],
                "content": candidate["content"],
                "source_uri": candidate["source_uri"],
                "title_path": candidate["title_path"],
                "page_number": candidate["page_number"],
            }
        )
        item["vector_rank"] = rank
        item["hybrid_score"] = (item.get("hybrid_score") or 0.0) + 0.5 / (RRF_K + rank)
    for item in merged.values():
        item["hybrid_score"] = round(item.get("hybrid_score") or 0.0, 6)
        item["relevance"] = item["hybrid_score"]
        item["rrf_score"] = item["hybrid_score"]
        item["final_score"] = item["hybrid_score"]
        item["rerank_score"] = None
        item["selected"] = False
        item["decision"] = "RRF_CANDIDATE"
    return sorted(merged.values(), key=lambda item: item["hybrid_score"], reverse=True)[: max(1, limit)]


def search_hybrid_knowledge(
    db: Session,
    query: str,
    *,
    provider=None,
    provider_error: DomainError | None = None,
    tenant_scope: str,
    channel_scope: str = "*",
    product_scope: str = "*",
    now: datetime | None = None,
    limit: int = 5,
    strategy: str = "hybrid_rrf_v1",
) -> dict:
    """Return hybrid RRF results or a scope-safe lexical fallback."""

    current_time = now or datetime.now(UTC)
    vector: list[dict] = []
    vector_failure = provider_error
    if provider is not None:
        try:
            vector = search_vector_candidates(
                db,
                query,
                provider=provider,
                strategy=strategy,
                tenant_scope=tenant_scope,
                channel_scope=channel_scope,
                product_scope=product_scope,
                now=current_time,
                limit=max(limit, 20),
            )
        except DomainError as error:
            vector_failure = error
    elif vector_failure is None:
        vector_failure = DomainError(
            "EMBEDDING_PROVIDER_NOT_CONFIGURED",
            "embedding provider 未配置，保持 lexical_v1 回退",
            503,
        )

    try:
        lexical = search_chunk_lexical_candidates(
            db,
            query,
            strategy=strategy,
            tenant_scope=tenant_scope,
            channel_scope=channel_scope,
            product_scope=product_scope,
            now=current_time,
            limit=max(limit, 20),
        )
    except DomainError:
        lexical = []

    if vector or lexical:
        merged = _merge_candidates(lexical, vector, limit=max(limit, 20))
        visible = merged[: max(1, limit)]
        score = visible[0]["hybrid_score"] if visible else 0.0
        partial_fallback = not (vector and lexical)
        fallback_reason = (
            vector_failure.code
            if vector_failure is not None
            else ("EMBEDDING_NO_MATCHES" if not vector else None)
        )
        return {
            "strategy": "hybrid_rrf_v1" if vector and lexical else "lexical_v1",
            "confident": bool(merged and score >= MIN_HYBRID_SCORE),
            "score": score,
            "results": visible,
            "trace_candidates": merged,
            "fallback": partial_fallback,
            "fallback_reason": fallback_reason,
            "release_version": visible[0]["release_version"] if visible else None,
            "provider": provider.provider if provider else None,
        }
    reason = vector_failure.code if vector_failure else "EMBEDDING_NO_RESULTS"
    return _legacy_fallback(
        db,
        query,
        tenant_scope=tenant_scope,
        channel_scope=channel_scope,
        product_scope=product_scope,
        now=current_time,
        limit=limit,
        reason=reason,
    )
