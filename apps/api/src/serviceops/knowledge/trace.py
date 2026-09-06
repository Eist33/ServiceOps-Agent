"""De-identified retrieval trace persistence and quality aggregates."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.models import (
    KnowledgeRetrievalFeedback,
    KnowledgeRetrievalTrace,
    KnowledgeRetrievalTraceCandidate,
)
from serviceops.shared.errors import ConflictError, NotFoundError, ValidationError

FEEDBACK_LABELS = frozenset(
    {
        "ZERO_RESULT",
        "LOW_CONFIDENCE",
        "WRONG_CITATION",
        "NEGATIVE_RATING",
        "HUMAN_CORRECTION",
    }
)
FEEDBACK_STATUSES = frozenset({"PENDING_REVIEW", "APPROVED", "REJECTED"})
_CONTROLLED_SOURCE_PREFIXES = ("fixture://", "file://", "kb://", "upload://")
_SENSITIVE_FEEDBACK_TERMS = (
    "验证码",
    "动态码",
    "password",
    "cookie",
    "token",
    "api_key",
    "secret",
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _scope_hash(tenant_scope: str, channel_scope: str, product_scope: str) -> str:
    return _hash("|".join((tenant_scope, channel_scope, product_scope)))


def _safe_source_uri(value: object) -> str | None:
    source_uri = str(value or "")
    return source_uri if source_uri.startswith(_CONTROLLED_SOURCE_PREFIXES) else None


def _validate_note(note: str | None, *, code: str) -> str | None:
    normalized = (note or "").strip() or None
    if normalized and len(normalized) > 500:
        raise ValidationError(code, "反馈备注不能超过 500 个字符")
    if normalized and any(term in normalized.lower() for term in _SENSITIVE_FEEDBACK_TERMS):
        raise ValidationError(
            "RETRIEVAL_FEEDBACK_SENSITIVE",
            "反馈备注不能包含凭据或验证码等敏感字段",
        )
    return normalized


def _trace_candidates(report: dict) -> list[dict]:
    candidates = report.get("trace_candidates") or report.get("results") or []
    return [candidate for candidate in candidates if isinstance(candidate, dict)]


def record_retrieval_trace(
    db: Session,
    *,
    query: str,
    request_trace_id: str,
    tenant_scope: str,
    channel_scope: str,
    product_scope: str,
    report: dict,
    duration_ms: int,
    status: str = "SUCCEEDED",
    error_code: str | None = None,
) -> KnowledgeRetrievalTrace:
    """Persist scores and decisions without persisting query/candidate text."""

    candidates = _trace_candidates(report)
    selected_ids = {
        str(candidate.get("chunk_id"))
        for candidate in report.get("results", [])
        if candidate.get("selected") and candidate.get("chunk_id")
    }
    if report.get("confident") and not selected_ids and report.get("results"):
        first_chunk_id = report["results"][0].get("chunk_id")
        if first_chunk_id:
            selected_ids.add(str(first_chunk_id))
    trace = KnowledgeRetrievalTrace(
        request_trace_id=request_trace_id[:64],
        query_hash=_hash(query),
        query_length=len(query),
        strategy=str(report.get("strategy") or "unknown"),
        release_version=report.get("release_version"),
        provider=report.get("provider"),
        provider_model=report.get("provider_model"),
        reranker_provider=report.get("reranker_provider"),
        reranker_model=report.get("reranker_model"),
        reranker_version=report.get("reranker_version"),
        reranker_input_tokens=int(report.get("reranker_input_tokens") or 0),
        reranker_cost_micros=int(report.get("reranker_cost_micros") or 0),
        status=status,
        decision="ANSWER" if report.get("confident") else "REFUSE",
        confident=bool(report.get("confident")),
        fallback=bool(report.get("fallback") or report.get("reranker_fallback")),
        fallback_reason=report.get("reranker_fallback_reason")
        or report.get("fallback_reason"),
        filter_summary={
            "authorization": "KNOWLEDGE_MANAGER",
            "published_only": True,
            "tenant_scope_hash": _hash(tenant_scope),
            "channel_scope_hash": _hash(channel_scope),
            "product_scope_hash": _hash(product_scope),
            "scope_binding_hash": _scope_hash(tenant_scope, channel_scope, product_scope),
            "effective_period_applied": True,
            "out_of_scope_filtered": True,
            "expired_chunks_filtered": True,
            "provider_metadata_bound": bool(report.get("provider")),
        },
        candidate_counts={
            "lexical": sum(1 for item in candidates if item.get("lexical_rank")),
            "vector": sum(1 for item in candidates if item.get("vector_rank")),
            "fused": sum(1 for item in candidates if item.get("rrf_score") is not None),
            "final": len(report.get("results") or []),
        },
        duration_ms=max(0, min(int(duration_ms), 2_147_483_647)),
        error_code=error_code,
        error_message="检索失败，已失败关闭" if error_code else None,
    )
    db.add(trace)
    db.flush()
    for candidate in candidates:
        chunk_id = candidate.get("chunk_id")
        selected = bool(candidate.get("selected")) or (
            bool(report.get("confident")) and str(chunk_id) in selected_ids
        )
        db.add(
            KnowledgeRetrievalTraceCandidate(
                trace_id=trace.id,
                chunk_id=str(chunk_id) if chunk_id else None,
                release_id=candidate.get("release_id"),
                release_version=candidate.get("release_version"),
                source_uri=_safe_source_uri(candidate.get("source_uri")),
                lexical_rank=candidate.get("lexical_rank"),
                vector_rank=candidate.get("vector_rank"),
                rrf_score=candidate.get("rrf_score")
                if candidate.get("rrf_score") is not None
                else candidate.get("hybrid_score"),
                lexical_score=candidate.get("lexical_score"),
                vector_score=candidate.get("vector_score"),
                rerank_score=candidate.get("rerank_score"),
                final_score=candidate.get("final_score") or candidate.get("relevance"),
                selected=selected,
                decision="SELECTED" if selected else str(candidate.get("decision") or "CANDIDATE"),
                exclusion_reason=(None if selected else candidate.get("exclusion_reason") or "NOT_SELECTED"),
            )
        )
    db.commit()
    db.refresh(trace)
    return trace


def get_retrieval_trace(db: Session, trace_id: str) -> dict:
    trace = db.get(KnowledgeRetrievalTrace, trace_id)
    if trace is None:
        raise NotFoundError("检索 Trace 不存在")
    candidates = list(
        db.scalars(
            select(KnowledgeRetrievalTraceCandidate)
            .where(KnowledgeRetrievalTraceCandidate.trace_id == trace.id)
            .order_by(
                KnowledgeRetrievalTraceCandidate.selected.desc(),
                KnowledgeRetrievalTraceCandidate.final_score.desc(),
            )
        )
    )
    return {
        "id": trace.id,
        "request_trace_id": trace.request_trace_id,
        "query_hash": trace.query_hash,
        "query_length": trace.query_length,
        "strategy": trace.strategy,
        "release_version": trace.release_version,
        "provider": trace.provider,
        "provider_model": trace.provider_model,
        "reranker_provider": trace.reranker_provider,
        "reranker_model": trace.reranker_model,
        "reranker_version": trace.reranker_version,
        "reranker_input_tokens": trace.reranker_input_tokens,
        "reranker_cost_micros": trace.reranker_cost_micros,
        "status": trace.status,
        "decision": trace.decision,
        "confident": trace.confident,
        "fallback": trace.fallback,
        "fallback_reason": trace.fallback_reason,
        "filter_summary": trace.filter_summary,
        "candidate_counts": trace.candidate_counts,
        "duration_ms": trace.duration_ms,
        "error_code": trace.error_code,
        "created_at": trace.created_at,
        "candidates": [
            {
                "id": item.id,
                "chunk_id": item.chunk_id,
                "release_id": item.release_id,
                "release_version": item.release_version,
                "source_uri": item.source_uri,
                "lexical_rank": item.lexical_rank,
                "vector_rank": item.vector_rank,
                "rrf_score": item.rrf_score,
                "lexical_score": item.lexical_score,
                "vector_score": item.vector_score,
                "rerank_score": item.rerank_score,
                "final_score": item.final_score,
                "selected": item.selected,
                "decision": item.decision,
                "exclusion_reason": item.exclusion_reason,
            }
            for item in candidates
        ],
    }


def create_retrieval_feedback(
    db: Session,
    *,
    trace_id: str,
    label: str,
    idempotency_key: str,
    created_by: str,
    deidentified_note: str | None = None,
) -> KnowledgeRetrievalFeedback:
    normalized_label = label.strip().upper()
    if normalized_label not in FEEDBACK_LABELS:
        raise ValidationError("RETRIEVAL_FEEDBACK_LABEL_INVALID", "反馈标签不受支持")
    normalized_idempotency_key = idempotency_key.strip()
    if not normalized_idempotency_key or len(normalized_idempotency_key) > 160:
        raise ValidationError(
            "RETRIEVAL_FEEDBACK_IDEMPOTENCY_INVALID",
            "反馈幂等键不能为空且不能超过 160 个字符",
        )
    note = _validate_note(deidentified_note, code="RETRIEVAL_FEEDBACK_NOTE_INVALID")
    if db.get(KnowledgeRetrievalTrace, trace_id) is None:
        raise NotFoundError("检索 Trace 不存在")
    existing = db.scalar(
        select(KnowledgeRetrievalFeedback).where(
            KnowledgeRetrievalFeedback.idempotency_key == normalized_idempotency_key
        )
    )
    if existing is not None:
        if existing.trace_id != trace_id or existing.label != normalized_label:
            raise ConflictError("RETRIEVAL_FEEDBACK_IDEMPOTENCY_CONFLICT", "幂等键已经绑定到其他反馈")
        return existing
    feedback = KnowledgeRetrievalFeedback(
        trace_id=trace_id,
        label=normalized_label,
        idempotency_key=normalized_idempotency_key,
        deidentified_note=note,
        created_by=created_by,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def review_retrieval_feedback(
    db: Session,
    *,
    feedback_id: str,
    status: str,
    reviewed_by: str,
    review_note: str | None = None,
) -> KnowledgeRetrievalFeedback:
    normalized_status = status.strip().upper()
    if normalized_status not in {"APPROVED", "REJECTED"}:
        raise ValidationError("RETRIEVAL_FEEDBACK_STATUS_INVALID", "反馈审核状态只能是 APPROVED 或 REJECTED")
    note = _validate_note(review_note, code="RETRIEVAL_FEEDBACK_NOTE_INVALID")
    feedback = db.get(KnowledgeRetrievalFeedback, feedback_id)
    if feedback is None:
        raise NotFoundError("检索反馈不存在")
    if feedback.status != "PENDING_REVIEW":
        if feedback.status == normalized_status:
            return feedback
        raise ConflictError("RETRIEVAL_FEEDBACK_ALREADY_REVIEWED", "反馈已经完成审核")
    feedback.status = normalized_status
    feedback.reviewed_by = reviewed_by
    feedback.review_note = note
    feedback.evaluation_eligible = normalized_status == "APPROVED"
    feedback.reviewed_at = datetime.now(UTC)
    db.commit()
    db.refresh(feedback)
    return feedback


def retrieval_quality_report(
    db: Session,
    *,
    window_hours: int = 24,
    now: datetime | None = None,
) -> dict:
    if window_hours < 1 or window_hours > 24 * 90:
        raise ValidationError("RETRIEVAL_QUALITY_WINDOW_INVALID", "质量窗口必须在 1 到 2160 小时之间")
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(hours=window_hours)
    traces = [
        item
        for item in db.scalars(
            select(KnowledgeRetrievalTrace).order_by(KnowledgeRetrievalTrace.created_at.desc())
        )
        if (item.created_at if item.created_at.tzinfo else item.created_at.replace(tzinfo=UTC))
        >= cutoff
    ]
    feedback = [
        item
        for item in db.scalars(select(KnowledgeRetrievalFeedback))
        if (item.created_at if item.created_at.tzinfo else item.created_at.replace(tzinfo=UTC))
        >= cutoff
    ]
    durations = sorted(item.duration_ms for item in traces)
    p50 = durations[max(0, ceil(0.50 * len(durations)) - 1)] if durations else 0
    p95 = durations[max(0, ceil(0.95 * len(durations)) - 1)] if durations else 0
    return {
        "window_hours": window_hours,
        "trace_count": len(traces),
        "zero_result_count": sum(not item.confident and item.decision == "REFUSE" for item in traces),
        "low_confidence_count": sum(not item.confident for item in traces),
        "failure_count": sum(item.status == "FAILED" for item in traces),
        "fallback_count": sum(item.fallback for item in traces),
        "reranker_fallback_count": sum(
            str(item.fallback_reason or "").startswith("RERANKER_") for item in traces
        ),
        "p50_duration_ms": p50,
        "p95_duration_ms": p95,
        "pending_feedback_count": sum(item.status == "PENDING_REVIEW" for item in feedback),
        "approved_feedback_count": sum(item.status == "APPROVED" for item in feedback),
        "rejected_feedback_count": sum(item.status == "REJECTED" for item in feedback),
        "evaluation_eligible_count": sum(item.evaluation_eligible for item in feedback),
        "external_requests_enabled": False,
    }
