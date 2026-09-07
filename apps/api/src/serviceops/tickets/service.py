import uuid
from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.models import (
    Conversation,
    Customer,
    CustomerSatisfactionFeedback,
    HandoffStatus,
    Ticket,
    TicketEvent,
    TicketPriority,
    TicketStatus,
    utcnow,
)
from serviceops.orders.service import get_order
from serviceops.shared.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from serviceops.shared.schemas import TicketResponse

ALLOWED_TICKET_TRANSITIONS = {
    TicketStatus.OPEN.value: {TicketStatus.WAITING_APPROVAL.value, TicketStatus.RESOLVED.value},
    TicketStatus.WAITING_APPROVAL.value: {TicketStatus.RESOLVED.value},
    TicketStatus.RESOLVED.value: set(),
}

TICKET_ROUTING = {
    "SHIPPING": (TicketPriority.P2.value, 4, "物流专员组"),
    "ORDER": (TicketPriority.P2.value, 4, "订单支持组"),
    "REFUND": (TicketPriority.P1.value, 1, "退款审核组"),
    "OTHER": (TicketPriority.P3.value, 8, "综合支持组"),
}

TICKET_MESSAGE_ACTIONS = {
    "CUSTOMER_MESSAGE_SENT": "CUSTOMER",
    "AGENT_REPLY_SENT": "SUPPORT_AGENT",
}


def _ticket_number(now: datetime | None = None) -> str:
    stamp = (now or utcnow()).strftime("%Y%m%d")
    return f"TK-{stamp}-{uuid.uuid4().hex[:6].upper()}"


def transition_ticket(
    db: Session, ticket: Ticket, target: str, *, actor: str, detail: str
) -> Ticket:
    if target not in ALLOWED_TICKET_TRANSITIONS.get(ticket.status, set()):
        raise ConflictError(
            "INVALID_TICKET_TRANSITION",
            f"工单不能从 {ticket.status} 转换为 {target}",
        )
    ticket.status = target
    if target == TicketStatus.RESOLVED.value and ticket.handoff_status == HandoffStatus.ASSIGNED:
        ticket.handoff_status = HandoffStatus.COMPLETED.value
    ticket.version += 1
    ticket.updated_at = utcnow()
    db.add(TicketEvent(ticket_id=ticket.id, action=f"STATUS_{target}", detail=detail, actor=actor))
    return ticket


def create_ticket(
    db: Session,
    customer: Customer,
    *,
    conversation_id: str,
    order_number: str,
    ticket_type: str,
    reason: str,
    evidence: dict | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> Ticket:
    if ticket_type not in TICKET_ROUTING:
        raise ValidationError("INVALID_TICKET_TYPE", "不支持的工单类型")
    order = get_order(db, customer, order_number)
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise NotFoundError("会话不存在")
    if conversation.customer_id != customer.id:
        raise ForbiddenError("无法访问该会话")
    existing = db.scalar(
        select(Ticket)
        .where(
            Ticket.customer_id == customer.id,
            Ticket.order_id == order.id,
            Ticket.conversation_id == conversation_id,
            Ticket.ticket_type == ticket_type,
            Ticket.status.in_([TicketStatus.OPEN.value, TicketStatus.WAITING_APPROVAL.value]),
        )
        .order_by(Ticket.created_at.desc())
    )
    if existing:
        return existing
    current_time = now or utcnow()
    priority, sla_hours, _ = TICKET_ROUTING[ticket_type]
    ticket = Ticket(
        ticket_number=_ticket_number(current_time),
        customer_id=customer.id,
        order_id=order.id,
        conversation_id=conversation_id,
        ticket_type=ticket_type,
        priority=priority,
        sla_due_at=current_time + timedelta(hours=sla_hours),
        reason=reason,
        evidence=evidence or {},
        created_at=current_time,
        updated_at=current_time,
    )
    db.add(ticket)
    db.flush()
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            action="CREATED",
            detail="Agent 创建工单并关联订单、物流证据和会话",
            actor="agent",
        )
    )
    if commit:
        db.commit()
        db.refresh(ticket)
    return ticket


