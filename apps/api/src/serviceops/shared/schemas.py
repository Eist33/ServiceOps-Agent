from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    MESSAGE_DELTA = "message_delta"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    APPROVAL_REQUIRED = "approval_required"
    BUSINESS_STATE_CHANGED = "business_state_changed"
    ORDER_SELECTION_REQUIRED = "order_selection_required"
    ACTIVE_ORDER_CHANGED = "active_order_changed"
    MODEL_FALLBACK = "model_fallback"
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


class DevelopmentAccountResponse(BaseModel):
    login_name: str
    display_name: str
    principal_type: str
    role: str


class AuthLoginRequest(BaseModel):
    login_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class AuthPrincipalResponse(BaseModel):
    account_id: str
    provider: str
    principal_type: str
    principal_id: str
    display_name: str
    role: str


class AuthLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    principal: AuthPrincipalResponse


class ConversationCreateResponse(BaseModel):
    id: str
    customer_name: str


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class ActiveOrderRequest(BaseModel):
    order_number: str = Field(min_length=4, max_length=40)


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


class KnowledgeDocumentIngestRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    source_uri: str = Field(min_length=4, max_length=500)
    content_base64: str = Field(min_length=1, max_length=7_000_000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)
    tenant_scope: str = Field(default="local-demo", min_length=1, max_length=120)
    channel_scope: str = Field(default="*", min_length=1, max_length=120)
    product_scope: str = Field(default="*", min_length=1, max_length=120)
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    source_uri: str
    filename: str
    media_type: str
    content_hash: str
    byte_size: int
    parser_version: str
    chunking_version: str
    status: str
    error_code: str | None
    error_message: str | None
    idempotency_key: str | None
    supersedes_document_id: str | None
    tenant_scope: str
    channel_scope: str
    product_scope: str
    valid_from: datetime | None
    valid_until: datetime | None
    page_count: int
    block_count: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class KnowledgeChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    chunk_index: int
    content: str
    content_hash: str
    block_type: str
    title_path: list[str]
    page_number: int | None
    start_offset: int
    end_offset: int
    source_uri: str
    tenant_scope: str
    channel_scope: str
    product_scope: str
    valid_from: datetime | None
    valid_until: datetime | None
    created_at: datetime


class KnowledgeReleaseCreateRequest(BaseModel):
    release_version: str = Field(min_length=2, max_length=80)
    document_ids: list[str] = Field(min_length=1, max_length=100)
    git_commit: str = Field(default="unbound", min_length=1, max_length=64)
    evaluation_dataset_version: str = Field(
        default="knowledge-baseline-30-v1",
        min_length=2,
        max_length=100,
    )
    retrieval_strategy_version: Literal["lexical_v1", "vector_v1", "hybrid_rrf_v1"] = "lexical_v1"


class KnowledgeReleaseRollbackRequest(BaseModel):
    target_release_id: str = Field(min_length=1, max_length=36)


class KnowledgeReleaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    release_version: str
    status: str
    parser_version: str
    chunking_version: str
    retrieval_strategy_version: str
    evaluation_dataset_version: str
    evaluation_report: dict | None
    source_manifest: list[dict]
    git_commit: str
    created_by: str
    approved_by: str | None
    rollback_release_id: str | None
    created_at: datetime
    evaluated_at: datetime | None
    approved_at: datetime | None
    published_at: datetime | None
    rolled_back_at: datetime | None
    embedding_provider: str | None
    embedding_model: str | None
    embedding_dimensions: int | None
    embedding_normalization_version: str | None
    embedding_status: str
    embedding_batch_id: str | None


class KnowledgeEmbeddingRequest(BaseModel):
    provider: str | None = Field(default=None, min_length=2, max_length=80)
    batch_size: int | None = Field(default=None, ge=1, le=128)


class KnowledgeEmbeddingBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    release_id: str
    provider: str
    model: str
    dimensions: int
    normalization_version: str
    status: str
    requested_count: int
    embedded_count: int
    reused_count: int
    failed_count: int
    attempts: int
    input_tokens: int
    cost_micros: int
    idempotency_key: str
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeHybridSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    tenant_scope: str = Field(min_length=1, max_length=120)
    channel_scope: str = Field(default="*", min_length=1, max_length=120)
    product_scope: str = Field(default="*", min_length=1, max_length=120)
    strategy: Literal["vector_v1", "hybrid_rrf_v1"] = "hybrid_rrf_v1"
    provider: str | None = Field(default=None, min_length=2, max_length=80)
    reranker: str | None = Field(default=None, min_length=2, max_length=80)
    limit: int = Field(default=5, ge=1, le=20)
    now: datetime | None = None


class KnowledgeSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    release_id: str
    release_version: str
    content: str
    source_uri: str
    title_path: list[str]
    page_number: int | None
    relevance: float
    vector_score: float | None = None
    lexical_score: float | None = None
    hybrid_score: float | None = None
    lexical_rank: int | None = None
    vector_rank: int | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None
    final_score: float | None = None
    selected: bool = False
    decision: str | None = None


