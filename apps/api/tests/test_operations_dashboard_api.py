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
