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
    current_customer,
    current_operator,
    current_support_agent,
)
from serviceops.knowledge.management import (
    deactivate_knowledge_article,
    list_knowledge_articles,
    publish_knowledge_article,
)
from serviceops.models import Customer, Operator
from serviceops.observability import log_request_event, normalize_trace_id
from serviceops.operations.service import (
    acknowledge_operations_alert,
    operations_alerts,
    operations_dashboard,
    operations_quality_report,
    operations_ticket_report,
)
from serviceops.operations.streaming import stream_operations_alerts
from serviceops.orders.service import get_order, list_recent_orders
from serviceops.refunds.service import cancel_refund, confirm_refund
from serviceops.seed import reset_demo_state, seed_database
from serviceops.shared.errors import DomainError, ValidationError
from serviceops.shared.schemas import (
    ActiveOrderRequest,
    AgentTicketNoteRequest,
    AgentTicketResolveRequest,
    AgentTicketResponse,
    ConversationCreateResponse,
    CustomerFeedbackRequest,
    CustomerFeedbackResponse,
    KnowledgeArticleResponse,
    KnowledgePublishRequest,
    MessageRequest,
    OpsAlertAcknowledgementResponse,
    OpsAlertSnapshotResponse,
    OpsDashboardResponse,
    OpsQualityReportResponse,
    OpsTicketReportResponse,
    OrderResponse,
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
    list_workbench_tickets,
    resolve_workbench_ticket,
)
from serviceops.workbench.streaming import stream_workbench_tickets


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        seed_database(db)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Enterprise customer support and ticket execution Agent MVP",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.web_origin.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
        _operator: Operator = Depends(current_operator),
    ):
        return list_knowledge_articles(db)

    @app.get("/api/ops/dashboard", response_model=OpsDashboardResponse)
    def ops_dashboard(
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_operator),
    ):
        return operations_dashboard(db)

    @app.get("/api/ops/tickets", response_model=OpsTicketReportResponse)
    def ops_ticket_report(
        support_group: str | None = None,
        sla_status: str | None = None,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_operator),
    ):
        return operations_ticket_report(
            db,
            support_group=support_group,
            sla_status=sla_status,
        )

    @app.get("/api/ops/quality-reviews", response_model=OpsQualityReportResponse)
    def ops_quality_reviews(
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_operator),
    ):
        return operations_quality_report(db)

    @app.get("/api/ops/alerts", response_model=OpsAlertSnapshotResponse)
    def ops_alert_index(
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_operator),
    ):
        return operations_alerts(db)

    @app.get("/api/ops/alerts/stream")
    def ops_alert_stream(
        once: bool = False,
        operator: Operator = Depends(current_operator),
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
        operator: Operator = Depends(current_operator),
    ):
        return acknowledge_operations_alert(db, operator, ticket_id, alert_type)

    @app.post("/api/ops/knowledge", response_model=KnowledgeArticleResponse)
    def publish_knowledge(
        body: KnowledgePublishRequest,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_operator),
    ):
        return publish_knowledge_article(db, body)

    @app.post(
        "/api/ops/knowledge/{article_id}/deactivate",
        response_model=KnowledgeArticleResponse,
    )
    def deactivate_knowledge(
        article_id: str,
        db: Session = Depends(get_db),
        _operator: Operator = Depends(current_operator),
    ):
        return deactivate_knowledge_article(db, article_id)

    @app.post("/api/demo/reset")
    def reset_demo(
        db: Session = Depends(get_db),
        _customer: Customer = Depends(current_customer),
    ):
        if settings.app_env == "production":
            raise ValidationError("DEMO_RESET_DISABLED", "生产环境不允许重置演示数据")
        reset_demo_state(db)
        return {"status": "reset"}

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
            events = DeterministicSupportAgent(db, customer).run(
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

    @app.post("/api/refund-requests/{refund_id}/cancel", response_model=RefundResponse)
    def cancel_refund_endpoint(
        refund_id: str,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        return cancel_refund(db, customer, refund_id)

    return app


app = create_app()
