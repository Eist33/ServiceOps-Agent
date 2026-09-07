import json

from sqlalchemy import select

from serviceops.agent.orchestrator import DeterministicSupportAgent
from serviceops.conversations.service import create_conversation
from serviceops.identity.service import resolve_customer
from serviceops.models import Order, ShippingEvent, ToolInvocation
from serviceops.seed import AGENT_SESSION_TOKEN


def new_conversation(client):
    return client.post("/api/conversations").json()["id"]


def run_agent(client, conversation_id, content):
    response = client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": content}
    )
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines() if line]


def event_types(events):
    return [event["type"] for event in events]


def keep_demo_orders(db, order_numbers: set[str]) -> None:
    customer = resolve_customer(db, "demo-linmu-session")
    orders = list(db.scalars(select(Order).where(Order.customer_id == customer.id)))
    for order in orders:
        if order.order_number not in order_numbers:
            for event in db.scalars(
                select(ShippingEvent).where(ShippingEvent.order_id == order.id)
            ):
                db.delete(event)
            db.delete(order)
    db.commit()


def test_policy_flow_emits_source_tool_events(client):
    events = run_agent(client, new_conversation(client), "退货需要几天？")
    assert event_types(events)[:2] == ["ack", "thinking"]
    assert event_types(events)[2] == "tool_started"
    assert "tool_completed" in event_types(events)
    assert "message_delta" in event_types(events)
    completed = next(event for event in events if event["type"] == "tool_completed")
    assert completed["payload"]["tool_name"] == "search_knowledge_base"


def test_shipping_flow_uses_order_and_shipping_tools(client):
    events = run_agent(client, new_conversation(client), "订单 ORD-20260828-1042 物流到哪了？")
    tools = [event["payload"]["tool_name"] for event in events if event["type"] == "tool_completed"]
    assert tools == ["get_order", "get_shipping_status"]


def test_order_flow_requires_selection_when_recent_orders_are_ambiguous(client):
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "帮我查一下快递")

    tools = [
        event["payload"]["tool_name"]
        for event in events
        if event["type"] == "tool_completed"
    ]
    assert tools == ["list_recent_orders"]
    selection = next(
        event for event in events if event["type"] == "order_selection_required"
    )
    assert len(selection["payload"]["orders"]) == 3

    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["active_order"] is None
    assert state["order_selection"]["required"] is True
    assert len(state["order_selection"]["orders"]) == 3
    assert state["tickets"] == []
    assert state["refunds"] == []


def test_only_recent_order_is_automatically_selected(client, db):
    keep_demo_orders(db, {"ORD-20260828-1042"})
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "帮我查一下快递")

    tools = [
        event["payload"]["tool_name"]
        for event in events
        if event["type"] == "tool_completed"
    ]
    assert tools == ["list_recent_orders", "get_shipping_status"]
    assert "order_selection_required" not in event_types(events)
    assert "active_order_changed" in event_types(events)
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["active_order"]["order_number"] == "ORD-20260828-1042"


def test_no_orders_stops_before_order_business_tools(client, db):
    keep_demo_orders(db, set())
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "帮我查一下快递")

    tools = [
        event["payload"]["tool_name"]
        for event in events
        if event["type"] == "tool_completed"
    ]
    assert tools == ["list_recent_orders"]
    assert "order_selection_required" not in event_types(events)
    message = next(event for event in events if event["type"] == "message_delta")
    assert "没有可用订单" in message["payload"]["delta"]


def test_selected_order_is_reused_and_restored_in_conversation(client):
    conversation_id = new_conversation(client)
    run_agent(client, conversation_id, "帮我查一下快递")
    selected = client.post(
        f"/api/conversations/{conversation_id}/active-order",
        json={"order_number": "ORD-20260828-1042"},
    )
    assert selected.status_code == 200

    events = run_agent(client, conversation_id, "这个订单现在到哪里了？")
    tools = [
        event["payload"]["tool_name"]
        for event in events
        if event["type"] == "tool_completed"
    ]
    assert tools == ["get_order", "get_shipping_status"]

    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["active_order"]["order_number"] == "ORD-20260828-1042"
    assert state["order_selection"] == {"required": False, "orders": []}


