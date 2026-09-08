from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import ceil

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from serviceops.models import (
    Conversation,
    ConversationIntentEvent,
    Customer,
    CustomerSatisfactionFeedback,
    HandoffStatus,
    IdempotencyRecord,
    KnowledgeArticle,
    Message,
    ModelInvocation,
    OperationsAlertAcknowledgement,
    Operator,
    Order,
    RefundApprovalAudit,
    RefundRequest,
    RefundStatus,
    SecurityAuditEvent,
    Ticket,
    TicketEvent,
    TicketStatus,
    ToolInvocation,
)
from serviceops.seed import DEMO_INITIAL_ORDER_STATUSES, reset_demo_state
from serviceops.shared.errors import ConflictError, NotFoundError, ValidationError
from serviceops.shared.schemas import (
    OpsAlertAcknowledgementResponse,
    OpsAlertSnapshotResponse,
    OpsDashboardResponse,
    OpsOrderReportResponse,
    OpsQualityReportResponse,
    OpsTicketReportResponse,
)
from serviceops.tickets.service import TICKET_ROUTING, ticket_sla

TICKET_TYPE_LABELS = {
    "SHIPPING": "物流异常",
    "ORDER": "订单问题",
    "REFUND": "退款申请",
    "OTHER": "其他售后",
}

SLA_FILTERS = {"ON_TRACK", "DUE_SOON", "BREACHED", "COMPLETED", "RISK"}
ALERT_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
ALERT_TYPES = {"SLA_BREACHED", "SLA_DUE_SOON", "HANDOFF_QUEUED"}
QUALITY_FIRST_REPLY_MINUTES = 30
MODEL_METRICS_WINDOW_HOURS = 24


def reset_demo_state_after_completed_ticket(
    db: Session,
    operator: Operator,
    ticket_id: str,
):
    """Reset mutable demo data only after an authorized operator completed a ticket."""
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise NotFoundError("工单不存在")
    if ticket.status != TicketStatus.RESOLVED.value or ticket.handoff_status != HandoffStatus.COMPLETED.value:
        raise ConflictError(
            "DEMO_RESET_REQUIRES_COMPLETED_TICKET",
            "只有已完成的人工工单才能清除演示测试数据",
        )
    order = db.get(Order, ticket.order_id)
    if order is None:
        raise NotFoundError("工单关联的订单不存在")

    ticket_number = ticket.ticket_number
    order_number = order.order_number
    reset_demo_state(db)
    db.add(
        SecurityAuditEvent(
            event_type="DEMO_STATE_RESET",
            outcome="SUCCEEDED",
            principal_type="OPERATOR",
            principal_id=operator.id,
        )
    )
    db.commit()
    return {
        "status": "reset",
        "ticket_id": ticket_id,
        "ticket_number": ticket_number,
        "order_number": order_number,
        "operator_name": operator.name,
    }


def _ops_order_item(order: Order, customer_name: str) -> dict:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "customer_name": customer_name,
        "product_name": order.product_name,
        "paid_amount": order.paid_amount,
        "refundable_amount": order.refundable_amount,
        "status": order.status,
        "initial_status": DEMO_INITIAL_ORDER_STATUSES.get(order.order_number, order.status),
        "ordered_at": order.ordered_at,
        "updated_at": order.updated_at,
    }


def operations_orders(db: Session) -> OpsOrderReportResponse:
    rows = db.execute(
        select(Order, Customer.name)
        .join(Customer, Customer.id == Order.customer_id)
        .order_by(Order.ordered_at.desc(), Order.order_number.desc())
    ).all()
    return OpsOrderReportResponse(
        generated_at=datetime.now(UTC),
        total=len(rows),
        items=[_ops_order_item(order, customer_name) for order, customer_name in rows],
    )


