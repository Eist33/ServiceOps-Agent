from pathlib import Path

ROOT = Path(__file__).parents[1]
STAGE4_DOC = ROOT / "docs" / "阶段4-重排、检索追踪与质量运营.md"
PLAN = ROOT / "docs" / "企业客服与工单执行Agent_改进计划_v1.0.md"


def test_stage4_document_matches_plan_and_has_machine_contract() -> None:
    document = STAGE4_DOC.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")

    assert "阶段 4：重排、检索追踪与质量运营" in plan
    for marker in (
        "输入、输出与信任边界",
        "RerankerProvider",
        "fixture-cross-encoder-v1",
        "KnowledgeRetrievalTrace",
        "query_hash",
        "PENDING_REVIEW",
        "evaluation_eligible",
        "RERANKER_TIMEOUT",
        "external_requests_enabled=false",
        "Docker-only",
        "网页/可见验收步骤",
        "阶段 5",
    ):
        assert marker in document
    assert "PowerShell" not in document


def test_stage4_docs_and_compose_expose_operator_routes_and_docker_evidence() -> None:
    document = STAGE4_DOC.read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    process = (
        ROOT / "docs" / "企业客服与工单执行Agent_生产化开发流程_v1.0.md"
    ).read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.stage3.yml").read_text(encoding="utf-8")

    for content in (document, readme, architecture, process):
        assert "阶段 4" in content
        assert "docker compose" in content
        assert "/api/ops/knowledge/traces/{trace_id}" in content or "检索 Trace" in content
        assert "/api/ops/knowledge/quality" in content
        assert "KNOWLEDGE_MANAGER" in content
    assert "tests/test_retrieval_quality.py" in compose
    assert "Dockerfile.test" in document


def test_stage4_sources_have_no_network_or_stage5_execution_side_effect() -> None:
    sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "apps/api/src/serviceops/knowledge/rerank.py",
            "apps/api/src/serviceops/knowledge/trace.py",
            "apps/api/src/serviceops/knowledge/fusion.py",
            "apps/api/src/serviceops/knowledge/vector.py",
        )
    ).lower()

    for forbidden in ("requests.", "httpx", "websocket", "fetch(", "axios"):
        assert forbidden not in sources
    for forbidden in ("query rewrite", "query_rewrite", "hyde", "multi-query"):
        assert forbidden not in sources


def test_stage4_tests_cover_failure_fallback_privacy_and_manual_review() -> None:
    tests = (ROOT / "apps/api/tests/test_retrieval_quality.py").read_text(encoding="utf-8")
    for marker in (
        "RERANKER_TIMEOUT",
        "reranker_fallback",
        "query_hash",
        "RETRIEVAL_FEEDBACK_IDEMPOTENCY_CONFLICT",
        "RETRIEVAL_FEEDBACK_SENSITIVE",
        "evaluation_eligible",
        "external_requests_enabled",
        "KNOWLEDGE_MANAGER",
    ):
        assert marker in tests
