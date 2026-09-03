from datetime import UTC, datetime, timedelta

from serviceops.models import Ticket
from serviceops.seed import OPS_SESSION_TOKEN

OPS_HEADERS = {"X-Ops-Session": OPS_SESSION_TOKEN}


def _start_conversation(client) -> str:
    response = client.post("/api/conversations")
    assert response.status_code == 200
    return response.json()["id"]


def _run_agent(client, conversation_id: str, content: str) -> None:
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": content},
    )
    assert response.status_code == 200


def test_operations_dashboard_requires_operator_identity(client):
    response = client.get("/api/ops/dashboard")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"

    report = client.get("/api/ops/tickets")
    assert report.status_code == 403


def test_empty_dashboard_reports_fixed_knowledge_and_seven_day_window(client):
    response = client.get("/api/ops/dashboard", headers=OPS_HEADERS)

    assert response.status_code == 200
    dashboard = response.json()
    assert dashboard["tickets"]["total"] == 0
    assert dashboard["refunds"]["total"] == 0
    assert dashboard["tools"]["total"] == 0
    assert dashboard["knowledge"] == {"active": 12, "historical": 0, "versions": 1}
    assert len(dashboard["activity"]) == 7
    assert dashboard["recent_tickets"] == []


def test_dashboard_aggregates_ticket_handoff_sla_and_tool_health(client):
    conversation_id = _start_conversation(client)
    _run_agent(
        client,
        conversation_id,
        "ORD-20260828-1042 物流两天没更新，帮我创建工单",
    )
    state = client.get(f"/api/conversations/{conversation_id}").json()
    ticket_id = state["tickets"][0]["id"]
    handoff = client.post(f"/api/tickets/{ticket_id}/handoff")
    assert handoff.status_code == 200

    response = client.get("/api/ops/dashboard", headers=OPS_HEADERS)

    assert response.status_code == 200
    dashboard = response.json()
    assert dashboard["tickets"]["total"] == 1
    assert dashboard["tickets"]["active"] == 1
    assert dashboard["tickets"]["assigned"] == 1
    assert dashboard["tools"]["total"] == 3
    assert dashboard["tools"]["success_rate"] == 100.0
    assert dashboard["ticket_types"][0] == {
        "type": "SHIPPING",
        "label": "物流异常",
        "count": 1,
    }
    assert dashboard["recent_tickets"][0]["assignee_name"] == "物流专员组"
    assert dashboard["recent_tickets"][0]["sla_status"] == "ON_TRACK"
    assert [item["tool_name"] for item in dashboard["recent_tools"]] == [
        "create_ticket",
        "get_shipping_status",
        "get_order",
    ]


def test_ticket_report_filters_by_support_group_and_sla(client, db):
    shipping_conversation = _start_conversation(client)
    shipping = client.post(
        "/api/tickets",
        json={
            "conversation_id": shipping_conversation,
            "order_number": "ORD-20260828-1042",
            "ticket_type": "SHIPPING",
            "reason": "物流停滞",
        },
    ).json()
    other_conversation = _start_conversation(client)
    other = client.post(
        "/api/tickets",
        json={
            "conversation_id": other_conversation,
            "order_number": "ORD-20260828-1042",
            "ticket_type": "OTHER",
            "reason": "其他售后问题",
        },
    ).json()

    shipping_ticket = db.get(Ticket, shipping["id"])
    assert shipping_ticket is not None
    shipping_ticket.sla_due_at = datetime.now(UTC) - timedelta(minutes=5)
    db.commit()

    all_tickets = client.get("/api/ops/tickets", headers=OPS_HEADERS)
    assert all_tickets.status_code == 200
    report = all_tickets.json()
    assert report["total"] == 2
    assert report["risk"] == 1
    assert report["breached"] == 1
    assert report["available_support_groups"] == [
        "物流专员组",
        "订单支持组",
        "退款审核组",
        "综合支持组",
    ]

    shipping_group = client.get(
        "/api/ops/tickets",
        headers=OPS_HEADERS,
        params={"support_group": "物流专员组"},
    ).json()
    assert shipping_group["total"] == 1
    assert shipping_group["items"][0]["ticket_number"] == shipping["ticket_number"]
    assert shipping_group["items"][0]["customer_name"] == "林沐"
    assert shipping_group["items"][0]["sla_status"] == "BREACHED"

    risk = client.get(
        "/api/ops/tickets",
        headers=OPS_HEADERS,
        params={"sla_status": "RISK"},
    ).json()
    assert [item["id"] for item in risk["items"]] == [shipping["id"]]

    no_match = client.get(
        "/api/ops/tickets",
        headers=OPS_HEADERS,
        params={"support_group": "综合支持组", "sla_status": "RISK"},
    ).json()
    assert no_match["total"] == 0
    assert other["id"] not in {item["id"] for item in no_match["items"]}

    invalid = client.get(
        "/api/ops/tickets",
        headers=OPS_HEADERS,
        params={"sla_status": "UNKNOWN"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_SLA_STATUS"