def reset_operations_order(
    db: Session,
    operator: Operator,
    order_id: str,
) -> dict:
    order = db.get(Order, order_id)
    if order is None:
        raise NotFoundError("订单不存在")
    initial_status = DEMO_INITIAL_ORDER_STATUSES.get(order.order_number)
    if initial_status is None:
        raise ConflictError(
            "ORDER_RESET_UNSUPPORTED",
            "该订单没有固定的演示初始状态，不能从运营页面重置",
        )
    customer = db.get(Customer, order.customer_id)
    if customer is None:
        raise NotFoundError("订单关联的客户不存在")

    ticket_ids = list(
        db.scalars(select(Ticket.id).where(Ticket.order_id == order.id))
    )
    refund_ids = list(
        db.scalars(select(RefundRequest.id).where(RefundRequest.order_id == order.id))
    )
    conversation_ids = set(
        db.scalars(
            select(Conversation.id).where(Conversation.active_order_id == order.id)
        )
    )
    conversation_ids.update(
        db.scalars(
            select(Ticket.conversation_id).where(Ticket.order_id == order.id)
        )
    )
    deletable_conversation_ids = [
        conversation_id
        for conversation_id in conversation_ids
        if db.scalar(
            select(Ticket.id)
            .where(
                Ticket.conversation_id == conversation_id,
                Ticket.order_id != order.id,
            )
            .limit(1)
        )
        is None
    ]

    if ticket_ids or refund_ids or deletable_conversation_ids:
        db.execute(
            delete(ConversationIntentEvent).where(
                or_(
                    ConversationIntentEvent.conversation_id.in_(
                        deletable_conversation_ids
                    ),
                    ConversationIntentEvent.source_ticket_id.in_(ticket_ids),
                    ConversationIntentEvent.related_ticket_id.in_(ticket_ids),
                    ConversationIntentEvent.related_refund_id.in_(refund_ids),
                )
            )
        )
        db.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.resource_id.in_(ticket_ids + refund_ids)
            )
        )
        db.execute(
            delete(CustomerSatisfactionFeedback).where(
                CustomerSatisfactionFeedback.ticket_id.in_(ticket_ids)
            )
        )
        db.execute(
            delete(OperationsAlertAcknowledgement).where(
                OperationsAlertAcknowledgement.ticket_id.in_(ticket_ids)
            )
        )
        db.execute(delete(RefundApprovalAudit).where(RefundApprovalAudit.refund_request_id.in_(refund_ids)))
        db.execute(delete(TicketEvent).where(TicketEvent.ticket_id.in_(ticket_ids)))
        db.execute(delete(RefundRequest).where(RefundRequest.id.in_(refund_ids)))
        db.execute(delete(Ticket).where(Ticket.id.in_(ticket_ids)))
        db.execute(
            delete(ToolInvocation).where(
                ToolInvocation.conversation_id.in_(deletable_conversation_ids)
            )
        )
        db.execute(
            delete(ModelInvocation).where(
                ModelInvocation.conversation_id.in_(deletable_conversation_ids)
            )
        )
        db.execute(
            delete(Message).where(Message.conversation_id.in_(deletable_conversation_ids))
        )
        db.execute(
            delete(Conversation).where(Conversation.id.in_(deletable_conversation_ids))
        )

    order.status = initial_status
    order.refundable_amount = order.paid_amount
    order.updated_at = datetime.now(UTC)
    db.add(
        SecurityAuditEvent(
            event_type="DEMO_ORDER_STATE_RESET",
            outcome="SUCCEEDED",
            principal_type="OPERATOR",
            principal_id=operator.id,
        )
    )
    db.commit()
    db.refresh(order)
    return {
        "status": "reset",
        "order": _ops_order_item(order, customer.name),
        "operator_name": operator.name,
        "cleared_ticket_count": len(ticket_ids),
        "cleared_refund_count": len(refund_ids),
    }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _nearest_rank_percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, ceil(percentile * len(ordered)) - 1)]


