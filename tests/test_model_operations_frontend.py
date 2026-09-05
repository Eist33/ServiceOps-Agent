from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_operations_dashboard_displays_model_reliability_metrics() -> None:
    client = (
        ROOT / "demo" / "app" / "operations" / "operations-client.tsx"
    ).read_text(encoding="utf-8")
    contract = (ROOT / "demo" / "lib" / "api.ts").read_text(encoding="utf-8")

    assert "模型运行健康度" in client
    assert "dashboard.models.success_rate" in client
    assert "dashboard.models.p95_duration_ms" in client
    assert "dashboard.models.total_tokens" in client
    assert "dashboard.recent_model_invocations" in client
    assert "recent_model_invocations:" in contract
