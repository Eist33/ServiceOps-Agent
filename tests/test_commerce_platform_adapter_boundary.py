from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMERCE = ROOT / "apps" / "api" / "src" / "serviceops" / "integrations" / "commerce"
CONTRACT_DOC = ROOT / "docs" / "电商平台只读适配器契约.md"
PLAN = ROOT / "docs" / "企业客服与工单执行Agent_生产化开发流程_v1.0.md"


def test_commerce_boundary_declares_three_platform_neutral_protocols() -> None:
    contracts = (COMMERCE / "contracts.py").read_text(encoding="utf-8")

    for protocol in ("IdentityProvider", "OrderReader", "ShippingReader"):
        assert f"class {protocol}(Protocol)" in contracts
    for provider in ("TAOBAO", "XIAOHONGSHU", "XIANYU"):
        assert provider in contracts
    assert "MAX_RECENT_ORDER_LIMIT = 3" in contracts


def test_default_platform_stubs_are_fail_closed_and_network_disabled() -> None:
    stubs = (COMMERCE / "stubs.py").read_text(encoding="utf-8")
    registry = (COMMERCE / "registry.py").read_text(encoding="utf-8")

    assert "UnconfiguredCommercePlatform" in stubs
    assert "external_requests_enabled=False" in stubs
    assert "AdapterErrorCode.NOT_CONFIGURED" in stubs
    assert "for provider in CommerceProvider" in registry
    for forbidden_import in (
        "import httpx",
        "import requests",
        "from urllib",
        "import socket",
    ):
        assert forbidden_import not in stubs


def test_9c_readiness_gate_requires_external_evidence_without_network_code() -> None:
    contracts = (COMMERCE / "contracts.py").read_text(encoding="utf-8")
    readiness = (COMMERCE / "readiness.py").read_text(encoding="utf-8")
    contract_doc = CONTRACT_DOC.read_text(encoding="utf-8")

    for requirement in (
        "OfficialAdapterReadinessEvidence",
        "OfficialAdapterReadinessReport",
        "ReadinessRequirement",
        "READ_ONLY_CAPABILITIES",
        "REQUIRED_READINESS_REQUIREMENTS",
    ):
        assert requirement in contracts
    assert "external_requests_enabled=False" in readiness
    assert "state=AdapterState.NOT_CONFIGURED" in readiness
    for forbidden_import in (
        "import httpx",
        "import requests",
        "from urllib",
        "import socket",
    ):
        assert forbidden_import not in readiness
    assert "9C 本地准入门禁（无外部副作用）" in contract_doc
    assert "不会发起网络请求" in contract_doc


def test_contract_and_plan_do_not_claim_real_platform_connectivity() -> None:
    contract = CONTRACT_DOC.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")

    assert "没有连接任何真实平台" in contract
    assert "不会产生外部网络请求" in contract
    assert "阶段 9A：平台无关契约与失败关闭桩（已完成）" in plan
    assert (
        "阶段 9B：闲鱼个人账号本地只读实验（进行中；9B-1～9B-4 已完成本地模拟验收）"
        in plan
    )
    assert "阶段 9C：官方只读沙箱适配器（待外部条件）" in plan


def test_operations_dashboard_exposes_only_safe_platform_status() -> None:
    main = (ROOT / "apps" / "api" / "src" / "serviceops" / "main.py").read_text(
        encoding="utf-8"
    )
    frontend = (
        ROOT / "demo" / "app" / "operations" / "operations-client.tsx"
    ).read_text(encoding="utf-8")

    assert '"/api/ops/integrations/commerce"' in main
    assert "Depends(current_operations_operator)" in main
    assert "电商平台接入状态" in frontend
    assert "外部请求已关闭" in frontend