def operations_dashboard(
    db: Session,
    *,
    now: datetime | None = None,
) -> OpsDashboardResponse:
    current_time = _aware(now or datetime.now(UTC))
    tickets = list(db.scalars(select(Ticket).order_by(Ticket.created_at.desc())))
    refunds = list(
        db.scalars(select(RefundRequest).order_by(RefundRequest.created_at.desc()))
    )
    tools = list(
        db.scalars(select(ToolInvocation).order_by(ToolInvocation.created_at.desc()))
    )
    model_cutoff = current_time - timedelta(hours=MODEL_METRICS_WINDOW_HOURS)
    model_invocations = [
        invocation
        for invocation in db.scalars(
            select(ModelInvocation).order_by(ModelInvocation.created_at.desc())
        )
        if _aware(invocation.created_at) >= model_cutoff
    ]
    articles = list(db.scalars(select(KnowledgeArticle)))

    sla_by_ticket = {ticket.id: ticket_sla(ticket, now=current_time) for ticket in tickets}
    ticket_type_counts = {
        ticket_type: sum(ticket.ticket_type == ticket_type for ticket in tickets)
        for ticket_type in TICKET_TYPE_LABELS
    }
    succeeded_tools = sum(tool.status == "SUCCEEDED" for tool in tools)
    failed_tools = len(tools) - succeeded_tools
    average_duration = sum(tool.duration_ms for tool in tools) / len(tools) if tools else 0
    succeeded_models = sum(
        invocation.status == "SUCCEEDED" for invocation in model_invocations
    )
    model_durations = [invocation.duration_ms for invocation in model_invocations]
    succeeded_refunds = [
        refund for refund in refunds if refund.status == RefundStatus.SUCCEEDED.value
    ]

    order_ids = {ticket.order_id for ticket in tickets}
    orders = (
        list(db.scalars(select(Order).where(Order.id.in_(order_ids)))) if order_ids else []
    )
    order_numbers = {order.id: order.order_number for order in orders}

    days = [current_time.date() - timedelta(days=offset) for offset in range(6, -1, -1)]
    activity = []
    for day in days:
        activity.append(
            {
                "date": day.isoformat(),
                "label": day.strftime("%m-%d"),
                "tickets": sum(_aware(item.created_at).date() == day for item in tickets),
                "refunds": sum(_aware(item.created_at).date() == day for item in refunds),
                "tools": sum(_aware(item.created_at).date() == day for item in tools),
            }
        )

    return OpsDashboardResponse(
        generated_at=current_time,
        tickets={
            "total": len(tickets),
            "active": sum(ticket.status != TicketStatus.RESOLVED.value for ticket in tickets),
            "resolved": sum(ticket.status == TicketStatus.RESOLVED.value for ticket in tickets),
            "assigned": sum(
                ticket.handoff_status == HandoffStatus.ASSIGNED.value for ticket in tickets
            ),
            "due_soon": sum(status == "DUE_SOON" for status, _ in sla_by_ticket.values()),
            "breached": sum(status == "BREACHED" for status, _ in sla_by_ticket.values()),
        },
        refunds={
            "total": len(refunds),
            "pending": sum(
                refund.status
                in {
                    RefundStatus.PENDING_HUMAN_APPROVAL.value,
                    RefundStatus.PENDING_CONFIRMATION.value,
                }
                for refund in refunds
            ),
            "succeeded": len(succeeded_refunds),
            "cancelled": sum(
                refund.status == RefundStatus.CANCELLED.value for refund in refunds
            ),
            "total_refunded_amount": sum(
                (Decimal(refund.amount) for refund in succeeded_refunds),
                start=Decimal("0.00"),
            ),
        },
        tools={
            "total": len(tools),
            "succeeded": succeeded_tools,
            "failed": failed_tools,
            "success_rate": round(succeeded_tools / len(tools) * 100, 1) if tools else 0,
            "average_duration_ms": round(average_duration, 1),
        },
        models={
            "window_hours": MODEL_METRICS_WINDOW_HOURS,
            "total": len(model_invocations),
            "succeeded": succeeded_models,
            "failed": len(model_invocations) - succeeded_models,
            "fallback": sum(
                invocation.fallback_used for invocation in model_invocations
            ),
            "success_rate": (
                round(succeeded_models / len(model_invocations) * 100, 1)
                if model_invocations
                else 0
            ),
            "average_duration_ms": (
                round(sum(model_durations) / len(model_durations), 1)
                if model_durations
                else 0
            ),
            "p95_duration_ms": _nearest_rank_percentile(model_durations, 0.95),
            "input_tokens": sum(
                invocation.input_tokens for invocation in model_invocations
            ),
            "output_tokens": sum(
                invocation.output_tokens for invocation in model_invocations
            ),
            "total_tokens": sum(
                invocation.total_tokens for invocation in model_invocations
            ),
        },
        knowledge={
            "active": sum(article.active for article in articles),
            "historical": sum(not article.active for article in articles),
            "versions": len({article.version for article in articles}),
        },
        ticket_types=[
            {
                "type": ticket_type,
                "label": label,
                "count": ticket_type_counts[ticket_type],
            }
            for ticket_type, label in TICKET_TYPE_LABELS.items()
        ],
        activity=activity,
        recent_tickets=[
            {
                "id": ticket.id,
                "ticket_number": ticket.ticket_number,
                "order_number": order_numbers.get(ticket.order_id, "未知订单"),
                "ticket_type": ticket.ticket_type,
                "status": ticket.status,
                "priority": ticket.priority,
                "handoff_status": ticket.handoff_status,
                "assignee_name": ticket.assignee_name,
                "sla_status": sla_by_ticket[ticket.id][0],
                "sla_remaining_minutes": sla_by_ticket[ticket.id][1],
                "created_at": _aware(ticket.created_at).isoformat(),
            }
            for ticket in tickets[:6]
        ],
        recent_tools=[
            {
                "id": tool.id,
                "tool_name": tool.tool_name,
                "status": tool.status,
                "duration_ms": tool.duration_ms,
                "error_type": tool.error_type,
                "created_at": _aware(tool.created_at).isoformat(),
            }
            for tool in tools[:8]
        ],
        recent_model_invocations=[
            {
                "id": invocation.id,
                "provider": invocation.provider,
                "model_name": invocation.model_name,
                "status": invocation.status,
                "duration_ms": invocation.duration_ms,
                "total_tokens": invocation.total_tokens,
                "error_type": invocation.error_type,
                "fallback_used": invocation.fallback_used,
                "created_at": _aware(invocation.created_at).isoformat(),
            }
            for invocation in model_invocations[:8]
        ],
    )