def get_ticket(db: Session, customer: Customer, ticket_id: str) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise NotFoundError("工单不存在")
    if ticket.customer_id != customer.id:
        raise ForbiddenError("无法访问该工单")
    return ticket


def get_current_ticket(
    db: Session,
    customer: Customer,
    conversation_id: str,
) -> Ticket | None:
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise NotFoundError("会话不存在")
    if conversation.customer_id != customer.id:
        raise ForbiddenError("无法访问该会话")
    return db.scalar(
        select(Ticket)
        .where(
            Ticket.customer_id == customer.id,
            Ticket.conversation_id == conversation_id,
        )
        .order_by(Ticket.created_at.desc())
        .limit(1)
    )


def request_human_handoff(
    db: Session,
    customer: Customer,
    ticket_id: str,
    *,
    now: datetime | None = None,
) -> Ticket:
    ticket = get_ticket(db, customer, ticket_id)
    if ticket.status == TicketStatus.RESOLVED.value:
        raise ConflictError("RESOLVED_TICKET_HANDOFF", "已解决工单不能转人工")
    if ticket.handoff_status == HandoffStatus.ASSIGNED.value:
        return ticket

    current_time = now or utcnow()
    _, _, support_group = TICKET_ROUTING[ticket.ticket_type]
    ticket.handoff_status = HandoffStatus.ASSIGNED.value
    ticket.handoff_requested_at = current_time
    ticket.assignee_name = support_group
    ticket.assigned_at = current_time
    ticket.updated_at = current_time
    ticket.version += 1
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            action="HUMAN_HANDOFF_ASSIGNED",
            detail=f"工单已转人工并自动分派至{support_group}",
            actor="routing-service",
            created_at=current_time,
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def cancel_human_handoff(
    db: Session,
    customer: Customer,
    ticket_id: str,
    *,
    now: datetime | None = None,
) -> Ticket:
    ticket = get_ticket(db, customer, ticket_id)
    if ticket.status == TicketStatus.RESOLVED.value:
        raise ConflictError("RESOLVED_TICKET_HANDOFF", "已解决工单不能撤销人工接管")
    if ticket.handoff_status != HandoffStatus.ASSIGNED.value:
        raise ConflictError("HANDOFF_NOT_ASSIGNED", "当前工单没有可撤销的人工接管")

    current_time = now or utcnow()
    previous_assignee = ticket.assignee_name or "人工支持组"
    ticket.handoff_status = HandoffStatus.BOT_ACTIVE.value
    ticket.handoff_requested_at = None
    ticket.assignee_name = None
    ticket.assigned_at = None
    ticket.updated_at = current_time
    ticket.version += 1
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            action="HUMAN_HANDOFF_CANCELLED",
            detail=f"用户撤销由{previous_assignee}处理，工单退回 Agent",
            actor="customer",
            created_at=current_time,
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def add_customer_ticket_message(
    db: Session,
    customer: Customer,
    ticket_id: str,
    content: str,
    *,
    now: datetime | None = None,
) -> Ticket:
    ticket = get_ticket(db, customer, ticket_id)
    if ticket.status == TicketStatus.RESOLVED.value:
        raise ConflictError("TICKET_ALREADY_RESOLVED", "已解决工单不能继续发送消息")
    if ticket.handoff_status != HandoffStatus.ASSIGNED.value:
        raise ConflictError("TICKET_NOT_HANDED_OFF", "请先将工单转人工再发送消息")
    message = content.strip()
    if not message:
        raise ValidationError("EMPTY_TICKET_MESSAGE", "消息内容不能为空")

    current_time = now or utcnow()
    ticket.updated_at = current_time
    ticket.version += 1
    conversation = db.get(Conversation, ticket.conversation_id)
    if conversation:
        conversation.updated_at = current_time
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            action="CUSTOMER_MESSAGE_SENT",
            detail=message,
            actor=f"customer:{customer.name}",
            created_at=current_time,
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def ticket_sla(ticket: Ticket, *, now: datetime | None = None) -> tuple[str, int]:
    current_time = _aware(now or utcnow())
    due_at = _aware(ticket.sla_due_at)
    remaining_minutes = max(0, ceil((due_at - current_time).total_seconds() / 60))
    if ticket.status == TicketStatus.RESOLVED.value:
        return "COMPLETED", remaining_minutes
    if current_time >= due_at:
        return "BREACHED", 0
    if due_at - current_time <= timedelta(hours=1):
        return "DUE_SOON", remaining_minutes
    return "ON_TRACK", remaining_minutes


