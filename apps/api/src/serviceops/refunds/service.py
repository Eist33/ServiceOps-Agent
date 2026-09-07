import time
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from serviceops.models import (
    Customer,
    IdempotencyRecord,
    Operator,
    Order,
    RefundApprovalAudit,
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

ACTIVE_REFUND_STATUSES = (
    RefundStatus.PENDING_HUMAN_APPROVAL.value,
    RefundStatus.PENDING_CONFIRMATION.value,
    RefundStatus.PROCESSING.value,
    RefundStatus.SUCCEEDED.value,
)
APPROVAL = "APPROVED"
REJECTION = "REJECTED"
WITHDRAWAL = "WITHDRAWN"


def _refund_number(now: datetime | None = None) -> str:
    stamp = (now or utcnow()).strftime("%m%d")
    return f"RF-{stamp}-{uuid.uuid4().hex[:6].upper()}"


def _validated_idempotency_key(idempotency_key: str) -> str:
    key = (idempotency_key or "").strip()
    if not key or len(key) > 160:
        raise ValidationError("INVALID_IDEMPOTENCY_KEY", "退款操作必须携带有效幂等键")
    return key


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
        approved_by_operator_id=refund.approved_by_operator_id,
        approved_at=refund.approved_at,
        confirmed_at=refund.confirmed_at,
        version=refund.version,
        created_at=refund.created_at,
        updated_at=refund.updated_at,
    )


def _refund_by_id(db: Session, refund_id: str, *, for_update: bool = False) -> RefundRequest:
    query = select(RefundRequest).where(RefundRequest.id == refund_id)
    if for_update:
        query = query.with_for_update()
    refund = db.scalar(query)
    if not refund:
        raise NotFoundError("退款申请不存在")
    return refund


def _owned_refund(
    db: Session,
    customer: Customer,
    refund_id: str,
    *,
    for_update: bool = False,
) -> RefundRequest:
    refund = _refund_by_id(db, refund_id, for_update=for_update)
    if refund.customer_id != customer.id:
        raise ForbiddenError("无法访问该退款申请")
    return refund


def _active_refund(db: Session, customer_id: str, order_id: str) -> RefundRequest | None:
    return db.scalar(
        select(RefundRequest)
        .where(
            RefundRequest.customer_id == customer_id,
            RefundRequest.order_id == order_id,
            RefundRequest.status.in_(ACTIVE_REFUND_STATUSES),
        )
        .order_by(RefundRequest.created_at.desc())
    )


def create_refund_request(
    db: Session,
    customer: Customer,
    *,
    conversation_id: str,
    order_number: str,
    reason: str,
    requested_amount: Decimal | None = None,
    reuse_existing: bool = True,
) -> RefundRequest:
    order = get_order(db, customer, order_number)
    locked_order = db.scalar(select(Order).where(Order.id == order.id).with_for_update())
    if locked_order is not None:
        order = locked_order

    # A repeat request must return the existing operation even after it succeeded;
    # checking this before the amount validation avoids creating a second refund
    # after the order's refundable balance has been reduced to zero.
    existing = _active_refund(db, customer.id, order.id)
    if existing:
        if not reuse_existing:
            raise ConflictError(
                "REFUND_TARGET_CONFLICT",
                "该订单已有活动退款操作，不能从其他意图重复创建",
            )
        return existing

    amount = requested_amount if requested_amount is not None else order.refundable_amount
    if amount <= 0 or amount > order.refundable_amount:
        raise ValidationError("INVALID_REFUND_AMOUNT", "退款金额不能超过当前可退金额")

    ticket = create_ticket(
        db,
        customer,
        conversation_id=conversation_id,
        order_number=order_number,
        ticket_type="REFUND",
        reason=reason,
        evidence={"server_calculated_refundable_amount": str(order.refundable_amount)},
        commit=False,
    )
    if ticket.status == TicketStatus.OPEN.value:
        transition_ticket(
            db,
            ticket,
            TicketStatus.WAITING_APPROVAL.value,
            actor="system",
            detail="退款申请已创建，等待客服人工审批和客户明确确认",
        )
    refund = RefundRequest(
        refund_number=_refund_number(),
        customer_id=customer.id,
        order_id=order.id,
        ticket_id=ticket.id,
        reason=reason,
        amount=amount,
        status=RefundStatus.PENDING_HUMAN_APPROVAL.value,
    )
    db.add(refund)
    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        existing = _active_refund(db, customer.id, order.id)
        if existing:
            if not reuse_existing:
                raise ConflictError(
                    "REFUND_TARGET_CONFLICT",
                    "该订单已有并发退款操作，不能从其他意图重复创建",
                ) from err
            return existing
        raise ConflictError(
            "REFUND_TARGET_CONFLICT",
            "该订单已有并发退款操作，不能重复创建",
        ) from None
    db.refresh(refund)
    return refund