class KnowledgeSearchResponse(BaseModel):
    strategy: str
    confident: bool
    score: float
    results: list[KnowledgeSearchResult]
    fallback: bool = False
    fallback_reason: str | None = None
    release_version: str | None = None
    provider: str | None = None
    trace_id: str | None = None
    reranker_status: str = "NOT_CONFIGURED"
    reranker_provider: str | None = None
    reranker_model: str | None = None
    reranker_version: str | None = None
    reranker_fallback: bool = False
    reranker_fallback_reason: str | None = None


class KnowledgeRetrievalTraceCandidateResponse(BaseModel):
    id: str
    chunk_id: str | None
    release_id: str | None
    release_version: str | None
    source_uri: str | None
    lexical_rank: int | None
    vector_rank: int | None
    rrf_score: float | None
    lexical_score: float | None
    vector_score: float | None
    rerank_score: float | None
    final_score: float | None
    selected: bool
    decision: str
    exclusion_reason: str | None


class KnowledgeRetrievalTraceResponse(BaseModel):
    id: str
    request_trace_id: str
    query_hash: str
    query_length: int
    strategy: str
    release_version: str | None
    provider: str | None
    provider_model: str | None
    reranker_provider: str | None
    reranker_model: str | None
    reranker_version: str | None
    reranker_input_tokens: int
    reranker_cost_micros: int
    status: str
    decision: str
    confident: bool
    fallback: bool
    fallback_reason: str | None
    filter_summary: dict[str, Any]
    candidate_counts: dict[str, Any]
    duration_ms: int
    error_code: str | None
    created_at: datetime
    candidates: list[KnowledgeRetrievalTraceCandidateResponse]


class KnowledgeRetrievalFeedbackRequest(BaseModel):
    label: Literal[
        "ZERO_RESULT",
        "LOW_CONFIDENCE",
        "WRONG_CITATION",
        "NEGATIVE_RATING",
        "HUMAN_CORRECTION",
    ]
    idempotency_key: str = Field(min_length=1, max_length=160)
    deidentified_note: str | None = Field(default=None, max_length=500)


