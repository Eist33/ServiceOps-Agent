import argparse
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from serviceops.cli import parse_as_of
from serviceops.database import Base
from serviceops.models import (
    AuthSession,
    Conversation,
    Customer,
    CustomerSatisfactionFeedback,
    IdempotencyRecord,
    IdentityAccount,
    Message,
    ModelInvocation,
    OperationsAlertAcknowledgement,
    Operator,
    Order,
    RefundRequest,
    RetentionRun,
    SecurityAuditEvent,
    Ticket,
    TicketEvent,
    ToolInvocation,
)
from serviceops.retention.service import (
    RETENTION_POLICY_VERSION,
    RetentionDataClass,
    is_expired,
    purge_expired_data,
    retention_cutoff,
)

AS_OF = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def test_cli_as_of_requires_timezone_and_normalizes_utc() -> None:
    assert parse_as_of("2026-09-05T12:00:00Z") == AS_OF
    assert parse_as_of("2026-09-05T20:00:00+08:00") == AS_OF
    with pytest.raises(argparse.ArgumentTypeError, match="--as-of 必须包含时区"):
        parse_as_of("2026-09-05T12:00:00")


def _customer(db, session_token: str) -> Customer:
    customer = db.scalar(select(Customer).where(Customer.session_token == session_token))
    assert customer is not None
    return customer


def _order(db, order_number: str) -> Order:
    order = db.scalar(select(Order).where(Order.order_number == order_number))
    assert order is not None
    return order


def test_retention_boundaries_are_strict_and_cover_all_documented_windows():
    expected_days = {
        RetentionDataClass.CHAT_MESSAGES: 180,
        RetentionDataClass.TICKET_DATA: 365,
        RetentionDataClass.AUTH_SECURITY_AUDIT: 180,
        RetentionDataClass.MODEL_INVOCATIONS: 30,
        RetentionDataClass.PARSE_FAILURE_DIAGNOSTICS: 7,
        RetentionDataClass.DATABASE_BACKUPS: 30,
    }

    for data_class, days in expected_days.items():
        cutoff = retention_cutoff(data_class, as_of=AS_OF)
        assert cutoff == AS_OF - timedelta(days=days)
        assert not is_expired(data_class, cutoff, as_of=AS_OF)
        assert is_expired(data_class, cutoff - timedelta(microseconds=1), as_of=AS_OF)


