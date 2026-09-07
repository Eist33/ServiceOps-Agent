from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from serviceops.models import (
    AuthSession,
    Conversation,
    CustomerSatisfactionFeedback,
    IdempotencyRecord,
    Message,
    ModelInvocation,
    OperationsAlertAcknowledgement,
    RefundApprovalAudit,
    RefundRequest,
    RetentionRun,
    SecurityAuditEvent,
    Ticket,
    TicketEvent,
    TicketStatus,
    ToolInvocation,
    utcnow,
)

RETENTION_POLICY_VERSION = "9B-4-v1"


class RetentionDataClass(StrEnum):
    CHAT_MESSAGES = "chat_messages"
    TICKET_DATA = "ticket_data"
    AUTH_SECURITY_AUDIT = "auth_security_audit"
    MODEL_INVOCATIONS = "model_invocations"
    PARSE_FAILURE_DIAGNOSTICS = "parse_failure_diagnostics"
    DATABASE_BACKUPS = "database_backups"


RETENTION_WINDOWS: dict[RetentionDataClass, timedelta] = {
    RetentionDataClass.CHAT_MESSAGES: timedelta(days=180),
    RetentionDataClass.TICKET_DATA: timedelta(days=365),
    RetentionDataClass.AUTH_SECURITY_AUDIT: timedelta(days=180),
    RetentionDataClass.MODEL_INVOCATIONS: timedelta(days=30),
    RetentionDataClass.PARSE_FAILURE_DIAGNOSTICS: timedelta(days=7),
    RetentionDataClass.DATABASE_BACKUPS: timedelta(days=30),
}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def retention_cutoff(
    data_class: RetentionDataClass,
    *,
    as_of: datetime,
) -> datetime:
    return _aware(as_of) - RETENTION_WINDOWS[data_class]


def retention_cutoffs(*, as_of: datetime) -> dict[RetentionDataClass, datetime]:
    return {
        data_class: retention_cutoff(data_class, as_of=as_of) for data_class in RetentionDataClass
    }


def is_expired(
    data_class: RetentionDataClass,
    occurred_at: datetime,
    *,
    as_of: datetime,
) -> bool:
    """Return whether data is strictly older than its retention boundary."""
    return _aware(occurred_at) < retention_cutoff(data_class, as_of=as_of)


@dataclass(frozen=True)
class RetentionPurgeReport:
    run_id: str
    policy_version: str
    as_of: datetime
    cutoffs: dict[str, str]
    deleted: dict[str, int]
    anonymized: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "policy_version": self.policy_version,
            "as_of": self.as_of.isoformat(),
            "cutoffs": self.cutoffs,
            "deleted": self.deleted,
            "anonymized": self.anonymized,
        }


def _ids(db: Session, statement) -> list[str]:
    return list(db.scalars(statement))


def _delete_ids(db: Session, model, ids: list[str]) -> int:
    if not ids:
        return 0
    db.execute(delete(model).where(model.id.in_(ids)))
    return len(ids)


def purge_expired_data(
    db: Session,
    *,
    as_of: datetime | None = None,
) -> RetentionPurgeReport:
    try:
        return _purge_expired_data(db, as_of=as_of)
    except Exception:
        db.rollback()
        raise