class KnowledgeRetrievalFeedbackReviewRequest(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    review_note: str | None = Field(default=None, max_length=500)


class KnowledgeRetrievalFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    trace_id: str
    label: str
    status: str
    idempotency_key: str
    deidentified_note: str | None
    created_by: str
    reviewed_by: str | None
    review_note: str | None
    evaluation_eligible: bool
    created_at: datetime
    reviewed_at: datetime | None


class KnowledgeRetrievalQualityResponse(BaseModel):
    window_hours: int
    trace_count: int
    zero_result_count: int
    low_confidence_count: int
    failure_count: int
    fallback_count: int
    reranker_fallback_count: int
    p50_duration_ms: int
    p95_duration_ms: int
    pending_feedback_count: int
    approved_feedback_count: int
    rejected_feedback_count: int
    evaluation_eligible_count: int
    external_requests_enabled: bool


class KnowledgeQueryEnhancementRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    tenant_scope: str = Field(min_length=1, max_length=120)
    channel_scope: str = Field(default="*", min_length=1, max_length=120)
    product_scope: str = Field(default="*", min_length=1, max_length=120)
    retrieval_strategy: Literal["vector_v1", "hybrid_rrf_v1"] = "hybrid_rrf_v1"
    embedding_provider: str | None = Field(default=None, min_length=2, max_length=80)
    enhancement_provider: str = Field(default="not_configured", min_length=2, max_length=80)
    enhancement_strategy: Literal["rewrite_v1", "hyde_v1", "multi_query_v1"] = "rewrite_v1"
    enabled: bool = False
    experiment_group: Literal["shadow"] = "shadow"
    max_variants: int = Field(default=3, ge=1, le=5)
    now: datetime | None = None


class KnowledgeQueryEnhancementEvaluationRequest(BaseModel):
    enhancement_provider: str = Field(default="fixture", min_length=2, max_length=80)
    enhancement_strategy: Literal["rewrite_v1", "hyde_v1", "multi_query_v1"] = "rewrite_v1"
    max_variants: int = Field(default=3, ge=1, le=5)


class KnowledgeQueryEnhancementResponse(BaseModel):
    experiment_id: str
    config_version: str
    provider: str
    strategy: str
    experiment_group: str
    query_hash: str
    query_length: int
    control: dict[str, Any]
    treatment: dict[str, Any]
    guardrails: dict[str, Any]
    decision: str
    promotion_allowed: bool
    production_strategy: str
    external_requests_enabled: bool


class KnowledgeQueryEnhancementEvaluationResponse(BaseModel):
    dataset_version: str
    config_version: str
    provider: str
    strategy: str
    control: dict[str, Any]
    treatment: dict[str, Any]
    cases: list[dict[str, Any]]
    promotion_allowed: bool
    decision: str
    external_requests_enabled: bool


class ProductionReleaseGateRequest(BaseModel):
    manifest: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    offline_metrics: dict[str, Any] = Field(default_factory=dict)
    online_metrics: dict[str, Any] = Field(default_factory=dict)
    maintenance_checks: dict[str, Any] = Field(default_factory=dict)


class ProductionGovernanceResponse(BaseModel):
    governance_version: str
    state: str
    release_gate: dict[str, Any]
    sli: dict[str, Any]
    maintenance: dict[str, Any]
    audit: dict[str, Any]
    publish_allowed: bool
    rollback_allowed: bool
    external_resources_enabled: bool
    external_requests_enabled: bool


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


class OpsModelSummary(BaseModel):
    window_hours: int
    total: int
    succeeded: int
    failed: int
    fallback: int
    success_rate: float
    average_duration_ms: float
    p95_duration_ms: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


class OpsKnowledgeSummary(BaseModel):
    active: int
    historical: int
    versions: int


class CommerceIntegrationStatusResponse(BaseModel):
    provider: str
    state: str
    capabilities: list[str]
    external_requests_enabled: bool
    message: str


class OpsDashboardResponse(BaseModel):
    generated_at: datetime
    tickets: OpsTicketSummary
    refunds: OpsRefundSummary
    tools: OpsToolSummary
    models: OpsModelSummary
    knowledge: OpsKnowledgeSummary
    ticket_types: list[dict[str, Any]]
    activity: list[dict[str, Any]]
    recent_tickets: list[dict[str, Any]]
    recent_tools: list[dict[str, Any]]
    recent_model_invocations: list[dict[str, Any]]


class OpsTicketReportResponse(BaseModel):
    generated_at: datetime
    selected_support_group: str | None
    selected_sla_status: str | None
    available_support_groups: list[str]
    total: int
    risk: int
    breached: int
    items: list[dict[str, Any]]


class OpsAlertSnapshotResponse(BaseModel):
    generated_at: datetime
    total: int
    unacknowledged: int
    critical: int
    high: int
    medium: int
    items: list[dict[str, Any]]


class OpsAlertAcknowledgementResponse(BaseModel):
    id: str
    ticket_id: str
    alert_type: str
    acknowledged_by: str
    acknowledged_at: datetime


class OpsQualityCheck(BaseModel):
    key: str
    label: str
    passed: bool
    score: int
    max_score: int


class OpsQualityItem(BaseModel):
    ticket_id: str
    ticket_number: str
    order_number: str
    customer_name: str
    support_group: str
    assignee_name: str
    resolved_at: datetime
    score: int
    grade: str
    checks: list[OpsQualityCheck]
    customer_rating: int | None
    customer_comment: str | None
    feedback_submitted_at: datetime | None


class OpsQualityReportResponse(BaseModel):
    generated_at: datetime
    total: int
    excellent: int
    qualified: int
    attention: int
    average_score: float
    feedback_received: int
    low_ratings: int
    average_customer_rating: float
    items: list[OpsQualityItem]


class AgentTicketNoteRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)


class AgentTicketResolveRequest(BaseModel):
    resolution: str = Field(min_length=2, max_length=500)


class TicketMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)


class TicketMessageResponse(BaseModel):
    id: str
    sender_role: str
    sender_name: str
    content: str
    created_at: datetime


class RefundResponse(BaseModel):
    id: str
    refund_number: str
    ticket_id: str
    order_id: str
    status: str
    amount: Decimal
    method: str
    reason: str
    approved_by_operator_id: str | None = None
    approved_at: datetime | None = None
    confirmed_at: datetime | None
    created_at: datetime


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
    messages: list[TicketMessageResponse] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    # Refund facts are only attached to the support-agent workbench response.
    # Mutations still go through the dedicated approval routes below.
    refund: RefundResponse | None = None


class TicketCreateRequest(BaseModel):
    conversation_id: str
    order_number: str
    ticket_type: str = "SHIPPING"
    reason: str = Field(min_length=2, max_length=500)


class TicketResolution(BaseModel):
    summary: str
    handled_by: str
    resolved_at: datetime


class CustomerFeedbackRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


class CustomerFeedbackResponse(BaseModel):
    id: str
    ticket_id: str
    rating: int
    comment: str | None
    submitted_at: datetime


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
    feedback: CustomerFeedbackResponse | None = None
    evidence: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    messages: list[TicketMessageResponse] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)


class RefundCreateRequest(BaseModel):
    conversation_id: str
    order_number: str
    reason: str = Field(min_length=2, max_length=500)
    requested_amount: Decimal | None = Field(default=None, gt=0)


class RefundDecisionRequest(BaseModel):
    reason: str | None = Field(default=None, min_length=2, max_length=500)


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
