from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from serviceops.models import (
    Customer,
    CustomerSatisfactionFeedback,
    TicketEvent,
    TicketStatus,
    utcnow,
)
from serviceops.shared.errors import ConflictError, ValidationError
from serviceops.shared.schemas import CustomerFeedbackResponse
from serviceops.tickets.service import get_ticket


def feedback_response(
    feedback: CustomerSatisfactionFeedback,
) -> CustomerFeedbackResponse:
    return CustomerFeedbackResponse(
        id=feedback.id,
        ticket_id=feedback.ticket_id,
        rating=feedback.rating,
        comment=feedback.comment,
        submitted_at=feedback.submitted_at,
    )


def submit_customer_feedback(
    db: Session,
    customer: Customer,
    ticket_id: str,
    *,
    rating: int,
    comment: str | None = None,
) -> CustomerFeedbackResponse:
    ticket = get_ticket(db, customer, ticket_id)
    if ticket.status != TicketStatus.RESOLVED.value:
        raise ConflictError("TICKET_NOT_RESOLVED", "工单解决后才能提交满意度评价")
    if rating < 1 or rating > 5:
        raise ValidationError("INVALID_FEEDBACK_RATING", "满意度评分必须为 1 至 5 星")
    normalized_comment = comment.strip() if comment else None
    if normalized_comment == "":
        normalized_comment = None

    existing = db.scalar(
        select(CustomerSatisfactionFeedback).where(
            CustomerSatisfactionFeedback.ticket_id == ticket.id
        )
    )
    if existing:
        if existing.rating == rating and existing.comment == normalized_comment:
            return feedback_response(existing)
        raise ConflictError(
            "FEEDBACK_ALREADY_SUBMITTED",
            "该工单已经提交过满意度评价",
        )

    current_time = utcnow()
    feedback = CustomerSatisfactionFeedback(
        ticket_id=ticket.id,
        customer_id=customer.id,
        rating=rating,
        comment=normalized_comment,
        submitted_at=current_time,
        updated_at=current_time,
    )
    db.add(feedback)
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            action="CUSTOMER_FEEDBACK_SUBMITTED",
            detail=f"客户提交 {rating} 星满意度评价",
            actor=f"customer:{customer.name}",
            created_at=current_time,
        )
    )
    try:
        db.commit()
        db.refresh(feedback)
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(CustomerSatisfactionFeedback).where(
                CustomerSatisfactionFeedback.ticket_id == ticket.id
            )
        )
        if existing and existing.rating == rating and existing.comment == normalized_comment:
            return feedback_response(existing)
        raise ConflictError(
            "FEEDBACK_ALREADY_SUBMITTED",
            "该工单已经提交过满意度评价",
        ) from None
    return feedback_response(feedback)
