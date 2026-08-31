from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.models import (
    Conversation,
    Customer,
    Message,
    RefundRequest,
    Ticket,
    ToolInvocation,
    utcnow,
)
from serviceops.shared.errors import ForbiddenError, NotFoundError


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
    tickets = list(
        db.scalars(
            select(Ticket)
            .where(Ticket.conversation_id == conversation.id)
            .order_by(Ticket.created_at.desc())
        )
    )
    ticket_ids = [ticket.id for ticket in tickets]
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
    invocations = list(
        db.scalars(
            select(ToolInvocation)
            .where(ToolInvocation.conversation_id == conversation.id)
            .order_by(ToolInvocation.created_at.asc())
        )
    )
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
            {
                "id": item.id,
                "ticket_number": item.ticket_number,
                "order_id": item.order_id,
                "ticket_type": item.ticket_type,
                "status": item.status,
                "reason": item.reason,
                "created_at": item.created_at.isoformat(),
            }
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
