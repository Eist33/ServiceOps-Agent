import json

from serviceops.cli import main
from serviceops.production.governance import (
    compute_sli_snapshot,
    production_governance_report,
    run_continuous_governance_checks,
)
from serviceops.seed import OPS_SESSION_TOKEN

OPS_HEADERS = {"X-Ops-Session": OPS_SESSION_TOKEN}
_IMAGE_DIGEST = "sha256:" + "a" * 64


def _manifest(**overrides):
    manifest = {
        "manifest_version": "release-manifest-v1",
        "release_id": "serviceops-2026-09-07.1",
        "application_version": "2026.09.07.1",
        "image_ref": f"registry.example/serviceops/api@{_IMAGE_DIGEST}",
        "image_digest": _IMAGE_DIGEST,
        "migration_head": "20260906_0014_retrieval_trace_quality",
        "agent_release_id": "agent-support-v1",
        "agent_release_version": "1.0.0",
        "model_policy_version": "model-routing-v1",
        "model_provider": "fixture",
        "model_name": "support-deterministic-v1",
        "knowledge_release_version": "2026-07",
        "retrieval_strategy_version": "lexical_v1",
        "evaluation_dataset_version": "knowledge-baseline-30-v1",
        "evaluation_report_sha256": "sha256:" + "b" * 64,
        "sbom_sha256": "sha256:" + "c" * 64,
        "rollback_release_id": "serviceops-2026-09-06.3",
        "query_enhancement_promotion_allowed": False,
        "external_platform_writes_enabled": False,
    }
    manifest.update(overrides)
    return manifest


def _evidence(**overrides):
    evidence = {
        "environment": "production",
        "approvals": ["PRODUCT", "ENGINEERING", "SECURITY", "OPERATIONS"],
        "image_signature_verified": True,
        "sbom_verified": True,
        "migration_dry_run_verified": True,
        "backup_restore_verified": True,
        "rollback_drill_verified": True,
        "knowledge_scope_verified": True,
        "cross_version_consistency_verified": True,
        "retention_check_verified": True,
        "rollback_target_authorized": True,
        "rollback_target_not_expired": True,
        "rollback_scope_consistent": True,
    }
    evidence.update(overrides)
    return evidence


def _offline(**overrides):
    metrics = {
        "hit_at_1": 0.99,
        "hit_at_3": 0.995,
        "hit_at_5": 1.0,
        "mrr": 0.98,
        "refusal_accuracy": 1.0,
        "false_accept_rate": 0.0,
        "p95_latency_ms": 120,
        "cost_per_session_micros": 1000,
    }
    metrics.update(overrides)
    return metrics


def _online(**overrides):
    metrics = {
        "zero_result_rate": 0.05,
        "low_confidence_rate": 0.03,
        "citation_error_rate": 0.0,
        "human_handoff_rate": 0.2,
        "satisfaction_avg": 4.8,
        "repeat_consultation_rate": 0.04,
        "cross_scope_leaks": 0,
        "expired_knowledge_hits": 0,
        "prompt_injection_successes": 0,
        "unsupported_commitments": 0,
        "refund_auto_executions": 0,
    }
    metrics.update(overrides)
    return metrics


def _checks(**overrides):
    checks = {
        "expired_knowledge_count": 0,
        "orphan_chunk_count": 0,
        "failed_embedding_count": 0,
        "cross_version_mismatch_count": 0,
        "partial_release_index_count": 0,
    }
    checks.update(overrides)
    return checks


def test_default_governance_is_fail_closed_and_secret_free():
    report = production_governance_report()

    assert report["state"] == "NOT_CONFIGURED"
    assert report["publish_allowed"] is False
    assert report["rollback_allowed"] is False
    assert report["external_resources_enabled"] is False
    assert report["external_requests_enabled"] is False
    assert "manifest_required" in report["release_gate"]["missing_configuration"]
    assert "image_ref" not in json.dumps(report, ensure_ascii=False)


def test_complete_candidate_is_reviewable_but_never_published_automatically():
    first = production_governance_report(
        manifest=_manifest(),
        evidence=_evidence(),
        offline_metrics=_offline(),
        online_metrics=_online(),
        maintenance_checks=_checks(),
    )
    second = production_governance_report(
        manifest=_manifest(),
        evidence=_evidence(),
        offline_metrics=_offline(),
        online_metrics=_online(),
        maintenance_checks=_checks(),
    )

    assert first == second
    assert first["state"] == "READY_FOR_PRODUCTION_REVIEW"
    assert first["release_gate"]["gates"] == {
        "manifest_integrity": True,
        "artifact_signature_and_sbom": True,
        "quality": True,
        "online_safety": True,
        "maintenance": True,
        "rollback": True,
    }
    assert first["publish_allowed"] is False
    assert first["rollback_allowed"] is True
    assert first["audit"]["manifest_sha256"] == first["release_gate"]["manifest_sha256"]


