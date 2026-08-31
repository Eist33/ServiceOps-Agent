from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from serviceops.conversations.service import create_conversation
from serviceops.identity.service import resolve_customer
from serviceops.models import (
    HandoffStatus,
    IdempotencyRecord,
    Order,
    RefundRequest,
    RefundStatus,
    Ticket,
    TicketEvent,
    TicketStatus,
)
from serviceops.refunds.service import cancel_refund, confirm_refund, create_refund_request
from serviceops.shared.errors import ConflictError, ForbiddenError, ValidationError
from serviceops.tickets.service import (
    create_ticket,
    get_ticket,
    request_human_handoff,
    ticket_sla,
    transition_ticket,
)


def make_conversation(db, token="demo-linmu-session"):
    customer = resolve_customer(db, token)
    return customer, create_conversation(db, customer)


def make_refund(db):
    customer, conversation = make_conversation(db)
    refund = create_refund_request(
        db,
        customer,
        conversation_id=conversation.id,
        order_number="ORD-20260828-1042",
        reason="不想要了",
    )
    return customer, refund


def test_ticket_create_is_idempotent(db):
    customer, conversation = make_conversation(db)
    first = create_ticket(
        db,
        customer,
        conversation_id=conversation.id,
        order_number="ORD-20260828-1042",
        ticket_type="SHIPPING",
        reason="物流停滞",
    )
    second = create_ticket(
        db,
        customer,
        conversation_id=conversation.id,
        order_number="ORD-20260828-1042",
        ticket_type="SHIPPING",
        reason="再次请求",
    )
    assert first.id == second.id
    assert db.scalar(select(func.count()).select_from(Ticket)) == 1


def test_ticket_gets_priority_and_sla_from_server_policy(db):
    customer, conversation = make_conversation(db)
    now = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)
    ticket = create_ticket(
        db,
        customer,
        conversation_id=conversation.id,
        order_number="ORD-20260828-1042",
        ticket_type="SHIPPING",
        reason="物流停滞",
        now=now,
    )
    assert ticket.priority == "P2"
    assert ticket.sla_due_at.replace(tzinfo=UTC) == now + timedelta(hours=4)
    assert ticket_sla(ticket, now=now) == ("ON_TRACK", 240)
    assert ticket_sla(ticket, now=now + timedelta(hours=3, minutes=30)) == (
        "DUE_SOON",
        30,
    )
    assert ticket_sla(ticket, now=now + timedelta(hours=5)) == ("BREACHED", 0)


def test_human_handoff_is_auto_assigned_and_idempotent(db):
    customer, conversation = make_conversation(db)
    ticket = create_ticket(
        db,
        customer,
        conversation_id=conversation.id,
        order_number="ORD-20260828-1042",
        ticket_type="SHIPPING",
        reason="物流停滞",
    )
    first = request_human_handoff(db, customer, ticket.id)
    second = request_human_handoff(db, customer, ticket.id)
    assert first.id == second.id
    assert first.handoff_status == HandoffStatus.ASSIGNED.value
    assert first.assignee_name == "物流专员组"
    assert first.handoff_requested_at is not None
    assert first.assigned_at is not None
    assert db.scalar(
        select(func.count())
        .select_from(TicketEvent)
        .where(
            TicketEvent.ticket_id == ticket.id,
            TicketEvent.action == "HUMAN_HANDOFF_ASSIGNED",
        )
    ) == 1
    transition_ticket(db, first, TicketStatus.RESOLVED.value, actor="test", detail="resolved")
    assert first.handoff_status == HandoffStatus.COMPLETED.value


def test_resolved_ticket_cannot_handoff(db):
    customer, conversation = make_conversation(db)
    ticket = create_ticket(
        db,
        customer,
        conversation_id=conversation.id,
        order_number="ORD-20260828-1042",
        ticket_type="SHIPPING",
        reason="物流停滞",
    )
    transition_ticket(db, ticket, TicketStatus.RESOLVED.value, actor="test", detail="resolved")
    db.commit()
    with pytest.raises(ConflictError):
        request_human_handoff(db, customer, ticket.id)