def _customer_visible_actor(actor: str) -> str:
    if actor.startswith("customer:") or actor in {
        "agent",
        "system",
        "routing-service",
        "refund-service",
    }:
        return "Harbor Support"
    return actor


def _resolution_snapshot(event: TicketEvent | None) -> dict | None:
    if not event:
        return None
    return {
        "summary": event.detail,
        "handled_by": _customer_visible_actor(event.actor),
        "resolved_at": event.created_at,
    }


def ticket_message_snapshots(events: list[TicketEvent]) -> list[dict]:
    return [
        {
            "id": event.id,
            "sender_role": TICKET_MESSAGE_ACTIONS[event.action],
            "sender_name": (
                event.actor.removeprefix("customer:")
                if event.action == "CUSTOMER_MESSAGE_SENT"
                else event.actor
            ),
            "content": event.detail,
            "created_at": event.created_at,
        }
        for event in events
        if event.action in TICKET_MESSAGE_ACTIONS
    ]


def ticket_snapshot(
    ticket: Ticket,
    *,
    now: datetime | None = None,
    resolution_event: TicketEvent | None = None,
    message_events: list[TicketEvent] | None = None,
    feedback: CustomerSatisfactionFeedback | None = None,
) -> dict:
    sla_status, remaining_minutes = ticket_sla(ticket, now=now)
    return {
        "id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "order_id": ticket.order_id,
        "conversation_id": ticket.conversation_id,
        "ticket_type": ticket.ticket_type,
        "status": ticket.status,
        "priority": ticket.priority,
        "handoff_status": ticket.handoff_status,
        "assignee_name": ticket.assignee_name,
        "handoff_requested_at": ticket.handoff_requested_at,
        "assigned_at": ticket.assigned_at,
        "sla_due_at": ticket.sla_due_at,
        "sla_status": sla_status,
        "sla_remaining_minutes": remaining_minutes,
        "reason": ticket.reason,
        "resolution": _resolution_snapshot(resolution_event),
        "feedback": (
            {
                "id": feedback.id,
                "ticket_id": feedback.ticket_id,
                "rating": feedback.rating,
                "comment": feedback.comment,
                "submitted_at": feedback.submitted_at,
            }
            if feedback
            else None
        ),
        "messages": ticket_message_snapshots(message_events or []),
        "created_at": ticket.created_at,
    }


def ticket_response(db: Session, ticket: Ticket) -> TicketResponse:
    events = list(
        db.scalars(
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket.id)
            .order_by(TicketEvent.created_at.asc())
        )
    )
    resolution_event = next(
        (item for item in reversed(events) if item.action == "STATUS_RESOLVED"),
        None,
    )
    feedback = db.scalar(
        select(CustomerSatisfactionFeedback).where(
            CustomerSatisfactionFeedback.ticket_id == ticket.id
        )
    )
    return TicketResponse(
        **ticket_snapshot(
            ticket,
            resolution_event=resolution_event,
            message_events=events,
            feedback=feedback,
        ),
        evidence=ticket.evidence,
        updated_at=ticket.updated_at,
        events=[
            {
                "action": item.action,
                "detail": item.detail,
                "actor": item.actor,
                "created_at": item.created_at.isoformat(),
            }
            for item in events
            if item.action != "AGENT_NOTE_ADDED"
        ],
    )
