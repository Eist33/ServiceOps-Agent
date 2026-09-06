from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE_1 = ROOT / "docs" / "阶段1-模块边界、Agent发布与上下文治理.md"


def test_stage1_document_has_contracts_examples_and_docker_acceptance() -> None:
    text = STAGE_1.read_text(encoding="utf-8")
    for required in (
        "AgentRelease",
        "customer-tools-v1",
        "ContextAssembler",
        "CONTEXT_SENSITIVE_INPUT",
        "CONTEXT_BUDGET_EXCEEDED",
        "agent-governance",
        "docker compose exec -T api python -m pytest tests/test_agent_governance.py",
        "Docker Engine 不可用时只记录环境阻塞",
    ):
        assert required in text
    for forbidden in ("TODO", "PowerShell", "embedding 管道已启用", "自动发送"):
        assert forbidden not in text


def test_stage1_references_are_present_in_readme_architecture_and_flow() -> None:
    for path in (
        ROOT / "README.md",
        ROOT / "docs" / "architecture.md",
        ROOT / "docs" / "企业客服与工单执行Agent_生产化开发流程_v1.0.md",
    ):
        text = path.read_text(encoding="utf-8")
        assert "阶段 1" in text
        assert "agent-support-v1" in text or "AgentRelease" in text
        assert "agent-governance" in text or "上下文治理" in text