def operations_ticket_report(
    db: Session,
    *,
    support_group: str | None = None,
    sla_status: str | None = None,
    now: datetime | None = None,
) -> OpsTicketReportResponse:
    available_support_groups = list(
        dict.fromkeys(route[2] for route in TICKET_ROUTING.values())
    )
    if support_group and support_group not in available_support_groups:
        raise ValidationError("INVALID_SUPPORT_GROUP", "不支持的处理组筛选条件")
    if sla_status and sla_status not in SLA_FILTERS:
        raise ValidationError("INVALID_SLA_STATUS", "不支持的 SLA 筛选条件")

    current_time = _aware(now or datetime.now(UTC))
    tickets = list(db.scalars(select(Ticket).order_by(Ticket.updated_at.desc())))
    order_ids = {ticket.order_id for ticket in tickets}
    customer_ids = {ticket.customer_id for ticket in tickets}
    orders = (
        list(db.scalars(select(Order).where(Order.id.in_(order_ids)))) if order_ids else []
    )
    customers = (
        list(db.scalars(select(Customer).where(Customer.id.in_(customer_ids))))
        if customer_ids
        else []
    )
    order_numbers = {order.id: order.order_number for order in orders}
    customer_names = {customer.id: customer.name for customer in customers}

    items = []
    for ticket in tickets:
        ticket_support_group = TICKET_ROUTING[ticket.ticket_type][2]
        ticket_sla_status, remaining_minutes = ticket_sla(ticket, now=current_time)
        if support_group and ticket_support_group != support_group:
            continue
        if sla_status == "RISK" and ticket_sla_status not in {"DUE_SOON", "BREACHED"}:
            continue
        if sla_status and sla_status != "RISK" and ticket_sla_status != sla_status:
            continue
        items.append(
            {
                "id": ticket.id,
                "ticket_number": ticket.ticket_number,
                "order_number": order_numbers.get(ticket.order_id, "未知订单"),
                "customer_name": customer_names.get(ticket.customer_id, "未知客户"),
                "ticket_type": ticket.ticket_type,
                "priority": ticket.priority,
                "status": ticket.status,
                "handoff_status": ticket.handoff_status,
                "support_group": ticket_support_group,
                "assignee_name": ticket.assignee_name,
                "sla_status": ticket_sla_status,
                "sla_remaining_minutes": remaining_minutes,
                "updated_at": _aware(ticket.updated_at).isoformat(),
            }
        )

    return OpsTicketReportResponse(
        generated_at=current_time,
        selected_support_group=support_group,
        selected_sla_status=sla_status,
        available_support_groups=available_support_groups,
        total=len(items),
        risk=sum(item["sla_status"] in {"DUE_SOON", "BREACHED"} for item in items),
        breached=sum(item["sla_status"] == "BREACHED" for item in items),
        items=items,
    )


