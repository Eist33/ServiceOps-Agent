import pytest

from serviceops.config import Settings
from serviceops.knowledge.query_enhancement import (
    FixtureQueryEnhancer,
    QueryEnhancementBatch,
    QueryEnhancementConfig,
    QueryEnhancementProviderError,
    QueryVariant,
    build_query_enhancer,
    evaluate_fixture_query_enhancement,
    run_query_enhancement_experiment,
)
from serviceops.seed import OPS_SESSION_TOKEN
from serviceops.shared.errors import ValidationError

OPS_HEADERS = {"X-Ops-Session": OPS_SESSION_TOKEN}


def _search(query: str) -> dict:
    confident = "退货" in query or "物流" in query
    return {
        "strategy": "hybrid_rrf_v1",
        "confident": confident,
        "score": 0.9 if confident else 0.0,
        "results": (
            [
                {
                    "chunk_id": "fixture-result",
                    "release_version": "fixture-v1",
                    "selected": True,
                }
            ]
            if confident
            else []
        ),
        "fallback": False,
        "fallback_reason": None,
        "release_version": "fixture-v1",
    }


def test_query_enhancement_provider_defaults_to_fail_closed_and_fixture_is_not_production():
    with pytest.raises(QueryEnhancementProviderError) as missing:
        build_query_enhancer(settings=Settings(query_enhancement_provider="not_configured"))
    assert missing.value.code == "QUERY_ENHANCEMENT_PROVIDER_NOT_CONFIGURED"

    with pytest.raises(QueryEnhancementProviderError) as production:
        build_query_enhancer(
            settings=Settings(
                app_env="production",
                demo_mode_enabled=False,
                api_docs_enabled=False,
                database_url="postgresql+psycopg://serviceops:secret@db/serviceops",
                web_origin="https://serviceops.example",
                query_enhancement_provider="fixture",
            )
        )
    assert production.value.code == "QUERY_ENHANCEMENT_FIXTURE_FORBIDDEN"


def test_fixture_variants_are_deterministic_and_do_not_expose_raw_text():
    provider = FixtureQueryEnhancer()
    first = provider.enhance("退货多久", strategy="rewrite_v1", max_variants=3)
    second = provider.enhance("退货多久", strategy="rewrite_v1", max_variants=3)
    assert first == second
    assert [variant.kind for variant in first.variants] == ["ORIGINAL", "REWRITE"]
    assert first.variants[1].text == "退货 时间"
    assert first.variants[0].public()["text_hash"] != "退货多久"
    assert first.entity_drift_count == 0


def test_disabled_experiment_runs_only_control_and_does_not_return_raw_query():
    calls: list[str] = []

    def search(query: str) -> dict:
        calls.append(query)
        return _search(query)

    report = run_query_enhancement_experiment(
        "退货多久",
        config=QueryEnhancementConfig(enabled=False, provider="not_configured"),
        search=search,
    )
    assert calls == ["退货多久"]
    assert report["treatment"]["status"] == "NOT_ENABLED"
    assert report["decision"] == "CONTROL_ONLY"
    assert "退货多久" not in str(report)


def test_provider_failure_keeps_control_and_stops_experiment():
    report = run_query_enhancement_experiment(
        "退货规则",
        config=QueryEnhancementConfig(
            enabled=True,
            provider="fixture",
            strategy="rewrite_v1",
        ),
        search=_search,
        provider=None,
        provider_error=QueryEnhancementProviderError(
            "QUERY_ENHANCEMENT_TIMEOUT",
            "fixture timeout",
        ),
    )
    assert report["control"]["confident"] is True
    assert report["treatment"]["status"] == "FALLBACK"
    assert report["treatment"]["reason"] == "QUERY_ENHANCEMENT_TIMEOUT"
    assert report["decision"] == "CONTROL_ONLY"
    assert report["promotion_allowed"] is False


def test_enhancement_provider_failure_uses_only_original_control_query():
    calls: list[str] = []

    class FailingProvider:
        provider = "fixture"
        model = "fixture-failing-v1"
        version = "query_enhancement_v1"
        timeout_ms = 150

        def enhance(self, query: str, *, strategy: str, max_variants: int):
            raise QueryEnhancementProviderError(
                "QUERY_ENHANCEMENT_TIMEOUT",
                "controlled fixture timeout",
            )

    def search(query: str) -> dict:
        calls.append(query)
        return _search(query)

    report = run_query_enhancement_experiment(
        "退货多久",
        config=QueryEnhancementConfig(enabled=True, provider="fixture"),
        search=search,
        provider=FailingProvider(),
    )
    assert calls == ["退货多久"]
    assert report["treatment"]["status"] == "FALLBACK"
    assert report["decision"] == "STOP"


