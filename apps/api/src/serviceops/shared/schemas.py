from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    MESSAGE_DELTA = "message_delta"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    APPROVAL_REQUIRED = "approval_required"
    BUSINESS_STATE_CHANGED = "business_state_changed"
    ERROR = "error"
    RESPONSE_COMPLETED = "response_completed"


class AgentEvent(BaseModel):
    type: EventType
    conversation_id: str
    message_id: str
    tool_call_id: str | None = None
    trace_id: str
    order_id: str | None = None
    ticket_id: str | None = None
    refund_request_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ConversationCreateResponse(BaseModel):
    id: str
    customer_name: str


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class TicketCreateRequest(BaseModel):
    conversation_id: str
    order_number: str
    ticket_type: str = "SHIPPING"
    reason: str = Field(min_length=2, max_length=500)


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ticket_number: str
    order_id: str
    conversation_id: str
    ticket_type: str
    status: str
    reason: str
    evidence: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    events: list[dict[str, Any]] = Field(default_factory=list)


class RefundCreateRequest(BaseModel):
    conversation_id: str
    order_number: str
    reason: str = Field(min_length=2, max_length=500)
    requested_amount: Decimal | None = Field(default=None, gt=0)


class RefundResponse(BaseModel):
    id: str
    refund_number: str
    ticket_id: str
    order_id: str
    status: str
    amount: Decimal
    method: str
    reason: str
    confirmed_at: datetime | None
    created_at: datetime


class OrderResponse(BaseModel):
    id: str
    order_number: str
    product_name: str
    paid_amount: Decimal
    refundable_amount: Decimal
    status: str
    ordered_at: datetime


class ShippingResponse(BaseModel):
    order_id: str
    order_number: str
    abnormal: bool
    abnormal_reason: str | None
    stale_hours: int
    nodes: list[dict[str, Any]]