def test_changing_order_clears_previous_choice_until_customer_selects(client):
    conversation_id = new_conversation(client)
    selected = client.post(
        f"/api/conversations/{conversation_id}/active-order",
        json={"order_number": "ORD-20260828-1042"},
    )
    assert selected.status_code == 200

    response = client.post(
        f"/api/conversations/{conversation_id}/order-selection"
    )
    assert response.status_code == 200
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["active_order"] is None
    assert state["order_selection"]["required"] is True

    events = run_agent(client, conversation_id, "帮我申请退款")
    assert "approval_required" not in event_types(events)
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["refunds"] == []


def test_active_order_selection_enforces_conversation_and_order_ownership(
    client, other_client
):
    conversation_id = new_conversation(client)
    forbidden_conversation = other_client.post(
        f"/api/conversations/{conversation_id}/active-order",
        json={"order_number": "ORD-20260827-9001"},
    )
    assert forbidden_conversation.status_code == 403

    forbidden_order = client.post(
        f"/api/conversations/{conversation_id}/active-order",
        json={"order_number": "ORD-20260827-9001"},
    )
    assert forbidden_order.status_code == 403


def test_explicit_order_number_becomes_active_order(client):
    conversation_id = new_conversation(client)
    events = run_agent(
        client, conversation_id, "订单 ORD-20260828-1042 物流到哪了？"
    )
    assert "active_order_changed" in event_types(events)
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["active_order"]["order_number"] == "ORD-20260828-1042"


def test_ticket_flow_changes_business_state(client):
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "ORD-20260828-1042 物流没更新，帮我催一下")
    assert "business_state_changed" in event_types(events)
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["tickets"][0]["status"] == "OPEN"
    assert state["tickets"][0]["priority"] == "P2"
    assert state["tickets"][0]["sla_status"] == "ON_TRACK"


def test_new_conversation_creates_its_own_ticket(client):
    first_conversation_id = new_conversation(client)
    run_agent(
        client,
        first_conversation_id,
        "ORD-20260828-1042 物流没更新，帮我催一下",
    )
    first_ticket = client.get(
        f"/api/conversations/{first_conversation_id}"
    ).json()["tickets"][0]

    second_conversation_id = new_conversation(client)
    run_agent(
        client,
        second_conversation_id,
        "ORD-20260828-1042 物流没更新，帮我催一下",
    )
    second_state = client.get(f"/api/conversations/{second_conversation_id}").json()

    assert len(second_state["tickets"]) == 1
    assert second_state["tickets"][0]["id"] != first_ticket["id"]
    assert second_state["tickets"][0]["ticket_number"] != first_ticket["ticket_number"]
    assert second_state["tool_invocations"][-1]["tool_name"] == "create_ticket"


def test_ticket_can_handoff_to_human_support_group(client, other_client):
    conversation_id = new_conversation(client)
    run_agent(client, conversation_id, "ORD-20260828-1042 物流没更新，帮我催一下")
    ticket = client.get(f"/api/conversations/{conversation_id}").json()["tickets"][0]

    forbidden = other_client.post(f"/api/tickets/{ticket['id']}/handoff")
    assert forbidden.status_code == 403

    response = client.post(f"/api/tickets/{ticket['id']}/handoff")
    assert response.status_code == 200
    handed_off = response.json()
    assert handed_off["handoff_status"] == "ASSIGNED"
    assert handed_off["assignee_name"] == "物流专员组"
    assert handed_off["sla_due_at"]
    assert handed_off["events"][-1]["action"] == "HUMAN_HANDOFF_ASSIGNED"

    repeated = client.post(f"/api/tickets/{ticket['id']}/handoff")
    assert repeated.status_code == 200
    assert repeated.json()["assigned_at"] == handed_off["assigned_at"]

    forbidden_cancel = other_client.post(
        f"/api/tickets/{ticket['id']}/handoff/cancel"
    )
    assert forbidden_cancel.status_code == 403

    cancelled = client.post(f"/api/tickets/{ticket['id']}/handoff/cancel")
    assert cancelled.status_code == 200
    returned_to_agent = cancelled.json()
    assert returned_to_agent["handoff_status"] == "BOT_ACTIVE"
    assert returned_to_agent["assignee_name"] is None
    assert returned_to_agent["assigned_at"] is None
    assert returned_to_agent["events"][-1]["action"] == "HUMAN_HANDOFF_CANCELLED"


