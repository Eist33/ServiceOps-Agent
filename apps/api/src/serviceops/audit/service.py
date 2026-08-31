from sqlalchemy.orm import Session

from serviceops.models import ToolInvocation

SENSITIVE_KEYS = {"user_id", "session_token", "api_key", "payment_details"}


def redact(value: dict) -> dict:
    return {key: "[REDACTED]" if key in SENSITIVE_KEYS else item for key, item in value.items()}


def record_invocation(
    db: Session,
    *,
    trace_id: str,
    conversation_id: str,
    message_id: str,
    tool_call_id: str,
    tool_name: str,
    input_summary: dict,
    output_summary: dict,
    status: str = "SUCCEEDED",
    duration_ms: int = 0,
    error_type: str | None = None,
    order_id: str | None = None,
    ticket_id: str | None = None,
    refund_request_id: str | None = None,
) -> ToolInvocation:
    invocation = ToolInvocation(
        trace_id=trace_id,
        conversation_id=conversation_id,
        message_id=message_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        input_summary=redact(input_summary),
        output_summary=redact(output_summary),
        status=status,
        duration_ms=duration_ms,
        error_type=error_type,
        order_id=order_id,
        ticket_id=ticket_id,
        refund_request_id=refund_request_id,
    )
    db.add(invocation)
    db.commit()
    return invocation
