from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from serviceops.models import (
    Conversation,
    Customer,
    CustomerSatisfactionFeedback,
    Message,
    RefundRequest,
    Ticket,
    TicketEvent,
    ToolInvocation,
    utcnow,
)
from serviceops.shared.errors import ForbiddenError, NotFoundError
from serviceops.tickets.service import ticket_snapshot


def create_conversation(db: Session, customer: Customer) -> Conversation:
    conversation = Conversation(customer_id=customer.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_conversation(db: Session, customer: Customer, conversation_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise NotFoundError("会话不存在")
    if conversation.customer_id != customer.id:
        raise ForbiddenError("无法访问该会话")
    return conversation


def add_message(db: Session, conversation: Conversation, role: str, content: str) -> Message:
    message = Message(conversation_id=conversation.id, role=role, content=content)
    conversation.updated_at = utcnow()
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def conversation_state(db: Session, customer: Customer, conversation_id: str) -> dict:
    conversation = get_conversation(db, customer, conversation_id)
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc())
        )
    )
    invocations = list(
        db.scalars(
            select(ToolInvocation)
            .where(ToolInvocation.conversation_id == conversation.id)
            .order_by(ToolInvocation.created_at.asc())
        )
    )
    invoked_ticket_ids = {
        invocation.ticket_id for invocation in invocations if invocation.ticket_id is not None
    }
    ticket_scope = Ticket.conversation_id == conversation.id
    if invoked_ticket_ids:
        ticket_scope = or_(ticket_scope, Ticket.id.in_(invoked_ticket_ids))
    tickets = list(
        db.scalars(
            select(Ticket)
            .where(Ticket.customer_id == customer.id, ticket_scope)
            .order_by(Ticket.created_at.desc())
        )
    )
    ticket_ids = [ticket.id for ticket in tickets]
    ticket_events = (
        list(
            db.scalars(
                select(TicketEvent)
                .where(
                    TicketEvent.ticket_id.in_(ticket_ids),
                    TicketEvent.action.in_(
                        [
                            "STATUS_RESOLVED",
                            "CUSTOMER_MESSAGE_SENT",
                            "AGENT_REPLY_SENT",
                        ]
                    ),
                )
                .order_by(TicketEvent.created_at.asc())
            )
        )
        if ticket_ids
        else []
    )
    events_by_ticket: dict[str, list[TicketEvent]] = {}
    resolution_by_ticket: dict[str, TicketEvent] = {}
    for event in ticket_events:
        events_by_ticket.setdefault(event.ticket_id, []).append(event)
        if event.action == "STATUS_RESOLVED":
            resolution_by_ticket[event.ticket_id] = event
    refunds = (
        list(
            db.scalars(
                select(RefundRequest)
                .where(RefundRequest.ticket_id.in_(ticket_ids))
                .order_by(RefundRequest.created_at.desc())
            )
        )
        if ticket_ids
        else []
    )
    feedback_items = (
        list(
            db.scalars(
                select(CustomerSatisfactionFeedback).where(
                    CustomerSatisfactionFeedback.ticket_id.in_(ticket_ids)
                )
            )
        )
        if ticket_ids
        else []
    )
    feedback_by_ticket = {item.ticket_id: item for item in feedback_items}
    return {
        "conversation": {"id": conversation.id, "updated_at": conversation.updated_at.isoformat()},
        "messages": [
            {
                "id": item.id,
                "role": item.role,
                "content": item.content,
                "created_at": item.created_at.isoformat(),
            }
            for item in messages
        ],
        "tickets": [
            ticket_snapshot(
                item,
                resolution_event=resolution_by_ticket.get(item.id),
                message_events=events_by_ticket.get(item.id),
                feedback=feedback_by_ticket.get(item.id),
            )
            for item in tickets
        ],
        "refunds": [
            {
                "id": item.id,
                "refund_number": item.refund_number,
                "ticket_id": item.ticket_id,
                "status": item.status,
                "amount": str(item.amount),
                "method": item.method,
                "reason": item.reason,
                "created_at": item.created_at.isoformat(),
            }
            for item in refunds
        ],
        "tool_invocations": [
            {
                "id": item.id,
                "tool_call_id": item.tool_call_id,
                "tool_name": item.tool_name,
                "status": item.status,
                "duration_ms": item.duration_ms,
                "error_type": item.error_type,
                "created_at": item.created_at.isoformat(),
            }
            for item in invocations
        ],
    }