def test_refund_flow_requires_approval(client):
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "订单 ORD-20260828-1042 不想要了，申请退款")
    approval = next(event for event in events if event["type"] == "approval_required")
    assert approval["payload"]["amount"] == "329.00"
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["refunds"][0]["status"] == "PENDING_HUMAN_APPROVAL"


def test_customer_intent_history_preserves_shipping_before_refund(client):
    conversation_id = new_conversation(client)
    shipping = run_agent(client, conversation_id, "订单 ORD-20260828-1042 的物流到哪了？")
    assert "approval_required" not in event_types(shipping)
    after_shipping = client.get(f"/api/conversations/{conversation_id}").json()
    assert after_shipping["current_intent"] == "SHIPPING"
    assert after_shipping["intent_history"][-1]["intent"] == "SHIPPING"

    refund = run_agent(
        client,
        conversation_id,
        "订单 ORD-20260828-1042 商品不合适，申请退款",
    )
    assert "approval_required" in event_types(refund)
    after_refund = client.get(f"/api/conversations/{conversation_id}").json()
    assert after_refund["current_intent"] == "REFUND"
    assert [item["intent"] for item in after_refund["intent_history"]][-2:] == [
        "SHIPPING",
        "REFUND",
    ]
    assert after_refund["refunds"][0]["status"] == "PENDING_HUMAN_APPROVAL"


def test_refund_missing_reason_is_asked_and_resumed_on_next_turn(client):
    conversation_id = new_conversation(client)
    client.post(
        f"/api/conversations/{conversation_id}/active-order",
        json={"order_number": "ORD-20260828-1042"},
    )

    first = run_agent(client, conversation_id, "帮我申请退款")
    assert "approval_required" not in event_types(first)
    question = next(event for event in first if event["type"] == "message_delta")
    assert "退款的原因" in question["payload"]["delta"]
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["conversation"]["pending_action"] == "REFUND_REASON"
    assert state["refunds"] == []

    small_talk = run_agent(client, conversation_id, "你好")
    assert "approval_required" not in event_types(small_talk)
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["conversation"]["pending_action"] == "REFUND_REASON"
    assert state["refunds"] == []

    interruption = run_agent(client, conversation_id, "物流到哪了？")
    assert "approval_required" not in event_types(interruption)
    assert any(
        event["payload"].get("tool_name") == "get_shipping_status"
        for event in interruption
        if event["type"] == "tool_completed"
    )
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["conversation"]["pending_action"] == "REFUND_REASON"
    assert state["refunds"] == []

    second = run_agent(client, conversation_id, "商品有质量问题")
    assert "approval_required" in event_types(second)
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["conversation"]["pending_action"] is None
    assert state["refunds"][0]["reason"] == "商品有质量问题"


def test_selecting_order_resumes_pending_natural_language_action(client):
    conversation_id = new_conversation(client)
    first = run_agent(client, conversation_id, "帮我查一下快递")
    assert "order_selection_required" in event_types(first)
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["conversation"]["pending_action"] == "SHIPPING_QUERY"

    client.post(
        f"/api/conversations/{conversation_id}/active-order",
        json={"order_number": "ORD-20260828-1042"},
    )
    resumed = run_agent(
        client,
        conversation_id,
        "我选择订单 ORD-20260828-1042，请继续处理刚才的问题。",
    )
    tools = [
        event["payload"]["tool_name"]
        for event in resumed
        if event["type"] == "tool_completed"
    ]
    assert tools == ["get_order", "get_shipping_status"]
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["conversation"]["pending_action"] is None