def test_entity_drift_stops_before_fabricated_variant_reaches_retrieval():
    calls: list[str] = []

    class FabricatedEntityProvider:
        provider = "fixture"
        model = "fixture-fabricated-entity-v1"
        version = "query_enhancement_v1"
        timeout_ms = 150

        def enhance(self, query: str, *, strategy: str, max_variants: int):
            return QueryEnhancementBatch(
                provider=self.provider,
                model=self.model,
                version=self.version,
                variants=(
                    QueryVariant(kind="ORIGINAL", text=query),
                    QueryVariant(kind="REWRITE", text=f"{query} 量子宠物"),
                ),
                input_tokens=2,
                cost_micros=0,
                duration_ms=0,
                entity_drift_count=1,
            )

    def search(query: str) -> dict:
        calls.append(query)
        return _search(query)

    report = run_query_enhancement_experiment(
        "退货规则",
        config=QueryEnhancementConfig(enabled=True, provider="fixture"),
        search=search,
        provider=FabricatedEntityProvider(),
    )
    assert calls == ["退货规则"]
    assert report["treatment"]["status"] == "FALLBACK"
    assert report["treatment"]["reason"] == "ENTITY_DRIFT"
    assert report["promotion_allowed"] is False


def test_guardrail_stops_refusal_regression_and_never_promotes_treatment():
    report = run_query_enhancement_experiment(
        "退货多久",
        config=QueryEnhancementConfig(enabled=True, provider="fixture"),
        search=_search,
        provider=FixtureQueryEnhancer(),
    )
    assert report["control"]["confident"] is True
    assert report["treatment"]["status"] == "READY"
    assert report["promotion_allowed"] is False
    assert report["production_strategy"] == "CONTROL"
    assert report["decision"] == "CONTROL_ONLY"

    def refusal_regression_search(query: str) -> dict:
        return {
            **_search(query),
            "confident": "时间" in query,
            "results": ([{"chunk_id": "expanded-result"}] if "时间" in query else []),
        }

    stopped = run_query_enhancement_experiment(
        "多久",
        config=QueryEnhancementConfig(enabled=True, provider="fixture"),
        search=refusal_regression_search,
        provider=FixtureQueryEnhancer(),
    )
    assert stopped["guardrails"]["refusal_regression"] == 1
    assert "REFUSAL_REGRESSION" in stopped["guardrails"]["stop_reasons"]
    assert stopped["decision"] == "STOP"
    assert stopped["promotion_allowed"] is False


def test_fixture_evaluation_is_reproducible_and_ood_safe():
    provider = FixtureQueryEnhancer()
    config = QueryEnhancementConfig(enabled=True, provider="fixture", strategy="rewrite_v1")
    first = evaluate_fixture_query_enhancement(config=config, provider=provider)
    second = evaluate_fixture_query_enhancement(config=config, provider=provider)
    assert first == second
    assert first["dataset_version"] == "query-enhancement-fixture-v1"
    assert first["treatment"]["hit_rate"] >= first["control"]["hit_rate"]
    ood = next(case for case in first["cases"] if case["case_id"] == "out-of-scope")
    assert ood["treatment_refusal_safe"] is True
    assert first["promotion_allowed"] is False
    assert all("query" not in case for case in first["cases"])


def test_api_experiment_and_offline_evaluation_are_operator_scoped(client):
    disabled = client.post(
        "/api/ops/knowledge/search-experiment",
        headers=OPS_HEADERS,
        json={
            "query": "退货规则",
            "tenant_scope": "local-demo",
            "enhancement_provider": "not_configured",
        },
    )
    assert disabled.status_code == 200
    disabled_body = disabled.json()
    assert disabled_body["treatment"]["status"] == "NOT_ENABLED"
    assert "退货规则" not in str(disabled_body)

    enabled = client.post(
        "/api/ops/knowledge/search-experiment",
        headers=OPS_HEADERS,
        json={
            "query": "退货规则",
            "tenant_scope": "local-demo",
            "enhancement_provider": "fixture",
            "enhancement_strategy": "multi_query_v1",
            "enabled": True,
        },
    )
    assert enabled.status_code == 200
    assert enabled.json()["treatment"]["status"] in {"READY", "NO_VARIANT"}

    evaluated = client.post(
        "/api/ops/knowledge/query-enhancement/evaluate",
        headers=OPS_HEADERS,
        json={"enhancement_provider": "fixture", "enhancement_strategy": "hyde_v1"},
    )
    assert evaluated.status_code == 200
    assert evaluated.json()["decision"] == "FIXTURE_ONLY_NOT_FOR_PRODUCTION"
    assert evaluated.json()["external_requests_enabled"] is False

    forbidden = client.post(
        "/api/ops/knowledge/query-enhancement/evaluate",
        json={"enhancement_provider": "fixture"},
    )
    assert forbidden.status_code == 403


def test_invalid_experiment_config_fails_closed():
    with pytest.raises(ValidationError) as error:
        QueryEnhancementConfig(strategy="unknown_v1").validate()
    assert error.value.code == "QUERY_ENHANCEMENT_STRATEGY_UNSUPPORTED"
