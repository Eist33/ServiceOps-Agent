from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "demo" / "app" / "demo-client.tsx"
API = ROOT / "demo" / "lib" / "api.ts"
E2E = ROOT / "demo" / "e2e" / "core-flows.spec.ts"
MIGRATION = (
    ROOT
    / "apps"
    / "api"
    / "alembic"
    / "versions"
    / "20260904_0006_conversation_active_order.py"
)


def test_customer_client_renders_and_restores_order_selection() -> None:
    text = CLIENT.read_text(encoding="utf-8")

    assert "OrderSelectionCards" in text
    assert "请选择需要处理的订单" in text
    assert "setOrder(persisted.active_order)" in text
    assert "selectActiveOrder(conversationId, orderNumber)" in text
    assert "requestOrderSelection(conversationId)" in text
    assert "createShippingTicket(\n        conversationId,\n        order.order_number" in text
    assert "Promise.all([\n          getOrder()," not in text


def test_frontend_contract_has_selection_and_active_order_events() -> None:
    text = API.read_text(encoding="utf-8")

    assert "'order_selection_required'" in text
    assert "'active_order_changed'" in text
    assert "active_order: OrderData | null" in text
    assert "/api/orders/recent" in text
    assert "/active-order" in text
    assert "/order-selection" in text


def test_e2e_records_refreshable_recent_order_choice() -> None:
    text = E2E.read_text(encoding="utf-8")

    assert "自然语言触发最近三笔订单选择并在刷新后恢复活动订单" in text
    assert "帮我查一下快递" in text
    assert "await page.reload()" in text


def test_active_order_has_forward_and_reverse_migration() -> None:
    text = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "20260904_0006"' in text
    assert 'down_revision = "20260903_0005"' in text
    assert '"active_order_id"' in text
    assert '"order_selection_pending"' in text
    assert "def downgrade()" in text
