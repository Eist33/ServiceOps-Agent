import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from serviceops.models import ModelInvocation, OperationsAlertAcknowledgement, Ticket
from serviceops.seed import AGENT_SESSION_TOKEN, OPS_SESSION_TOKEN

OPS_HEADERS = {"X-Ops-Session": OPS_SESSION_TOKEN}
AGENT_HEADERS = {"X-Agent-Session": AGENT_SESSION_TOKEN}


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

    quality = client.get("/api/ops/quality-reviews")
    assert quality.status_code == 403

    alerts = client.get("/api/ops/alerts")
    assert alerts.status_code == 403

    stream = client.get("/api/ops/alerts/stream?once=true")
    assert stream.status_code == 403

    acknowledge = client.post(
        "/api/ops/alerts/missing/HANDOFF_QUEUED/acknowledge"
    )
    assert acknowledge.status_code == 403


def test_empty_dashboard_reports_fixed_knowledge_and_seven_day_window(client):
    response = client.get("/api/ops/dashboard", headers=OPS_HEADERS)

    assert response.status_code == 200
    dashboard = response.json()
    assert dashboard["tickets"]["total"] == 0
    assert dashboard["refunds"]["total"] == 0
    assert dashboard["tools"]["total"] == 0
    assert dashboard["models"] == {
        "window_hours": 24,
        "total": 0,
        "succeeded": 0,
        "failed": 0,
        "fallback": 0,
        "success_rate": 0.0,
        "average_duration_ms": 0.0,
        "p95_duration_ms": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    assert dashboard["recent_model_invocations"] == []
    assert dashboard["knowledge"] == {"active": 12, "historical": 0, "versions": 1}
    assert len(dashboard["activity"]) == 7
    assert dashboard["recent_tickets"] == []

    quality = client.get("/api/ops/quality-reviews", headers=OPS_HEADERS)
    assert quality.status_code == 200
    assert quality.json() == {
        "generated_at": quality.json()["generated_at"],
        "total": 0,
        "excellent": 0,
        "qualified": 0,
        "attention": 0,
        "average_score": 0.0,
        "feedback_received": 0,
        "low_ratings": 0,
        "average_customer_rating": 0.0,
        "items": [],
    }


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


def test_dashboard_aggregates_recent_model_reliability_and_tokens(client, db):
    conversation_id = _start_conversation(client)
    now = datetime.now(UTC)
    db.add_all(
        [
            ModelInvocation(
                trace_id="model-success-fast",
                conversation_id=conversation_id,
                message_id="message-success-fast",
                provider="deepseek",
                model_name="deepseek-v4-flash",
                api_style="responses",
                status="SUCCEEDED",
                duration_ms=100,
                input_tokens=30,
                output_tokens=20,
                total_tokens=50,
                created_at=now - timedelta(minutes=3),
            ),
            ModelInvocation(
                trace_id="model-success-slow",
                conversation_id=conversation_id,
                message_id="message-success-slow",
                provider="deepseek",
                model_name="deepseek-v4-flash",
                api_style="responses",
                status="SUCCEEDED",
                duration_ms=300,
                input_tokens=40,
                output_tokens=30,
                total_tokens=70,
                created_at=now - timedelta(minutes=2),
            ),
            ModelInvocation(
                trace_id="model-timeout",
                conversation_id=conversation_id,
                message_id="message-timeout",
                provider="deepseek",
                model_name="deepseek-v4-flash",
                api_style="responses",
                status="FAILED",
                duration_ms=500,
                error_type="MODEL_TIMEOUT",
                fallback_used=True,
                created_at=now - timedelta(minutes=1),
            ),
            ModelInvocation(
                trace_id="model-old",
                conversation_id=conversation_id,
                message_id="message-old",
                provider="deepseek",
                model_name="deepseek-v4-flash",
                api_style="responses",
                status="FAILED",
                duration_ms=900,
                error_type="MODEL_CONNECTION_ERROR",
                created_at=now - timedelta(hours=25),
            ),
        ]
    )
    db.commit()

    response = client.get("/api/ops/dashboard", headers=OPS_HEADERS)

    assert response.status_code == 200
    dashboard = response.json()
    assert dashboard["models"] == {
        "window_hours": 24,
        "total": 3,
        "succeeded": 2,
        "failed": 1,
        "fallback": 1,
        "success_rate": 66.7,
        "average_duration_ms": 300.0,
        "p95_duration_ms": 500,
        "input_tokens": 70,
        "output_tokens": 50,
        "total_tokens": 120,
    }
    recent = dashboard["recent_model_invocations"]
    assert [item["status"] for item in recent] == [
        "FAILED",
        "SUCCEEDED",
        "SUCCEEDED",
    ]
    assert recent[0]["error_type"] == "MODEL_TIMEOUT"
    assert recent[0]["fallback_used"] is True


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


def test_operations_alerts_prioritize_sla_and_close_accepted_queue(client, db):
    conversation_id = _start_conversation(client)
    created = {}
    for ticket_type, reason in [
        ("SHIPPING", "物流停滞"),
        ("ORDER", "订单信息异常"),
        ("REFUND", "退款审核异常"),
        ("OTHER", "其他售后问题"),
    ]:
        response = client.post(
            "/api/tickets",
            json={
                "conversation_id": conversation_id,
                "order_number": "ORD-20260828-1042",
                "ticket_type": ticket_type,
                "reason": reason,
            },
        )
        assert response.status_code == 200
        created[ticket_type] = response.json()

    due_soon_id = created["SHIPPING"]["id"]
    queued_id = created["OTHER"]["id"]
    assert client.post(f"/api/tickets/{due_soon_id}/handoff").status_code == 200
    assert client.post(f"/api/tickets/{queued_id}/handoff").status_code == 200
    due_soon = db.get(Ticket, due_soon_id)
    breached = db.get(Ticket, created["REFUND"]["id"])
    assert due_soon is not None and breached is not None
    due_soon.sla_due_at = datetime.now(UTC) + timedelta(minutes=30)
    breached.sla_due_at = datetime.now(UTC) - timedelta(minutes=5)
    db.commit()

    response = client.get("/api/ops/alerts", headers=OPS_HEADERS)
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["total"] == 3
    assert snapshot["unacknowledged"] == 3
    assert snapshot["critical"] == 1
    assert snapshot["high"] == 1
    assert snapshot["medium"] == 1
    assert [item["type"] for item in snapshot["items"]] == [
        "SLA_BREACHED",
        "SLA_DUE_SOON",
        "HANDOFF_QUEUED",
    ]
    assert snapshot["items"][0]["ticket_number"] == created["REFUND"]["ticket_number"]
    assert snapshot["items"][1]["sla_remaining_minutes"] in {29, 30}
    assert snapshot["items"][1]["ticket_id"] == due_soon_id
    assert snapshot["items"][2]["support_group"] == "综合支持组"
    assert snapshot["items"][2]["customer_name"] == "林沐"
    assert snapshot["items"][2]["acknowledged"] is False

    accepted = client.post(
        f"/api/agent/tickets/{queued_id}/accept",
        headers=AGENT_HEADERS,
    )
    assert accepted.status_code == 200
    after_accept = client.get("/api/ops/alerts", headers=OPS_HEADERS).json()
    assert after_accept["total"] == 2
    assert queued_id not in {item["ticket_id"] for item in after_accept["items"]}


def test_quality_report_scores_only_resolved_human_tickets(client, db):
    def create_human_ticket(*, complete: bool) -> dict:
        conversation_id = _start_conversation(client)
        ticket = client.post(
            "/api/tickets",
            json={
                "conversation_id": conversation_id,
                "order_number": "ORD-20260828-1042",
                "ticket_type": "SHIPPING",
                "reason": "物流停滞，需要人工核查",
            },
        ).json()
        assert client.post(f"/api/tickets/{ticket['id']}/handoff").status_code == 200
        assert (
            client.post(
                f"/api/agent/tickets/{ticket['id']}/accept",
                headers=AGENT_HEADERS,
            ).status_code
            == 200
        )
        if complete:
            assert (
                client.post(
                    f"/api/agent/tickets/{ticket['id']}/messages",
                    headers=AGENT_HEADERS,
                    json={"content": "已联系承运商，正在核查转运进度。"},
                ).status_code
                == 200
            )
            assert (
                client.post(
                    f"/api/agent/tickets/{ticket['id']}/notes",
                    headers=AGENT_HEADERS,
                    json={"content": "承运商确认今晚恢复转运。"},
                ).status_code
                == 200
            )
        else:
            db.expire_all()
            stored = db.get(Ticket, ticket["id"])
            assert stored is not None
            stored.sla_due_at = datetime.now(UTC) - timedelta(minutes=5)
            db.commit()
        resolution = "承运商已恢复转运，客户接受继续等待。" if complete else "已处理"
        response = client.post(
            f"/api/agent/tickets/{ticket['id']}/resolve",
            headers=AGENT_HEADERS,
            json={"resolution": resolution},
        )
        assert response.status_code == 200
        return ticket

    complete = create_human_ticket(complete=True)
    incomplete = create_human_ticket(complete=False)
    assert (
        client.post(
            f"/api/tickets/{complete['id']}/feedback",
            json={"rating": 5, "comment": "处理及时，方案清楚。"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/tickets/{incomplete['id']}/feedback",
            json={"rating": 2, "comment": "没有及时同步进展。"},
        ).status_code
        == 200
    )

    response = client.get("/api/ops/quality-reviews", headers=OPS_HEADERS)
    assert response.status_code == 200
    report = response.json()
    assert report["total"] == 2
    assert report["excellent"] == 1
    assert report["qualified"] == 0
    assert report["attention"] == 1
    assert report["average_score"] == 50.0
    assert report["feedback_received"] == 2
    assert report["low_ratings"] == 1
    assert report["average_customer_rating"] == 3.5

    by_ticket = {item["ticket_id"]: item for item in report["items"]}
    excellent = by_ticket[complete["id"]]
    assert excellent["score"] == 100
    assert excellent["grade"] == "EXCELLENT"
    assert excellent["assignee_name"] == "沈清禾"
    assert excellent["customer_name"] == "林沐"
    assert excellent["customer_rating"] == 5
    assert excellent["customer_comment"] == "处理及时，方案清楚。"
    assert excellent["feedback_submitted_at"] is not None
    assert all(check["passed"] for check in excellent["checks"])

    attention = by_ticket[incomplete["id"]]
    assert attention["score"] == 0
    assert attention["grade"] == "ATTENTION"
    assert [check["key"] for check in attention["checks"] if not check["passed"]] == [
        "sla_met",
        "first_reply_timely",
        "internal_note_present",
        "resolution_complete",
    ]


def test_operations_alert_acknowledgement_is_durable_idempotent_and_state_scoped(
    client,
    db,
):
    conversation_id = _start_conversation(client)
    ticket = client.post(
        "/api/tickets",
        json={
            "conversation_id": conversation_id,
            "order_number": "ORD-20260828-1042",
            "ticket_type": "SHIPPING",
            "reason": "物流停滞",
        },
    ).json()
    ticket_id = ticket["id"]
    client.post(f"/api/tickets/{ticket_id}/handoff")
    acknowledge_url = (
        f"/api/ops/alerts/{ticket_id}/HANDOFF_QUEUED/acknowledge"
    )

    first = client.post(acknowledge_url, headers=OPS_HEADERS)
    assert first.status_code == 200
    acknowledgement = first.json()
    assert acknowledgement["ticket_id"] == ticket_id
    assert acknowledgement["alert_type"] == "HANDOFF_QUEUED"
    assert acknowledgement["acknowledged_by"] == "许知夏"

    repeated = client.post(acknowledge_url, headers=OPS_HEADERS)
    assert repeated.status_code == 200
    assert repeated.json()["id"] == acknowledgement["id"]
    db.expire_all()
    stored = list(db.scalars(select(OperationsAlertAcknowledgement)))
    assert len(stored) == 1

    snapshot = client.get("/api/ops/alerts", headers=OPS_HEADERS).json()
    assert snapshot["unacknowledged"] == 0
    assert snapshot["items"][0]["acknowledged"] is True
    assert snapshot["items"][0]["acknowledged_by"] == "许知夏"
    assert snapshot["items"][0]["acknowledged_at"] is not None

    current_ticket = db.get(Ticket, ticket_id)
    assert current_ticket is not None
    current_ticket.sla_due_at = datetime.now(UTC) + timedelta(minutes=30)
    db.commit()
    upgraded = client.get("/api/ops/alerts", headers=OPS_HEADERS).json()
    assert upgraded["unacknowledged"] == 1
    assert upgraded["items"][0]["type"] == "SLA_DUE_SOON"
    assert upgraded["items"][0]["acknowledged"] is False

    stale = client.post(acknowledge_url, headers=OPS_HEADERS)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "ALERT_NOT_ACTIVE"
    invalid = client.post(
        f"/api/ops/alerts/{ticket_id}/UNKNOWN/acknowledge",
        headers=OPS_HEADERS,
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_ALERT_TYPE"


def test_operations_alert_stream_returns_protected_snapshot(client):
    conversation_id = _start_conversation(client)
    ticket = client.post(
        "/api/tickets",
        json={
            "conversation_id": conversation_id,
            "order_number": "ORD-20260828-1042",
            "ticket_type": "SHIPPING",
            "reason": "物流停滞",
        },
    ).json()
    client.post(f"/api/tickets/{ticket['id']}/handoff")

    response = client.get(
        "/api/ops/alerts/stream?once=true",
        headers=OPS_HEADERS,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    event = json.loads(response.text.strip())
    assert event["type"] == "operations_alert_snapshot"
    assert event["snapshot"]["total"] == 1
    assert event["snapshot"]["items"][0]["ticket_id"] == ticket["id"]
    assert event["snapshot"]["items"][0]["type"] == "HANDOFF_QUEUED"