def test_purge_removes_expired_bodies_for_all_customers_and_keeps_live_data(db):
    old = AS_OF - timedelta(days=400)
    recent = AS_OF - timedelta(days=2)
    old_message_time = AS_OF - timedelta(days=181)
    old_model_time = AS_OF - timedelta(days=31)
    old_audit_time = AS_OF - timedelta(days=181)

    customer = _customer(db, "demo-linmu-session")
    other_customer = _customer(db, "demo-other-session")
    order = _order(db, "ORD-20260828-1042")
    other_order = _order(db, "ORD-20260827-9001")
    operator = db.scalar(select(Operator).where(Operator.role == "SUPPORT_AGENT"))
    identity = db.scalar(select(IdentityAccount).where(IdentityAccount.principal_id == customer.id))
    other_identity = db.scalar(
        select(IdentityAccount).where(IdentityAccount.principal_id == other_customer.id)
    )
    assert operator is not None
    assert identity is not None
    assert other_identity is not None

    chat_cutoff = retention_cutoff(RetentionDataClass.CHAT_MESSAGES, as_of=AS_OF)
    ticket_cutoff = retention_cutoff(RetentionDataClass.TICKET_DATA, as_of=AS_OF)
    model_cutoff = retention_cutoff(RetentionDataClass.MODEL_INVOCATIONS, as_of=AS_OF)
    audit_cutoff = retention_cutoff(RetentionDataClass.AUTH_SECURITY_AUDIT, as_of=AS_OF)

    stale_conversation = Conversation(
        customer_id=customer.id,
        created_at=old_message_time,
        updated_at=old_message_time,
    )
    other_stale_conversation = Conversation(
        customer_id=other_customer.id,
        created_at=old_message_time,
        updated_at=old_message_time,
    )
    active_conversation = Conversation(
        customer_id=customer.id,
        created_at=old_message_time,
        updated_at=recent,
    )
    boundary_conversation = Conversation(
        customer_id=other_customer.id,
        created_at=chat_cutoff,
        updated_at=chat_cutoff,
    )
    db.add_all(
        [
            stale_conversation,
            other_stale_conversation,
            active_conversation,
            boundary_conversation,
        ]
    )
    db.flush()
    db.add_all(
        [
            Message(
                conversation_id=stale_conversation.id,
                role="user",
                content="旧会话正文 A",
                created_at=old_message_time,
            ),
            Message(
                conversation_id=other_stale_conversation.id,
                role="user",
                content="旧会话正文 B",
                created_at=old_message_time,
            ),
            Message(
                conversation_id=active_conversation.id,
                role="user",
                content="活跃会话正文",
                created_at=old_message_time,
            ),
            Message(
                conversation_id=boundary_conversation.id,
                role="user",
                content="边界会话正文",
                created_at=chat_cutoff,
            ),
        ]
    )

    old_ticket = Ticket(
        ticket_number="TK-RETENTION-OLD",
        customer_id=customer.id,
        order_id=order.id,
        conversation_id=stale_conversation.id,
        ticket_type="SHIPPING",
        status="RESOLVED",
        priority="P2",
        handoff_status="COMPLETED",
        sla_due_at=old,
        reason="旧工单正文",
        evidence={"raw": "旧证据"},
        created_at=old,
        updated_at=old,
    )
    active_ticket = Ticket(
        ticket_number="TK-RETENTION-ACTIVE",
        customer_id=other_customer.id,
        order_id=other_order.id,
        conversation_id=other_stale_conversation.id,
        ticket_type="ORDER",
        status="OPEN",
        priority="P2",
        handoff_status="BOT_ACTIVE",
        sla_due_at=recent,
        reason="未到期工单",
        evidence={"keep": True},
        created_at=old,
        updated_at=old,
    )
    recent_ticket = Ticket(
        ticket_number="TK-RETENTION-NEW",
        customer_id=customer.id,
        order_id=order.id,
        conversation_id=active_conversation.id,
        ticket_type="OTHER",
        status="RESOLVED",
        priority="P3",
        handoff_status="COMPLETED",
        sla_due_at=recent,
        reason="近期工单正文",
        evidence={"keep": True},
        created_at=recent,
        updated_at=recent,
    )
    boundary_ticket = Ticket(
        ticket_number="TK-RETENTION-BOUNDARY",
        customer_id=other_customer.id,
        order_id=other_order.id,
        conversation_id=boundary_conversation.id,
        ticket_type="OTHER",
        status="RESOLVED",
        priority="P3",
        handoff_status="COMPLETED",
        sla_due_at=ticket_cutoff,
        reason="边界工单正文",
        evidence={"keep": True},
        created_at=ticket_cutoff,
        updated_at=ticket_cutoff,
    )
    db.add_all([old_ticket, active_ticket, recent_ticket, boundary_ticket])
    db.flush()

    db.add_all(
        [
            TicketEvent(
                ticket_id=old_ticket.id,
                action="STATUS_RESOLVED",
                detail="旧处理结果",
                actor="沈清禾",
                created_at=old,
            ),
            CustomerSatisfactionFeedback(
                ticket_id=old_ticket.id,
                customer_id=customer.id,
                rating=2,
                comment="旧评价正文",
                submitted_at=old,
                updated_at=old,
            ),
            RefundRequest(
                refund_number="RF-RETENTION-OLD",
                customer_id=customer.id,
                order_id=order.id,
                ticket_id=old_ticket.id,
                status="SUCCEEDED",
                reason="旧退款原因",
                amount=1,
                method="原路退回",
                confirmed_at=old,
                created_at=old,
                updated_at=old,
            ),
            OperationsAlertAcknowledgement(
                ticket_id=old_ticket.id,
                alert_type="SLA_BREACHED",
                acknowledged_by_operator_id=operator.id,
                acknowledged_by_name=operator.name,
                acknowledged_at=old,
            ),
            IdempotencyRecord(
                scope="refund_confirm:old",
                idempotency_key="old-key",
                resource_id=old_ticket.id,
                response_json={"ticket_id": old_ticket.id, "body": "旧响应"},
                created_at=old,
            ),
            IdempotencyRecord(
                scope="refund_confirm:old",
                idempotency_key="recent-key",
                resource_id=old_ticket.id,
                response_json={"ticket_id": old_ticket.id, "body": "近期旧工单响应"},
                created_at=recent,
            ),
            ToolInvocation(
                trace_id="old-tool-trace",
                conversation_id=stale_conversation.id,
                message_id="old-tool-message",
                tool_call_id="old-tool-call",
                tool_name="create_ticket",
                input_summary={"reason": "旧处理输入"},
                output_summary={"ticket_id": old_ticket.id, "body": "旧处理输出"},
                status="SUCCEEDED",
                created_at=old,
            ),
            ToolInvocation(
                trace_id="boundary-tool-trace",
                conversation_id=boundary_conversation.id,
                message_id="boundary-tool-message",
                tool_call_id="boundary-tool-call",
                tool_name="get_order",
                input_summary={"order": "边界"},
                output_summary={"status": "边界"},
                status="SUCCEEDED",
                created_at=ticket_cutoff,
            ),
            ToolInvocation(
                trace_id="new-tool-trace",
                conversation_id=active_conversation.id,
                message_id="new-tool-message",
                tool_call_id="new-tool-call",
                tool_name="get_order",
                input_summary={"order": "近期"},
                output_summary={"status": "近期"},
                status="SUCCEEDED",
                created_at=recent,
            ),
            ModelInvocation(
                trace_id="old-trace",
                conversation_id=stale_conversation.id,
                message_id="old-message",
                provider="deepseek",
                model_name="test-model",
                api_style="responses",
                status="SUCCEEDED",
                duration_ms=10,
                created_at=old_model_time,
            ),
            ModelInvocation(
                trace_id="old-other-trace",
                conversation_id=other_stale_conversation.id,
                message_id="old-other-message",
                provider="deepseek",
                model_name="test-model",
                api_style="responses",
                status="SUCCEEDED",
                duration_ms=10,
                created_at=old_model_time,
            ),
            ModelInvocation(
                trace_id="boundary-trace",
                conversation_id=boundary_conversation.id,
                message_id="boundary-message",
                provider="deepseek",
                model_name="test-model",
                api_style="responses",
                status="SUCCEEDED",
                duration_ms=10,
                created_at=model_cutoff,
            ),
            ModelInvocation(
                trace_id="new-trace",
                conversation_id=active_conversation.id,
                message_id="new-message",
                provider="deepseek",
                model_name="test-model",
                api_style="responses",
                status="SUCCEEDED",
                duration_ms=10,
                created_at=recent,
            ),
            SecurityAuditEvent(
                event_type="AUTH_LOGIN",
                outcome="SUCCEEDED",
                account_id=identity.id,
                principal_type="CUSTOMER",
                principal_id=customer.id,
                trace_id="old-audit-trace",
                created_at=old_audit_time,
            ),
            SecurityAuditEvent(
                event_type="AUTH_LOGIN",
                outcome="SUCCEEDED",
                account_id=other_identity.id,
                principal_type="CUSTOMER",
                principal_id=other_customer.id,
                trace_id="old-other-audit-trace",
                created_at=old_audit_time,
            ),
            SecurityAuditEvent(
                event_type="AUTH_LOGIN",
                outcome="SUCCEEDED",
                account_id=other_identity.id,
                principal_type="CUSTOMER",
                principal_id=other_customer.id,
                trace_id="boundary-audit-trace",
                created_at=audit_cutoff,
            ),
            SecurityAuditEvent(
                event_type="AUTH_LOGIN",
                outcome="SUCCEEDED",
                account_id=identity.id,
                principal_type="CUSTOMER",
                principal_id=customer.id,
                trace_id="new-audit-trace",
                created_at=recent,
            ),
            AuthSession(
                identity_account_id=identity.id,
                token_hash="a" * 64,
                expires_at=AS_OF - timedelta(minutes=1),
                created_at=recent,
            ),
            AuthSession(
                identity_account_id=identity.id,
                token_hash="b" * 64,
                expires_at=AS_OF + timedelta(days=1),
                revoked_at=AS_OF - timedelta(minutes=1),
                created_at=recent,
            ),
            AuthSession(
                identity_account_id=identity.id,
                token_hash="c" * 64,
                expires_at=AS_OF + timedelta(days=1),
                created_at=recent,
            ),
        ]
    )
    db.commit()

    report = purge_expired_data(db, as_of=AS_OF)

    assert report.policy_version == RETENTION_POLICY_VERSION
    assert report.deleted == {
        "auth_sessions": 2,
        "messages": 2,
        "model_invocations": 2,
        "tool_invocations": 1,
        "ticket_events": 1,
        "customer_feedback": 1,
        "refund_approval_audits": 0,
        "refund_requests": 1,
        "operations_alert_acknowledgements": 1,
        "idempotency_records": 2,
        "tickets": 1,
        "conversation_intent_events": 0,
    }
    assert report.anonymized == {"security_audit_events": 2}

    assert db.scalar(select(func.count(Message.id))) == 2
    assert db.scalar(select(func.count(Ticket.id))) == 3
    assert db.scalar(select(func.count(ModelInvocation.id))) == 2
    assert db.scalar(select(func.count(ToolInvocation.id))) == 2
    assert db.scalar(select(func.count(AuthSession.id))) == 1

    old_audit = db.scalar(
        select(SecurityAuditEvent).where(SecurityAuditEvent.trace_id == None)  # noqa: E711
    )
    assert old_audit is not None
    assert old_audit.account_id is None
    assert old_audit.principal_type is None
    assert old_audit.principal_id is None
    assert old_audit.anonymized_at.replace(tzinfo=UTC) == AS_OF
    old_other_audit = db.scalar(
        select(SecurityAuditEvent).where(
            SecurityAuditEvent.trace_id == None,  # noqa: E711
            SecurityAuditEvent.id != old_audit.id,
        )
    )
    assert old_other_audit is not None
    assert old_other_audit.account_id is None
    new_audit = db.scalar(
        select(SecurityAuditEvent).where(SecurityAuditEvent.trace_id == "new-audit-trace")
    )
    assert new_audit is not None
    assert new_audit.account_id == identity.id
    boundary_audit = db.scalar(
        select(SecurityAuditEvent).where(SecurityAuditEvent.trace_id == "boundary-audit-trace")
    )
    assert boundary_audit is not None
    assert boundary_audit.account_id == other_identity.id

    run = db.get(RetentionRun, report.run_id)
    assert run is not None
    assert run.status == "SUCCEEDED"
    assert run.cutoffs[RetentionDataClass.DATABASE_BACKUPS.value].endswith("+00:00")

    repeated = purge_expired_data(db, as_of=AS_OF)
    assert repeated.deleted == {key: 0 for key in report.deleted}
    assert repeated.anonymized == {"security_audit_events": 0}
    assert repeated.run_id != report.run_id
    assert db.scalar(select(func.count(RetentionRun.id))) == 2