def _purge_expired_data(
    db: Session,
    *,
    as_of: datetime | None = None,
) -> RetentionPurgeReport:
    """Delete expired business bodies and anonymize aged security subjects.

    The operation is intentionally system-scoped: it accepts no customer,
    operator, account, or model-provided identifiers. Re-running it at the
    same clock value is safe because deleted rows are absent and anonymized
    audit rows are excluded by ``anonymized_at``.
    """
    current_time = _aware(as_of or utcnow())
    cutoffs = retention_cutoffs(as_of=current_time)
    deleted = {
        "auth_sessions": 0,
        "messages": 0,
        "model_invocations": 0,
        "tool_invocations": 0,
        "ticket_events": 0,
        "customer_feedback": 0,
        "refund_requests": 0,
        "refund_approval_audits": 0,
        "operations_alert_acknowledgements": 0,
        "idempotency_records": 0,
        "tickets": 0,
    }
    anonymized = {"security_audit_events": 0}

    expired_auth_ids = _ids(
        db,
        select(AuthSession.id).where(
            (AuthSession.expires_at <= current_time) | AuthSession.revoked_at.is_not(None)
        ),
    )
    deleted["auth_sessions"] = _delete_ids(db, AuthSession, expired_auth_ids)

    stale_conversation_ids = _ids(
        db,
        select(Conversation.id).where(
            Conversation.updated_at < cutoffs[RetentionDataClass.CHAT_MESSAGES]
        ),
    )
    stale_message_ids = _ids(
        db,
        select(Message.id).where(
            Message.created_at < cutoffs[RetentionDataClass.CHAT_MESSAGES],
            Message.conversation_id.in_(stale_conversation_ids),
        ),
    )
    deleted["messages"] = _delete_ids(db, Message, stale_message_ids)

    old_model_ids = _ids(
        db,
        select(ModelInvocation.id).where(
            ModelInvocation.created_at < cutoffs[RetentionDataClass.MODEL_INVOCATIONS]
        ),
    )
    deleted["model_invocations"] = _delete_ids(db, ModelInvocation, old_model_ids)

    old_tool_ids = _ids(
        db,
        select(ToolInvocation.id).where(
            ToolInvocation.created_at < cutoffs[RetentionDataClass.TICKET_DATA]
        ),
    )
    deleted["tool_invocations"] = _delete_ids(db, ToolInvocation, old_tool_ids)

    old_ticket_ids = _ids(
        db,
        select(Ticket.id).where(
            Ticket.status == TicketStatus.RESOLVED.value,
            Ticket.updated_at < cutoffs[RetentionDataClass.TICKET_DATA],
        ),
    )
    old_ticket_event_ids = _ids(
        db,
        select(TicketEvent.id).where(TicketEvent.ticket_id.in_(old_ticket_ids)),
    )
    old_feedback_ids = _ids(
        db,
        select(CustomerSatisfactionFeedback.id).where(
            CustomerSatisfactionFeedback.ticket_id.in_(old_ticket_ids)
        ),
    )
    old_refund_ids = _ids(
        db,
        select(RefundRequest.id).where(RefundRequest.ticket_id.in_(old_ticket_ids)),
    )
    old_refund_audit_ids = _ids(
        db,
        select(RefundApprovalAudit.id).where(
            RefundApprovalAudit.refund_request_id.in_(old_refund_ids)
        ),
    )
    old_acknowledgement_ids = _ids(
        db,
        select(OperationsAlertAcknowledgement.id).where(
            OperationsAlertAcknowledgement.ticket_id.in_(old_ticket_ids)
        ),
    )
    old_resource_ids = old_ticket_ids + old_refund_ids
    old_idempotency_ids = _ids(
        db,
        select(IdempotencyRecord.id).where(
            (IdempotencyRecord.created_at < cutoffs[RetentionDataClass.TICKET_DATA])
            | IdempotencyRecord.resource_id.in_(old_resource_ids)
        ),
    )
    deleted["ticket_events"] = _delete_ids(db, TicketEvent, old_ticket_event_ids)
    deleted["customer_feedback"] = _delete_ids(db, CustomerSatisfactionFeedback, old_feedback_ids)
    deleted["refund_approval_audits"] = _delete_ids(
        db, RefundApprovalAudit, old_refund_audit_ids
    )
    deleted["refund_requests"] = _delete_ids(db, RefundRequest, old_refund_ids)
    deleted["operations_alert_acknowledgements"] = _delete_ids(
        db, OperationsAlertAcknowledgement, old_acknowledgement_ids
    )
    deleted["idempotency_records"] = _delete_ids(db, IdempotencyRecord, old_idempotency_ids)
    deleted["tickets"] = _delete_ids(db, Ticket, old_ticket_ids)

    old_audit_ids = _ids(
        db,
        select(SecurityAuditEvent.id).where(
            SecurityAuditEvent.created_at < cutoffs[RetentionDataClass.AUTH_SECURITY_AUDIT],
            SecurityAuditEvent.anonymized_at.is_(None),
        ),
    )
    if old_audit_ids:
        db.execute(
            update(SecurityAuditEvent)
            .where(
                SecurityAuditEvent.id.in_(old_audit_ids),
                SecurityAuditEvent.anonymized_at.is_(None),
            )
            .values(
                account_id=None,
                principal_type=None,
                principal_id=None,
                trace_id=None,
                anonymized_at=current_time,
            )
        )
    anonymized["security_audit_events"] = len(old_audit_ids)

    run = RetentionRun(
        policy_version=RETENTION_POLICY_VERSION,
        as_of=current_time,
        status="SUCCEEDED",
        cutoffs={data_class.value: cutoff.isoformat() for data_class, cutoff in cutoffs.items()},
        deleted_counts=deleted,
        anonymized_counts=anonymized,
        started_at=current_time,
        completed_at=current_time,
    )
    db.add(run)
    db.commit()
    return RetentionPurgeReport(
        run_id=run.id,
        policy_version=run.policy_version,
        as_of=current_time,
        cutoffs=run.cutoffs,
        deleted=deleted,
        anonymized=anonymized,
    )
