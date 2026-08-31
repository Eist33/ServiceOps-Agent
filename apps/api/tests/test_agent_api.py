import json


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


def test_policy_flow_emits_source_tool_events(client):
    events = run_agent(client, new_conversation(client), "退货需要几天？")
    assert event_types(events)[0] == "tool_started"
    assert "tool_completed" in event_types(events)
    assert "message_delta" in event_types(events)
    completed = next(event for event in events if event["type"] == "tool_completed")
    assert completed["payload"]["tool_name"] == "search_knowledge_base"


def test_shipping_flow_uses_order_and_shipping_tools(client):
    events = run_agent(client, new_conversation(client), "订单 ORD-20260828-1042 物流到哪了？")
    tools = [event["payload"]["tool_name"] for event in events if event["type"] == "tool_completed"]
    assert tools == ["get_order", "get_shipping_status"]


def test_ticket_flow_changes_business_state(client):
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "ORD-20260828-1042 物流没更新，帮我催一下")
    assert "business_state_changed" in event_types(events)
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["tickets"][0]["status"] == "OPEN"
    assert state["tickets"][0]["priority"] == "P2"
    assert state["tickets"][0]["sla_status"] == "ON_TRACK"


def test_reused_ticket_is_projected_into_new_conversation(client):
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
    assert second_state["tickets"][0]["id"] == first_ticket["id"]
    assert second_state["tickets"][0]["ticket_number"] == first_ticket["ticket_number"]
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


def test_refund_flow_requires_approval(client):
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "订单 ORD-20260828-1042 不想要了，申请退款")
    approval = next(event for event in events if event["type"] == "approval_required")
    assert approval["payload"]["amount"] == "329.00"
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["refunds"][0]["status"] == "PENDING_CONFIRMATION"


def test_refund_api_is_idempotent(client):
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "ORD-20260828-1042 申请退款")
    refund_id = next(
        event["refund_request_id"] for event in events if event["type"] == "approval_required"
    )
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
    events = run_agent(client, conversation_id, "ORD-20260828-1042 申请退款")
    refund_id = next(
        event["refund_request_id"] for event in events if event["type"] == "approval_required"
    )
    response = client.post(f"/api/refund-requests/{refund_id}/confirm")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_IDEMPOTENCY_KEY"


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


def test_demo_reset_restores_repeatable_state(client):
    conversation_id = new_conversation(client)
    events = run_agent(client, conversation_id, "ORD-20260828-1042 申请退款")
    refund_id = next(
        event["refund_request_id"] for event in events if event["type"] == "approval_required"
    )
    client.post(
        f"/api/refund-requests/{refund_id}/confirm", headers={"Idempotency-Key": "reset-key"}
    )
    assert client.get("/api/orders/ORD-20260828-1042").json()["refundable_amount"] == "0.00"
    response = client.post("/api/demo/reset")
    assert response.json()["status"] == "reset"
    assert client.get("/api/orders/ORD-20260828-1042").json()["refundable_amount"] == "329.00"
