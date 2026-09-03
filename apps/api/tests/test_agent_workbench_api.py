import json

from serviceops.seed import (
    AGENT_SESSION_TOKEN,
    OPS_SESSION_TOKEN,
    SECOND_AGENT_SESSION_TOKEN,
)

AGENT_HEADERS = {"X-Agent-Session": AGENT_SESSION_TOKEN}
SECOND_AGENT_HEADERS = {"X-Agent-Session": SECOND_AGENT_SESSION_TOKEN}


def _create_handed_off_ticket(client) -> str:
    conversation_id = client.post("/api/conversations").json()["id"]
    created = client.post(
        "/api/tickets",
        json={
            "conversation_id": conversation_id,
            "order_number": "ORD-20260828-1042",
            "ticket_type": "SHIPPING",
            "reason": "物流停滞，需要人工联系承运商",
        },
    )
    assert created.status_code == 200
    ticket_id = created.json()["id"]
    handed_off = client.post(f"/api/tickets/{ticket_id}/handoff")
    assert handed_off.status_code == 200
    return ticket_id


def test_agent_queue_requires_support_agent_identity(client):
    missing = client.get("/api/agent/tickets")
    assert missing.status_code == 403

    wrong_role = client.get(
        "/api/agent/tickets",
        headers={"X-Agent-Session": OPS_SESSION_TOKEN},
    )
    assert wrong_role.status_code == 403

    profile = client.get("/api/agent/me", headers=AGENT_HEADERS)
    assert profile.status_code == 200
    assert profile.json() == {
        "id": profile.json()["id"],
        "name": "沈清禾",
        "role": "SUPPORT_AGENT",
    }

    second_profile = client.get("/api/agent/me", headers=SECOND_AGENT_HEADERS)
    assert second_profile.status_code == 200
    assert second_profile.json()["name"] == "陆川"
    assert second_profile.json()["role"] == "SUPPORT_AGENT"


