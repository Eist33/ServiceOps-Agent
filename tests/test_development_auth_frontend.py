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
    assert "useState('')" in gate
    assert "value={password}" in gate
    assert "本地默认密码为 serviceops" not in gate
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
    assert "refundVersionRef" in customer_client
    assert "客服已同意退款，请确认退款" in customer_client
    assert "approval-granted-${refund.id}-${refund.version}" in customer_client
    assert "确认退款" in customer_client


def test_customer_refund_status_is_server_canonical_and_staff_can_change_intent() -> None:
    workbench = (
        ROOT / "demo" / "app" / "agent" / "workbench-client.tsx"
    ).read_text(encoding="utf-8")
    customer_client = (
        ROOT / "demo" / "app" / "demo-client.tsx"
    ).read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")

    assert "/api/agent/tickets/${ticketId}/intent" in api
    assert "changeAgentTicketIntent" in workbench
    assert "intent: 'REFUND'" in workbench
    assert "intent-change-panel" in workbench
    assert "intent_history" in api
    assert "current_intent" in api
    assert "status: 'PENDING_HUMAN_APPROVAL'" in customer_client
    assert "退款状态：${refundStatusLabel(item.status)}" in customer_client
    assert "state?.refunds.find((refund) => refund.ticket_id === activeTicket?.id)" in customer_client
    assert "event.payload.status" not in customer_client


def test_message_progress_events_are_structured_safe_and_deduplicated() -> None:
    api = API.read_text(encoding="utf-8")
    customer_client = (
        ROOT / "demo" / "app" / "demo-client.tsx"
    ).read_text(encoding="utf-8")
    schemas = (
        ROOT / "apps" / "api" / "src" / "serviceops" / "shared" / "schemas.py"
    ).read_text(encoding="utf-8")
    workflow = (
        ROOT / "docs" / "消息回复事件链路与网页验收.md"
    ).read_text(encoding="utf-8")

    for token in (
        "'model_start'",
        "'timeout_ack'",
        "event_id",
        "sequence",
        "phase",
    ):
        assert token in api
    for token in (
        "seenEventIdsRef",
        "event.type === 'model_start'",
        "event.type === 'timeout_ack'",
        "我正在帮你查询，请稍候",
    ):
        assert token in customer_client
    for token in (
        "class EventPhase",
        "MODEL_START = \"MODEL_START\"",
        "TIMEOUT_ACK = \"TIMEOUT_ACK\"",
        "TOOL_RESULT",
        "FINAL_RESPONSE",
    ):
        assert token in schemas
    assert "MODEL_START → TOOL_CALL → TOOL_RESULT → FINAL_RESPONSE" in workflow
    assert "MODEL_START → TIMEOUT_ACK → TOOL_CALL" in workflow
    assert "思维链" in workflow


def test_conversation_intent_migration_is_reversible_and_auditable() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260907_0016_conversation_intent_history.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260907_0016"' in migration
    assert 'down_revision = "20260907_0015"' in migration
    assert '"current_intent"' in migration
    assert '"conversation_intent_events"' in migration
    assert '"uq_conversation_intent_message"' in migration
    assert 'def downgrade()' in migration


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
