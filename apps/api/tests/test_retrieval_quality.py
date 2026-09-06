import pytest

from serviceops.knowledge.rerank import (
    FixtureReranker,
    RerankerProviderError,
    apply_optional_reranker,
)
from serviceops.knowledge.trace import (
    create_retrieval_feedback,
    get_retrieval_trace,
    record_retrieval_trace,
    retrieval_quality_report,
    review_retrieval_feedback,
)
from serviceops.seed import OPS_SESSION_TOKEN
from serviceops.shared.errors import ConflictError, ValidationError

OPS_HEADERS = {"X-Ops-Session": OPS_SESSION_TOKEN}


def _report(*, confident: bool = True) -> dict:
    candidate = {
        "chunk_id": "stage4-chunk-1",
        "release_id": "stage4-release-1",
        "release_version": "stage4-v1",
        "source_uri": "fixture://stage4/policy.md",
        "content": "退货规则：签收后七天内可以申请退货。",
        "lexical_rank": 1,
        "vector_rank": 2,
        "rrf_score": 0.0123,
        "lexical_score": 0.91,
        "vector_score": 0.87,
        "hybrid_score": 0.0123,
        "final_score": 0.0123,
        "selected": True,
        "decision": "RRF_CANDIDATE",
    }
    return {
        "strategy": "hybrid_rrf_v1",
        "confident": confident,
        "score": 0.0123 if confident else 0.0,
        "results": [candidate],
        "trace_candidates": [candidate],
        "fallback": False,
        "release_version": "stage4-v1",
        "provider": "fixture",
        "provider_model": "fixture-embedding-v1",
    }


def test_fixture_reranker_is_optional_and_preserves_rrf_on_timeout():
    report = _report()
    reranked = apply_optional_reranker(report, "退货规则", provider=FixtureReranker())
    assert reranked["reranker_status"] == "READY"
    assert reranked["reranker_version"] == "reranker_v1"
    assert reranked["results"][0]["final_score"] is not None

    class TimeoutReranker(FixtureReranker):
        def rerank(self, query, candidates):
            raise RerankerProviderError("RERANKER_TIMEOUT", "fixture timeout")

    fallback = apply_optional_reranker(_report(), "退货规则", provider=TimeoutReranker())
    assert fallback["reranker_status"] == "FALLBACK"
    assert fallback["reranker_fallback"] is True
    assert fallback["reranker_fallback_reason"] == "RERANKER_TIMEOUT"
    assert fallback["results"][0]["chunk_id"] == "stage4-chunk-1"
    assert fallback["results"][0]["rrf_score"] == fallback["results"][0]["final_score"]


def test_trace_is_deidentified_and_records_candidate_explanation(db):
    query = "用户手机号 13800000000 的退货规则"
    trace = record_retrieval_trace(
        db,
        query=query,
        request_trace_id="http-stage4-trace",
        tenant_scope="local-demo",
        channel_scope="xianyu",
        product_scope="phone",
        report=_report(),
        duration_ms=17,
    )
    payload = get_retrieval_trace(db, trace.id)
    assert payload["query_hash"] != query
    assert query not in str(payload)
    assert "13800000000" not in str(payload)
    assert payload["filter_summary"]["out_of_scope_filtered"] is True
    assert payload["candidate_counts"] == {"lexical": 1, "vector": 1, "fused": 1, "final": 1}
    assert payload["candidates"][0]["selected"] is True
    assert payload["candidates"][0]["source_uri"] == "fixture://stage4/policy.md"