def operations_alerts(
    db: Session,
    *,
    now: datetime | None = None,
) -> OpsAlertSnapshotResponse:
    current_time = _aware(now or datetime.now(UTC))
    tickets = list(
        db.scalars(
            select(Ticket)
            .where(Ticket.status != TicketStatus.RESOLVED.value)
            .order_by(Ticket.sla_due_at.asc())
        )
    )
    order_ids = {ticket.order_id for ticket in tickets}
    customer_ids = {ticket.customer_id for ticket in tickets}
    orders = (
        list(db.scalars(select(Order).where(Order.id.in_(order_ids)))) if order_ids else []
    )
    customers = (
        list(db.scalars(select(Customer).where(Customer.id.in_(customer_ids))))
        if customer_ids
        else []
    )
    order_numbers = {order.id: order.order_number for order in orders}
    customer_names = {customer.id: customer.name for customer in customers}
    acknowledgements = (
        list(
            db.scalars(
                select(OperationsAlertAcknowledgement).where(
                    OperationsAlertAcknowledgement.ticket_id.in_(
                        {ticket.id for ticket in tickets}
                    )
                )
            )
        )
        if tickets
        else []
    )
    acknowledgements_by_alert = {
        (item.ticket_id, item.alert_type): item for item in acknowledgements
    }

    items = []
    for ticket in tickets:
        support_group = TICKET_ROUTING[ticket.ticket_type][2]
        sla_status, remaining_minutes = ticket_sla(ticket, now=current_time)
        if sla_status == "BREACHED":
            alert_type = "SLA_BREACHED"
            severity = "CRITICAL"
            title = "SLA 已超时"
            detail = f"{ticket.ticket_number} 已超过处理时限，请立即升级处理。"
            triggered_at = _aware(ticket.sla_due_at)
        elif sla_status == "DUE_SOON":
            alert_type = "SLA_DUE_SOON"
            severity = "HIGH"
            title = "SLA 即将到期"
            detail = f"{ticket.ticket_number} 剩余 {remaining_minutes} 分钟，请优先处理。"
            triggered_at = max(
                _aware(ticket.created_at),
                _aware(ticket.sla_due_at) - timedelta(hours=1),
            )
        elif (
            ticket.handoff_status == HandoffStatus.ASSIGNED.value
            and ticket.assignee_name == support_group
        ):
            alert_type = "HANDOFF_QUEUED"
            severity = "MEDIUM"
            title = "人工工单等待受理"
            detail = f"{ticket.ticket_number} 已进入{support_group}，等待坐席受理。"
            triggered_at = _aware(
                ticket.handoff_requested_at or ticket.assigned_at or ticket.updated_at
            )
        else:
            continue

        acknowledgement = acknowledgements_by_alert.get((ticket.id, alert_type))

        items.append(
            {
                "id": f"{ticket.id}:{alert_type}",
                "type": alert_type,
                "severity": severity,
                "title": title,
                "detail": detail,
                "ticket_id": ticket.id,
                "ticket_number": ticket.ticket_number,
                "order_number": order_numbers.get(ticket.order_id, "未知订单"),
                "customer_name": customer_names.get(ticket.customer_id, "未知客户"),
                "support_group": support_group,
                "priority": ticket.priority,
                "sla_status": sla_status,
                "sla_remaining_minutes": remaining_minutes,
                "triggered_at": triggered_at.isoformat(),
                "acknowledged": acknowledgement is not None,
                "acknowledged_by": (
                    acknowledgement.acknowledged_by_name if acknowledgement else None
                ),
                "acknowledged_at": (
                    _aware(acknowledgement.acknowledged_at).isoformat()
                    if acknowledgement
                    else None
                ),
            }
        )

    items.sort(
        key=lambda item: (
            ALERT_SEVERITY_ORDER[item["severity"]],
            item["sla_remaining_minutes"],
            item["triggered_at"],
        )
    )
    return OpsAlertSnapshotResponse(
        generated_at=current_time,
        total=len(items),
        unacknowledged=sum(not item["acknowledged"] for item in items),
        critical=sum(item["severity"] == "CRITICAL" for item in items),
        high=sum(item["severity"] == "HIGH" for item in items),
        medium=sum(item["severity"] == "MEDIUM" for item in items),
        items=items,
    )


