import inspect
import json
import uuid
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
)
from serviceops.database import Base, engine, get_db
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
from serviceops.operations.service import operations_dashboard
from serviceops.orders.service import get_order
from serviceops.refunds.service import cancel_refund, confirm_refund
from serviceops.seed import reset_demo_state, seed_database
from serviceops.shared.errors import DomainError, ValidationError
from serviceops.shared.schemas import (
    AgentTicketNoteRequest,
    AgentTicketResolveRequest,
    AgentTicketResponse,
    ConversationCreateResponse,
    KnowledgeArticleResponse,
    KnowledgePublishRequest,
    MessageRequest,
    OpsDashboardResponse,
    OrderResponse,
    RefundResponse,
    ShippingResponse,
    TicketCreateRequest,
    TicketResponse,
)
from serviceops.shipping.service import get_shipping_status
from serviceops.tickets.service import (
    cancel_human_handoff,
    create_ticket,
    get_ticket,
    request_human_handoff,
    ticket_response,
)
from serviceops.workbench.service import (
    accept_workbench_ticket,
    add_workbench_note,
    list_workbench_tickets,
    resolve_workbench_ticket,
)


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
        request.state.trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Trace-ID"] = request.state.trace_id
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
        _operator: Operator = Depends(current_support_agent),
    ):
        return list_workbench_tickets(db)

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

    @app.post("/api/conversations/{conversation_id}/messages")
    async def post_message(
        conversation_id: str,
        body: MessageRequest,
        db: Session = Depends(get_db),
        customer: Customer = Depends(current_customer),
    ):
        runtime: object
        if settings.agent_mode == "openai" and settings.openai_api_key:
            from serviceops.agent.openai_runtime import OpenAISupportAgent

            runtime = OpenAISupportAgent(db, customer, settings.openai_model)
        else:
            runtime = DeterministicSupportAgent(db, customer)
        result = runtime.run(conversation_id, body.content)
        events = await result if inspect.isawaitable(result) else result

        async def stream() -> AsyncIterator[str]:
            for event in events:
                yield json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

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
