import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.models import (
    Conversation,
    Customer,
    Ticket,
    TicketEvent,
    TicketStatus,
    utcnow,
)
from serviceops.orders.service import get_order
from serviceops.shared.errors import ConflictError, ForbiddenError, NotFoundError
from serviceops.shared.schemas import TicketResponse

ALLOWED_TICKET_TRANSITIONS = {
    TicketStatus.OPEN.value: {TicketStatus.WAITING_APPROVAL.value, TicketStatus.RESOLVED.value},
    TicketStatus.WAITING_APPROVAL.value: {TicketStatus.RESOLVED.value},
    TicketStatus.RESOLVED.value: set(),
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
) -> Ticket:
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
            Ticket.ticket_type == ticket_type,
            Ticket.status.in_([TicketStatus.OPEN.value, TicketStatus.WAITING_APPROVAL.value]),
        )
        .order_by(Ticket.created_at.desc())
    )
    if existing:
        return existing
    ticket = Ticket(
        ticket_number=_ticket_number(),
        customer_id=customer.id,
        order_id=order.id,
        conversation_id=conversation_id,
        ticket_type=ticket_type,
        reason=reason,
        evidence=evidence or {},
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


def ticket_response(db: Session, ticket: Ticket) -> TicketResponse:
    events = list(
        db.scalars(
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket.id)
            .order_by(TicketEvent.created_at.asc())
        )
    )
    return TicketResponse(
        id=ticket.id,
        ticket_number=ticket.ticket_number,
        order_id=ticket.order_id,
        conversation_id=ticket.conversation_id,
        ticket_type=ticket.ticket_type,
        status=ticket.status,
        reason=ticket.reason,
        evidence=ticket.evidence,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        events=[
            {
                "action": item.action,
                "detail": item.detail,
                "actor": item.actor,
                "created_at": item.created_at.isoformat(),
            }
            for item in events
        ],
    )
