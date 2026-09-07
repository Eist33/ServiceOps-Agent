from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REFUND_DOC = REPO_ROOT / "docs" / "退款人工审批与并发幂等安全修复.md"


def test_refund_safety_document_describes_machine_contract() -> None:
    content = REFUND_DOC.read_text(encoding="utf-8")
    required = (
        "PENDING_HUMAN_APPROVAL",
        "PENDING_CONFIRMATION",
        "REFUND_HUMAN_APPROVAL_REQUIRED",
        "REFUND_ALREADY_EXECUTED",
        "REFUND_CONCURRENCY_CONFLICT",
        "refund_approval_audits",
        "uq_refund_requests_customer_order_active",
        "docker compose config --quiet",
        "localhost:3000",
    )
    assert all(marker in content for marker in required)


def test_refund_service_has_no_external_write_client() -> None:
    content = (
        REPO_ROOT / "apps" / "api" / "src" / "serviceops" / "refunds" / "service.py"
    ).read_text(encoding="utf-8")
    forbidden = ("import requests", "import httpx", "fetch(", "websocket", "http://", "https://")
    assert not any(marker in content.lower() for marker in forbidden)
