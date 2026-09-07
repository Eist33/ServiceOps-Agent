from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "demo" / "lib" / "api.ts"
AUTH_SESSION = ROOT / "demo" / "lib" / "auth-session.ts"
AUTH_GATE = ROOT / "demo" / "components" / "auth-gate.tsx"
STAFF_NAV = ROOT / "demo" / "app" / "staff" / "staff-navigation.tsx"
ADR = ROOT / "docs" / "ADR-0001-开发账号认证与多电商平台身份接入.md"


def test_frontend_uses_login_sessions_instead_of_embedded_identity_tokens() -> None:
    api = API.read_text(encoding="utf-8")
    session = AUTH_SESSION.read_text(encoding="utf-8")

    for fixed_token in (
        "demo-linmu-session",
        "demo-knowledge-ops-session",
        "demo-support-agent-session",
    ):
        assert fixed_token not in api
    assert "/api/auth/login" in api
    assert "Authorization" in api
    assert "sessionStorage" in session
    assert "harbor-support-customer-auth" in session
    assert "harbor-support-staff-auth" in session


def test_login_and_staff_navigation_are_role_aware() -> None:
    gate = AUTH_GATE.read_text(encoding="utf-8")
    navigation = STAFF_NAV.read_text(encoding="utf-8")

    for label in ("登录客户服务", "登录客服后台", "开发环境密码", "切换账号"):
        assert label in gate
    assert "allowedRoles" in gate
    assert "area.roles.includes(staff.principal.role)" in navigation
    assert "退出客服后台" in navigation
    assert "切换演示坐席" not in (
        ROOT / "demo" / "app" / "agent" / "workbench-client.tsx"
    ).read_text(encoding="utf-8")


def test_refund_approval_is_visible_only_in_the_support_agent_workbench() -> None:
    workbench = (
        ROOT / "demo" / "app" / "agent" / "workbench-client.tsx"
    ).read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")

    for label in (
        "退款人工审批",
        "通过人工审批",
        "拒绝退款",
        "撤回退款",
        "客户仍需回到客户页面手动点击",
    ):
        assert label in workbench
    for route in (
        "/api/agent/refund-requests/${refundId}/approve",
        "/api/agent/refund-requests/${refundId}/reject",
        "/api/agent/refund-requests/${refundId}/withdraw",
    ):
        assert route in api
    assert "agentRequest<RefundData>" in api
    assert "Idempotency-Key" in api
    assert 'allowedRoles={["SUPPORT_AGENT"]}' in (
        ROOT / "demo" / "app" / "staff" / "agent" / "page.tsx"
    ).read_text(encoding="utf-8")
    customer_client = (
        ROOT / "demo" / "app" / "demo-client.tsx"
    ).read_text(encoding="utf-8")
    assert "PENDING_HUMAN_APPROVAL" in customer_client
    assert "PENDING_CONFIRMATION" in customer_client
    assert "persistedRefundItems" in customer_client
    assert "refundNeedsRefresh" in customer_client
    assert "确认退款" in customer_client


def test_platform_identity_adr_is_fail_closed_and_provider_neutral() -> None:
    text = ADR.read_text(encoding="utf-8")

    for platform in ("淘宝", "小红书", "闲鱼"):
        assert platform in text
    for boundary in (
        "IdentityProvider",
        "OrderReader",
        "ShippingReader",
        "WebhookReceiver",
    ):
        assert boundary in text
    assert "只使用平台官方开放接口" in text
    assert "不能传入可信客户 ID" in text
    assert "当前实现不能被描述为已经接入任何真实电商平台" in text


def test_identity_migration_follows_current_alembic_head() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260905_0009_identity_accounts_auth_sessions.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260905_0009"' in migration
    assert 'down_revision = "20260904_0008"' in migration
    assert '"identity_accounts"' in migration
    assert '"auth_sessions"' in migration
    assert '"token_hash"' in migration