def test_agent_queue_stream_requires_identity_and_returns_snapshot(client):
    missing = client.get("/api/agent/tickets/stream?once=true")
    assert missing.status_code == 403

    wrong_role = client.get(
        "/api/agent/tickets/stream?once=true",
        headers={"X-Agent-Session": OPS_SESSION_TOKEN},
    )
    assert wrong_role.status_code == 403

    ticket_id = _create_handed_off_ticket(client)
    response = client.get(
        "/api/agent/tickets/stream?once=true",
        headers=AGENT_HEADERS,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    event = json.loads(response.text.strip())
    assert event["type"] == "ticket_queue_snapshot"
    assert event["tickets"][0]["id"] == ticket_id
    assert event["tickets"][0]["work_state"] == "QUEUED"


def test_customer_and_assignee_exchange_visible_ticket_messages(client, other_client):
    conversation_id = client.post("/api/conversations").json()["id"]
    ticket = client.post(
        "/api/tickets",
        json={
            "conversation_id": conversation_id,
            "order_number": "ORD-20260828-1042",
            "ticket_type": "SHIPPING",
            "reason": "物流停滞，需要人工联系承运商",
        },
    ).json()

    before_handoff = client.post(
        f"/api/tickets/{ticket['id']}/messages",
        json={"content": "有人处理吗？"},
    )
    assert before_handoff.status_code == 409
    assert before_handoff.json()["error"]["code"] == "TICKET_NOT_HANDED_OFF"

    client.post(f"/api/tickets/{ticket['id']}/handoff")
    forbidden_customer = other_client.post(
        f"/api/tickets/{ticket['id']}/messages",
        json={"content": "尝试访问他人工单"},
    )
    assert forbidden_customer.status_code == 403

    customer_message = client.post(
        f"/api/tickets/{ticket['id']}/messages",
        json={"content": "请问今晚可以恢复转运吗？"},
    )
    assert customer_message.status_code == 200
    assert customer_message.json()["messages"] == [
        {
            "id": customer_message.json()["messages"][0]["id"],
            "sender_role": "CUSTOMER",
            "sender_name": "林沐",
            "content": "请问今晚可以恢复转运吗？",
            "created_at": customer_message.json()["messages"][0]["created_at"],
        }
    ]

    accepted = client.post(
        f"/api/agent/tickets/{ticket['id']}/accept",
        headers=AGENT_HEADERS,
    )
    assert accepted.status_code == 200
    assert accepted.json()["messages"][0]["sender_role"] == "CUSTOMER"

    wrong_agent = client.post(
        f"/api/agent/tickets/{ticket['id']}/messages",
        headers=SECOND_AGENT_HEADERS,
        json={"content": "尝试回复其他坐席工单"},
    )
    assert wrong_agent.status_code == 409
    assert wrong_agent.json()["error"]["code"] == "TICKET_NOT_ACCEPTED"

    reply = client.post(
        f"/api/agent/tickets/{ticket['id']}/messages",
        headers=AGENT_HEADERS,
        json={"content": "已联系承运商，预计今晚恢复转运。"},
    )
    assert reply.status_code == 200
    assert [message["sender_role"] for message in reply.json()["messages"]] == [
        "CUSTOMER",
        "SUPPORT_AGENT",
    ]

    client.post(
        f"/api/agent/tickets/{ticket['id']}/notes",
        headers=AGENT_HEADERS,
        json={"content": "内部备注：明早再次检查轨迹。"},
    )
    customer_detail = client.get(f"/api/tickets/{ticket['id']}").json()
    assert customer_detail["messages"][1]["sender_name"] == "沈清禾"
    assert customer_detail["messages"][1]["content"] == (
        "已联系承运商，预计今晚恢复转运。"
    )
    assert "内部备注" not in str(customer_detail["messages"])
    conversation_state = client.get(f"/api/conversations/{conversation_id}").json()
    assert conversation_state["tickets"][0]["messages"] == customer_detail["messages"]


def test_agent_can_accept_note_and_resolve_handed_off_ticket(client):
    ticket_id = _create_handed_off_ticket(client)

    queue = client.get("/api/agent/tickets", headers=AGENT_HEADERS)
    assert queue.status_code == 200
    queued = queue.json()[0]
    assert queued["id"] == ticket_id
    assert queued["work_state"] == "QUEUED"
    assert queued["support_group"] == "物流专员组"
    assert queued["customer_name"] == "林沐"
    assert queued["order_number"] == "ORD-20260828-1042"
    assert queued["is_mine"] is False

    premature_note = client.post(
        f"/api/agent/tickets/{ticket_id}/notes",
        headers=AGENT_HEADERS,
        json={"content": "尚未受理"},
    )
    assert premature_note.status_code == 409
    assert premature_note.json()["error"]["code"] == "TICKET_NOT_ACCEPTED"

    accepted = client.post(
        f"/api/agent/tickets/{ticket_id}/accept",
        headers=AGENT_HEADERS,
    )
    assert accepted.status_code == 200
    in_progress = accepted.json()
    assert in_progress["work_state"] == "IN_PROGRESS"
    assert in_progress["assignee_name"] == "沈清禾"
    assert in_progress["is_mine"] is True
    assert in_progress["events"][-1]["action"] == "HUMAN_HANDOFF_ACCEPTED"

    repeated = client.post(
        f"/api/agent/tickets/{ticket_id}/accept",
        headers=AGENT_HEADERS,
    )
    assert repeated.status_code == 200
    assert repeated.json()["version"] == in_progress["version"]

    noted = client.post(
        f"/api/agent/tickets/{ticket_id}/notes",
        headers=AGENT_HEADERS,
        json={"content": "已联系承运商，确认包裹将在今晚恢复转运。"},
    )
    assert noted.status_code == 200
    assert noted.json()["events"][-1] == {
        "action": "AGENT_NOTE_ADDED",
        "detail": "已联系承运商，确认包裹将在今晚恢复转运。",
        "actor": "沈清禾",
        "created_at": noted.json()["events"][-1]["created_at"],
    }

    resolved = client.post(
        f"/api/agent/tickets/{ticket_id}/resolve",
        headers=AGENT_HEADERS,
        json={"resolution": "承运商已恢复转运，客户接受继续等待。"},
    )
    assert resolved.status_code == 200
    completed = resolved.json()
    assert completed["status"] == "RESOLVED"
    assert completed["handoff_status"] == "COMPLETED"
    assert completed["work_state"] == "RESOLVED"
    assert completed["events"][-1]["action"] == "STATUS_RESOLVED"

    customer_state = client.get(
        f"/api/conversations/{completed['conversation_id']}"
    )
    assert customer_state.status_code == 200
    customer_ticket = customer_state.json()["tickets"][0]
    assert customer_ticket["resolution"] == {
        "summary": "承运商已恢复转运，客户接受继续等待。",
        "handled_by": "沈清禾",
        "resolved_at": customer_ticket["resolution"]["resolved_at"],
    }

    customer_detail = client.get(f"/api/tickets/{ticket_id}")
    assert customer_detail.status_code == 200
    assert customer_detail.json()["resolution"]["summary"] == (
        "承运商已恢复转运，客户接受继续等待。"
    )
    assert all(
        event["action"] != "AGENT_NOTE_ADDED"
        for event in customer_detail.json()["events"]
    )


def test_only_first_agent_can_claim_and_operate_ticket(client):
    ticket_id = _create_handed_off_ticket(client)

    accepted = client.post(
        f"/api/agent/tickets/{ticket_id}/accept",
        headers=AGENT_HEADERS,
    )
    assert accepted.status_code == 200
    assert accepted.json()["assignee_name"] == "沈清禾"

    conflict = client.post(
        f"/api/agent/tickets/{ticket_id}/accept",
        headers=SECOND_AGENT_HEADERS,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"] == {
        "code": "TICKET_ALREADY_ACCEPTED",
        "message": "工单已由 沈清禾 受理",
    }

    second_queue = client.get("/api/agent/tickets", headers=SECOND_AGENT_HEADERS)
    assert second_queue.status_code == 200
    claimed = next(ticket for ticket in second_queue.json() if ticket["id"] == ticket_id)
    assert claimed["work_state"] == "IN_PROGRESS"
    assert claimed["assignee_name"] == "沈清禾"
    assert claimed["is_mine"] is False

    forbidden_note = client.post(
        f"/api/agent/tickets/{ticket_id}/notes",
        headers=SECOND_AGENT_HEADERS,
        json={"content": "尝试处理其他坐席的工单"},
    )
    assert forbidden_note.status_code == 409
    assert forbidden_note.json()["error"]["code"] == "TICKET_NOT_ACCEPTED"

    forbidden_resolve = client.post(
        f"/api/agent/tickets/{ticket_id}/resolve",
        headers=SECOND_AGENT_HEADERS,
        json={"resolution": "尝试解决其他坐席的工单"},
    )
    assert forbidden_resolve.status_code == 409
    assert forbidden_resolve.json()["error"]["code"] == "TICKET_NOT_ACCEPTED"


def test_agent_actions_validate_current_work_state(client):
    ticket_id = _create_handed_off_ticket(client)
    blank_note = client.post(
        f"/api/agent/tickets/{ticket_id}/notes",
        headers=AGENT_HEADERS,
        json={"content": "   "},
    )
    assert blank_note.status_code == 409

    client.post(f"/api/agent/tickets/{ticket_id}/accept", headers=AGENT_HEADERS)
    blank_resolution = client.post(
        f"/api/agent/tickets/{ticket_id}/resolve",
        headers=AGENT_HEADERS,
        json={"resolution": "   "},
    )
    assert blank_resolution.status_code == 422
    assert blank_resolution.json()["error"]["code"] == "EMPTY_RESOLUTION"
