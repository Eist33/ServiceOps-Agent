"""Stage-6 production release and continuous-governance contracts.

This module evaluates a release *candidate* without deploying it.  The input
is an allow-listed set of digests, versions, de-identified quality metrics and
human evidence.  No cloud SDK, secret value, customer content, backup command,
alert webhook or traffic switch is exposed here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

STAGE6_GOVERNANCE_VERSION = "stage6-release-governance-v1"
RELEASE_MANIFEST_VERSION = "release-manifest-v1"
SLI_VERSION = "serviceops-sli-v1"

SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
IMAGE_REF_PATTERN = re.compile(r"^.{1,240}@sha256:[0-9a-f]{64}$")
SUPPORTED_RETRIEVAL_STRATEGIES = frozenset(
    {"lexical_v1", "vector_v1", "hybrid_rrf_v1"}
)
REQUIRED_APPROVALS = frozenset({"PRODUCT", "ENGINEERING", "SECURITY", "OPERATIONS"})
REQUIRED_MAINTENANCE_CHECKS = (
    "expired_knowledge_count",
    "orphan_chunk_count",
    "failed_embedding_count",
    "cross_version_mismatch_count",
    "partial_release_index_count",
)
OFFLINE_METRIC_GATES: dict[str, tuple[str, float]] = {
    "hit_at_1": ("min", 0.95),
    "hit_at_3": ("min", 0.95),
    "hit_at_5": ("min", 0.95),
    "mrr": ("min", 0.95),
    "refusal_accuracy": ("min", 1.0),
    "false_accept_rate": ("max", 0.0),
    "p95_latency_ms": ("max", 500.0),
    "cost_per_session_micros": ("max", 5_000.0),
}
ONLINE_METRIC_GATES: dict[str, tuple[str, float]] = {
    "zero_result_rate": ("max", 0.20),
    "low_confidence_rate": ("max", 0.20),
    "citation_error_rate": ("max", 0.0),
    "human_handoff_rate": ("max", 0.50),
    "satisfaction_avg": ("min", 4.0),
    "repeat_consultation_rate": ("max", 0.20),
}
ONLINE_SAFETY_COUNTERS = (
    "cross_scope_leaks",
    "expired_knowledge_hits",
    "prompt_injection_successes",
    "unsupported_commitments",
    "refund_auto_executions",
)


class ReleaseGateState(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_APPROVED = "NOT_APPROVED"
    READY_FOR_PRODUCTION_REVIEW = "READY_FOR_PRODUCTION_REVIEW"


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    """Allow-listed, immutable release identity; it never contains payloads."""

    release_id: str
    application_version: str
    image_ref: str
    image_digest: str
    migration_head: str
    agent_release_id: str
    agent_release_version: str
    model_policy_version: str
    model_provider: str
    model_name: str
    knowledge_release_version: str
    retrieval_strategy_version: str
    evaluation_dataset_version: str
    evaluation_report_sha256: str
    sbom_sha256: str
    rollback_release_id: str
    query_enhancement_promotion_allowed: bool = False
    external_platform_writes_enabled: bool = False
    query_enhancement_flag_valid: bool = True
    external_platform_writes_flag_valid: bool = True
    manifest_version: str = RELEASE_MANIFEST_VERSION

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ReleaseManifest:
        def text(name: str) -> str:
            item = value.get(name)
            return item.strip() if isinstance(item, str) else ""

        query_flag = value.get("query_enhancement_promotion_allowed")
        external_writes_flag = value.get("external_platform_writes_enabled")
        return cls(
            release_id=text("release_id"),
            application_version=text("application_version"),
            image_ref=text("image_ref"),
            image_digest=text("image_digest"),
            migration_head=text("migration_head"),
            agent_release_id=text("agent_release_id"),
            agent_release_version=text("agent_release_version"),
            model_policy_version=text("model_policy_version"),
            model_provider=text("model_provider"),
            model_name=text("model_name"),
            knowledge_release_version=text("knowledge_release_version"),
            retrieval_strategy_version=text("retrieval_strategy_version"),
            evaluation_dataset_version=text("evaluation_dataset_version"),
            evaluation_report_sha256=text("evaluation_report_sha256"),
            sbom_sha256=text("sbom_sha256"),
            rollback_release_id=text("rollback_release_id"),
            query_enhancement_promotion_allowed=query_flag is True,
            external_platform_writes_enabled=external_writes_flag is True,
            query_enhancement_flag_valid=(query_flag is None or isinstance(query_flag, bool)),
            external_platform_writes_flag_valid=(
                external_writes_flag is None or isinstance(external_writes_flag, bool)
            ),
            manifest_version=text("manifest_version") or RELEASE_MANIFEST_VERSION,
        )

    def canonical_payload(self) -> dict[str, object]:
        return {
            "manifest_version": self.manifest_version,
            "release_id": self.release_id,
            "application_version": self.application_version,
            "image_ref": self.image_ref,
            "image_digest": self.image_digest,
            "migration_head": self.migration_head,
            "agent_release_id": self.agent_release_id,
            "agent_release_version": self.agent_release_version,
            "model_policy_version": self.model_policy_version,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "knowledge_release_version": self.knowledge_release_version,
            "retrieval_strategy_version": self.retrieval_strategy_version,
            "evaluation_dataset_version": self.evaluation_dataset_version,
            "evaluation_report_sha256": self.evaluation_report_sha256,
            "sbom_sha256": self.sbom_sha256,
            "rollback_release_id": self.rollback_release_id,
            "query_enhancement_promotion_allowed": self.query_enhancement_promotion_allowed,
            "external_platform_writes_enabled": self.external_platform_writes_enabled,
        }

    @property
    def manifest_sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {**self.canonical_payload(), "manifest_sha256": self.manifest_sha256}


@dataclass(frozen=True, slots=True)
class ReleaseEvidence:
    """Human/deployment evidence, represented only by booleans and enums."""

    environment: str = "development"
    approvals: frozenset[str] = frozenset()
    image_signature_verified: bool = False
    sbom_verified: bool = False
    migration_dry_run_verified: bool = False
    backup_restore_verified: bool = False
    rollback_drill_verified: bool = False
    knowledge_scope_verified: bool = False
    cross_version_consistency_verified: bool = False
    retention_check_verified: bool = False
    rollback_target_authorized: bool = False
    rollback_target_not_expired: bool = False
    rollback_scope_consistent: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ReleaseEvidence:
        raw_approvals = value.get("approvals", ())
        approvals = frozenset(
            item.strip().upper()
            for item in raw_approvals
            if isinstance(item, str) and item.strip()
        ) if isinstance(raw_approvals, (list, tuple, set, frozenset)) else frozenset()

        def flag(name: str) -> bool:
            return value.get(name) is True

        environment = value.get("environment")
        return cls(
            environment=environment.strip().lower() if isinstance(environment, str) else "",
            approvals=approvals,
            image_signature_verified=flag("image_signature_verified"),
            sbom_verified=flag("sbom_verified"),
            migration_dry_run_verified=flag("migration_dry_run_verified"),
            backup_restore_verified=flag("backup_restore_verified"),
            rollback_drill_verified=flag("rollback_drill_verified"),
            knowledge_scope_verified=flag("knowledge_scope_verified"),
            cross_version_consistency_verified=flag("cross_version_consistency_verified"),
            retention_check_verified=flag("retention_check_verified"),
            rollback_target_authorized=flag("rollback_target_authorized"),
            rollback_target_not_expired=flag("rollback_target_not_expired"),
            rollback_scope_consistent=flag("rollback_scope_consistent"),
        )


@dataclass(frozen=True, slots=True)
class ReleaseGateReport:
    state: ReleaseGateState
    manifest_sha256: str | None
    release_id: str | None
    missing_configuration: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    missing_approvals: tuple[str, ...]
    failures: tuple[str, ...]
    gates: dict[str, bool]
    metrics: dict[str, object]
    rollback: dict[str, object]
    publish_allowed: bool = False
    external_resources_enabled: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "governance_version": STAGE6_GOVERNANCE_VERSION,
            "state": self.state.value,
            "manifest_sha256": self.manifest_sha256,
            "release_id": self.release_id,
            "missing_configuration": list(self.missing_configuration),
            "missing_requirements": list(self.missing_requirements),
            "missing_approvals": list(self.missing_approvals),
            "failures": list(self.failures),
            "gates": self.gates,
            "metrics": self.metrics,
            "rollback": self.rollback,
            "publish_allowed": self.publish_allowed,
            "external_resources_enabled": self.external_resources_enabled,
        }


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _safe_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _metric_gaps(
    values: Mapping[str, Any],
    gates: Mapping[str, tuple[str, float]],
    *,
    prefix: str,
) -> tuple[list[str], list[str], dict[str, float]]:
    missing: list[str] = []
    failures: list[str] = []
    sanitized: dict[str, float] = {}
    for name, (operator, threshold) in gates.items():
        current = _number(values.get(name))
        if current is None:
            missing.append(f"{prefix}_metric:{name}")
            continue
        sanitized[name] = round(current, 6)
        failed = current < threshold if operator == "min" else current > threshold
        if failed:
            failures.append(f"{prefix.upper()}_{name.upper()}_GATE")
    return missing, failures, sanitized


def _validate_manifest(manifest: ReleaseManifest) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    failures: list[str] = []
    for name in (
        "release_id",
        "application_version",
        "image_ref",
        "image_digest",
        "migration_head",
        "agent_release_id",
        "agent_release_version",
        "model_policy_version",
        "model_provider",
        "model_name",
        "knowledge_release_version",
        "retrieval_strategy_version",
        "evaluation_dataset_version",
        "evaluation_report_sha256",
        "sbom_sha256",
        "rollback_release_id",
    ):
        if not getattr(manifest, name).strip():
            missing.append(f"manifest:{name}")
    if manifest.manifest_version != RELEASE_MANIFEST_VERSION:
        failures.append("RELEASE_MANIFEST_VERSION_UNSUPPORTED")
    if not manifest.query_enhancement_flag_valid:
        failures.append("STAGE5_PROMOTION_FLAG_INVALID")
    if not manifest.external_platform_writes_flag_valid:
        failures.append("EXTERNAL_PLATFORM_WRITES_FLAG_INVALID")
    if manifest.image_digest and not SHA256_PATTERN.fullmatch(manifest.image_digest):
        failures.append("IMAGE_DIGEST_INVALID")
    if manifest.image_ref and not IMAGE_REF_PATTERN.fullmatch(manifest.image_ref):
        failures.append("IMAGE_REF_NOT_IMMUTABLE")
    if (
        manifest.image_ref
        and manifest.image_digest
        and not manifest.image_ref.endswith(f"@{manifest.image_digest}")
    ):
        failures.append("IMAGE_REF_DIGEST_MISMATCH")
    for name in ("evaluation_report_sha256", "sbom_sha256"):
        value = getattr(manifest, name)
        if value and not SHA256_PATTERN.fullmatch(value):
            failures.append(f"{name.upper()}_INVALID")
    if manifest.retrieval_strategy_version not in SUPPORTED_RETRIEVAL_STRATEGIES:
        failures.append("RETRIEVAL_STRATEGY_UNSUPPORTED")
    if manifest.query_enhancement_promotion_allowed:
        failures.append("STAGE5_QUERY_ENHANCEMENT_NOT_PROMOTABLE")
    if manifest.external_platform_writes_enabled:
        failures.append("EXTERNAL_PLATFORM_WRITES_MUST_REMAIN_DISABLED")
    return missing, failures


def evaluate_release_gate(
    manifest: ReleaseManifest | Mapping[str, Any] | None,
    evidence: ReleaseEvidence | Mapping[str, Any] | None = None,
    *,
    offline_metrics: Mapping[str, Any] | None = None,
    online_metrics: Mapping[str, Any] | None = None,
    maintenance_checks: Mapping[str, Any] | None = None,
) -> ReleaseGateReport:
    """Evaluate a candidate release without publishing or changing state."""

    if isinstance(manifest, ReleaseManifest):
        candidate = manifest
    elif isinstance(manifest, Mapping):
        candidate = ReleaseManifest.from_mapping(manifest)
    else:
        candidate = None

    deployment = evidence if isinstance(evidence, ReleaseEvidence) else ReleaseEvidence.from_mapping(
        _safe_mapping(evidence)
    )
    missing_configuration: list[str] = []
    missing_requirements: list[str] = []
    missing_approvals: list[str] = []
    failures: list[str] = []

    if candidate is None:
        missing_configuration.append("manifest_required")
        manifest_missing = ["manifest"]
        manifest_failures: list[str] = []
    else:
        manifest_missing, manifest_failures = _validate_manifest(candidate)
        missing_configuration.extend(manifest_missing)
        failures.extend(manifest_failures)
    if deployment.environment != "production":
        missing_configuration.append("production_environment_required")
    if candidate is not None and candidate.external_platform_writes_enabled:
        missing_configuration.append("external_platform_writes_disabled")

    missing_approvals.extend(
        f"approval:{approval}"
        for approval in sorted(REQUIRED_APPROVALS - deployment.approvals)
    )
    evidence_flags = {
        "image_signature_verified": deployment.image_signature_verified,
        "sbom_verified": deployment.sbom_verified,
        "migration_dry_run_verified": deployment.migration_dry_run_verified,
        "backup_restore_verified": deployment.backup_restore_verified,
        "rollback_drill_verified": deployment.rollback_drill_verified,
        "knowledge_scope_verified": deployment.knowledge_scope_verified,
        "cross_version_consistency_verified": deployment.cross_version_consistency_verified,
        "retention_check_verified": deployment.retention_check_verified,
        "rollback_target_authorized": deployment.rollback_target_authorized,
        "rollback_target_not_expired": deployment.rollback_target_not_expired,
        "rollback_scope_consistent": deployment.rollback_scope_consistent,
    }
    missing_requirements.extend(
        f"evidence:{name}" for name, completed in evidence_flags.items() if not completed
    )

    offline_missing, offline_failures, offline = _metric_gaps(
        _safe_mapping(offline_metrics), OFFLINE_METRIC_GATES, prefix="offline"
    )
    online_missing, online_failures, online = _metric_gaps(
        _safe_mapping(online_metrics), ONLINE_METRIC_GATES, prefix="online"
    )
    missing_requirements.extend(offline_missing + online_missing)
    failures.extend(offline_failures + online_failures)

    online_values = _safe_mapping(online_metrics)
    safety_metrics: dict[str, float] = {}
    for name in ONLINE_SAFETY_COUNTERS:
        current = _number(online_values.get(name))
        if current is None:
            missing_requirements.append(f"online_safety_metric:{name}")
        else:
            safety_metrics[name] = round(current, 6)
            if current != 0:
                failures.append(f"ONLINE_SAFETY_{name.upper()}")

    maintenance_values = _safe_mapping(maintenance_checks)
    maintenance: dict[str, float] = {}
    missing_maintenance: list[str] = []
    for name in REQUIRED_MAINTENANCE_CHECKS:
        current = _number(maintenance_values.get(name))
        if current is None:
            missing_maintenance.append(name)
            missing_requirements.append(f"maintenance_check:{name}")
        else:
            maintenance[name] = round(current, 6)
            if current != 0:
                failures.append(f"MAINTENANCE_{name.upper()}")

    if missing_configuration:
        state = ReleaseGateState.NOT_CONFIGURED
    elif missing_requirements or missing_approvals or failures:
        state = ReleaseGateState.NOT_APPROVED
    else:
        state = ReleaseGateState.READY_FOR_PRODUCTION_REVIEW

    rollback = {
        "target_release_id": candidate.rollback_release_id if candidate else None,
        "drill_verified": deployment.rollback_drill_verified,
        "target_authorized": deployment.rollback_target_authorized,
        "target_not_expired": deployment.rollback_target_not_expired,
        "scope_consistent": deployment.rollback_scope_consistent,
        "automatic_execution": False,
    }
    return ReleaseGateReport(
        state=state,
        manifest_sha256=candidate.manifest_sha256 if candidate else None,
        release_id=candidate.release_id if candidate and candidate.release_id else None,
        missing_configuration=tuple(sorted(set(missing_configuration))),
        missing_requirements=tuple(sorted(set(missing_requirements))),
        missing_approvals=tuple(sorted(set(missing_approvals))),
        failures=tuple(sorted(set(failures))),
        gates={
            "manifest_integrity": candidate is not None and not manifest_missing and not manifest_failures,
            "artifact_signature_and_sbom": (
                deployment.image_signature_verified and deployment.sbom_verified
            ),
            "quality": not offline_missing and not offline_failures,
            "online_safety": not online_missing and not online_failures and not any(
                name.startswith("ONLINE_SAFETY_") for name in failures
            ),
            "maintenance": not missing_maintenance and (
                all(value == 0 for value in maintenance.values())
            ),
            "rollback": all(
                (
                    deployment.rollback_drill_verified,
                    deployment.rollback_target_authorized,
                    deployment.rollback_target_not_expired,
                    deployment.rollback_scope_consistent,
                )
            ),
        },
        metrics={
            "offline": offline,
            "online": online,
            "online_safety": safety_metrics,
            "maintenance": maintenance,
        },
        rollback=rollback,
        publish_allowed=False,
        external_resources_enabled=False,
    )


def _ratio(value: object, denominator: object) -> float | None:
    numerator = _number(value)
    divisor = _number(denominator)
    if numerator is None or divisor is None or divisor <= 0:
        return None
    return round(numerator / divisor, 6)


def compute_sli_snapshot(metrics: Mapping[str, Any] | None) -> dict[str, object]:
    """Compute de-identified online SLI values from counters or supplied rates."""

    values = _safe_mapping(metrics)
    total_queries = values.get("total_queries", values.get("retrievals"))
    total_sessions = values.get("total_sessions", values.get("sessions"))
    total_citations = values.get("total_citations", values.get("citation_impressions"))
    total_satisfaction = values.get("satisfaction_count")
    rates: dict[str, float] = {}
    derived = {
        "zero_result_rate": ("zero_result_queries", total_queries),
        "low_confidence_rate": ("low_confidence_queries", total_queries),
        "refusal_rate": ("refused_sessions", total_sessions),
        "human_handoff_rate": ("human_handoffs", total_sessions),
        "citation_click_rate": ("citation_clicks", total_citations),
        "citation_error_rate": ("citation_errors", total_citations),
        "citation_revision_rate": ("citation_revisions", total_citations),
        "once_resolution_rate": ("resolved_sessions", total_sessions),
        "repeat_consultation_rate": ("repeat_consultations", total_sessions),
    }
    for name, (numerator, denominator) in derived.items():
        supplied = _number(values.get(name))
        result = supplied if supplied is not None else _ratio(values.get(numerator), denominator)
        if result is not None:
            rates[name] = round(result, 6)
    satisfaction_avg = _number(values.get("satisfaction_avg"))
    if satisfaction_avg is None:
        satisfaction_avg = _ratio(values.get("satisfaction_sum"), total_satisfaction)
    if satisfaction_avg is not None:
        rates["satisfaction_avg"] = round(satisfaction_avg, 6)
    for name in ("p50_latency_ms", "p95_latency_ms", "cost_per_session_micros"):
        value = _number(values.get(name))
        if value is None and name == "cost_per_session_micros":
            value = _ratio(values.get("total_cost_micros"), total_sessions)
        if value is not None:
            rates[name] = round(value, 6)
    alert_codes: list[str] = []
    for name, (operator, threshold) in ONLINE_METRIC_GATES.items():
        value = rates.get(name)
        if value is None:
            continue
        if (operator == "min" and value < threshold) or (operator == "max" and value > threshold):
            alert_codes.append(f"ONLINE_{name.upper()}_GATE")
    for name in ONLINE_SAFETY_COUNTERS:
        value = _number(values.get(name))
        if value is not None and value != 0:
            alert_codes.append(f"ONLINE_SAFETY_{name.upper()}")
    return {
        "sli_version": SLI_VERSION,
        "metrics": rates,
        "alert_codes": sorted(set(alert_codes)),
        "external_requests_enabled": False,
    }


def run_continuous_governance_checks(
    checks: Mapping[str, Any] | None,
) -> dict[str, object]:
    """Evaluate scheduled maintenance facts; never runs a scheduler or query."""

    values = _safe_mapping(checks)
    normalized: dict[str, float] = {}
    missing: list[str] = []
    failures: list[str] = []
    for name in REQUIRED_MAINTENANCE_CHECKS:
        value = _number(values.get(name))
        if value is None:
            missing.append(name)
            continue
        normalized[name] = round(value, 6)
        if value != 0:
            failures.append(f"MAINTENANCE_{name.upper()}")
    status = "PASS" if not missing and not failures else "BLOCKED"
    return {
        "status": status,
        "cadence": "daily",
        "checks": normalized,
        "missing_checks": sorted(missing),
        "failures": sorted(failures),
        "external_requests_enabled": False,
    }


def production_governance_report(
    *,
    manifest: ReleaseManifest | Mapping[str, Any] | None = None,
    evidence: ReleaseEvidence | Mapping[str, Any] | None = None,
    offline_metrics: Mapping[str, Any] | None = None,
    online_metrics: Mapping[str, Any] | None = None,
    maintenance_checks: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    """Return a complete secret-free report for the API, CLI and web docs."""

    sli = compute_sli_snapshot(online_metrics)
    online_for_gate = {
        **_safe_mapping(online_metrics),
        **_safe_mapping(sli.get("metrics")),
    }
    release = evaluate_release_gate(
        manifest,
        evidence,
        offline_metrics=offline_metrics,
        online_metrics=online_for_gate,
        maintenance_checks=maintenance_checks,
    )
    maintenance = run_continuous_governance_checks(maintenance_checks)
    state = release.state
    if state == ReleaseGateState.READY_FOR_PRODUCTION_REVIEW and maintenance["status"] != "PASS":
        state = ReleaseGateState.NOT_APPROVED
    manifest_sha = release.manifest_sha256
    return {
        "governance_version": STAGE6_GOVERNANCE_VERSION,
        "state": state.value,
        "release_gate": release.as_dict(),
        "sli": sli,
        "maintenance": maintenance,
        "audit": {
            "event": "production_release_gate_evaluated",
            "manifest_sha256": manifest_sha,
            "release_id": release.release_id,
            "state": state.value,
        },
        "publish_allowed": False,
        "rollback_allowed": bool(
            release.rollback["drill_verified"]
            and state == ReleaseGateState.READY_FOR_PRODUCTION_REVIEW
        ),
        "external_resources_enabled": False,
        "external_requests_enabled": False,
    }