def test_customer_can_cancel_an_incomplete_action_without_writes(client):
    conversation_id = new_conversation(client)
    first = run_agent(client, conversation_id, "帮我申请退款")
    assert "order_selection_required" in event_types(first)

    cancelled = run_agent(client, conversation_id, "算了")
    message = next(
        event for event in cancelled if event["type"] == "message_delta"
    )
    assert "没有产生新的业务写入" in message["payload"]["delta"]
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["conversation"]["pending_action"] is None
    assert state["order_selection"]["required"] is False
    assert state["tickets"] == []
    assert state["refunds"] == []


def test_multi_intent_executes_shipping_before_pending_refund(client):
    conversation_id = new_conversation(client)
    events = run_agent(
        client,
        conversation_id,
        "订单 ORD-20260828-1042 的物流到哪了？这个商品我不想要了，申请退款。",
    )
    tools = [
        event["payload"]["tool_name"]
        for event in events
        if event["type"] == "tool_completed"
    ]
    assert tools == [
        "get_order",
        "get_shipping_status",
        "get_order",
        "search_knowledge_base",
        "create_refund_request",
    ]
    assert "approval_required" in event_types(events)


def test_ticket_status_and_human_handoff_use_current_conversation_ticket(client):
    conversation_id = new_conversation(client)
    run_agent(
        client,
        conversation_id,
        "ORD-20260828-1042 物流没更新，帮我催一下",
    )

    status_events = run_agent(client, conversation_id, "刚才的工单处理了吗？")
    status_tool = next(
        event for event in status_events if event["type"] == "tool_completed"
    )
    assert status_tool["payload"]["tool_name"] == "get_current_ticket"

    handoff_events = run_agent(client, conversation_id, "我要转人工客服")
    tools = [
        event["payload"]["tool_name"]
        for event in handoff_events
        if event["type"] == "tool_completed"
    ]
    assert tools == ["get_current_ticket", "request_human_handoff"]
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["tickets"][0]["handoff_status"] == "ASSIGNED"


def test_refund_api_is_idempotent(client):
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "ORD-20260828-1042 不想要了，申请退款")
    refund_id = next(
        event["refund_request_id"] for event in events if event["type"] == "approval_required"
    )
    approval = client.post(
        f"/api/agent/refund-requests/{refund_id}/approve",
        headers={
            "X-Agent-Session": AGENT_SESSION_TOKEN,
            "Idempotency-Key": "agent-approval-key",
        },
    )
    assert approval.status_code == 200
    assert approval.json()["status"] == "PENDING_CONFIRMATION"
    first = client.post(
        f"/api/refund-requests/{refund_id}/confirm", headers={"Idempotency-Key": "api-key"}
    )
    second = client.post(
        f"/api/refund-requests/{refund_id}/confirm", headers={"Idempotency-Key": "api-key"}
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_refund_api_rejects_missing_key(client):
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "ORD-20260828-1042 不想要了，申请退款")
    refund_id = next(
        event["refund_request_id"] for event in events if event["type"] == "approval_required"
    )
    response = client.post(f"/api/refund-requests/{refund_id}/confirm")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_IDEMPOTENCY_KEY"


