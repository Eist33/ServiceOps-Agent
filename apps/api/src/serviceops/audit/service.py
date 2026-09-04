from sqlalchemy.orm import Session

from serviceops.models import ModelInvocation, ToolInvocation
from serviceops.observability import redact


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


def record_model_invocation(
    db: Session,
    *,
    trace_id: str,
    conversation_id: str,
    message_id: str,
    provider: str,
    model_name: str,
    api_style: str,
    status: str,
    duration_ms: int,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    error_type: str | None = None,
    fallback_used: bool = False,
) -> ModelInvocation:
    """Persist metadata-only model telemetry without prompts, outputs, URLs or keys."""
    invocation = ModelInvocation(
        trace_id=trace_id,
        conversation_id=conversation_id,
        message_id=message_id,
        provider=provider[:40],
        model_name=model_name[:100],
        api_style=api_style[:30],
        status=status,
        duration_ms=duration_ms,
        input_tokens=max(0, input_tokens),
        output_tokens=max(0, output_tokens),
        total_tokens=max(0, total_tokens),
        error_type=error_type[:80] if error_type else None,
        fallback_used=fallback_used,
    )
    db.add(invocation)
    db.commit()
    return invocation
