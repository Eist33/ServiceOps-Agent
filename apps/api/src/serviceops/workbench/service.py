from datetime import datetime

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from serviceops.conversations.intents import (
    intent_history_snapshots,
    record_intent_event,
)
from serviceops.models import (
    Conversation,
    Customer,
    HandoffStatus,
    Operator,
    Order,
    RefundRequest,
    RefundStatus,
    Ticket,
    TicketEvent,
    TicketStatus,
    utcnow,
)
from serviceops.refunds.service import (
    ACTIVE_REFUND_STATUSES,
    create_refund_request,
    refund_response,
)
from serviceops.shared.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from serviceops.shared.schemas import AgentTicketResponse
from serviceops.tickets.service import (
    TICKET_ROUTING,
    ticket_message_snapshots,
    ticket_sla,
    transition_ticket,
)


def _get_ticket(db: Session, ticket_id: str) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise NotFoundError("工单不存在")
    return ticket


def _support_group(ticket: Ticket) -> str:
    return TICKET_ROUTING[ticket.ticket_type][2]


def _require_current_assignee(ticket: Ticket, operator: Operator) -> None:
    if ticket.status == TicketStatus.RESOLVED.value:
        raise ConflictError("TICKET_ALREADY_RESOLVED", "工单已经解决")
    if ticket.handoff_status != HandoffStatus.ASSIGNED.value:
        raise ConflictError("TICKET_NOT_HANDED_OFF", "工单当前不在人工处理队列")
    if ticket.assignee_name != operator.name:
        raise ConflictError("TICKET_NOT_ACCEPTED", "请先受理该工单再进行处理")


