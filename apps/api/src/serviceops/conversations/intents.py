from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.models import Conversation, ConversationIntentEvent, utcnow
from serviceops.shared.errors import NotFoundError


def record_intent_event(
    db: Session,
    conversation_id: str,
    intent: str,
    *,
    actor: str,
    source: str,
    message_id: str | None = None,
    source_ticket_id: str | None = None,
    related_ticket_id: str | None = None,
    related_refund_id: str | None = None,
    detail: str = "",
    now: datetime | None = None,
) -> ConversationIntentEvent:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("会话不存在")

    existing = None
    if message_id is not None:
        existing = db.scalar(
            select(ConversationIntentEvent).where(
                ConversationIntentEvent.conversation_id == conversation_id,
                ConversationIntentEvent.message_id == message_id,
                ConversationIntentEvent.intent == intent,
            )
        )
    if existing is not None:
        changed = False
        for field, value in {
            "source_ticket_id": source_ticket_id,
            "related_ticket_id": related_ticket_id,
            "related_refund_id": related_refund_id,
        }.items():
            if value is not None and getattr(existing, field) != value:
                setattr(existing, field, value)
                changed = True
        if changed:
            conversation.updated_at = now or utcnow()
            db.commit()
            db.refresh(existing)
        return existing

    current_time = now or utcnow()
    previous_intent = conversation.current_intent
    conversation.current_intent = intent
    conversation.updated_at = current_time
    event = ConversationIntentEvent(
        conversation_id=conversation_id,
        message_id=message_id,
        intent=intent,
        previous_intent=previous_intent,
        actor=actor,
        source=source,
        source_ticket_id=source_ticket_id,
        related_ticket_id=related_ticket_id,
        related_refund_id=related_refund_id,
        detail=detail,
        created_at=current_time,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def intent_history_snapshots(
    db: Session,
    conversation_id: str,
) -> list[dict[str, object]]:
    events = list(
        db.scalars(
            select(ConversationIntentEvent)
            .where(ConversationIntentEvent.conversation_id == conversation_id)
            .order_by(
                ConversationIntentEvent.created_at.asc(),
                ConversationIntentEvent.id.asc(),
            )
        )
    )
    return [
        {
            "id": event.id,
            "intent": event.intent,
            "previous_intent": event.previous_intent,
            "actor": event.actor,
            "source": event.source,
            "source_ticket_id": event.source_ticket_id,
            "related_ticket_id": event.related_ticket_id,
            "related_refund_id": event.related_refund_id,
            "detail": event.detail,
            "created_at": event.created_at,
        }
        for event in events
    ]
