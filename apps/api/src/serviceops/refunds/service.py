import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.models import (
    Customer,
    IdempotencyRecord,
    RefundRequest,
    RefundStatus,
    Ticket,
    TicketStatus,
    utcnow,
)
from serviceops.orders.service import get_order
from serviceops.shared.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from serviceops.shared.schemas import RefundResponse
from serviceops.tickets.service import create_ticket, transition_ticket


def _refund_number(now: datetime | None = None) -> str:
    stamp = (now or utcnow()).strftime("%m%d")
    return f"RF-{stamp}-{uuid.uuid4().hex[:6].upper()}"


def refund_response(refund: RefundRequest) -> RefundResponse:
    return RefundResponse(
        id=refund.id,
        refund_number=refund.refund_number,
        ticket_id=refund.ticket_id,
        order_id=refund.order_id,
        status=refund.status,
        amount=refund.amount,
        method=refund.method,
        reason=refund.reason,
        confirmed_at=refund.confirmed_at,
        created_at=refund.created_at,
    )


def create_refund_request(
    db: Session,
    customer: Customer,
    *,
    conversation_id: str,
    order_number: str,
    reason: str,
    requested_amount: Decimal | None = None,
) -> RefundRequest:
    order = get_order(db, customer, order_number)
    amount = requested_amount if requested_amount is not None else order.refundable_amount
    if amount <= 0 or amount > order.refundable_amount:
        raise ValidationError("INVALID_REFUND_AMOUNT", "退款金额不能超过当前可退金额")
    existing = db.scalar(
        select(RefundRequest)
        .where(
            RefundRequest.customer_id == customer.id,
            RefundRequest.order_id == order.id,
            RefundRequest.status.in_(
                [
                    RefundStatus.PENDING_CONFIRMATION.value,
                    RefundStatus.PROCESSING.value,
                    RefundStatus.SUCCEEDED.value,
                ]
            ),
        )
        .order_by(RefundRequest.created_at.desc())
    )
    if existing:
        return existing
    ticket = create_ticket(
        db,
        customer,
        conversation_id=conversation_id,
        order_number=order_number,
        ticket_type="REFUND",
        reason=reason,
        evidence={"server_calculated_refundable_amount": str(order.refundable_amount)},
    )
    if ticket.status == TicketStatus.OPEN.value:
        transition_ticket(
            db,
            ticket,
            TicketStatus.WAITING_APPROVAL.value,
            actor="system",
            detail="退款申请已创建，等待用户明确确认",
        )
    refund = RefundRequest(
        refund_number=_refund_number(),
        customer_id=customer.id,
        order_id=order.id,
        ticket_id=ticket.id,
        reason=reason,
        amount=amount,
    )
    db.add(refund)
    db.commit()
    db.refresh(refund)
    return refund


def get_refund(db: Session, customer: Customer, refund_id: str) -> RefundRequest:
    refund = db.get(RefundRequest, refund_id)
    if not refund:
        raise NotFoundError("退款申请不存在")
    if refund.customer_id != customer.id:
        raise ForbiddenError("无法访问该退款申请")
    return refund


def confirm_refund(
    db: Session,
    customer: Customer,
    refund_id: str,
    idempotency_key: str,
) -> RefundResponse:
    if not idempotency_key or len(idempotency_key) > 160:
        raise ValidationError("INVALID_IDEMPOTENCY_KEY", "退款确认必须携带有效幂等键")
    refund = get_refund(db, customer, refund_id)
    scope = f"refund_confirm:{refund.id}"
    previous = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    if previous:
        return RefundResponse.model_validate(previous.response_json)
    order = get_order(db, customer, _order_number(db, refund.order_id))
    if refund.status == RefundStatus.SUCCEEDED.value:
        response = refund_response(refund)
        db.add(
            IdempotencyRecord(
                scope=scope,
                idempotency_key=idempotency_key,
                resource_id=refund.id,
                response_json=response.model_dump(mode="json"),
            )
        )
        db.commit()
        return response
    if Decimal(refund.amount) > Decimal(order.refundable_amount):
        raise ValidationError("REFUND_AMOUNT_CHANGED", "可退金额已变化，请重新发起退款")
    if refund.status != RefundStatus.PENDING_CONFIRMATION.value:
        raise ConflictError("INVALID_REFUND_STATE", f"当前退款状态 {refund.status} 不能确认")
    ticket = db.get(Ticket, refund.ticket_id)
    refund.status = RefundStatus.PROCESSING.value
    refund.version += 1
    refund.updated_at = utcnow()
    # MVP adapter is deterministic and never touches a real payment provider.
    refund.status = RefundStatus.SUCCEEDED.value
    refund.confirmed_at = utcnow()
    refund.version += 1
    refund.updated_at = utcnow()
    order.refundable_amount = Decimal("0.00")
    order.status = "REFUNDED"
    order.updated_at = utcnow()
    if ticket and ticket.status == TicketStatus.WAITING_APPROVAL.value:
        transition_ticket(
            db,
            ticket,
            TicketStatus.RESOLVED.value,
            actor=f"customer:{customer.id}",
            detail="用户确认后模拟退款成功，工单已解决",
        )
    response = refund_response(refund)
    db.add(
        IdempotencyRecord(
            scope=scope,
            idempotency_key=idempotency_key,
            resource_id=refund.id,
            response_json=response.model_dump(mode="json"),
        )
    )
    db.commit()
    return response


def _order_number(db: Session, order_id: str) -> str:
    from serviceops.models import Order

    order = db.get(Order, order_id)
    if not order:
        raise NotFoundError("关联订单不存在")
    return order.order_number


def cancel_refund(db: Session, customer: Customer, refund_id: str) -> RefundResponse:
    refund = get_refund(db, customer, refund_id)
    if refund.status != RefundStatus.PENDING_CONFIRMATION.value:
        raise ConflictError("INVALID_REFUND_STATE", f"当前退款状态 {refund.status} 不能取消")
    refund.status = RefundStatus.CANCELLED.value
    refund.version += 1
    refund.updated_at = utcnow()
    db.commit()
    return refund_response(refund)
