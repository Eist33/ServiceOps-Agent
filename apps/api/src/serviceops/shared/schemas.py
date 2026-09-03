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


class KnowledgePublishRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    version: str = Field(min_length=2, max_length=40)
    section: str = Field(min_length=2, max_length=80)
    content: str = Field(min_length=4, max_length=5000)
    keywords: list[str] = Field(min_length=1, max_length=20)
    source_uri: str = Field(min_length=4, max_length=500)


class KnowledgeArticleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    version: str
    section: str
    content: str
    keywords: list[str]
    source_uri: str
    content_hash: str
    active: bool
    valid_from: datetime
    valid_until: datetime | None
    created_at: datetime


class OpsTicketSummary(BaseModel):
    total: int
    active: int
    resolved: int
    assigned: int
    due_soon: int
    breached: int


class OpsRefundSummary(BaseModel):
    total: int
    pending: int
    succeeded: int
    cancelled: int
    total_refunded_amount: Decimal


class OpsToolSummary(BaseModel):
    total: int
    succeeded: int
    failed: int
    success_rate: float
    average_duration_ms: float


class OpsKnowledgeSummary(BaseModel):
    active: int
    historical: int
    versions: int


class OpsDashboardResponse(BaseModel):
    generated_at: datetime
    tickets: OpsTicketSummary
    refunds: OpsRefundSummary
    tools: OpsToolSummary
    knowledge: OpsKnowledgeSummary
    ticket_types: list[dict[str, Any]]
    activity: list[dict[str, Any]]
    recent_tickets: list[dict[str, Any]]
    recent_tools: list[dict[str, Any]]


class AgentTicketNoteRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)


class AgentTicketResolveRequest(BaseModel):
    resolution: str = Field(min_length=2, max_length=500)


class AgentTicketResponse(BaseModel):
    id: str
    ticket_number: str
    conversation_id: str
    order_number: str
    customer_name: str
    product_name: str
    ticket_type: str
    status: str
    priority: str
    handoff_status: str
    work_state: str
    support_group: str
    assignee_name: str | None
    is_mine: bool
    sla_due_at: datetime
    sla_status: str
    sla_remaining_minutes: int
    reason: str
    evidence: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime
    events: list[dict[str, Any]] = Field(default_factory=list)


class TicketCreateRequest(BaseModel):
    conversation_id: str
    order_number: str
    ticket_type: str = "SHIPPING"
    reason: str = Field(min_length=2, max_length=500)


class TicketResolution(BaseModel):
    summary: str
    handled_by: str
    resolved_at: datetime


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ticket_number: str
    order_id: str
    conversation_id: str
    ticket_type: str
    status: str
    priority: str
    handoff_status: str
    assignee_name: str | None
    handoff_requested_at: datetime | None
    assigned_at: datetime | None
    sla_due_at: datetime
    sla_status: str
    sla_remaining_minutes: int
    reason: str
    resolution: TicketResolution | None = None
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
