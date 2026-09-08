import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from serviceops.agent.orchestrator import DeterministicSupportAgent
from serviceops.agent.release import governance_snapshot
from serviceops.config import get_settings
from serviceops.conversations.service import (
    conversation_state,
    create_conversation,
    request_order_selection,
    set_active_order,
)
from serviceops.database import Base, engine, get_db
from serviceops.feedback.service import submit_customer_feedback
from serviceops.identity.service import (
    AuthenticatedPrincipal,
    current_authenticated_principal,
    current_customer,
    current_demo_reset_operator,
    current_knowledge_manager,
    current_operations_operator,
    current_operator,
    current_support_agent,
    list_development_accounts,
    login_development_account,
    revoke_auth_session,
)
from serviceops.integrations.commerce import build_default_commerce_registry
from serviceops.knowledge.embedding_pipeline import embed_knowledge_release
from serviceops.knowledge.embeddings import EmbeddingProviderError, build_embedding_provider
from serviceops.knowledge.fusion import search_hybrid_knowledge
from serviceops.knowledge.ingestion import (
    decode_base64_document,
    ingest_document,
    list_document_chunks,
    list_documents,
)
from serviceops.knowledge.management import (
    deactivate_knowledge_article,
    list_knowledge_articles,
    publish_knowledge_article,
)
from serviceops.knowledge.query_enhancement import (
    QueryEnhancementConfig,
    QueryEnhancementProviderError,
    build_query_enhancer,
    evaluate_fixture_query_enhancement,
    run_query_enhancement_experiment,
)
from serviceops.knowledge.releases import (
    approve_knowledge_release,
    create_knowledge_release,
    evaluate_knowledge_release,
    list_release_items,
    list_releases,
    publish_knowledge_release,
    rollback_knowledge_release,
)
from serviceops.knowledge.rerank import (
    RerankerProviderError,
    apply_optional_reranker,
    build_reranker,
)
from serviceops.knowledge.trace import (
    create_retrieval_feedback,
    get_retrieval_trace,
    record_retrieval_trace,
    retrieval_quality_report,
    review_retrieval_feedback,
)
from serviceops.knowledge.vector import search_vector_candidates
from serviceops.models import Customer, KnowledgeChunk, Operator
from serviceops.observability import log_request_event, normalize_trace_id
from serviceops.operations.service import (
    acknowledge_operations_alert,
    operations_alerts,
    operations_dashboard,
    operations_quality_report,
    operations_ticket_report,
    reset_demo_state_after_completed_ticket,
)
from serviceops.operations.streaming import stream_operations_alerts
from serviceops.orders.service import get_order, list_recent_orders
from serviceops.production.governance import production_governance_report
from serviceops.refunds.service import (
    approve_refund,
    cancel_refund,
    confirm_refund,
    reject_refund,
    withdraw_refund,
)
from serviceops.seed import reset_demo_state, seed_database
from serviceops.shared.errors import DomainError, ValidationError
from serviceops.shared.schemas import (
    ActiveOrderRequest,
    AgentIntentChangeRequest,
    AgentTicketNoteRequest,
    AgentTicketResolveRequest,
    AgentTicketResponse,
    AuthLoginRequest,
    AuthLoginResponse,
    AuthPrincipalResponse,
    CommerceIntegrationStatusResponse,
    ConversationCreateResponse,
    CustomerFeedbackRequest,
    CustomerFeedbackResponse,
    DemoResetResponse,
    DevelopmentAccountResponse,
    KnowledgeArticleResponse,
    KnowledgeChunkResponse,
    KnowledgeDocumentIngestRequest,
    KnowledgeDocumentResponse,
    KnowledgeEmbeddingBatchResponse,
    KnowledgeEmbeddingRequest,
    KnowledgeHybridSearchRequest,
    KnowledgePublishRequest,
    KnowledgeQueryEnhancementEvaluationRequest,
    KnowledgeQueryEnhancementEvaluationResponse,
    KnowledgeQueryEnhancementRequest,
    KnowledgeQueryEnhancementResponse,
    KnowledgeReleaseCreateRequest,
    KnowledgeReleaseResponse,
    KnowledgeReleaseRollbackRequest,
    KnowledgeRetrievalFeedbackRequest,
    KnowledgeRetrievalFeedbackResponse,
    KnowledgeRetrievalFeedbackReviewRequest,
    KnowledgeRetrievalQualityResponse,
    KnowledgeRetrievalTraceResponse,
    KnowledgeSearchResponse,
    MessageRequest,
    OpsAlertAcknowledgementResponse,
    OpsAlertSnapshotResponse,
    OpsDashboardResponse,
    OpsQualityReportResponse,
    OpsTicketReportResponse,
    OrderResponse,
    ProductionGovernanceResponse,
    ProductionReleaseGateRequest,
    RefundDecisionRequest,
    RefundResponse,
    ShippingResponse,
    TicketCreateRequest,
    TicketMessageRequest,
    TicketResponse,
)
from serviceops.shipping.service import get_shipping_status
from serviceops.tickets.service import (
    add_customer_ticket_message,
    cancel_human_handoff,
    create_ticket,
    get_ticket,
    request_human_handoff,
    ticket_response,
)
from serviceops.workbench.service import (
    accept_workbench_ticket,
    add_workbench_note,
    add_workbench_reply,
    change_workbench_intent,
    list_workbench_tickets,
    resolve_workbench_ticket,
)
from serviceops.workbench.streaming import stream_workbench_tickets


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    if settings.demo_mode_enabled:
        with Session(engine) as db:
            seed_database(db)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    commerce_registry = build_default_commerce_registry()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Enterprise customer support and ticket execution Agent MVP",
        lifespan=lifespan,
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
        openapi_url="/openapi.json" if settings.api_docs_enabled else None,
    )
    app.state.commerce_registry = commerce_registry
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.web_origin.split(",")],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "Idempotency-Key",
            "X-Agent-Session",
            "X-Demo-Session",
            "X-Ops-Session",
            "X-Trace-ID",
        ],
        expose_headers=["X-Trace-ID"],
    )

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        request.state.trace_id = normalize_trace_id(request.headers.get("X-Trace-ID"))
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            log_request_event(
                logging.ERROR,
                "request_failed",
                trace_id=request.state.trace_id,
                method=request.method,
                path=request.url.path,
                error_type=type(exc).__name__,
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "服务暂时不可用，请稍后重试",
                    },
                    "trace_id": request.state.trace_id,
                },
            )
        response.headers["X-Trace-ID"] = request.state.trace_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if settings.app_env.strip().lower() == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        log_request_event(
            logging.INFO,
            "request_completed",
            trace_id=request.state.trace_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=max(1, int((time.perf_counter() - started) * 1000)),
        )
        return response

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": exc.code, "message": exc.message},
                "trace_id": request.state.trace_id,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "请求参数无效",
                    "details": exc.errors(),
                },
                "trace_id": request.state.trace_id,
            },
        )

    @app.get("/health")
    def health(db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
        return {"status": "ok", "service": "api"}

    def principal_response(
        principal: AuthenticatedPrincipal,
    ) -> AuthPrincipalResponse:
        return AuthPrincipalResponse(
            account_id=principal.account_id,
            provider=principal.provider,
            principal_type=principal.principal_type,
            principal_id=principal.principal_id,
            display_name=principal.display_name,
            role=principal.role,
        )

    if settings.demo_mode_enabled:

        @app.get(
            "/api/auth/development-accounts",
            response_model=list[DevelopmentAccountResponse],
        )
        def development_account_index(db: Session = Depends(get_db)):
            return [
                DevelopmentAccountResponse(
                    login_name=account.login_name or "",
                    display_name=account.display_name,
                    principal_type=account.principal_type,
                    role=account.role,
                )
                for account in list_development_accounts(db)
            ]

        @app.post("/api/auth/login", response_model=AuthLoginResponse)
        def auth_login(body: AuthLoginRequest, db: Session = Depends(get_db)):
            token, expires_at, principal = login_development_account(
                db, body.login_name, body.password, settings
            )
            return AuthLoginResponse(
                access_token=token,
                expires_at=expires_at,
                principal=principal_response(principal),
            )

    @app.get("/api/auth/me", response_model=AuthPrincipalResponse)
    def auth_me(
        principal: AuthenticatedPrincipal = Depends(current_authenticated_principal),
    ):
        return principal_response(principal)

    @app.post("/api/auth/logout")
    def auth_logout(
        authorization: str | None = Header(default=None, alias="Authorization"),
        db: Session = Depends(get_db),
        _principal: AuthenticatedPrincipal = Depends(current_authenticated_principal),
    ):
        revoke_auth_session(db, authorization)
        return {"status": "logged_out"}

    @app.get("/api/me")
    def me(customer: Customer = Depends(current_customer)):
        return {"id": customer.id, "name": customer.name}

    @app.get("/api/ops/me")
    def ops_me(operator: Operator = Depends(current_operator)):
        return {"id": operator.id, "name": operator.name, "role": operator.role}

    @app.get("/api/agent/me")
    def agent_me(operator: Operator = Depends(current_support_agent)):
        return {"id": operator.id, "name": operator.name, "role": operator.role}

    @app.get("/api/agent/tickets", response_model=list[AgentTicketResponse])
    def agent_ticket_queue(
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_support_agent),
    ):
        return list_workbench_tickets(db, operator)

    @app.get("/api/agent/tickets/stream")
    def agent_ticket_stream(
        once: bool = False,
        operator: Operator = Depends(current_support_agent),
    ):
        return StreamingResponse(
            stream_workbench_tickets(operator.id, once=once),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post(
        "/api/agent/tickets/{ticket_id}/accept",
        response_model=AgentTicketResponse,
    )
    def accept_agent_ticket(
        ticket_id: str,
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_support_agent),
    ):
        return accept_workbench_ticket(db, operator, ticket_id)

    @app.post(
        "/api/agent/tickets/{ticket_id}/intent",
        response_model=AgentTicketResponse,
    )
    def change_agent_ticket_intent(
        ticket_id: str,
        body: AgentIntentChangeRequest,
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_support_agent),
    ):
        return change_workbench_intent(
            db,
            operator,
            ticket_id,
            intent=body.intent,
            reason=body.reason,
            order_number=body.order_number,
        )

    @app.post(
        "/api/agent/tickets/{ticket_id}/notes",
        response_model=AgentTicketResponse,
    )
    def add_agent_ticket_note(
        ticket_id: str,
        body: AgentTicketNoteRequest,
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_support_agent),
    ):
        return add_workbench_note(db, operator, ticket_id, body.content)

    @app.post(
        "/api/agent/tickets/{ticket_id}/messages",
        response_model=AgentTicketResponse,
    )
    def add_agent_ticket_message(
        ticket_id: str,
        body: TicketMessageRequest,
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_support_agent),
    ):
        return add_workbench_reply(db, operator, ticket_id, body.content)

    @app.post(
        "/api/agent/tickets/{ticket_id}/resolve",
        response_model=AgentTicketResponse,
    )
    def resolve_agent_ticket(
        ticket_id: str,
        body: AgentTicketResolveRequest,
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_support_agent),
    ):
        return resolve_workbench_ticket(db, operator, ticket_id, body.resolution)

    @app.get("/api/ops/knowledge", response_model=list[KnowledgeArticleResponse])
    def knowledge_index(
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        return list_knowledge_articles(db)

    @app.post(
        "/api/ops/knowledge/documents",
        response_model=KnowledgeDocumentResponse,
    )
    def ingest_knowledge_document(
        body: KnowledgeDocumentIngestRequest,
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_knowledge_manager),
    ):
        content = decode_base64_document(body.content_base64)
        result = ingest_document(
            db,
            filename=body.filename,
            source_uri=body.source_uri,
            data=content,
            idempotency_key=body.idempotency_key,
            owner=operator.name,
            tenant_scope=body.tenant_scope,
            channel_scope=body.channel_scope,
            product_scope=body.product_scope,
            valid_from=body.valid_from,
            valid_until=body.valid_until,
        )
        return result.document

    @app.get(
        "/api/ops/knowledge/documents",
        response_model=list[KnowledgeDocumentResponse],
    )
    def knowledge_document_index(
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        return list_documents(db)

    @app.get(
        "/api/ops/knowledge/documents/{document_id}/chunks",
        response_model=list[KnowledgeChunkResponse],
    )
    def knowledge_document_chunks(
        document_id: str,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        return list_document_chunks(db, document_id)

    @app.get(
        "/api/ops/knowledge/releases",
        response_model=list[KnowledgeReleaseResponse],
    )
    def knowledge_release_index(
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        return list_releases(db)

    @app.post(
        "/api/ops/knowledge/releases",
        response_model=KnowledgeReleaseResponse,
    )
    def knowledge_release_create(
        body: KnowledgeReleaseCreateRequest,
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_knowledge_manager),
    ):
        return create_knowledge_release(
            db,
            release_version=body.release_version,
            document_ids=body.document_ids,
            created_by=operator.name,
            git_commit=body.git_commit,
            evaluation_dataset_version=body.evaluation_dataset_version,
            retrieval_strategy_version=body.retrieval_strategy_version,
        )

    @app.post(
        "/api/ops/knowledge/releases/{release_id}/evaluate",
        response_model=KnowledgeReleaseResponse,
    )
    def knowledge_release_evaluate(
        release_id: str,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        return evaluate_knowledge_release(db, release_id)

    @app.post(
        "/api/ops/knowledge/releases/{release_id}/approve",
        response_model=KnowledgeReleaseResponse,
    )
    def knowledge_release_approve(
        release_id: str,
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_knowledge_manager),
    ):
        return approve_knowledge_release(db, release_id, approved_by=operator.name)

    @app.post(
        "/api/ops/knowledge/releases/{release_id}/publish",
        response_model=KnowledgeReleaseResponse,
    )
    def knowledge_release_publish(
        release_id: str,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        return publish_knowledge_release(db, release_id)

    @app.post(
        "/api/ops/knowledge/releases/{release_id}/embeddings",
        response_model=KnowledgeEmbeddingBatchResponse,
    )
    def knowledge_release_embeddings(
        release_id: str,
        body: KnowledgeEmbeddingRequest,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        provider = build_embedding_provider(body.provider)
        return embed_knowledge_release(
            db,
            release_id,
            provider=provider,
            batch_size=body.batch_size,
        )

    @app.post(
        "/api/ops/knowledge/search",
        response_model=KnowledgeSearchResponse,
    )
    def knowledge_search(
        request: Request,
        body: KnowledgeHybridSearchRequest,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        started = time.perf_counter()
        provider = None
        provider_error: EmbeddingProviderError | None = None
        report: dict = {"strategy": body.strategy, "results": [], "confident": False}
        try:
            try:
                provider = build_embedding_provider(body.provider)
            except EmbeddingProviderError as error:
                provider_error = error
                if body.strategy == "vector_v1":
                    raise
            if body.strategy == "vector_v1":
                candidates = search_vector_candidates(
                    db,
                    body.query,
                    provider=provider,
                    strategy=body.strategy,
                    tenant_scope=body.tenant_scope,
                    channel_scope=body.channel_scope,
                    product_scope=body.product_scope,
                    now=body.now,
                    limit=body.limit,
                )
                score = candidates[0]["relevance"] if candidates else 0.0
                report = {
                    "strategy": "vector_v1",
                    "confident": bool(candidates),
                    "score": score,
                    "results": candidates,
                    "trace_candidates": candidates,
                    "fallback": False,
                    "fallback_reason": None,
                    "release_version": candidates[0]["release_version"] if candidates else None,
                    "provider": provider.provider if provider else None,
                    "provider_model": provider.model if provider else None,
                }
            else:
                report = search_hybrid_knowledge(
                    db,
                    body.query,
                    provider=provider,
                    provider_error=provider_error,
                    tenant_scope=body.tenant_scope,
                    channel_scope=body.channel_scope,
                    product_scope=body.product_scope,
                    now=body.now,
                    limit=body.limit,
                    strategy=body.strategy,
                )
                report["provider_model"] = provider.model if provider else None

            reranker = None
            if body.reranker:
                try:
                    reranker = build_reranker(body.reranker)
                except RerankerProviderError as error:
                    report["reranker_status"] = "FALLBACK"
                    report["reranker_fallback"] = True
                    report["reranker_fallback_reason"] = error.code
            report = apply_optional_reranker(report, body.query, provider=reranker)
            trace = record_retrieval_trace(
                db,
                query=body.query,
                request_trace_id=request.state.trace_id,
                tenant_scope=body.tenant_scope,
                channel_scope=body.channel_scope,
                product_scope=body.product_scope,
                report=report,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            report["trace_id"] = trace.id
            return report
        except DomainError as error:
            record_retrieval_trace(
                db,
                query=body.query,
                request_trace_id=request.state.trace_id,
                tenant_scope=body.tenant_scope,
                channel_scope=body.channel_scope,
                product_scope=body.product_scope,
                report=report,
                duration_ms=int((time.perf_counter() - started) * 1000),
                status="FAILED",
                error_code=error.code,
            )
            raise

    @app.get(
        "/api/ops/knowledge/traces/{trace_id}",
        response_model=KnowledgeRetrievalTraceResponse,
    )
    def knowledge_retrieval_trace(
        trace_id: str,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        return get_retrieval_trace(db, trace_id)

    @app.post(
        "/api/ops/knowledge/traces/{trace_id}/feedback",
        response_model=KnowledgeRetrievalFeedbackResponse,
    )
    def knowledge_retrieval_feedback(
        trace_id: str,
        body: KnowledgeRetrievalFeedbackRequest,
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_knowledge_manager),
    ):
        return create_retrieval_feedback(
            db,
            trace_id=trace_id,
            label=body.label,
            idempotency_key=body.idempotency_key,
            created_by=operator.name,
            deidentified_note=body.deidentified_note,
        )

    @app.post(
        "/api/ops/knowledge/feedback/{feedback_id}/review",
        response_model=KnowledgeRetrievalFeedbackResponse,
    )
    def knowledge_retrieval_feedback_review(
        feedback_id: str,
        body: KnowledgeRetrievalFeedbackReviewRequest,
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_knowledge_manager),
    ):
        return review_retrieval_feedback(
            db,
            feedback_id=feedback_id,
            status=body.status,
            reviewed_by=operator.name,
            review_note=body.review_note,
        )

    @app.get(
        "/api/ops/knowledge/quality",
        response_model=KnowledgeRetrievalQualityResponse,
    )
    def knowledge_retrieval_quality(
        window_hours: int = 24,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        return retrieval_quality_report(db, window_hours=window_hours)

    @app.post(
        "/api/ops/knowledge/search-experiment",
        response_model=KnowledgeQueryEnhancementResponse,
    )
    def knowledge_query_enhancement_experiment(
        body: KnowledgeQueryEnhancementRequest,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        embedding_provider = None
        embedding_error: EmbeddingProviderError | None = None
        try:
            embedding_provider = build_embedding_provider(body.embedding_provider)
        except EmbeddingProviderError as error:
            embedding_error = error

        def search_variant(query: str) -> dict:
            if body.retrieval_strategy == "vector_v1":
                if embedding_error is not None or embedding_provider is None:
                    if embedding_error is not None:
                        raise embedding_error
                    raise EmbeddingProviderError(
                        "EMBEDDING_PROVIDER_NOT_CONFIGURED",
                        "embedding provider 未配置",
                    )
                candidates = search_vector_candidates(
                    db,
                    query,
                    provider=embedding_provider,
                    strategy=body.retrieval_strategy,
                    tenant_scope=body.tenant_scope,
                    channel_scope=body.channel_scope,
                    product_scope=body.product_scope,
                    now=body.now,
                    limit=5,
                )
                return {
                    "strategy": body.retrieval_strategy,
                    "confident": bool(candidates),
                    "score": candidates[0]["relevance"] if candidates else 0.0,
                    "results": candidates,
                    "fallback": False,
                    "fallback_reason": None,
                    "release_version": candidates[0]["release_version"] if candidates else None,
                    "provider": embedding_provider.provider,
                }
            report = search_hybrid_knowledge(
                db,
                query,
                provider=embedding_provider,
                provider_error=embedding_error,
                tenant_scope=body.tenant_scope,
                channel_scope=body.channel_scope,
                product_scope=body.product_scope,
                now=body.now,
                limit=5,
                strategy=body.retrieval_strategy,
            )
            report["provider_model"] = (
                embedding_provider.model if embedding_provider is not None else None
            )
            return report

        enhancement_provider = None
        enhancement_error: QueryEnhancementProviderError | None = None
        if body.enabled:
            try:
                enhancement_provider = build_query_enhancer(body.enhancement_provider)
            except QueryEnhancementProviderError as error:
                enhancement_error = error
        config = QueryEnhancementConfig(
            enabled=body.enabled,
            provider=body.enhancement_provider,
            strategy=body.enhancement_strategy,
            experiment_group=body.experiment_group,
            max_variants=body.max_variants,
        )
        return run_query_enhancement_experiment(
            body.query,
            config=config,
            search=search_variant,
            provider=enhancement_provider,
            provider_error=enhancement_error,
        )

    @app.post(
        "/api/ops/knowledge/query-enhancement/evaluate",
        response_model=KnowledgeQueryEnhancementEvaluationResponse,
    )
    def knowledge_query_enhancement_evaluate(
        body: KnowledgeQueryEnhancementEvaluationRequest,
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        provider = build_query_enhancer(body.enhancement_provider)
        config = QueryEnhancementConfig(
            enabled=True,
            provider=body.enhancement_provider,
            strategy=body.enhancement_strategy,
            max_variants=body.max_variants,
        )
        return evaluate_fixture_query_enhancement(config=config, provider=provider)

    @app.post(
        "/api/ops/knowledge/releases/{release_id}/rollback",
        response_model=KnowledgeReleaseResponse,
    )
    def knowledge_release_rollback(
        release_id: str,
        body: KnowledgeReleaseRollbackRequest,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        return rollback_knowledge_release(
            db,
            release_id,
            target_release_id=body.target_release_id,
        )

    @app.get(
        "/api/ops/knowledge/releases/{release_id}/chunks",
        response_model=list[KnowledgeChunkResponse],
    )
    def knowledge_release_chunks(
        release_id: str,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        items = list_release_items(db, release_id)
        return [
            chunk
            for item in items
            if (chunk := db.get(KnowledgeChunk, item.chunk_id)) is not None
        ]

    @app.get("/api/ops/dashboard", response_model=OpsDashboardResponse)
    def ops_dashboard(
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_operations_operator),
    ):
        return operations_dashboard(db)

    @app.get(
        "/api/ops/integrations/commerce",
        response_model=list[CommerceIntegrationStatusResponse],
    )
    def commerce_integration_status(
        _operator: Operator = Depends(current_operations_operator),
    ):
        return [
            CommerceIntegrationStatusResponse(
                provider=status.provider.value,
                state=status.state.value,
                capabilities=[capability.value for capability in status.capabilities],
                external_requests_enabled=status.external_requests_enabled,
                message=status.message,
            )
            for status in commerce_registry.statuses()
        ]

    @app.get("/api/ops/agent-governance")
    def agent_governance_status(
        _operator: Operator = Depends(current_operations_operator),
    ):
        return governance_snapshot()

    @app.get(
        "/api/ops/production/governance",
        response_model=ProductionGovernanceResponse,
    )
    def production_governance_status(
        _operator: Operator = Depends(current_operations_operator),
    ):
        return production_governance_report()

    @app.post(
        "/api/ops/production/release-gate",
        response_model=ProductionGovernanceResponse,
    )
    def production_release_gate(
        body: ProductionReleaseGateRequest,
        _operator: Operator = Depends(current_operations_operator),
    ):
        return production_governance_report(
            manifest=body.manifest,
            evidence=body.evidence,
            offline_metrics=body.offline_metrics,
            online_metrics=body.online_metrics,
            maintenance_checks=body.maintenance_checks,
        )

    @app.get("/api/ops/tickets", response_model=OpsTicketReportResponse)
    def ops_ticket_report(
        support_group: str | None = None,
        sla_status: str | None = None,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_operations_operator),
    ):
        return operations_ticket_report(
            db,
            support_group=support_group,
            sla_status=sla_status,
        )

    @app.get("/api/ops/quality-reviews", response_model=OpsQualityReportResponse)
    def ops_quality_reviews(
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_operations_operator),
    ):
        return operations_quality_report(db)

    @app.get("/api/ops/alerts", response_model=OpsAlertSnapshotResponse)
    def ops_alert_index(
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_operations_operator),
    ):
        return operations_alerts(db)

    @app.get("/api/ops/alerts/stream")
    def ops_alert_stream(
        once: bool = False,
        operator: Operator = Depends(current_operations_operator),
    ):
        return StreamingResponse(
            stream_operations_alerts(operator.id, once=once),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post(
        "/api/ops/alerts/{ticket_id}/{alert_type}/acknowledge",
        response_model=OpsAlertAcknowledgementResponse,
    )
    def ops_alert_acknowledge(
        ticket_id: str,
        alert_type: str,
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_operations_operator),
    ):
        return acknowledge_operations_alert(db, operator, ticket_id, alert_type)

    @app.post("/api/ops/knowledge", response_model=KnowledgeArticleResponse)
    def publish_knowledge(
        body: KnowledgePublishRequest,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        return publish_knowledge_article(db, body)

    @app.post(
        "/api/ops/knowledge/{article_id}/deactivate",
        response_model=KnowledgeArticleResponse,
    )
    def deactivate_knowledge(
        article_id: str,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_knowledge_manager),
    ):
        return deactivate_knowledge_article(db, article_id)

    if settings.demo_mode_enabled:

        @app.post("/api/demo/reset")
        def reset_demo(
            db: Session = Depends(get_db),
            _customer: Customer = Depends(current_customer),
        ):
            reset_demo_state(db)
            return {"status": "reset"}

        @app.post(
            "/api/demo/reset-after-completion/{ticket_id}",
            response_model=DemoResetResponse,
        )
        def reset_demo_after_completion(
            ticket_id: str,
            db: Session = Depends(get_db),
            operator: Operator = Depends(current_demo_reset_operator),
        ):
            return reset_demo_state_after_completed_ticket(db, operator, ticket_id)

    @app.post("/api/conversations", response_model=ConversationCreateResponse)
    def start_conversation(
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        conversation = create_conversation(db, customer)
        return ConversationCreateResponse(id=conversation.id, customer_name=customer.name)

    @app.get("/api/conversations/{conversation_id}")
    def get_conversation_state(
        conversation_id: str,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        return conversation_state(db, customer, conversation_id)

    @app.post(
        "/api/conversations/{conversation_id}/active-order",
        response_model=OrderResponse,
    )
    def choose_active_order(
        conversation_id: str,
        body: ActiveOrderRequest,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        order = set_active_order(db, customer, conversation_id, body.order_number)
        return OrderResponse.model_validate(order, from_attributes=True)

    @app.post(
        "/api/conversations/{conversation_id}/order-selection",
        response_model=list[OrderResponse],
    )
    def open_order_selection(
        conversation_id: str,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        return request_order_selection(db, customer, conversation_id)

    @app.post("/api/conversations/{conversation_id}/messages")
    async def post_message(
        conversation_id: str,
        body: MessageRequest,
        request: Request,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        async def stream() -> AsyncIterator[str]:
            if settings.agent_mode.strip().lower() in {"model", "openai"}:
                from serviceops.agent.openai_runtime import ModelSupportAgent
                from serviceops.agent.providers import ModelProviderConfiguration

                configuration = ModelProviderConfiguration.from_settings(settings)
                async for event in ModelSupportAgent(
                    db,
                    customer,
                    configuration,
                ).stream(
                    conversation_id,
                    body.content,
                    trace_id=request.state.trace_id,
                ):
                    yield (
                        json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
                        + "\n"
                    )
                return
            events = DeterministicSupportAgent(db, customer).stream(
                conversation_id,
                body.content,
                trace_id=request.state.trace_id,
            )
            for event in events:
                yield json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.get("/api/orders/recent", response_model=list[OrderResponse])
    def recent_orders(
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        return list_recent_orders(db, customer)

    @app.get("/api/orders/{order_number}", response_model=OrderResponse)
    def order_detail(
        order_number: str,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        order = get_order(db, customer, order_number)
        return OrderResponse.model_validate(order, from_attributes=True)

    @app.get("/api/orders/{order_number}/shipping", response_model=ShippingResponse)
    def shipping_detail(
        order_number: str,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        return get_shipping_status(db, customer, order_number)

    @app.post("/api/tickets", response_model=TicketResponse)
    def create_ticket_endpoint(
        body: TicketCreateRequest,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        if body.ticket_type not in {"SHIPPING", "ORDER", "REFUND", "OTHER"}:
            raise ValidationError("INVALID_TICKET_TYPE", "不支持的工单类型")
        ticket = create_ticket(
            db,
            customer,
            conversation_id=body.conversation_id,
            order_number=body.order_number,
            ticket_type=body.ticket_type,
            reason=body.reason,
        )
        return ticket_response(db, ticket)

    @app.get("/api/tickets/{ticket_id}", response_model=TicketResponse)
    def ticket_detail(
        ticket_id: str,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        return ticket_response(db, get_ticket(db, customer, ticket_id))

    @app.post("/api/tickets/{ticket_id}/messages", response_model=TicketResponse)
    def add_customer_ticket_message_endpoint(
        ticket_id: str,
        body: TicketMessageRequest,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        ticket = add_customer_ticket_message(db, customer, ticket_id, body.content)
        return ticket_response(db, ticket)

    @app.post(
        "/api/tickets/{ticket_id}/feedback",
        response_model=CustomerFeedbackResponse,
    )
    def submit_ticket_feedback(
        ticket_id: str,
        body: CustomerFeedbackRequest,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        return submit_customer_feedback(
            db,
            customer,
            ticket_id,
            rating=body.rating,
            comment=body.comment,
        )

    @app.post("/api/tickets/{ticket_id}/handoff", response_model=TicketResponse)
    def handoff_ticket_endpoint(
        ticket_id: str,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        return ticket_response(db, request_human_handoff(db, customer, ticket_id))

    @app.post("/api/tickets/{ticket_id}/handoff/cancel", response_model=TicketResponse)
    def cancel_handoff_ticket_endpoint(
        ticket_id: str,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        return ticket_response(db, cancel_human_handoff(db, customer, ticket_id))

    @app.post("/api/refund-requests/{refund_id}/confirm", response_model=RefundResponse)
    def confirm_refund_endpoint(
        refund_id: str,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        return confirm_refund(db, customer, refund_id, idempotency_key or "")

    @app.post("/api/agent/refund-requests/{refund_id}/approve", response_model=RefundResponse)
    def approve_refund_endpoint(
        refund_id: str,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_support_agent),
    ):
        return approve_refund(db, operator, refund_id, idempotency_key or "")

    @app.post("/api/agent/refund-requests/{refund_id}/reject", response_model=RefundResponse)
    def reject_refund_endpoint(
        refund_id: str,
        body: RefundDecisionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_support_agent),
    ):
        return reject_refund(db, operator, refund_id, idempotency_key or "", body.reason)

    @app.post("/api/agent/refund-requests/{refund_id}/withdraw", response_model=RefundResponse)
    def withdraw_refund_endpoint(
        refund_id: str,
        body: RefundDecisionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        operator: Operator = Depends(current_support_agent),
    ):
        return withdraw_refund(db, operator, refund_id, idempotency_key or "", body.reason)

    @app.post("/api/refund-requests/{refund_id}/cancel", response_model=RefundResponse)
    def cancel_refund_endpoint(
        refund_id: str,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        return cancel_refund(db, customer, refund_id)

    return app


app = create_app()
