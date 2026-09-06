from pathlib import Path

ROOT = Path(__file__).parents[1]
STAGE6_DOC = ROOT / "docs" / "阶段6-生产发布与持续治理.md"
PLAN = ROOT / "docs" / "企业客服与工单执行Agent_改进计划_v1.0.md"


def test_stage6_document_matches_plan_and_has_machine_contract() -> None:
    document = STAGE6_DOC.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")

    assert "阶段 6：生产发布与持续治理" in plan
    for marker in (
        "发布清单",
        "应用镜像",
        "数据库迁移",
        "AgentRelease",
        "KnowledgeRelease",
        "SBOM",
        "签名",
        "回滚演练",
        "Hit@1",
        "p95",
        "零结果率",
        "人工接管",
        "满意度",
        "单位会话成本",
        "过期知识",
        "孤立切块",
        "失败 embedding",
        "跨版本一致性",
        "备份隔离恢复",
        "发布失败不留下半发布索引",
        "READY_FOR_PRODUCTION_REVIEW",
        "NOT_CONFIGURED",
        "NOT_APPROVED",
        "Docker-only",
        "网页/可见验收步骤",
        "阶段 5",
    ):
        assert marker in document
    assert "PowerShell" not in document


def test_stage6_docs_and_compose_expose_governance_paths() -> None:
    document = STAGE6_DOC.read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    process = (
        ROOT / "docs" / "企业客服与工单执行Agent_生产化开发流程_v1.0.md"
    ).read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.stage3.yml").read_text(encoding="utf-8")

    for content in (document, readme, architecture, process):
        assert "阶段 6" in content
        assert "docker compose" in content
        assert "/api/ops/production/governance" in content
        assert "/api/ops/production/release-gate" in content
        assert "publish_allowed" in content
        assert "external_requests_enabled" in content
    assert "tests/test_production_governance.py" in compose
    assert "Dockerfile.test" in document


def test_stage6_sources_have_no_deployment_or_external_side_effects() -> None:
    sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "apps/api/src/serviceops/production/governance.py",
            "apps/api/src/serviceops/main.py",
            "apps/api/src/serviceops/cli.py",
        )
    ).lower()

    for forbidden in (
        "boto3",
        "google.cloud",
        "azure.",
        "requests.",
        "httpx",
        "websocket",
        "fetch(",
        "axios",
        "subprocess",
        "docker run",
        "kubectl",
    ):
        assert forbidden not in sources
    for forbidden in (
        "traffic_switch",
        "create_backup",
        "send_alert",
        "publish_image",
    ):
        assert forbidden not in sources


def test_stage6_tests_cover_gates_sli_rollback_and_secret_free_output() -> None:
    tests = (ROOT / "apps/api/tests/test_production_governance.py").read_text(
        encoding="utf-8"
    )
    for marker in (
        "READY_FOR_PRODUCTION_REVIEW",
        "publish_allowed",
        "rollback_allowed",
        "backup_restore_verified",
        "cross_scope_leaks",
        "partial_release_index_count",
        "external_requests_enabled",
        "forbidden.status_code == 403",
    ):
        assert marker in tests