def operations_quality_report(
    db: Session,
    *,
    now: datetime | None = None,
) -> OpsQualityReportResponse:
    current_time = _aware(now or datetime.now(UTC))
    resolved_tickets = list(
        db.scalars(
            select(Ticket)
            .where(
                Ticket.status == TicketStatus.RESOLVED.value,
                Ticket.handoff_status == HandoffStatus.COMPLETED.value,
            )
            .order_by(Ticket.updated_at.desc())
        )
    )
    ticket_ids = {ticket.id for ticket in resolved_tickets}
    events = (
        list(
            db.scalars(
                select(TicketEvent)
                .where(TicketEvent.ticket_id.in_(ticket_ids))
                .order_by(TicketEvent.created_at.asc())
            )
        )
        if ticket_ids
        else []
    )
    events_by_ticket: dict[str, list[TicketEvent]] = {}
    for event in events:
        events_by_ticket.setdefault(event.ticket_id, []).append(event)

    human_tickets = []
    review_context = {}
    for ticket in resolved_tickets:
        ticket_events = events_by_ticket.get(ticket.id, [])
        accepted = next(
            (event for event in ticket_events if event.action == "HUMAN_HANDOFF_ACCEPTED"),
            None,
        )
        resolved = next(
            (event for event in reversed(ticket_events) if event.action == "STATUS_RESOLVED"),
            None,
        )
        if accepted and resolved:
            human_tickets.append(ticket)
            review_context[ticket.id] = (ticket_events, accepted, resolved)

    order_ids = {ticket.order_id for ticket in human_tickets}
    customer_ids = {ticket.customer_id for ticket in human_tickets}
    orders = (
        list(db.scalars(select(Order).where(Order.id.in_(order_ids)))) if order_ids else []
    )
    customers = (
        list(db.scalars(select(Customer).where(Customer.id.in_(customer_ids))))
        if customer_ids
        else []
    )
    order_numbers = {order.id: order.order_number for order in orders}
    customer_names = {customer.id: customer.name for customer in customers}
    feedback_items = (
        list(
            db.scalars(
                select(CustomerSatisfactionFeedback).where(
                    CustomerSatisfactionFeedback.ticket_id.in_(
                        {ticket.id for ticket in human_tickets}
                    )
                )
            )
        )
        if human_tickets
        else []
    )
    feedback_by_ticket = {item.ticket_id: item for item in feedback_items}

    items = []
    for ticket in human_tickets:
        ticket_events, accepted, resolved = review_context[ticket.id]
        accepted_at = _aware(accepted.created_at)
        resolved_at = _aware(resolved.created_at)
        first_reply = next(
            (
                event
                for event in ticket_events
                if event.action == "AGENT_REPLY_SENT"
                and _aware(event.created_at) >= accepted_at
            ),
            None,
        )
        first_reply_timely = bool(
            first_reply
            and _aware(first_reply.created_at) - accepted_at
            <= timedelta(minutes=QUALITY_FIRST_REPLY_MINUTES)
        )
        checks = [
            {
                "key": "sla_met",
                "label": "SLA 内解决",
                "passed": resolved_at <= _aware(ticket.sla_due_at),
                "max_score": 35,
            },
            {
                "key": "first_reply_timely",
                "label": "30 分钟内首次回复",
                "passed": first_reply_timely,
                "max_score": 25,
            },
            {
                "key": "internal_note_present",
                "label": "留有内部处理记录",
                "passed": any(
                    event.action == "AGENT_NOTE_ADDED" for event in ticket_events
                ),
                "max_score": 15,
            },
            {
                "key": "resolution_complete",
                "label": "解决方案完整",
                "passed": len(resolved.detail.strip()) >= 10,
                "max_score": 25,
            },
        ]
        for check in checks:
            check["score"] = check["max_score"] if check["passed"] else 0
        score = sum(int(check["score"]) for check in checks)
        grade = "EXCELLENT" if score >= 90 else "QUALIFIED" if score >= 75 else "ATTENTION"
        feedback = feedback_by_ticket.get(ticket.id)
        items.append(
            {
                "ticket_id": ticket.id,
                "ticket_number": ticket.ticket_number,
                "order_number": order_numbers.get(ticket.order_id, "未知订单"),
                "customer_name": customer_names.get(ticket.customer_id, "未知客户"),
                "support_group": TICKET_ROUTING[ticket.ticket_type][2],
                "assignee_name": ticket.assignee_name or accepted.actor,
                "resolved_at": resolved_at,
                "score": score,
                "grade": grade,
                "checks": checks,
                "customer_rating": feedback.rating if feedback else None,
                "customer_comment": feedback.comment if feedback else None,
                "feedback_submitted_at": (
                    _aware(feedback.submitted_at) if feedback else None
                ),
            }
        )

    items.sort(key=lambda item: item["resolved_at"], reverse=True)
    ratings = [
        int(item["customer_rating"])
        for item in items
        if item["customer_rating"] is not None
    ]
    return OpsQualityReportResponse(
        generated_at=current_time,
        total=len(items),
        excellent=sum(item["grade"] == "EXCELLENT" for item in items),
        qualified=sum(item["grade"] == "QUALIFIED" for item in items),
        attention=sum(item["grade"] == "ATTENTION" for item in items),
        average_score=(
            round(sum(int(item["score"]) for item in items) / len(items), 1)
            if items
            else 0
        ),
        feedback_received=len(ratings),
        low_ratings=sum(rating <= 2 for rating in ratings),
        average_customer_rating=(
            round(sum(ratings) / len(ratings), 1) if ratings else 0
        ),
        items=items,
    )


