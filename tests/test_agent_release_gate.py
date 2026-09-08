from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_verification_runs_both_evaluation_gates() -> None:
    script = (ROOT / "scripts" / "verify-release.ps1").read_text(encoding="utf-8")

    assert "python -m serviceops.cli evaluate-knowledge" in script
    assert "python -m serviceops.cli evaluate-agent" in script
    assert "[switch]$VerifyModelProvider" in script
    assert "[switch]$EvaluateFullModel" in script
    assert "verify-model-provider.ps1" in script
    assert "evaluate-agent --runtime model" in script


def test_local_deployment_collects_key_without_echo_and_runs_release_gate() -> None:
    script = (ROOT / "scripts" / "deploy-local-deepseek.ps1").read_text(
        encoding="utf-8"
    )
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "Read-Host '请输入 DeepSeek API Key（输入内容不会显示）' -AsSecureString" in script
    assert "ZeroFreeBSTR" in script
    assert "MODEL_API_KEY = $apiKey" in script
    assert "verify-release.ps1" in script
    assert "-VerifyModelProvider" in script
    assert "[switch]$EvaluateFullModel" in script
    assert "Write-Host $apiKey" not in script
    assert ".env" in gitignore


def test_documentation_describes_isolated_gate_and_safe_local_deployment() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    deployment = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    assert "部署与运行指南" in readme
    assert "架构设计" in readme
    assert "不对公网开放数据库 `5432`" in deployment
    assert "每个场景使用独立临时数据库" in deployment
