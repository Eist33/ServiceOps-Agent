from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.models import (
    Customer,
    HandoffStatus,
    Operator,
    Order,
    Ticket,
    TicketEvent,
    TicketStatus,
    utcnow,
)
from serviceops.shared.errors import ConflictError, NotFoundError, ValidationError
from serviceops.shared.schemas import AgentTicketResponse
from serviceops.tickets.service import TICKET_ROUTING, ticket_sla, transition_ticket


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
    if ticket.status == TicketStatus.RESOLVED.value:
        work_state = "RESOLVED"
    elif ticket.assignee_name == support_group:
        work_state = "QUEUED"
    else:
        work_state = "IN_PROGRESS"
    sla_status, remaining_minutes = ticket_sla(ticket, now=now)
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
        sla_due_at=ticket.sla_due_at,
        sla_status=sla_status,
        sla_remaining_minutes=remaining_minutes,
        reason=ticket.reason,
        evidence=ticket.evidence,
        version=ticket.version,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        events=[
            {
                "action": event.action,
                "detail": event.detail,
                "actor": event.actor,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ],
    )


def list_workbench_tickets(db: Session) -> list[AgentTicketResponse]:
    tickets = list(
        db.scalars(
            select(Ticket)
            .where(
                Ticket.handoff_status.in_(
                    [HandoffStatus.ASSIGNED.value, HandoffStatus.COMPLETED.value]
                )
            )
            .order_by(Ticket.updated_at.desc())
        )
    )
    return [workbench_ticket_response(db, ticket) for ticket in tickets]


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
        return workbench_ticket_response(db, ticket, now=now)
    support_group = _support_group(ticket)
    if ticket.assignee_name != support_group:
        raise ConflictError(
            "TICKET_ALREADY_ACCEPTED",
            f"工单已由 {ticket.assignee_name} 受理",
        )

    current_time = now or utcnow()
    ticket.assignee_name = operator.name
    ticket.updated_at = current_time
    ticket.version += 1
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
    return workbench_ticket_response(db, ticket, now=current_time)


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
    return workbench_ticket_response(db, ticket, now=current_time)


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
    return workbench_ticket_response(db, ticket, now=current_time)
