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