def test_feedback_is_idempotent_and_requires_human_review(db):
    trace = record_retrieval_trace(
        db,
        query="退货规则",
        request_trace_id="feedback-trace",
        tenant_scope="local-demo",
        channel_scope="xianyu",
        product_scope="phone",
        report=_report(),
        duration_ms=10,
    )
    feedback = create_retrieval_feedback(
        db,
        trace_id=trace.id,
        label="wrong_citation",
        idempotency_key="stage4-feedback-1",
        created_by="operator-a",
        deidentified_note="人工复核候选来源",
    )
    repeated = create_retrieval_feedback(
        db,
        trace_id=trace.id,
        label="WRONG_CITATION",
        idempotency_key="stage4-feedback-1",
        created_by="operator-a",
    )
    assert repeated.id == feedback.id
    assert repeated.status == "PENDING_REVIEW"
    assert repeated.evaluation_eligible is False

    approved = review_retrieval_feedback(
        db,
        feedback_id=feedback.id,
        status="approved",
        reviewed_by="reviewer-a",
        review_note="已去标识化，可进入离线评测集",
    )
    assert approved.evaluation_eligible is True
    assert review_retrieval_feedback(
        db,
        feedback_id=feedback.id,
        status="APPROVED",
        reviewed_by="reviewer-a",
    ).id == feedback.id
    with pytest.raises(ConflictError) as conflict:
        create_retrieval_feedback(
            db,
            trace_id=trace.id,
            label="ZERO_RESULT",
            idempotency_key="stage4-feedback-1",
            created_by="operator-b",
        )
    assert conflict.value.code == "RETRIEVAL_FEEDBACK_IDEMPOTENCY_CONFLICT"
    with pytest.raises(ValidationError) as sensitive:
        review_retrieval_feedback(
            db,
            feedback_id=feedback.id,
            status="REJECTED",
            reviewed_by="reviewer-a",
            review_note="不要记录 token",
        )
    assert sensitive.value.code == "RETRIEVAL_FEEDBACK_SENSITIVE"


def test_quality_report_tracks_failures_fallbacks_and_feedback(db):
    trace = record_retrieval_trace(
        db,
        query="无结果问题",
        request_trace_id="quality-trace",
        tenant_scope="local-demo",
        channel_scope="xianyu",
        product_scope="phone",
        report={
            "strategy": "hybrid_rrf_v1",
            "results": [],
            "trace_candidates": [],
            "confident": False,
            "fallback": True,
            "fallback_reason": "RERANKER_TIMEOUT",
        },
        duration_ms=31,
        status="FAILED",
        error_code="RERANKER_TIMEOUT",
    )
    feedback = create_retrieval_feedback(
        db,
        trace_id=trace.id,
        label="LOW_CONFIDENCE",
        idempotency_key="quality-feedback-1",
        created_by="operator-a",
    )
    report = retrieval_quality_report(db, window_hours=24)
    assert report["trace_count"] == 1
    assert report["failure_count"] == 1
    assert report["fallback_count"] == 1
    assert report["reranker_fallback_count"] == 1
    assert report["pending_feedback_count"] == 1
    assert report["external_requests_enabled"] is False
    assert feedback.evaluation_eligible is False
    with pytest.raises(ValidationError) as window:
        retrieval_quality_report(db, window_hours=0)
    assert window.value.code == "RETRIEVAL_QUALITY_WINDOW_INVALID"


def test_api_exposes_operator_trace_feedback_and_quality_without_raw_query(client):
    response = client.post(
        "/api/ops/knowledge/search",
        headers=OPS_HEADERS,
        json={
            "query": "退货规则阶段4私密查询",
            "tenant_scope": "local-demo",
            "channel_scope": "xianyu",
            "product_scope": "phone",
            "reranker": "fixture",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"]
    assert body["reranker_status"] in {"READY", "NOT_CONFIGURED", "FALLBACK"}

    trace_response = client.get(
        f"/api/ops/knowledge/traces/{body['trace_id']}", headers=OPS_HEADERS
    )
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert "退货规则阶段4私密查询" not in str(trace)
    assert trace["query_length"] > 0
    assert trace["filter_summary"]["authorization"] == "KNOWLEDGE_MANAGER"

    feedback_response = client.post(
        f"/api/ops/knowledge/traces/{body['trace_id']}/feedback",
        headers=OPS_HEADERS,
        json={
            "label": "LOW_CONFIDENCE",
            "idempotency_key": "api-stage4-feedback",
            "deidentified_note": "需要人工核对",
        },
    )
    assert feedback_response.status_code == 200
    assert feedback_response.json()["status"] == "PENDING_REVIEW"
    feedback_id = feedback_response.json()["id"]
    review_response = client.post(
        f"/api/ops/knowledge/feedback/{feedback_id}/review",
        headers=OPS_HEADERS,
        json={"status": "APPROVED", "review_note": "人工已复核"},
    )
    assert review_response.status_code == 200
    assert review_response.json()["evaluation_eligible"] is True
    quality_response = client.get("/api/ops/knowledge/quality", headers=OPS_HEADERS)
    assert quality_response.status_code == 200
    assert quality_response.json()["pending_feedback_count"] == 0
    assert quality_response.json()["evaluation_eligible_count"] == 1


def test_trace_and_quality_routes_remain_operator_scoped(client):
    response = client.get("/api/ops/knowledge/quality")
    assert response.status_code == 403