def workbench_ticket_response(
    db: Session,
    ticket: Ticket,
    *,
    operator: Operator | None = None,
    now: datetime | None = None,
) -> AgentTicketResponse:
    order = db.get(Order, ticket.order_id)
    customer = db.get(Customer, ticket.customer_id)
    if not order or not customer:
        raise NotFoundError("工单关联的订单或客户不存在")
    events = list(
        db.scalars(
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket.id)
            .order_by(TicketEvent.created_at.asc())
        )
    )
    support_group = _support_group(ticket)
    refund_record = None
    if ticket.ticket_type == "REFUND":
        refund_record = db.scalar(
            select(RefundRequest)
            .where(RefundRequest.ticket_id == ticket.id)
            .order_by(RefundRequest.created_at.desc())
        )
    refund_pending = refund_record is not None and refund_record.status in {
        RefundStatus.PENDING_HUMAN_APPROVAL.value,
        RefundStatus.PENDING_CONFIRMATION.value,
    }
    if ticket.status == TicketStatus.RESOLVED.value:
        work_state = "RESOLVED"
    elif ticket.assignee_name == support_group or refund_pending:
        work_state = "QUEUED"
    else:
        work_state = "IN_PROGRESS"
    sla_status, remaining_minutes = ticket_sla(ticket, now=now)
    refund = refund_response(refund_record) if refund_record is not None else None
    conversation = db.get(Conversation, ticket.conversation_id)
    intent_history = intent_history_snapshots(db, ticket.conversation_id)
    return AgentTicketResponse(
        id=ticket.id,
        ticket_number=ticket.ticket_number,
        conversation_id=ticket.conversation_id,
        order_number=order.order_number,
        customer_name=customer.name,
        product_name=order.product_name,
        ticket_type=ticket.ticket_type,
        status=ticket.status,
        priority=ticket.priority,
        handoff_status=ticket.handoff_status,
        work_state=work_state,
        support_group=support_group,
        assignee_name=ticket.assignee_name,
        is_mine=operator is not None and ticket.assignee_name == operator.name,
        sla_due_at=ticket.sla_due_at,
        sla_status=sla_status,
        sla_remaining_minutes=remaining_minutes,
        reason=ticket.reason,
        evidence=ticket.evidence,
        version=ticket.version,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        messages=ticket_message_snapshots(events),
        events=[
            {
                "action": event.action,
                "detail": event.detail,
                "actor": event.actor,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ],
        refund=refund,
        current_intent=conversation.current_intent if conversation else None,
        intent_history=intent_history,
    )


def list_workbench_tickets(
    db: Session,
    operator: Operator,
) -> list[AgentTicketResponse]:
    tickets = list(
        db.scalars(
            select(Ticket)
            .where(
                or_(
                    Ticket.handoff_status.in_(
                        [HandoffStatus.ASSIGNED.value, HandoffStatus.COMPLETED.value]
                    ),
                    and_(
                        Ticket.ticket_type == "REFUND",
                        Ticket.id.in_(
                            select(RefundRequest.ticket_id).where(
                                RefundRequest.status.in_(
                                    [
                                        RefundStatus.PENDING_HUMAN_APPROVAL.value,
                                        RefundStatus.PENDING_CONFIRMATION.value,
                                    ]
                                )
                            )
                        ),
                    ),
                )
            )
            .order_by(Ticket.updated_at.desc())
        )
    )
    return [
        workbench_ticket_response(db, ticket, operator=operator) for ticket in tickets
    ]


def change_workbench_intent(
    db: Session,
    operator: Operator,
    ticket_id: str,
    *,
    intent: str,
    reason: str,
    order_number: str | None = None,
) -> AgentTicketResponse:
    if operator.role != "SUPPORT_AGENT":
        raise ForbiddenError("只有客服坐席可以变更客户意图")
    if intent != "REFUND":
        raise ValidationError("UNSUPPORTED_INTENT_CHANGE", "当前仅支持转为退款意图")
    source_ticket = _get_ticket(db, ticket_id)
    if source_ticket.status == TicketStatus.RESOLVED.value:
        raise ConflictError("TICKET_ALREADY_RESOLVED", "已解决工单不能继续变更客户意图")
    if source_ticket.handoff_status != HandoffStatus.ASSIGNED.value:
        raise ConflictError("TICKET_NOT_HANDED_OFF", "请先将工单转人工后再变更客户意图")
    if source_ticket.assignee_name not in {
        operator.name,
        _support_group(source_ticket),
    }:
        raise ConflictError(
            "TICKET_NOT_ASSIGNED_TO_OPERATOR",
            "当前坐席不能变更其他坐席已受理的工单意图",
        )
    if source_ticket.ticket_type == "REFUND":
        raise ConflictError(
            "INTENT_ALREADY_REFUND",
            "当前工单已经是退款处理事项，不能再次创建退款意图",
        )
    normalized_reason = reason.strip()
    if len(normalized_reason) < 2:
        raise ValidationError("REFUND_INTENT_REASON_REQUIRED", "退款意图必须填写原因")
    order = db.get(Order, source_ticket.order_id)
    if order is None:
        raise NotFoundError("工单关联的订单不存在")
    if order_number is not None and order_number.strip().upper() != order.order_number:
        raise ConflictError(
            "INTENT_ORDER_MISMATCH",
            "新意图必须继续关联原工单订单，不能跨订单覆盖原工单",
        )

    existing = db.scalar(
        select(RefundRequest).where(
            RefundRequest.customer_id == source_ticket.customer_id,
            RefundRequest.order_id == source_ticket.order_id,
            RefundRequest.status.in_(ACTIVE_REFUND_STATUSES),
        )
    )
    if existing is not None:
        raise ConflictError(
            "REFUND_INTENT_ALREADY_ACTIVE",
            "该订单已有活动退款事项，请先处理现有退款事项",
        )

    customer = db.get(Customer, source_ticket.customer_id)
    if customer is None:
        raise NotFoundError("工单关联的客户不存在")
    conversation = db.get(Conversation, source_ticket.conversation_id)
    if conversation is None:
        raise NotFoundError("工单关联的会话不存在")
    if conversation.current_intent is None:
        record_intent_event(
            db,
            conversation.id,
            "SHIPPING_TICKET" if source_ticket.ticket_type == "SHIPPING" else source_ticket.ticket_type,
            actor="system",
            source="LEGACY_TICKET",
            source_ticket_id=source_ticket.id,
            detail="从既有工单恢复当前意图",
        )

    refund = create_refund_request(
        db,
        customer,
        conversation_id=conversation.id,
        order_number=order.order_number,
        reason=normalized_reason,
        requested_amount=order.refundable_amount,
        reuse_existing=False,
    )
    current_time = utcnow()
    source_ticket.updated_at = current_time
    source_ticket.version += 1
    db.add(
        TicketEvent(
            ticket_id=source_ticket.id,
            action="INTENT_CHANGED",
            detail=(
                f"客户后续意图从 {conversation.current_intent or source_ticket.ticket_type} "
                f"切换为 REFUND，新退款事项为 {refund.refund_number}"
            ),
            actor=operator.name,
            created_at=current_time,
        )
    )
    record_intent_event(
        db,
        conversation.id,
        "REFUND",
        actor=operator.name,
        source="SUPPORT_AGENT_ACTION",
        source_ticket_id=source_ticket.id,
        related_ticket_id=refund.ticket_id,
        related_refund_id=refund.id,
        detail=f"客服将客户后续意图切换为退款，原因：{normalized_reason}",
        now=current_time,
    )
    db.commit()
    new_ticket = db.get(Ticket, refund.ticket_id)
    if new_ticket is None:
        raise NotFoundError("新退款处理事项不存在")
    return workbench_ticket_response(db, new_ticket, operator=operator, now=current_time)


def accept_workbench_ticket(
    db: Session,
    operator: Operator,
    ticket_id: str,
    *,
    now: datetime | None = None,
) -> AgentTicketResponse:
    ticket = _get_ticket(db, ticket_id)
    if ticket.status == TicketStatus.RESOLVED.value:
        raise ConflictError("TICKET_ALREADY_RESOLVED", "已解决工单不能再次受理")
    if ticket.handoff_status != HandoffStatus.ASSIGNED.value:
        raise ConflictError("TICKET_NOT_HANDED_OFF", "工单当前不在人工处理队列")
    if ticket.assignee_name == operator.name:
        return workbench_ticket_response(db, ticket, operator=operator, now=now)
    support_group = _support_group(ticket)
    if ticket.assignee_name != support_group:
        raise ConflictError(
            "TICKET_ALREADY_ACCEPTED",
            f"工单已由 {ticket.assignee_name} 受理",
        )

    current_time = now or utcnow()
    current_version = ticket.version
    claimed = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket.id,
            Ticket.handoff_status == HandoffStatus.ASSIGNED.value,
            Ticket.assignee_name == support_group,
            Ticket.version == current_version,
        )
        .values(
            assignee_name=operator.name,
            updated_at=current_time,
            version=current_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        current_ticket = _get_ticket(db, ticket_id)
        if current_ticket.assignee_name == operator.name:
            return workbench_ticket_response(
                db,
                current_ticket,
                operator=operator,
                now=now,
            )
        if current_ticket.assignee_name != _support_group(current_ticket):
            raise ConflictError(
                "TICKET_ALREADY_ACCEPTED",
                f"工单已由 {current_ticket.assignee_name} 受理",
            )
        raise ConflictError("TICKET_STATE_CHANGED", "工单状态已变化，请刷新后重试")
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            action="HUMAN_HANDOFF_ACCEPTED",
            detail=f"{operator.name} 受理工单，所属队列为{support_group}",
            actor=operator.name,
            created_at=current_time,
        )
    )
    db.commit()
    db.refresh(ticket)
    return workbench_ticket_response(
        db,
        ticket,
        operator=operator,
        now=current_time,
    )