def get_refund(db: Session, customer: Customer, refund_id: str) -> RefundRequest:
    return _owned_refund(db, customer, refund_id)


def _idempotency_response(
    db: Session, scope: str, idempotency_key: str
) -> RefundResponse | None:
    previous = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    if previous:
        return RefundResponse.model_validate(previous.response_json)
    return None


def _record_idempotency(
    db: Session,
    *,
    scope: str,
    idempotency_key: str,
    refund: RefundRequest,
    response: RefundResponse,
) -> None:
    db.add(
        IdempotencyRecord(
            scope=scope,
            idempotency_key=idempotency_key,
            resource_id=refund.id,
            response_json=response.model_dump(mode="json"),
        )
    )


def _decide_refund(
    db: Session,
    operator: Operator,
    refund_id: str,
    idempotency_key: str,
    *,
    decision: str,
    reason: str | None = None,
) -> RefundResponse:
    if operator.role != "SUPPORT_AGENT":
        raise ForbiddenError("只有客服坐席可以执行退款人工审批")
    key = _validated_idempotency_key(idempotency_key)
    scope = f"refund_approval:{refund_id}:{decision}"
    prior_audit = db.scalar(
        select(RefundApprovalAudit).where(
            RefundApprovalAudit.refund_request_id == refund_id,
            RefundApprovalAudit.idempotency_key == key,
        )
    )
    if prior_audit:
        if prior_audit.operator_id != operator.id or prior_audit.decision != decision:
            raise ConflictError(
                "IDEMPOTENCY_KEY_REUSE",
                "幂等键已绑定其他退款审批人或审批决定",
            )
        replay = _idempotency_response(db, scope, key)
        if replay is not None:
            return replay
        raise ConflictError("REFUND_APPROVAL_CONFLICT", "审批审计记录已存在但响应记录缺失")

    refund = _refund_by_id(db, refund_id, for_update=True)
    prior_audit = db.scalar(
        select(RefundApprovalAudit).where(
            RefundApprovalAudit.refund_request_id == refund.id,
            RefundApprovalAudit.idempotency_key == key,
        )
    )
    if prior_audit:
        if prior_audit.operator_id != operator.id or prior_audit.decision != decision:
            raise ConflictError(
                "IDEMPOTENCY_KEY_REUSE",
                "幂等键已绑定其他退款审批人或审批决定",
            )
        replay = _idempotency_response(db, scope, key)
        if replay is not None:
            return replay
        raise ConflictError("REFUND_APPROVAL_CONFLICT", "审批审计记录已存在但响应记录缺失")

    if decision == APPROVAL:
        if refund.status != RefundStatus.PENDING_HUMAN_APPROVAL.value:
            raise ConflictError(
                "REFUND_NOT_PENDING_HUMAN_APPROVAL",
                f"当前退款状态 {refund.status} 不能人工审批",
            )
        next_status = RefundStatus.PENDING_CONFIRMATION.value
        normalized_reason = None
    elif decision == REJECTION:
        if refund.status != RefundStatus.PENDING_HUMAN_APPROVAL.value:
            raise ConflictError(
                "REFUND_NOT_PENDING_HUMAN_APPROVAL",
                f"当前退款状态 {refund.status} 不能拒绝",
            )
        normalized_reason = (reason or "").strip()
        if len(normalized_reason) < 2:
            raise ValidationError("REFUND_DECISION_REASON_REQUIRED", "拒绝退款必须填写原因")
        next_status = RefundStatus.REJECTED.value
    elif decision == WITHDRAWAL:
        if refund.status != RefundStatus.PENDING_CONFIRMATION.value:
            raise ConflictError(
                "REFUND_NOT_PENDING_CONFIRMATION",
                f"当前退款状态 {refund.status} 不能撤回",
            )
        normalized_reason = (reason or "").strip()
        if len(normalized_reason) < 2:
            raise ValidationError("REFUND_DECISION_REASON_REQUIRED", "撤回退款必须填写原因")
        next_status = RefundStatus.WITHDRAWN.value
    else:
        raise ValidationError("INVALID_REFUND_DECISION", "不支持的退款审批决定")

    now = utcnow()
    refund.status = next_status
    refund.version += 1
    refund.updated_at = now
    if decision == APPROVAL:
        refund.approved_by_operator_id = operator.id
        refund.approved_at = now
    audit = RefundApprovalAudit(
        refund_request_id=refund.id,
        operator_id=operator.id,
        decision=decision,
        reason=normalized_reason,
        idempotency_key=key,
        created_at=now,
    )
    db.add(audit)
    response = refund_response(refund)
    _record_idempotency(
        db,
        scope=scope,
        idempotency_key=key,
        refund=refund,
        response=response,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = _idempotency_response(db, scope, key)
        if replay is not None:
            return replay
        raise ConflictError(
            "REFUND_APPROVAL_CONFLICT",
            "并发审批冲突，请读取当前退款状态后重试",
        ) from None
    return response


def approve_refund(
    db: Session, operator: Operator, refund_id: str, idempotency_key: str
) -> RefundResponse:
    return _decide_refund(
        db,
        operator,
        refund_id,
        idempotency_key,
        decision=APPROVAL,
    )


def reject_refund(
    db: Session,
    operator: Operator,
    refund_id: str,
    idempotency_key: str,
    reason: str | None,
) -> RefundResponse:
    return _decide_refund(
        db,
        operator,
        refund_id,
        idempotency_key,
        decision=REJECTION,
        reason=reason,
    )


def withdraw_refund(
    db: Session,
    operator: Operator,
    refund_id: str,
    idempotency_key: str,
    reason: str | None,
) -> RefundResponse:
    return _decide_refund(
        db,
        operator,
        refund_id,
        idempotency_key,
        decision=WITHDRAWAL,
        reason=reason,
    )


def _confirm_once(
    db: Session,
    customer: Customer,
    refund_id: str,
    key: str,
) -> RefundResponse:
    scope = f"refund_confirm:{refund_id}"
    replay = _idempotency_response(db, scope, key)
    if replay is not None:
        return replay

    refund = _owned_refund(db, customer, refund_id, for_update=True)
    # The first lookup can race with the transaction that owns the same key;
    # re-read it after acquiring the refund lock so a concurrent retry returns
    # the original response instead of being misclassified as a new execution.
    replay = _idempotency_response(db, scope, key)
    if replay is not None:
        return replay
    # A different key must never turn an already completed operation into a
    # second success response. It is an explicit conflict, not a new action.
    if refund.status == RefundStatus.SUCCEEDED.value:
        raise ConflictError(
            "REFUND_ALREADY_EXECUTED",
            "该退款已执行完成，不能使用新的幂等键重复执行",
        )
    if refund.status == RefundStatus.PENDING_HUMAN_APPROVAL.value:
        raise ConflictError(
            "REFUND_HUMAN_APPROVAL_REQUIRED",
            "退款尚未经过客服人工审批，不能确认或执行",
        )
    if refund.status in {
        RefundStatus.REJECTED.value,
        RefundStatus.WITHDRAWN.value,
        RefundStatus.CANCELLED.value,
    }:
        raise ConflictError(
            "REFUND_NOT_APPROVED",
            f"当前退款状态 {refund.status} 不允许确认或执行",
        )
    if refund.status != RefundStatus.PENDING_CONFIRMATION.value:
        raise ConflictError("INVALID_REFUND_STATE", f"当前退款状态 {refund.status} 不能确认")
    if not refund.approved_by_operator_id or refund.approved_at is None:
        raise ConflictError(
            "REFUND_HUMAN_APPROVAL_REQUIRED",
            "退款缺少可验证的客服人工审批记录，不能确认或执行",
        )

    order = db.scalar(select(Order).where(Order.id == refund.order_id).with_for_update())
    if order is None:
        raise NotFoundError("关联订单不存在")
    if Decimal(refund.amount) > Decimal(order.refundable_amount):
        raise ValidationError("REFUND_AMOUNT_CHANGED", "可退金额已变化，请重新发起退款")

    current_version = refund.version
    claimed = db.execute(
        update(RefundRequest)
        .where(
            RefundRequest.id == refund.id,
            RefundRequest.status == RefundStatus.PENDING_CONFIRMATION.value,
            RefundRequest.version == current_version,
        )
        .values(
            status=RefundStatus.PROCESSING.value,
            version=current_version + 1,
            updated_at=utcnow(),
        )
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise ConflictError(
            "REFUND_CONCURRENCY_CONFLICT",
            "退款已被其他请求处理，请读取当前状态",
        )
    refund.status = RefundStatus.PROCESSING.value
    refund.version = current_version + 1
    refund.updated_at = utcnow()

    # This deterministic adapter is local-only. There is deliberately no
    # payment provider, network request, hidden API, or external write here.
    refund.status = RefundStatus.SUCCEEDED.value
    refund.confirmed_at = utcnow()
    refund.version += 1
    refund.updated_at = utcnow()
    order.refundable_amount = Decimal("0.00")
    order.status = "REFUNDED"
    order.updated_at = utcnow()
    ticket = db.get(Ticket, refund.ticket_id)
    if ticket and ticket.status == TicketStatus.WAITING_APPROVAL.value:
        transition_ticket(
            db,
            ticket,
            TicketStatus.RESOLVED.value,
            actor=f"customer:{customer.id}",
            detail="客服人工审批且用户确认后模拟退款成功，工单已解决",
        )
    response = refund_response(refund)
    _record_idempotency(
        db,
        scope=scope,
        idempotency_key=key,
        refund=refund,
        response=response,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = _idempotency_response(db, scope, key)
        if replay is not None:
            return replay
        raise ConflictError(
            "REFUND_EXECUTION_CONFLICT",
            "退款执行发生并发冲突，请读取当前状态",
        ) from None
    return response


def confirm_refund(
    db: Session,
    customer: Customer,
    refund_id: str,
    idempotency_key: str,
) -> RefundResponse:
    key = _validated_idempotency_key(idempotency_key)
    for attempt in range(3):
        try:
            return _confirm_once(db, customer, refund_id, key)
        except OperationalError as exc:
            db.rollback()
            if "locked" not in str(exc).lower() or attempt == 2:
                raise ConflictError(
                    "REFUND_CONCURRENCY_CONFLICT",
                    "退款数据库事务冲突，请稍后读取状态重试",
                ) from exc
            time.sleep(0.02 * (attempt + 1))
    raise ConflictError("REFUND_CONCURRENCY_CONFLICT", "退款数据库事务冲突")


def cancel_refund(db: Session, customer: Customer, refund_id: str) -> RefundResponse:
    refund = _owned_refund(db, customer, refund_id, for_update=True)
    if refund.status not in {
        RefundStatus.PENDING_HUMAN_APPROVAL.value,
        RefundStatus.PENDING_CONFIRMATION.value,
    }:
        raise ConflictError("INVALID_REFUND_STATE", f"当前退款状态 {refund.status} 不能取消")
    refund.status = RefundStatus.CANCELLED.value
    refund.version += 1
    refund.updated_at = utcnow()
    db.commit()
    return refund_response(refund)
