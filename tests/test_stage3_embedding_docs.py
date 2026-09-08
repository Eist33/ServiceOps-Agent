from pathlib import Path

ROOT = Path(__file__).parents[1]
STAGE3_DOC = ROOT / "docs" / "阶段3-真实Embedding与混合检索.md"
PLAN = ROOT / "docs" / "企业客服与工单执行Agent_改进计划_v1.0.md"


def test_stage3_document_matches_plan_and_has_machine_contract() -> None:
    document = STAGE3_DOC.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")

    assert "阶段 3：真实 embedding 与混合检索" in plan
    for marker in (
        "输入输出",
        "EmbeddingProvider",
        "vector_v1",
        "hybrid_rrf_v1",
        "RRF_K=60",
        "tenant_scope",
        "cost_micros",
        "EMBEDDING_PROVIDER_NOT_CONFIGURED",
        "KNOWLEDGE_RELEASE_EMBEDDING_NOT_READY",
        "Docker-only",
        "网页/可见验收步骤",
        "失败关闭",
    ):
        assert marker in document
    assert "PowerShell" not in document


def test_stage3_docs_expose_only_operator_scoped_routes_and_docker_evidence() -> None:
    document = STAGE3_DOC.read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    process = (
        ROOT / "docs" / "企业客服与工单执行Agent_生产化开发流程_v1.0.md"
    ).read_text(encoding="utf-8")
    dockerfile_test = (ROOT / "apps/api/Dockerfile.test").read_text(encoding="utf-8")
    compose_test = (ROOT / "docker-compose.stage3.yml").read_text(encoding="utf-8")

    for content in (document, architecture, process):
        assert "阶段 3" in content
        assert "docker compose" in content
    assert "docker-compose.stage3.yml" in document
    assert "Dockerfile.test" in document
    assert "/api/ops/knowledge/releases/{release_id}/embeddings" in document
    assert "/api/ops/knowledge/search" in document
    assert "KNOWLEDGE_MANAGER" in document
    assert "lexical_v1" in document
    assert "PostgreSQL/pgvector" in document
    assert "COPY tests ./tests" in dockerfile_test
    assert "\".[test]\"" in dockerfile_test
    assert "api-test" in compose_test


def test_stage3_implementation_has_no_hidden_network_or_stage4_side_effect() -> None:
    sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "apps/api/src/serviceops/knowledge/embeddings.py",
            "apps/api/src/serviceops/knowledge/embedding_pipeline.py",
            "apps/api/src/serviceops/knowledge/vector.py",
            "apps/api/src/serviceops/knowledge/fusion.py",
        )
    ).lower()

    for forbidden in ("requests.", "httpx", "websocket", "fetch(", "axios"):
        assert forbidden not in sources
    for forbidden in ("reranker", "hyde", "retrieval_trace", "quality_operations"):
        assert forbidden not in sources


def test_stage3_tests_cover_provider_failure_scope_and_publish_gate() -> None:
    tests = (
        ROOT / "apps/api/tests/test_embedding_hybrid_retrieval.py"
    ).read_text(encoding="utf-8")
    for marker in (
        "EMBEDDING_PROVIDER_NOT_CONFIGURED",
        "EMBEDDING_DIMENSION_UNSUPPORTED",
        "EMBEDDING_CONTENT_HASH_MISMATCH",
        "KNOWLEDGE_RELEASE_EMBEDDING_NOT_READY",
        "EMBEDDING_PROVIDER_REQUEST_FAILED",
        "tenant_scope",
        "channel_scope",
        "product_scope",
        "valid_until",
        "fallback",
    ):
        assert marker in tests