def add_workbench_note(
    db: Session,
    operator: Operator,
    ticket_id: str,
    content: str,
    *,
    now: datetime | None = None,
) -> AgentTicketResponse:
    ticket = _get_ticket(db, ticket_id)
    _require_current_assignee(ticket, operator)
    note = content.strip()
    if not note:
        raise ValidationError("EMPTY_AGENT_NOTE", "处理记录不能为空")
    current_time = now or utcnow()
    ticket.updated_at = current_time
    ticket.version += 1
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            action="AGENT_NOTE_ADDED",
            detail=note,
            actor=operator.name,
            created_at=current_time,
        )
    )
    db.commit()
    db.refresh(ticket)
    return workbench_ticket_response(
        db,
        ticket,
        operator=operator,
        now=current_time,
    )


def add_workbench_reply(
    db: Session,
    operator: Operator,
    ticket_id: str,
    content: str,
    *,
    now: datetime | None = None,
) -> AgentTicketResponse:
    ticket = _get_ticket(db, ticket_id)
    _require_current_assignee(ticket, operator)
    message = content.strip()
    if not message:
        raise ValidationError("EMPTY_TICKET_MESSAGE", "回复内容不能为空")

    current_time = now or utcnow()
    ticket.updated_at = current_time
    ticket.version += 1
    conversation = db.get(Conversation, ticket.conversation_id)
    if conversation:
        conversation.updated_at = current_time
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            action="AGENT_REPLY_SENT",
            detail=message,
            actor=operator.name,
            created_at=current_time,
        )
    )
    db.commit()
    db.refresh(ticket)
    return workbench_ticket_response(
        db,
        ticket,
        operator=operator,
        now=current_time,
    )


def resolve_workbench_ticket(
    db: Session,
    operator: Operator,
    ticket_id: str,
    resolution: str,
    *,
    now: datetime | None = None,
) -> AgentTicketResponse:
    ticket = _get_ticket(db, ticket_id)
    _require_current_assignee(ticket, operator)
    detail = resolution.strip()
    if not detail:
        raise ValidationError("EMPTY_RESOLUTION", "解决说明不能为空")
    current_time = now or utcnow()
    transition_ticket(
        db,
        ticket,
        TicketStatus.RESOLVED.value,
        actor=operator.name,
        detail=detail,
    )
    ticket.updated_at = current_time
    db.commit()
    db.refresh(ticket)
    return workbench_ticket_response(
        db,
        ticket,
        operator=operator,
        now=current_time,
    )
