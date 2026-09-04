from sqlalchemy import select

from serviceops.models import CustomerSatisfactionFeedback, TicketEvent
from serviceops.seed import AGENT_SESSION_TOKEN

AGENT_HEADERS = {"X-Agent-Session": AGENT_SESSION_TOKEN}


def _create_ticket(client) -> tuple[str, str]:
    conversation = client.post("/api/conversations").json()
    ticket = client.post(
        "/api/tickets",
        json={
            "conversation_id": conversation["id"],
            "order_number": "ORD-20260828-1042",
            "ticket_type": "SHIPPING",
            "reason": "物流停滞，需要人工核查",
        },
    ).json()
    return conversation["id"], ticket["id"]


def _resolve_with_agent(client, ticket_id: str) -> None:
    assert client.post(f"/api/tickets/{ticket_id}/handoff").status_code == 200
    assert (
        client.post(
            f"/api/agent/tickets/{ticket_id}/accept",
            headers=AGENT_HEADERS,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/agent/tickets/{ticket_id}/resolve",
            headers=AGENT_HEADERS,
            json={"resolution": "承运商已恢复转运，客户接受继续等待。"},
        ).status_code
        == 200
    )


def test_feedback_requires_ticket_owner_and_resolved_state(client, other_client):
    _, ticket_id = _create_ticket(client)

    pending = client.post(
        f"/api/tickets/{ticket_id}/feedback",
        json={"rating": 5, "comment": "处理很及时"},
    )
    assert pending.status_code == 409
    assert pending.json()["error"]["code"] == "TICKET_NOT_RESOLVED"

    forbidden = other_client.post(
        f"/api/tickets/{ticket_id}/feedback",
        json={"rating": 5},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"


def test_feedback_is_durable_visible_and_idempotent(client, db):
    conversation_id, ticket_id = _create_ticket(client)
    _resolve_with_agent(client, ticket_id)

    invalid = client.post(
        f"/api/tickets/{ticket_id}/feedback",
        json={"rating": 6},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    submitted = client.post(
        f"/api/tickets/{ticket_id}/feedback",
        json={"rating": 5, "comment": "  回复及时，处理结果清楚。  "},
    )
    assert submitted.status_code == 200
    feedback = submitted.json()
    assert feedback["ticket_id"] == ticket_id
    assert feedback["rating"] == 5
    assert feedback["comment"] == "回复及时，处理结果清楚。"

    repeated = client.post(
        f"/api/tickets/{ticket_id}/feedback",
        json={"rating": 5, "comment": "回复及时，处理结果清楚。"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == feedback["id"]

    changed = client.post(
        f"/api/tickets/{ticket_id}/feedback",
        json={"rating": 4, "comment": "回复及时，处理结果清楚。"},
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "FEEDBACK_ALREADY_SUBMITTED"

    detail = client.get(f"/api/tickets/{ticket_id}").json()
    assert detail["feedback"] == feedback
    conversation = client.get(f"/api/conversations/{conversation_id}").json()
    assert conversation["tickets"][0]["feedback"] == feedback

    db.expire_all()
    assert len(list(db.scalars(select(CustomerSatisfactionFeedback)))) == 1
    feedback_events = list(
        db.scalars(
            select(TicketEvent).where(
                TicketEvent.ticket_id == ticket_id,
                TicketEvent.action == "CUSTOMER_FEEDBACK_SUBMITTED",
            )
        )
    )
    assert len(feedback_events) == 1
    assert feedback_events[0].detail == "客户提交 5 星满意度评价"
