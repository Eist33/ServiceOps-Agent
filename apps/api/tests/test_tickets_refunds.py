from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from serviceops.conversations.service import create_conversation
from serviceops.identity.service import resolve_customer, resolve_operator
from serviceops.models import (
    HandoffStatus,
    IdempotencyRecord,
    Order,
    RefundApprovalAudit,
    RefundRequest,
    RefundStatus,
    Ticket,
    TicketEvent,
    TicketStatus,
)
from serviceops.refunds.service import (
    approve_refund,
    cancel_refund,
    confirm_refund,
    create_refund_request,
    reject_refund,
    withdraw_refund,
)
from serviceops.seed import AGENT_SESSION_TOKEN, SECOND_AGENT_SESSION_TOKEN
from serviceops.shared.errors import ConflictError, ForbiddenError, ValidationError
from serviceops.tickets.service import (
    cancel_human_handoff,
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


def approve_for_test(db, refund, token=AGENT_SESSION_TOKEN, key="approval-key"):
    operator = resolve_operator(db, token)
    return approve_refund(db, operator, refund.id, key)


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


def test_new_conversation_creates_a_distinct_active_ticket(db):
    customer, first_conversation = make_conversation(db)
    second_conversation = create_conversation(db, customer)
    first = create_ticket(
        db,
        customer,
        conversation_id=first_conversation.id,
        order_number="ORD-20260828-1042",
        ticket_type="SHIPPING",
        reason="首次会话物流停滞",
    )
    second = create_ticket(
        db,
        customer,
        conversation_id=second_conversation.id,
        order_number="ORD-20260828-1042",
        ticket_type="SHIPPING",
        reason="新会话再次反馈物流停滞",
    )

    assert first.id != second.id
    assert first.ticket_number != second.ticket_number
    assert db.scalar(select(func.count()).select_from(Ticket)) == 2


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


def test_assigned_handoff_can_be_cancelled_and_requested_again(db):
    customer, conversation = make_conversation(db)
    ticket = create_ticket(
        db,
        customer,
        conversation_id=conversation.id,
        order_number="ORD-20260828-1042",
        ticket_type="SHIPPING",
        reason="物流停滞",
    )
    assigned = request_human_handoff(db, customer, ticket.id)
    cancelled = cancel_human_handoff(db, customer, assigned.id)

    assert cancelled.handoff_status == HandoffStatus.BOT_ACTIVE.value
    assert cancelled.assignee_name is None
    assert cancelled.handoff_requested_at is None
    assert cancelled.assigned_at is None
    assert db.scalar(
        select(func.count())
        .select_from(TicketEvent)
        .where(
            TicketEvent.ticket_id == ticket.id,
            TicketEvent.action == "HUMAN_HANDOFF_CANCELLED",
        )
    ) == 1

    reassigned = request_human_handoff(db, customer, ticket.id)
    assert reassigned.handoff_status == HandoffStatus.ASSIGNED.value
    assert reassigned.assignee_name == "物流专员组"


def test_handoff_cancellation_requires_an_assignment(db):
    customer, conversation = make_conversation(db)
    ticket = create_ticket(
        db,
        customer,
        conversation_id=conversation.id,
        order_number="ORD-20260828-1042",
        ticket_type="SHIPPING",
        reason="物流停滞",
    )

    with pytest.raises(ConflictError):
        cancel_human_handoff(db, customer, ticket.id)


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
    assert refund.status == RefundStatus.PENDING_HUMAN_APPROVAL.value


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


def test_confirm_fails_closed_before_human_approval(db):
    customer, refund = make_refund(db)
    with pytest.raises(ConflictError, match="人工审批") as error:
        confirm_refund(db, customer, refund.id, "before-approval")
    assert error.value.code == "REFUND_HUMAN_APPROVAL_REQUIRED"
    assert db.get(RefundRequest, refund.id).status == RefundStatus.PENDING_HUMAN_APPROVAL.value
    assert db.scalar(select(func.count()).select_from(RefundApprovalAudit)) == 0


def test_legacy_pending_confirmation_without_approval_fails_closed(db):
    customer, refund = make_refund(db)
    refund.status = RefundStatus.PENDING_CONFIRMATION.value
    db.commit()
    with pytest.raises(ConflictError) as error:
        confirm_refund(db, customer, refund.id, "legacy-without-approval")
    assert error.value.code == "REFUND_HUMAN_APPROVAL_REQUIRED"
    assert db.get(RefundRequest, refund.id).status == RefundStatus.PENDING_CONFIRMATION.value


def test_confirm_succeeds_and_resolves_ticket(db):
    customer, refund = make_refund(db)
    approval = approve_for_test(db, refund)
    assert approval.status == RefundStatus.PENDING_CONFIRMATION.value
    assert approval.approved_by_operator_id is not None
    assert approval.approved_at is not None
    result = confirm_refund(db, customer, refund.id, "confirm-1")
    assert result.status == RefundStatus.SUCCEEDED.value
    assert db.get(Ticket, refund.ticket_id).status == TicketStatus.RESOLVED.value
    order = db.get(Order, refund.order_id)
    assert order.refundable_amount == Decimal("0.00")
    assert order.status == "REFUNDED"


def test_same_key_returns_first_result(db):
    customer, refund = make_refund(db)
    approve_for_test(db, refund)
    first = confirm_refund(db, customer, refund.id, "same-key")
    second = confirm_refund(db, customer, refund.id, "same-key")
    assert first == second
    assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 2


def test_different_key_never_executes_second_refund(db):
    customer, refund = make_refund(db)
    approve_for_test(db, refund)
    first = confirm_refund(db, customer, refund.id, "key-a")
    with pytest.raises(ConflictError) as error:
        confirm_refund(db, customer, refund.id, "key-b")
    assert error.value.code == "REFUND_ALREADY_EXECUTED"
    assert first.status == RefundStatus.SUCCEEDED.value
    assert db.scalar(select(func.count()).select_from(RefundRequest)) == 1
    assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 2


def test_same_target_after_success_returns_existing_refund(db):
    customer, refund = make_refund(db)
    approve_for_test(db, refund)
    confirm_refund(db, customer, refund.id, "success-key")
    existing = create_refund_request(
        db,
        customer,
        conversation_id=db.get(Ticket, refund.ticket_id).conversation_id,
        order_number="ORD-20260828-1042",
        reason="重复申请",
    )
    assert existing.id == refund.id
    assert existing.status == RefundStatus.SUCCEEDED.value


def test_database_rejects_two_active_refunds_for_same_target(db):
    customer, refund = make_refund(db)
    duplicate = RefundRequest(
        refund_number="RF-DUPLICATE-TARGET",
        customer_id=customer.id,
        order_id=refund.order_id,
        ticket_id=refund.ticket_id,
        status=RefundStatus.PENDING_HUMAN_APPROVAL.value,
        reason="并发重复",
        amount=Decimal("1.00"),
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_approval_is_bound_to_operator_and_audited(db):
    _, refund = make_refund(db)
    result = approve_for_test(db, refund)
    audit = db.scalar(select(RefundApprovalAudit).where(RefundApprovalAudit.refund_request_id == refund.id))
    assert result.approved_by_operator_id == audit.operator_id
    assert result.approved_at.replace(tzinfo=None) == audit.created_at.replace(tzinfo=None)
    assert audit.decision == "APPROVED"


def test_same_approval_key_returns_first_audited_result(db):
    _, refund = make_refund(db)
    first = approve_for_test(db, refund, key="approval-retry")
    second = approve_for_test(db, refund, key="approval-retry")
    assert first == second
    assert db.scalar(select(func.count()).select_from(RefundApprovalAudit)) == 1


def test_approval_key_cannot_cross_operator_boundary(db):
    _, refund = make_refund(db)
    approve_for_test(db, refund, token=AGENT_SESSION_TOKEN, key="bound-key")
    other_operator = resolve_operator(db, SECOND_AGENT_SESSION_TOKEN)
    with pytest.raises(ConflictError) as error:
        approve_refund(db, other_operator, refund.id, "bound-key")
    assert error.value.code == "IDEMPOTENCY_KEY_REUSE"


def test_different_approval_key_cannot_approve_twice(db):
    _, refund = make_refund(db)
    approve_for_test(db, refund, key="approval-a")
    operator = resolve_operator(db, AGENT_SESSION_TOKEN)
    with pytest.raises(ConflictError) as error:
        approve_refund(db, operator, refund.id, "approval-b")
    assert error.value.code == "REFUND_NOT_PENDING_HUMAN_APPROVAL"
    assert db.scalar(select(func.count()).select_from(RefundApprovalAudit)) == 1


def test_rejected_refund_cannot_be_confirmed(db):
    customer, refund = make_refund(db)
    operator = resolve_operator(db, AGENT_SESSION_TOKEN)
    result = reject_refund(db, operator, refund.id, "reject-key", "凭证不足")
    assert result.status == RefundStatus.REJECTED.value
    with pytest.raises(ConflictError) as error:
        confirm_refund(db, customer, refund.id, "after-reject")
    assert error.value.code == "REFUND_NOT_APPROVED"


def test_approved_refund_can_be_withdrawn_but_not_confirmed(db):
    customer, refund = make_refund(db)
    approve_for_test(db, refund)
    operator = resolve_operator(db, SECOND_AGENT_SESSION_TOKEN)
    result = withdraw_refund(db, operator, refund.id, "withdraw-key", "客户撤回申请")
    assert result.status == RefundStatus.WITHDRAWN.value
    with pytest.raises(ConflictError) as error:
        confirm_refund(db, customer, refund.id, "after-withdraw")
    assert error.value.code == "REFUND_NOT_APPROVED"


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
