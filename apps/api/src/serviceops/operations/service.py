from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from serviceops.models import (
    Customer,
    HandoffStatus,
    KnowledgeArticle,
    OperationsAlertAcknowledgement,
    Operator,
    Order,
    RefundRequest,
    RefundStatus,
    Ticket,
    TicketEvent,
    TicketStatus,
    ToolInvocation,
)
from serviceops.shared.errors import ConflictError, NotFoundError, ValidationError
from serviceops.shared.schemas import (
    OpsAlertAcknowledgementResponse,
    OpsAlertSnapshotResponse,
    OpsDashboardResponse,
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


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


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
    articles = list(db.scalars(select(KnowledgeArticle)))

    sla_by_ticket = {ticket.id: ticket_sla(ticket, now=current_time) for ticket in tickets}
    ticket_type_counts = {
        ticket_type: sum(ticket.ticket_type == ticket_type for ticket in tickets)
        for ticket_type in TICKET_TYPE_LABELS
    }
    succeeded_tools = sum(tool.status == "SUCCEEDED" for tool in tools)
    failed_tools = len(tools) - succeeded_tools
    average_duration = sum(tool.duration_ms for tool in tools) / len(tools) if tools else 0
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
                refund.status == RefundStatus.PENDING_CONFIRMATION.value for refund in refunds
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
            }
        )

    items.sort(key=lambda item: item["resolved_at"], reverse=True)
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
