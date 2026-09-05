from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READINESS = ROOT / "apps" / "api" / "src" / "serviceops" / "production" / "readiness.py"
DOC = ROOT / "docs" / "阶段11-生产基础设施可观测性与灾备准入门禁.md"
ARCHITECTURE = ROOT / "docs" / "architecture.md"


def test_stage11_readiness_is_platform_neutral_and_has_no_external_clients() -> None:
    source = READINESS.read_text(encoding="utf-8")

    for symbol in (
        "InfrastructureCapability",
        "InfrastructureReadinessEvidence",
        "InfrastructureReadinessReport",
        "InfrastructureReadinessRequirement",
        "InfrastructureReadinessState",
        "InfrastructureRuntimeStatus",
        "evaluate_infrastructure_readiness",
    ):
        assert symbol in source
    assert "external_resources_enabled=False" in source
    assert "READY_FOR_PRODUCTION_REVIEW" in source
    for forbidden_import in (
        "import boto3",
        "import docker",
        "import httpx",
        "import requests",
        "import socket",
        "import subprocess",
        "import psycopg",
    ):
        assert forbidden_import not in source


def test_stage11_docs_state_zero_side_effects_and_later_stage_boundary() -> None:
    document = DOC.read_text(encoding="utf-8")
    architecture = ARCHITECTURE.read_text(encoding="utf-8")

    for required_text in (
        "阶段 11 本地准入门禁（无外部副作用）",
        "NOT_CONFIGURED",
        "NOT_APPROVED",
        "READY_FOR_PRODUCTION_REVIEW",
        "不会创建外部资源",
        "不会发起网络请求",
        "备份和恢复演练",
        "不等于生产就绪",
    ):
        assert required_text in document
    for required_text in (
        "InfrastructureReadinessEvidence",
        "阶段 11 尚无托管 PostgreSQL",
        "READY_FOR_PRODUCTION_REVIEW",
        "不创建资源",
    ):
        assert required_text in architecture


def test_stage11_has_no_production_runtime_registration_or_external_endpoint() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "apps" / "api" / "src" / "serviceops").rglob("*.py")
    )

    assert "create_production_resources" not in source
    assert "configure_external_alerts" not in source
    assert "run_backup" not in source
    assert "restore_backup" not in source
    assert "READY_FOR_PRODUCTION_REVIEW" in source