def test_missing_approval_and_restore_evidence_stays_not_approved():
    report = production_governance_report(
        manifest=_manifest(),
        evidence=_evidence(
            approvals=["PRODUCT"],
            backup_restore_verified=False,
            rollback_target_authorized=False,
        ),
        offline_metrics=_offline(),
        online_metrics=_online(),
        maintenance_checks=_checks(),
    )

    assert report["state"] == "NOT_APPROVED"
    assert "approval:ENGINEERING" in report["release_gate"]["missing_approvals"]
    assert "evidence:backup_restore_verified" in report["release_gate"]["missing_requirements"]
    assert report["rollback_allowed"] is False


def test_stage5_experiment_cannot_enter_release_manifest():
    report = production_governance_report(
        manifest=_manifest(query_enhancement_promotion_allowed=True),
        evidence=_evidence(),
        offline_metrics=_offline(),
        online_metrics=_online(),
        maintenance_checks=_checks(),
    )

    assert report["state"] == "NOT_APPROVED"
    assert "STAGE5_QUERY_ENHANCEMENT_NOT_PROMOTABLE" in report["release_gate"]["failures"]
    assert report["publish_allowed"] is False


def test_immutable_image_and_cross_version_failures_are_safe():
    report = production_governance_report(
        manifest=_manifest(image_ref="registry.example/serviceops/api:latest"),
        evidence=_evidence(),
        offline_metrics=_offline(false_accept_rate=0.01),
        online_metrics=_online(cross_scope_leaks=1),
        maintenance_checks=_checks(orphan_chunk_count=2),
    )

    assert report["state"] == "NOT_APPROVED"
    assert "IMAGE_REF_NOT_IMMUTABLE" in report["release_gate"]["failures"]
    assert "OFFLINE_FALSE_ACCEPT_RATE_GATE" in report["release_gate"]["failures"]
    assert "ONLINE_SAFETY_CROSS_SCOPE_LEAKS" in report["release_gate"]["failures"]
    assert "MAINTENANCE_ORPHAN_CHUNK_COUNT" in report["release_gate"]["failures"]


def test_model_policy_provider_and_model_are_required_release_bindings():
    report = production_governance_report(
        manifest=_manifest(model_policy_version="", model_provider="", model_name=""),
        evidence=_evidence(),
        offline_metrics=_offline(),
        online_metrics=_online(),
        maintenance_checks=_checks(),
    )

    assert report["state"] == "NOT_CONFIGURED"
    for name in ("model_policy_version", "model_provider", "model_name"):
        assert f"manifest:{name}" in report["release_gate"]["missing_configuration"]


def test_sli_snapshot_derives_rates_and_alerts_without_raw_content():
    snapshot = compute_sli_snapshot(
        {
            "total_queries": 100,
            "zero_result_queries": 25,
            "low_confidence_queries": 5,
            "total_sessions": 50,
            "refused_sessions": 5,
            "human_handoffs": 10,
            "total_citations": 80,
            "citation_clicks": 40,
            "citation_errors": 1,
            "resolved_sessions": 35,
            "satisfaction_sum": 225,
            "satisfaction_count": 50,
            "cross_scope_leaks": 0,
        }
    )

    assert snapshot["metrics"]["zero_result_rate"] == 0.25
    assert snapshot["metrics"]["refusal_rate"] == 0.1
    assert snapshot["metrics"]["citation_click_rate"] == 0.5
    assert snapshot["metrics"]["once_resolution_rate"] == 0.7
    assert snapshot["metrics"]["satisfaction_avg"] == 4.5
    assert "ONLINE_ZERO_RESULT_RATE_GATE" in snapshot["alert_codes"]
    assert "ONLINE_SAFETY_CROSS_SCOPE_LEAKS" not in snapshot["alert_codes"]
    assert "total_queries" not in json.dumps(snapshot)


def test_continuous_checks_are_blocked_until_all_scheduled_facts_exist():
    blocked = run_continuous_governance_checks({"orphan_chunk_count": 1})
    passed = run_continuous_governance_checks(_checks())

    assert blocked["status"] == "BLOCKED"
    assert "expired_knowledge_count" in blocked["missing_checks"]
    assert "MAINTENANCE_ORPHAN_CHUNK_COUNT" in blocked["failures"]
    assert passed["status"] == "PASS"
    assert passed["external_requests_enabled"] is False


def test_production_governance_api_is_operator_scoped_and_default_safe(client):
    response = client.get("/api/ops/production/governance", headers=OPS_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "NOT_CONFIGURED"
    assert body["publish_allowed"] is False
    assert body["external_resources_enabled"] is False

    candidate = client.post(
        "/api/ops/production/release-gate",
        headers=OPS_HEADERS,
        json={
            "manifest": _manifest(),
            "evidence": _evidence(),
            "offline_metrics": _offline(),
            "online_metrics": _online(),
            "maintenance_checks": _checks(),
        },
    )
    assert candidate.status_code == 200
    assert candidate.json()["state"] == "READY_FOR_PRODUCTION_REVIEW"

    forbidden = client.get("/api/ops/production/governance")
    assert forbidden.status_code == 403


def test_cli_governance_status_is_json_and_has_no_side_effect(capsys):
    assert main(["production-governance"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["state"] == "NOT_CONFIGURED"
    assert report["external_requests_enabled"] is False