def test_ticket_illegal_transition_is_rejected(db):
    customer, conversation = make_conversation(db)
    ticket = create_ticket(
        db,
        customer,
        conversation_id=conversation.id,
        order_number="ORD-20260828-1042",
        ticket_type="SHIPPING",
        reason="物流停滞",
    )
    transition_ticket(db, ticket, TicketStatus.RESOLVED.value, actor="test", detail="resolved")
    db.commit()
    with pytest.raises(ConflictError):
        transition_ticket(db, ticket, TicketStatus.OPEN.value, actor="test", detail="reopen")


def test_ticket_access_is_owner_only(db):
    customer, conversation = make_conversation(db)
    ticket = create_ticket(
        db,
        customer,
        conversation_id=conversation.id,
        order_number="ORD-20260828-1042",
        ticket_type="SHIPPING",
        reason="物流停滞",
    )
    other = resolve_customer(db, "demo-other-session")
    with pytest.raises(ForbiddenError):
        get_ticket(db, other, ticket.id)


def test_refund_request_uses_server_amount(db):
    _, refund = make_refund(db)
    assert refund.amount == Decimal("329.00")
    assert refund.status == RefundStatus.PENDING_CONFIRMATION.value


def test_refund_amount_cannot_exceed_refundable(db):
    customer, conversation = make_conversation(db)
    with pytest.raises(ValidationError):
        create_refund_request(
            db,
            customer,
            conversation_id=conversation.id,
            order_number="ORD-20260828-1042",
            reason="test",
            requested_amount=Decimal("330.00"),
        )


def test_refund_request_is_idempotent_while_active(db):
    customer, first = make_refund(db)
    second = create_refund_request(
        db,
        customer,
        conversation_id=db.get(Ticket, first.ticket_id).conversation_id,
        order_number="ORD-20260828-1042",
        reason="again",
    )
    assert first.id == second.id


def test_confirm_requires_idempotency_key(db):
    customer, refund = make_refund(db)
    with pytest.raises(ValidationError):
        confirm_refund(db, customer, refund.id, "")


def test_confirm_succeeds_and_resolves_ticket(db):
    customer, refund = make_refund(db)
    result = confirm_refund(db, customer, refund.id, "confirm-1")
    assert result.status == RefundStatus.SUCCEEDED.value
    assert db.get(Ticket, refund.ticket_id).status == TicketStatus.RESOLVED.value
    order = db.get(Order, refund.order_id)
    assert order.refundable_amount == Decimal("0.00")
    assert order.status == "REFUNDED"


def test_same_key_returns_first_result(db):
    customer, refund = make_refund(db)
    first = confirm_refund(db, customer, refund.id, "same-key")
    second = confirm_refund(db, customer, refund.id, "same-key")
    assert first == second
    assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1


def test_different_key_never_executes_second_refund(db):
    customer, refund = make_refund(db)
    first = confirm_refund(db, customer, refund.id, "key-a")
    second = confirm_refund(db, customer, refund.id, "key-b")
    assert first.status == second.status == RefundStatus.SUCCEEDED.value
    assert db.scalar(select(func.count()).select_from(RefundRequest)) == 1
    assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 2


def test_cancel_keeps_refund_unexecuted(db):
    customer, refund = make_refund(db)
    result = cancel_refund(db, customer, refund.id)
    assert result.status == RefundStatus.CANCELLED.value
    assert result.confirmed_at is None


def test_cancelled_refund_cannot_be_confirmed(db):
    customer, refund = make_refund(db)
    cancel_refund(db, customer, refund.id)
    with pytest.raises(ConflictError):
        confirm_refund(db, customer, refund.id, "after-cancel")
