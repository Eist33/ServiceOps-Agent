from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "apps" / "api" / "src" / "serviceops" / "agent" / "model_pilot_readiness.py"
)
DOC = ROOT / "docs" / "阶段12-真实模型发布门禁与小范围试点.md"
ARCHITECTURE = ROOT / "docs" / "architecture.md"


def test_stage12_gate_is_platform_neutral_and_has_no_external_clients() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    for symbol in (
        "ModelPilotCapability",
        "ModelPilotReadinessEvidence",
        "ModelPilotReadinessReport",
        "ModelPilotReadinessRequirement",
        "ModelPilotReadinessState",
        "ModelPilotRuntimeStatus",
        "ModelPilotScopeBinding",
        "evaluate_model_pilot_readiness",
    ):
        assert symbol in source
    assert "model_requests_enabled=False" in source
    assert "READY_FOR_PILOT_REVIEW" in source
    for forbidden_import in (
        "import boto3",
        "import httpx",
        "import requests",
        "import socket",
        "import subprocess",
        "import openai",
    ):
        assert forbidden_import not in source


def test_stage12_docs_state_zero_requests_and_pilot_boundary() -> None:
    document = DOC.read_text(encoding="utf-8")
    architecture = ARCHITECTURE.read_text(encoding="utf-8")

    for required_text in (
        "阶段 12 本地准入门禁（无外部副作用）",
        "NOT_CONFIGURED",
        "NOT_APPROVED",
        "READY_FOR_PILOT_REVIEW",
        "不会发起模型请求",
        "不会打开试点流量",
        "脱敏样本",
        "70 条",
        "退款保持人工审批",
        "不等于生产就绪",
    ):
        assert required_text in document
    for required_text in (
        "ModelPilotReadinessEvidence",
        "READY_FOR_PILOT_REVIEW",
        "不发起模型请求",
        "不扩大客户流量",
    ):
        assert required_text in architecture


def test_stage12_does_not_register_real_model_or_pilot_runtime() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "apps" / "api" / "src" / "serviceops").rglob("*.py")
    )

    for forbidden_runtime in (
        "enable_pilot_traffic",
        "openai.ChatCompletion",
        "create_model_client",
        "send_model_request",
        "publish_model_release",
    ):
        assert forbidden_runtime not in source
    assert "READY_FOR_PILOT_REVIEW" in source
