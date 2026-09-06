from pathlib import Path

ROOT = Path(__file__).parents[1]
STAGE2_DOC = ROOT / "docs" / "阶段2-文档摄取、结构化切块与知识快照.md"
PLAN = ROOT / "docs" / "企业客服与工单执行Agent_改进计划_v1.0.md"


def test_stage2_document_is_linked_to_plan_and_has_contract_sections():
    document = STAGE2_DOC.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")

    assert "阶段 2" in plan
    for marker in (
        "输入与输出",
        "状态",
        "幂等",
        "Docker-only",
        "网页/可见操作步骤",
        "KNOWLEDGE_IDEMPOTENCY_CONFLICT",
        "lexical_v1",
        "DOCUMENT_ENCRYPTED",
    ):
        assert marker in document
    assert "PowerShell" not in document


def test_stage2_docs_and_readme_expose_only_operator_contract():
    document = STAGE2_DOC.read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    process = (
        ROOT / "docs" / "企业客服与工单执行Agent_生产化开发流程_v1.0.md"
    ).read_text(encoding="utf-8")

    for content in (document, readme, architecture, process):
        assert "阶段 2" in content
        assert "docker compose" in content
    for route in (
        "/api/ops/knowledge/documents",
        "/api/ops/knowledge/releases",
    ):
        assert route in document
    assert "KNOWLEDGE_MANAGER" in document
    assert "不保存原始文件" in document


def test_stage2_implementation_has_no_external_io_or_stage3_retrieval():
    sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "apps/api/src/serviceops/knowledge/ingestion.py",
            "apps/api/src/serviceops/knowledge/releases.py",
        )
    ).lower()

    for forbidden in (
        "requests.",
        "httpx",
        "websocket",
        "fetch(",
        "axios",
        "embedding",
        "rrf",
        "vector_retrieval",
    ):
        assert forbidden not in sources


def test_stage2_tests_cover_required_failure_and_lifecycle_terms():
    tests = (ROOT / "apps/api/tests/test_knowledge_ingestion_pipeline.py").read_text(
        encoding="utf-8"
    )
    for marker in (
        "DOCUMENT_TYPE_UNSUPPORTED",
        "DOCUMENT_ENCRYPTED",
        "DOCUMENT_TOO_LARGE",
        "KNOWLEDGE_EXTERNAL_SOURCE_FORBIDDEN",
        "KNOWLEDGE_IDEMPOTENCY_CONFLICT",
        "supersedes_document_id",
        "rollback",
        "KNOWLEDGE_RELEASE_EVALUATION_FAILED",
    ):
        assert marker in tests