def acknowledge_operations_alert(
    db: Session,
    operator: Operator,
    ticket_id: str,
    alert_type: str,
    *,
    now: datetime | None = None,
) -> OpsAlertAcknowledgementResponse:
    if alert_type not in ALERT_TYPES:
        raise ValidationError("INVALID_ALERT_TYPE", "不支持的运营告警类型")
    if not db.get(Ticket, ticket_id):
        raise NotFoundError("工单不存在")

    current_time = _aware(now or datetime.now(UTC))
    snapshot = operations_alerts(db, now=current_time)
    active_alert = next(
        (item for item in snapshot.items if item["ticket_id"] == ticket_id),
        None,
    )
    if not active_alert or active_alert["type"] != alert_type:
        raise ConflictError("ALERT_NOT_ACTIVE", "该告警已关闭或已升级，请刷新后重试")

    existing = db.scalar(
        select(OperationsAlertAcknowledgement).where(
            OperationsAlertAcknowledgement.ticket_id == ticket_id,
            OperationsAlertAcknowledgement.alert_type == alert_type,
        )
    )
    if existing:
        return _acknowledgement_response(existing)

    acknowledgement = OperationsAlertAcknowledgement(
        ticket_id=ticket_id,
        alert_type=alert_type,
        acknowledged_by_operator_id=operator.id,
        acknowledged_by_name=operator.name,
        acknowledged_at=current_time,
    )
    db.add(acknowledgement)
    try:
        db.commit()
        db.refresh(acknowledgement)
    except IntegrityError:
        db.rollback()
        acknowledgement = db.scalar(
            select(OperationsAlertAcknowledgement).where(
                OperationsAlertAcknowledgement.ticket_id == ticket_id,
                OperationsAlertAcknowledgement.alert_type == alert_type,
            )
        )
        if not acknowledgement:
            raise
    return _acknowledgement_response(acknowledgement)


def _acknowledgement_response(
    acknowledgement: OperationsAlertAcknowledgement,
) -> OpsAlertAcknowledgementResponse:
    return OpsAlertAcknowledgementResponse(
        id=acknowledgement.id,
        ticket_id=acknowledgement.ticket_id,
        alert_type=acknowledgement.alert_type,
        acknowledged_by=acknowledgement.acknowledged_by_name,
        acknowledged_at=acknowledgement.acknowledged_at,
    )
