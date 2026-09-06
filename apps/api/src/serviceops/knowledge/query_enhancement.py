"""Stage-5 controlled query-enhancement experiments.

The module deliberately keeps enhancement outside the normal retrieval path.
It returns a control/treatment comparison, never a promoted production query,
and the only provider currently implemented is an offline deterministic fixture.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from serviceops.config import Settings, get_settings
from serviceops.shared.errors import DomainError, ValidationError

ENHANCEMENT_STRATEGIES = frozenset({"rewrite_v1", "hyde_v1", "multi_query_v1"})
EXPERIMENT_GROUPS = frozenset({"control", "shadow", "treatment"})
FIXTURE_DATASET_VERSION = "query-enhancement-fixture-v1"
_SAFE_EXPANSIONS = {
    "多久": "时间",
    "没更新": "停滞",
    "不动": "停滞",
    "换货": "换货 质量问题",
    "退款": "退款 原路退回",
    "退回": "退款 原路退回",
}
_GENERIC_HYDE_TERMS = "适用条件 处理规则"
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


class QueryEnhancementProviderError(DomainError):
    """A safe provider/configuration failure that keeps the control query."""

    def __init__(self, code: str, message: str, status_code: int = 503) -> None:
        super().__init__(code, message, status_code)


@dataclass(frozen=True)
class QueryEnhancementConfig:
    enabled: bool = False
    provider: str = "not_configured"
    strategy: str = "rewrite_v1"
    config_version: str = "query_enhancement_v1"
    experiment_group: str = "shadow"
    max_variants: int = 3
    timeout_ms: int = 150
    cost_budget_micros: int = 0
    max_added_latency_ms: int = 100
    max_refusal_regression: float = 0.0
    max_entity_drift: int = 0

    def validate(self) -> None:
        if self.strategy not in ENHANCEMENT_STRATEGIES:
            raise ValidationError(
                "QUERY_ENHANCEMENT_STRATEGY_UNSUPPORTED",
                "查询增强策略不受支持",
            )
        if self.experiment_group not in EXPERIMENT_GROUPS:
            raise ValidationError(
                "QUERY_ENHANCEMENT_GROUP_INVALID",
                "查询增强实验组不受支持",
            )
        if not 1 <= self.max_variants <= 5:
            raise ValidationError(
                "QUERY_ENHANCEMENT_VARIANTS_INVALID",
                "查询增强候选数必须在 1 到 5 之间",
            )
        if not 1 <= self.timeout_ms <= 2_000:
            raise ValidationError(
                "QUERY_ENHANCEMENT_TIMEOUT_INVALID",
                "查询增强超时必须在 1 到 2000 毫秒之间",
            )
        if self.cost_budget_micros < 0:
            raise ValidationError(
                "QUERY_ENHANCEMENT_COST_INVALID",
                "查询增强成本预算不能为负数",
            )
        if self.max_refusal_regression < 0 or self.max_entity_drift < 0:
            raise ValidationError(
                "QUERY_ENHANCEMENT_GUARDRAIL_INVALID",
                "查询增强停止门禁不能为负数",
            )


@dataclass(frozen=True)
class QueryVariant:
    kind: str
    text: str

    @property
    def text_hash(self) -> str:
        return _hash(self.text)

    def public(self) -> dict:
        return {
            "kind": self.kind,
            "text_hash": self.text_hash,
            "text_length": len(self.text),
        }


@dataclass(frozen=True)
class QueryEnhancementBatch:
    provider: str
    model: str
    version: str
    variants: tuple[QueryVariant, ...]
    input_tokens: int
    cost_micros: int
    duration_ms: int
    entity_drift_count: int


class QueryEnhancementProvider(Protocol):
    provider: str
    model: str
    version: str
    timeout_ms: int

    def enhance(
        self,
        query: str,
        *,
        strategy: str,
        max_variants: int,
    ) -> QueryEnhancementBatch:
        """Return derived queries without receiving credentials or external data."""


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(value.lower()))


def _normalize(value: str) -> str:
    return " ".join(value.strip().split())


def _rewrite(value: str) -> str:
    rewritten = value
    for source, target in _SAFE_EXPANSIONS.items():
        # Keep deterministic term boundaries in the fixture output.  Chinese
        # text has no mandatory whitespace, but the added separator makes the
        # derived terms auditable and prevents an alias from being fused with
        # an adjacent entity token.
        rewritten = rewritten.replace(source, f" {target} ")
    return _normalize(rewritten)


class FixtureQueryEnhancer:
    """Deterministic allowlist-based fixture; never calls a network provider."""

    provider = "fixture"
    model = "fixture-query-enhancer-v1"
    version = "query_enhancement_v1"

    def __init__(self, timeout_ms: int = 150) -> None:
        self.timeout_ms = timeout_ms

    def enhance(
        self,
        query: str,
        *,
        strategy: str,
        max_variants: int,
    ) -> QueryEnhancementBatch:
        normalized = _normalize(query)
        if not normalized:
            raise QueryEnhancementProviderError(
                "QUERY_ENHANCEMENT_QUERY_REQUIRED",
                "查询增强问题不能为空",
                422,
            )
        if strategy not in ENHANCEMENT_STRATEGIES:
            raise QueryEnhancementProviderError(
                "QUERY_ENHANCEMENT_STRATEGY_UNSUPPORTED",
                "查询增强策略不受支持",
                422,
            )
        started = time.perf_counter()
        variants: list[QueryVariant] = [QueryVariant(kind="ORIGINAL", text=normalized)]
        rewritten = _rewrite(normalized)
        if strategy in {"rewrite_v1", "multi_query_v1"} and rewritten != normalized:
            variants.append(QueryVariant(kind="REWRITE", text=rewritten))
        if strategy == "hyde_v1":
            variants.append(QueryVariant(kind="HYDE_FIXTURE", text=f"{normalized} {_GENERIC_HYDE_TERMS}"))
        if strategy == "multi_query_v1":
            normalized_without_punctuation = _normalize(re.sub(r"[^\w\u4e00-\u9fff ]+", " ", normalized))
            if normalized_without_punctuation != normalized:
                variants.append(QueryVariant(kind="NORMALIZED", text=normalized_without_punctuation))
            if rewritten != normalized:
                variants.append(QueryVariant(kind="ALIAS", text=rewritten))
        deduplicated: list[QueryVariant] = []
        seen: set[str] = set()
        for variant in variants:
            if variant.text not in seen:
                seen.add(variant.text)
                deduplicated.append(variant)
        clipped = tuple(deduplicated[: max(1, max_variants)])
        base_terms = _tokens(normalized)
        allowed_added = _tokens(" ".join(_SAFE_EXPANSIONS.values()) + " " + _GENERIC_HYDE_TERMS)
        entity_drift = sum(
            1
            for variant in clipped
            for token in (_tokens(variant.text) - base_terms)
            if token not in allowed_added
        )
        return QueryEnhancementBatch(
            provider=self.provider,
            model=self.model,
            version=self.version,
            variants=clipped,
            input_tokens=max(1, len(normalized) // 4),
            cost_micros=0,
            duration_ms=int((time.perf_counter() - started) * 1000),
            entity_drift_count=entity_drift,
        )


def build_query_enhancer(
    name: str | None = None,
    *,
    settings: Settings | None = None,
) -> QueryEnhancementProvider:
    current = settings or get_settings()
    provider_name = (name or current.query_enhancement_provider).strip().lower()
    if provider_name in {"", "none", "not_configured"}:
        raise QueryEnhancementProviderError(
            "QUERY_ENHANCEMENT_PROVIDER_NOT_CONFIGURED",
            "查询增强 provider 未配置，保持对照组",
        )
    if provider_name == "fixture":
        if current.app_env.strip().lower() == "production":
            raise QueryEnhancementProviderError(
                "QUERY_ENHANCEMENT_FIXTURE_FORBIDDEN",
                "生产环境不允许使用查询增强 fixture",
            )
        return FixtureQueryEnhancer(timeout_ms=max(1, current.query_enhancement_timeout_ms))
    raise QueryEnhancementProviderError(
        "QUERY_ENHANCEMENT_PROVIDER_UNSUPPORTED",
        "未识别的查询增强 provider，保持对照组",
    )


def config_from_settings(
    *,
    provider: str | None = None,
    strategy: str | None = None,
    enabled: bool | None = None,
    experiment_group: str = "shadow",
    max_variants: int | None = None,
    settings: Settings | None = None,
) -> QueryEnhancementConfig:
    current = settings or get_settings()
    config = QueryEnhancementConfig(
        enabled=current.query_enhancement_enabled if enabled is None else enabled,
        provider=provider or current.query_enhancement_provider,
        strategy=strategy or current.query_enhancement_strategy,
        config_version=current.query_enhancement_config_version,
        experiment_group=experiment_group,
        max_variants=(
            current.query_enhancement_max_variants
            if max_variants is None
            else max_variants
        ),
        timeout_ms=current.query_enhancement_timeout_ms,
        cost_budget_micros=current.query_enhancement_cost_budget_micros,
    )
    config.validate()
    return config


def _summary(report: dict) -> dict:
    results = list(report.get("results") or [])
    return {
        "strategy": report.get("strategy"),
        "confident": bool(report.get("confident")),
        "score": float(report.get("score") or 0.0),
        "fallback": bool(report.get("fallback")),
        "fallback_reason": report.get("fallback_reason"),
        "release_version": report.get("release_version"),
        "candidate_count": len(results),
        "candidate_ids": [str(item.get("chunk_id")) for item in results if item.get("chunk_id")],
        "selected_candidate_ids": [
            str(item.get("chunk_id"))
            for item in results
            if item.get("chunk_id") and item.get("selected")
        ],
    }


def run_query_enhancement_experiment(
    query: str,
    *,
    config: QueryEnhancementConfig,
    search: Callable[[str], dict],
    provider: QueryEnhancementProvider | None = None,
    provider_error: QueryEnhancementProviderError | None = None,
) -> dict:
    config.validate()
    normalized = _normalize(query)
    if not normalized:
        raise ValidationError("RETRIEVAL_QUERY_REQUIRED", "检索问题不能为空")
    experiment_id = f"qexp-{uuid.uuid4()}"
    control_started = time.perf_counter()
    control_report = search(normalized)
    control_duration_ms = int((time.perf_counter() - control_started) * 1000)
    control = _summary(control_report)
    base = {
        "experiment_id": experiment_id,
        "config_version": config.config_version,
        "provider": config.provider,
        "strategy": config.strategy,
        "experiment_group": config.experiment_group,
        "query_hash": _hash(normalized),
        "query_length": len(normalized),
        "control": control,
        "treatment": {"status": "NOT_RUN", "variants": []},
        "guardrails": {
            "max_added_latency_ms": config.max_added_latency_ms,
            "max_refusal_regression": config.max_refusal_regression,
            "max_entity_drift": config.max_entity_drift,
            "scope_filter_reused": True,
            "control_duration_ms": control_duration_ms,
        },
        "decision": "CONTROL_ONLY",
        "promotion_allowed": False,
        "production_strategy": "CONTROL",
        "external_requests_enabled": False,
    }
    if not config.enabled:
        base["treatment"] = {
            "status": "NOT_ENABLED",
            "reason": "QUERY_ENHANCEMENT_DISABLED",
            "variants": [],
        }
        return base
    if provider is None:
        base["treatment"] = {
            "status": "FALLBACK",
            "reason": (provider_error.code if provider_error else "QUERY_ENHANCEMENT_PROVIDER_NOT_CONFIGURED"),
            "variants": [],
        }
        return base
    try:
        treatment_started = time.perf_counter()
        batch = provider.enhance(
            normalized,
            strategy=config.strategy,
            max_variants=config.max_variants,
        )
        if batch.duration_ms > config.timeout_ms:
            raise QueryEnhancementProviderError(
                "QUERY_ENHANCEMENT_TIMEOUT",
                "查询增强超过延迟预算",
            )
        if batch.cost_micros > config.cost_budget_micros:
            raise QueryEnhancementProviderError(
                "QUERY_ENHANCEMENT_COST_BUDGET_EXCEEDED",
                "查询增强超过成本预算",
            )
        if batch.entity_drift_count > config.max_entity_drift:
            # Do not send a fabricated-entity variant through retrieval at all.
            # The original control query has already been evaluated, so this
            # is both a safe fallback and a cheap automatic stop.
            raise QueryEnhancementProviderError(
                "ENTITY_DRIFT",
                "查询增强引入未允许的实体",
            )
        treatment_variants: list[dict] = []
        for variant in batch.variants:
            if variant.kind == "ORIGINAL":
                continue
            treatment_variants.append(
                {
                    **variant.public(),
                    "result": _summary(search(variant.text)),
                }
            )
        treatment_confident = any(
            item["result"]["confident"] for item in treatment_variants
        )
        refusal_regression = int(not control["confident"] and treatment_confident)
        treatment_duration_ms = int((time.perf_counter() - treatment_started) * 1000)
        added_latency_ms = max(0, treatment_duration_ms - control_duration_ms)
        stop_reasons: list[str] = []
        if refusal_regression > config.max_refusal_regression:
            stop_reasons.append("REFUSAL_REGRESSION")
        if added_latency_ms > config.max_added_latency_ms:
            stop_reasons.append("LATENCY_BUDGET")
        base["treatment"] = {
            "status": "READY" if treatment_variants else "NO_VARIANT",
            "provider": batch.provider,
            "model": batch.model,
            "version": batch.version,
            "input_tokens": batch.input_tokens,
            "cost_micros": batch.cost_micros,
            "duration_ms": batch.duration_ms,
            "entity_drift_count": batch.entity_drift_count,
            "variants": treatment_variants,
        }
        base["guardrails"].update(
            {
                "added_latency_ms": added_latency_ms,
                "treatment_duration_ms": treatment_duration_ms,
                "refusal_regression": refusal_regression,
                "stop_reasons": stop_reasons,
                "auto_stop": bool(stop_reasons),
            }
        )
        base["decision"] = "STOP" if stop_reasons else "CONTROL_ONLY"
        return base
    except QueryEnhancementProviderError as error:
        base["treatment"] = {
            "status": "FALLBACK",
            "reason": error.code,
            "variants": [],
        }
        base["guardrails"]["auto_stop"] = True
        base["guardrails"]["stop_reasons"] = [error.code]
        base["decision"] = "STOP"
        return base


_FIXTURE_CASES = (
    ("return-time", "退货多久", ("退货", "时间"), False),
    ("shipping-stall", "物流没更新", ("物流", "停滞"), False),
    ("out-of-scope", "量子宠物", ("退货", "物流"), True),
)


def evaluate_fixture_query_enhancement(
    *,
    config: QueryEnhancementConfig,
    provider: QueryEnhancementProvider,
) -> dict:
    config.validate()
    cases: list[dict] = []
    control_hits = 0
    treatment_hits = 0
    control_refusal = 0
    treatment_refusal = 0
    for case_id, query, expected_terms, out_of_scope in _FIXTURE_CASES:
        batch = provider.enhance(
            query,
            strategy=config.strategy,
            max_variants=config.max_variants,
        )
        control_hit = all(term in query for term in expected_terms)
        treatment_hit = any(
            all(term in variant.text for term in expected_terms)
            for variant in batch.variants
        )
        control_safe = (not control_hit) if out_of_scope else True
        treatment_safe = (not treatment_hit) if out_of_scope else True
        control_hits += int(control_hit)
        treatment_hits += int(treatment_hit)
        control_refusal += int(control_safe)
        treatment_refusal += int(treatment_safe)
        cases.append(
            {
                "case_id": case_id,
                "query_hash": _hash(query),
                "query_length": len(query),
                "out_of_scope": out_of_scope,
                "control_hit": control_hit,
                "treatment_hit": treatment_hit,
                "control_refusal_safe": control_safe,
                "treatment_refusal_safe": treatment_safe,
                "variant_count": len(batch.variants),
                "entity_drift_count": batch.entity_drift_count,
            }
        )
    total = len(_FIXTURE_CASES)
    return {
        "dataset_version": FIXTURE_DATASET_VERSION,
        "config_version": config.config_version,
        "provider": provider.provider,
        "strategy": config.strategy,
        "control": {
            "hit_rate": round(control_hits / total, 6),
            "refusal_safety": round(control_refusal / total, 6),
        },
        "treatment": {
            "hit_rate": round(treatment_hits / total, 6),
            "refusal_safety": round(treatment_refusal / total, 6),
        },
        "cases": cases,
        "promotion_allowed": False,
        "decision": "FIXTURE_ONLY_NOT_FOR_PRODUCTION",
        "external_requests_enabled": False,
    }