def test_refund_api_requires_support_agent_approval(client):
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "ORD-20260828-1042 不想要了，申请退款")
    refund_id = next(
        event["refund_request_id"] for event in events if event["type"] == "approval_required"
    )
    response = client.post(
        f"/api/agent/refund-requests/{refund_id}/approve",
        headers={"Idempotency-Key": "unapproved-key"},
    )
    assert response.status_code == 403
    response = client.post(
        f"/api/refund-requests/{refund_id}/confirm",
        headers={"Idempotency-Key": "customer-key"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REFUND_HUMAN_APPROVAL_REQUIRED"


def test_conversation_refresh_restores_messages_and_audit(client):
    conversation_id = new_conversation(client)
    run_agent(client, conversation_id, "退货需要几天？")
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert [message["role"] for message in state["messages"]] == ["user", "agent"]
    assert state["tool_invocations"][0]["tool_name"] == "search_knowledge_base"


def test_cross_user_conversation_is_forbidden(client, other_client):
    conversation_id = new_conversation(client)
    response = other_client.get(f"/api/conversations/{conversation_id}")
    assert response.status_code == 403


def test_invalid_ticket_type_is_rejected(client):
    conversation_id = new_conversation(client)
    response = client.post(
        "/api/tickets",
        json={
            "conversation_id": conversation_id,
            "order_number": "ORD-20260828-1042",
            "ticket_type": "PAYMENT_OVERRIDE",
            "reason": "test",
        },
    )
    assert response.status_code == 422


def test_stream_events_have_correlation_ids(client):
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "退货政策")
    for event in events:
        assert event["conversation_id"] == conversation_id
        assert event["message_id"]
        assert event["trace_id"]


def test_stream_events_have_ordered_auditable_phases(client):
    events = run_agent(
        client,
        new_conversation(client),
        "订单 ORD-20260828-1042 物流到哪了？",
    )
    assert [event["type"] for event in events[:2]] == ["ack", "thinking"]
    phased = [event for event in events if event.get("phase")]
    assert [event["phase"] for event in phased[:4]] == [
        "ACK",
        "THINKING",
        "TOOL_CALL",
        "TOOL_RESULT",
    ]
    assert phased[-1]["phase"] == "FINAL_RESPONSE"
    assert [event["sequence"] for event in events] == list(range(len(events)))
    assert len({event["event_id"] for event in events}) == len(events)
    assert all("chain-of-thought" not in str(event).lower() for event in events)


def test_no_tool_reply_still_has_ack_thinking_and_final(client):
    events = run_agent(client, new_conversation(client), "你好")
    assert [event["type"] for event in events[:2]] == ["ack", "thinking"]
    assert any(
        event["type"] == "message_delta"
        and event["phase"] == "FINAL_RESPONSE"
        for event in events
    )


def test_tool_failure_has_safe_progress_and_final_reply(client):
    events = run_agent(
        client,
        new_conversation(client),
        "订单 ORD-999999-0000 物流到哪了？",
    )
    failed_tool = next(
        event
        for event in events
        if event["type"] == "tool_completed"
        and event["payload"]["status"] == "failed"
    )
    assert failed_tool["phase"] == "TOOL_RESULT"
    assert failed_tool["payload"]["message"] == "工具未完成，已安全停止处理。"
    final = next(
        event
        for event in events
        if event["type"] == "message_delta"
        and event["phase"] == "FINAL_RESPONSE"
    )
    assert "已安全停止处理" in final["payload"]["delta"]


def test_deterministic_stream_yields_progress_before_sync_tools(db):
    customer = resolve_customer(db, "demo-linmu-session")
    conversation = create_conversation(db, customer)
    events = DeterministicSupportAgent(db, customer).stream(
        conversation.id,
        "订单 ORD-20260828-1042 物流到哪了？",
        trace_id="stream-progress-trace",
    )

    first = next(events)
    second = next(events)
    assert first.type.value == "ack"
    assert second.type.value == "thinking"
    assert (
        db.scalar(
            select(ToolInvocation).where(
                ToolInvocation.conversation_id == conversation.id
            )
        )
        is None
    )
    assert list(events)


def test_demo_reset_restores_repeatable_state(client):
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "ORD-20260828-1042 不想要了，申请退款")
    refund_id = next(
        event["refund_request_id"] for event in events if event["type"] == "approval_required"
    )
    client.post(
        f"/api/agent/refund-requests/{refund_id}/approve",
        headers={
            "X-Agent-Session": AGENT_SESSION_TOKEN,
            "Idempotency-Key": "reset-approval-key",
        },
    )
    client.post(
        f"/api/refund-requests/{refund_id}/confirm", headers={"Idempotency-Key": "reset-key"}
    )
    assert client.get("/api/orders/ORD-20260828-1042").json()["refundable_amount"] == "0.00"
    response = client.post("/api/demo/reset")
    assert response.json()["status"] == "reset"
    assert client.get("/api/orders/ORD-20260828-1042").json()["refundable_amount"] == "329.00"
