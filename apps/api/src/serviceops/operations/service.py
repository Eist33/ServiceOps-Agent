from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.models import (
    HandoffStatus,
    KnowledgeArticle,
    Order,
    RefundRequest,
    RefundStatus,
    Ticket,
    TicketStatus,
    ToolInvocation,
)
from serviceops.shared.schemas import OpsDashboardResponse
from serviceops.tickets.service import ticket_sla

TICKET_TYPE_LABELS = {
    "SHIPPING": "物流异常",
    "ORDER": "订单问题",
    "REFUND": "退款申请",
    "OTHER": "其他售后",
}


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
