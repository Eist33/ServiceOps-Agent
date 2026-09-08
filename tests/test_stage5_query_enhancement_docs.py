from pathlib import Path

ROOT = Path(__file__).parents[1]
STAGE5_DOC = ROOT / "docs" / "阶段5-受控查询增强实验.md"
PLAN = ROOT / "docs" / "企业客服与工单执行Agent_改进计划_v1.0.md"


def test_stage5_document_matches_plan_and_has_machine_contract() -> None:
    document = STAGE5_DOC.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")

    assert "阶段 5：受控查询增强实验" in plan
    for marker in (
        "输入、输出与信任边界",
        "rewrite_v1",
        "hyde_v1",
        "multi_query_v1",
        "query-enhancement-fixture-v1",
        "query_hash",
        "FIXTURE_ONLY_NOT_FOR_PRODUCTION",
        "CONTROL_ONLY",
        "REFUSAL_REGRESSION",
        "ENTITY_DRIFT",
        "Docker-only",
        "网页/可见验收步骤",
        "阶段 6",
    ):
        assert marker in document
    assert "PowerShell" not in document


def test_stage5_docs_and_compose_expose_operator_routes_and_docker_evidence() -> None:
    document = STAGE5_DOC.read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    process = (
        ROOT / "docs" / "企业客服与工单执行Agent_生产化开发流程_v1.0.md"
    ).read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.stage3.yml").read_text(encoding="utf-8")

    for content in (document, architecture, process):
        assert "阶段 5" in content
        assert "docker compose" in content
        assert "/api/ops/knowledge/search-experiment" in content
        assert "/api/ops/knowledge/query-enhancement/evaluate" in content
        assert "promotion_allowed" in content
    assert "tests/test_query_enhancement.py" in compose
    assert "Dockerfile.test" in document


def test_stage5_sources_have_no_network_or_stage6_side_effects() -> None:
    sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "apps/api/src/serviceops/knowledge/query_enhancement.py",
            "apps/api/src/serviceops/main.py",
            "apps/api/src/serviceops/cli.py",
        )
    ).lower()

    for forbidden in ("requests.", "httpx", "websocket", "fetch(", "axios"):
        assert forbidden not in sources
    for forbidden in ("sbom", "image signing", "production rollout"):
        assert forbidden not in sources


def test_stage5_tests_cover_fallback_scope_ood_and_no_promotion() -> None:
    tests = (ROOT / "apps/api/tests/test_query_enhancement.py").read_text(
        encoding="utf-8"
    )
    for marker in (
        "QUERY_ENHANCEMENT_TIMEOUT",
        "FALLBACK",
        "out-of-scope",
        "promotion_allowed",
        "external_requests_enabled",
        "forbidden.status_code == 403",
    ):
        assert marker in tests