def test_diagnostics_and_backups_are_not_online_data_classes(db):
    table_names = set(Base.metadata.tables)

    assert RetentionDataClass.PARSE_FAILURE_DIAGNOSTICS.value not in table_names
    assert RetentionDataClass.DATABASE_BACKUPS.value not in table_names

    report = purge_expired_data(db, as_of=AS_OF)

    assert RetentionDataClass.PARSE_FAILURE_DIAGNOSTICS.value in report.cutoffs
    assert RetentionDataClass.DATABASE_BACKUPS.value in report.cutoffs
    assert RetentionDataClass.PARSE_FAILURE_DIAGNOSTICS.value not in report.deleted
    assert RetentionDataClass.DATABASE_BACKUPS.value not in report.deleted
    assert purge_expired_data(db, as_of=AS_OF).deleted == report.deleted


def test_purge_rolls_back_data_and_run_when_commit_fails(db, monkeypatch) -> None:
    customer = _customer(db, "demo-linmu-session")
    identity = db.scalar(select(IdentityAccount).where(IdentityAccount.principal_id == customer.id))
    assert identity is not None
    db.add(
        AuthSession(
            identity_account_id=identity.id,
            token_hash="f" * 64,
            expires_at=AS_OF - timedelta(minutes=1),
            created_at=AS_OF,
        )
    )
    db.commit()

    def fail_commit() -> None:
        raise RuntimeError("retention commit unavailable")

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="retention commit unavailable"):
        purge_expired_data(db, as_of=AS_OF)

    assert db.scalar(select(func.count(AuthSession.id))) == 1
    assert db.scalar(select(func.count(RetentionRun.id))) == 0
