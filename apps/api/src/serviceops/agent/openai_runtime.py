import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from agents import (
    Agent,
    ModelSettings,
    RunConfig,
    RunContextWrapper,
    Runner,
    ToolExecutionConfig,
    function_tool,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.agent.context import (
    ContextAssembler,
    ContextAssemblyError,
    ContextMessage,
    TrustedBusinessState,
)
from serviceops.agent.events import (
    SAFE_ACK_MESSAGE,
    SAFE_FAILURE_MESSAGE,
    SAFE_THINKING_MESSAGE,
    EventSequencer,
    phase_payload,
    progress_event,
)
from serviceops.agent.orchestrator import DeterministicSupportAgent
from serviceops.agent.providers import (
    ModelProviderConfiguration,
    ModelReliabilityGuard,
    classify_model_error,
    reliability_guard_for,
    sdk_model_provider_for,
)
from serviceops.agent.release import DEFAULT_AGENT_RELEASE, AgentRelease
from serviceops.audit.service import record_model_invocation
from serviceops.config import get_settings
from serviceops.conversations.service import (
    add_message,
    clear_pending_action,
    get_conversation,
    order_snapshot,
    request_order_selection,
    set_active_order,
    set_pending_action,
)
from serviceops.knowledge.service import search_knowledge_base as search_knowledge
from serviceops.models import Customer, Message, Order, new_id
from serviceops.observability import log_request_event
from serviceops.orders.service import get_order as fetch_order
from serviceops.orders.service import list_recent_orders as fetch_recent_orders
from serviceops.refunds.service import create_refund_request as create_refund
from serviceops.shared.schemas import AgentEvent, EventPhase, EventType
from serviceops.shipping.service import get_shipping_status as fetch_shipping
from serviceops.tickets.service import create_ticket as create_support_ticket
from serviceops.tickets.service import get_current_ticket as fetch_current_ticket
from serviceops.tickets.service import get_ticket as fetch_ticket
from serviceops.tickets.service import request_human_handoff as handoff_to_human
from serviceops.tickets.service import ticket_response


@dataclass
class AgentContext:
    db: Session
    customer: Customer
    conversation_id: str
    message_id: str
    trace_id: str
    events: list[AgentEvent] = field(default_factory=list)
    attempted_write_tools: set[str] = field(default_factory=set)

    @property
    def collector(self) -> DeterministicSupportAgent:
        return DeterministicSupportAgent(self.db, self.customer)


def _claim_write_attempt(context: AgentContext, tool_name: str) -> bool:
    """Allow each mutating tool at most once during one model request."""
    if tool_name in context.attempted_write_tools:
        return False
    context.attempted_write_tools.add(tool_name)
    return True


def _write_retry_blocked(tool_name: str) -> dict:
    return {
        "status": "FAILED",
        "error_code": "WRITE_TOOL_RETRY_BLOCKED",
        "tool_name": tool_name,
        "message": "同一请求中不能重复执行该写操作，请说明首次执行结果。",
    }


@function_tool(name_override="search_knowledge_base")
def search_knowledge_base(ctx: RunContextWrapper[AgentContext], query: str) -> dict:
    """Search active after-sales policy evidence and return source, version, section and relevance."""
    context = ctx.context
    result, _ = context.collector._invoke(
        context.events,
        trace_id=context.trace_id,
        conversation_id=context.conversation_id,
        message_id=context.message_id,
        name="search_knowledge_base",
        input_summary={"query": query},
        callback=lambda: search_knowledge(context.db, query),
    )
    return result


@function_tool(name_override="get_order")
def get_order(ctx: RunContextWrapper[AgentContext], order_number: str) -> dict:
    """Read one order after server-side ownership validation; never accepts a user_id."""
    context = ctx.context
    result, _ = context.collector._invoke(
        context.events,
        trace_id=context.trace_id,
        conversation_id=context.conversation_id,
        message_id=context.message_id,
        name="get_order",
        input_summary={"order_number": order_number},
        callback=lambda: fetch_order(context.db, context.customer, order_number),
    )
    set_active_order(
        context.db,
        context.customer,
        context.conversation_id,
        result.order_number,
    )
    context.collector._emit_active_order(
        context.events,
        context.trace_id,
        context.conversation_id,
        context.message_id,
        result,
    )
    clear_pending_action(context.db, context.customer, context.conversation_id)
    return context.collector._summary(result)


@function_tool(name_override="list_recent_orders")
def list_recent_orders(ctx: RunContextWrapper[AgentContext]) -> dict:
    """List at most three recent orders owned by the signed-in customer for explicit selection."""
    context = ctx.context
    result, _ = context.collector._invoke(
        context.events,
        trace_id=context.trace_id,
        conversation_id=context.conversation_id,
        message_id=context.message_id,
        name="list_recent_orders",
        input_summary={"limit": 3},
        callback=lambda: fetch_recent_orders(context.db, context.customer),
    )
    if len(result) == 1:
        set_active_order(
            context.db,
            context.customer,
            context.conversation_id,
            result[0].order_number,
        )
        context.collector._emit_active_order(
            context.events,
            context.trace_id,
            context.conversation_id,
            context.message_id,
            result[0],
        )
        clear_pending_action(context.db, context.customer, context.conversation_id)
    elif len(result) > 1:
        set_pending_action(
            context.db,
            context.customer,
            context.conversation_id,
            "MODEL_RESUME",
        )
        request_order_selection(
            context.db,
            context.customer,
            context.conversation_id,
        )
        context.events.append(
            AgentEvent(
                type=EventType.ORDER_SELECTION_REQUIRED,
                conversation_id=context.conversation_id,
                message_id=context.message_id,
                trace_id=context.trace_id,
                payload={
                    "reason": "multiple_recent_orders",
                    "orders": [order_snapshot(item) for item in result],
                },
            )
        )
    return context.collector._summary(result)


@function_tool(name_override="get_shipping_status")
def get_shipping_status(ctx: RunContextWrapper[AgentContext], order_number: str) -> dict:
    """Return shipping nodes and deterministic abnormality classification for an owned order."""
    context = ctx.context
    result, _ = context.collector._invoke(
        context.events,
        trace_id=context.trace_id,
        conversation_id=context.conversation_id,
        message_id=context.message_id,
        name="get_shipping_status",
        input_summary={"order_number": order_number},
        callback=lambda: fetch_shipping(context.db, context.customer, order_number),
    )
    clear_pending_action(context.db, context.customer, context.conversation_id)
    return result.model_dump(mode="json")


@function_tool(name_override="create_ticket")
def create_ticket(
    ctx: RunContextWrapper[AgentContext],
    order_number: str,
    reason: str,
) -> dict:
    """Idempotently create a shipping-exception ticket for an owned order."""
    context = ctx.context
    if not _claim_write_attempt(context, "create_ticket"):
        return _write_retry_blocked("create_ticket")
    result, _ = context.collector._invoke(
        context.events,
        trace_id=context.trace_id,
        conversation_id=context.conversation_id,
        message_id=context.message_id,
        name="create_ticket",
        input_summary={"order_number": order_number},
        callback=lambda: create_support_ticket(
            context.db,
            context.customer,
            conversation_id=context.conversation_id,
            order_number=order_number,
            ticket_type="SHIPPING",
            reason=reason,
        ),
    )
    clear_pending_action(context.db, context.customer, context.conversation_id)
    return context.collector._summary(result)


@function_tool(name_override="create_refund_request")
def create_refund_request(
    ctx: RunContextWrapper[AgentContext],
    order_number: str,
    reason: str,
) -> dict:
    """Create a pending refund request using the server-calculated refundable amount; does not refund."""
    context = ctx.context
    if not _claim_write_attempt(context, "create_refund_request"):
        return _write_retry_blocked("create_refund_request")
    order = fetch_order(context.db, context.customer, order_number)
    result, _ = context.collector._invoke(
        context.events,
        trace_id=context.trace_id,
        conversation_id=context.conversation_id,
        message_id=context.message_id,
        name="create_refund_request",
        input_summary={"order_number": order_number, "reason": reason},
        callback=lambda: create_refund(
            context.db,
            context.customer,
            conversation_id=context.conversation_id,
            order_number=order_number,
            reason=reason,
            requested_amount=Decimal(order.refundable_amount),
        ),
    )
    summary = context.collector._summary(result)
    context.events.append(
        AgentEvent(
            type=EventType.APPROVAL_REQUIRED,
            conversation_id=context.conversation_id,
            message_id=context.message_id,
            trace_id=context.trace_id,
            order_id=result.order_id,
            ticket_id=result.ticket_id,
            refund_request_id=result.id,
            payload={
                "approval_type": "refund_human_approval",
                "refund_number": result.refund_number,
                "amount": str(result.amount),
                "method": result.method,
                "reason": result.reason,
                "status": result.status,
            },
        )
    )
    clear_pending_action(context.db, context.customer, context.conversation_id)
    return summary


@function_tool(name_override="get_ticket")
def get_ticket(ctx: RunContextWrapper[AgentContext], ticket_id: str) -> dict:
    """Read one ticket and its processing records after server-side ownership validation."""
    context = ctx.context
    result, _ = context.collector._invoke(
        context.events,
        trace_id=context.trace_id,
        conversation_id=context.conversation_id,
        message_id=context.message_id,
        name="get_ticket",
        input_summary={"ticket_id": ticket_id},
        callback=lambda: fetch_ticket(context.db, context.customer, ticket_id),
    )
    return ticket_response(context.db, result).model_dump(mode="json")


@function_tool(name_override="get_current_ticket")
def get_current_ticket(ctx: RunContextWrapper[AgentContext]) -> dict:
    """Read the latest ticket owned by the customer in the current conversation."""
    context = ctx.context
    result, _ = context.collector._invoke(
        context.events,
        trace_id=context.trace_id,
        conversation_id=context.conversation_id,
        message_id=context.message_id,
        name="get_current_ticket",
        input_summary={},
        callback=lambda: fetch_current_ticket(
            context.db, context.customer, context.conversation_id
        ),
    )
    if result is None:
        return {"status": "NOT_FOUND"}
    return ticket_response(context.db, result).model_dump(mode="json")


@function_tool(name_override="request_human_handoff")
def request_human_handoff(
    ctx: RunContextWrapper[AgentContext], ticket_id: str
) -> dict:
    """Transfer an owned unresolved ticket to its server-selected human support group."""
    context = ctx.context
    if not _claim_write_attempt(context, "request_human_handoff"):
        return _write_retry_blocked("request_human_handoff")
    result, _ = context.collector._invoke(
        context.events,
        trace_id=context.trace_id,
        conversation_id=context.conversation_id,
        message_id=context.message_id,
        name="request_human_handoff",
        input_summary={"ticket_id": ticket_id},
        callback=lambda: handoff_to_human(
            context.db, context.customer, ticket_id
        ),
    )
    context.events.append(
        AgentEvent(
            type=EventType.BUSINESS_STATE_CHANGED,
            conversation_id=context.conversation_id,
            message_id=context.message_id,
            trace_id=context.trace_id,
            ticket_id=result.id,
            payload={
                "object": "ticket",
                "status": result.status,
                "handoff_status": result.handoff_status,
                "assignee_name": result.assignee_name,
            },
        )
    )
    clear_pending_action(context.db, context.customer, context.conversation_id)
    return ticket_response(context.db, result).model_dump(mode="json")


CUSTOMER_AGENT_TOOLS = [
    search_knowledge_base,
    list_recent_orders,
    get_order,
    get_shipping_status,
    create_ticket,
    get_current_ticket,
    get_ticket,
    request_human_handoff,
    create_refund_request,
]


WRITE_TOOL_NAMES = frozenset(
    {"create_ticket", "create_refund_request", "request_human_handoff"}
)


class ModelSupportAgent:
    def __init__(
        self,
        db: Session,
        customer: Customer,
        configuration: ModelProviderConfiguration,
        *,
        sdk_provider: Any | None = None,
        reliability_guard: ModelReliabilityGuard | None = None,
        runner_streamed: Callable[..., Any] | None = None,
        release: AgentRelease | None = None,
        context_assembler: ContextAssembler | None = None,
    ):
        self.db = db
        self.customer = customer
        self.configuration = configuration
        self.release = release or DEFAULT_AGENT_RELEASE
        self.context_assembler = context_assembler or ContextAssembler()
        self.run_binding = self.release.bind(
            runtime_mode="model",
            provider=configuration.provider,
            model_name=configuration.model_name,
            tool_names=tuple(tool.name for tool in CUSTOMER_AGENT_TOOLS),
        )
        self.sdk_provider = sdk_provider
        self.reliability_guard = reliability_guard or reliability_guard_for(configuration)
        self.runner_streamed = runner_streamed or Runner.run_streamed
        self.agent = Agent[AgentContext](
            name="Harbor Customer Support Agent",
            model=configuration.model_name,
            instructions=self.release.system_prompt,
            tools=CUSTOMER_AGENT_TOOLS,
            model_settings=ModelSettings(parallel_tool_calls=False),
        )

    async def stream(
        self,
        conversation_id: str,
        content: str,
        *,
        trace_id: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        conversation = get_conversation(self.db, self.customer, conversation_id)
        trace_id_value = trace_id or str(uuid.uuid4())
        user_message_id = new_id()
        response_message_id = new_id()
        sequencer = EventSequencer(trace_id_value)
        yield sequencer.stamp(
            progress_event(
                event_type=EventType.ACK,
                conversation_id=conversation_id,
                message_id=response_message_id,
                trace_id=trace_id_value,
                phase=EventPhase.ACK,
                message=SAFE_ACK_MESSAGE,
            )
        )
        yield sequencer.stamp(
            progress_event(
                event_type=EventType.THINKING,
                conversation_id=conversation_id,
                message_id=response_message_id,
                trace_id=trace_id_value,
                phase=EventPhase.THINKING,
                message=SAFE_THINKING_MESSAGE,
            )
        )
        settings = get_settings()
        active_order = (
            self.db.get(Order, conversation.active_order_id)
            if conversation.active_order_id
            else None
        )
        recent_messages = list(
            reversed(
                list(
                    self.db.scalars(
                        select(Message)
                        .where(Message.conversation_id == conversation_id)
                        .order_by(Message.created_at.desc())
                        .limit(12)
                    )
                )
            )
        )
        current_context_message = ContextMessage(
            message_id=user_message_id,
            role="user",
            content=content,
            source_id=f"customer-message:{user_message_id}",
        )
        context_assembly = None
        try:
            context_assembly = self.context_assembler.assemble(
                trusted_state=TrustedBusinessState(
                    source_id=f"conversation-state:{conversation_id}",
                    active_order_number=(
                        active_order.order_number
                        if active_order and active_order.customer_id == self.customer.id
                        else None
                    ),
                    pending_action=conversation.pending_action,
                    knowledge_release_version=self.run_binding.knowledge_release_version,
                ),
                recent_messages=[
                    ContextMessage(
                        message_id=item.id,
                        role=item.role,
                        content=item.content,
                        source_id=f"conversation-message:{item.id}",
                    )
                    for item in recent_messages
                ],
                current_message=current_context_message,
            )
        except ContextAssemblyError as error:
            record_model_invocation(
                self.db,
                trace_id=trace_id_value,
                conversation_id=conversation_id,
                message_id=user_message_id,
                provider=self.configuration.provider,
                model_name=self.configuration.model_name,
                api_style=self.configuration.api_style,
                status="BLOCKED",
                duration_ms=0,
                error_type=error.code,
                fallback_used=False,
                **self.run_binding.as_audit_kwargs(),
            )
            yield sequencer.stamp(
                AgentEvent(
                    type=EventType.MESSAGE_DELTA,
                    conversation_id=conversation_id,
                    message_id=response_message_id,
                    trace_id=trace_id_value,
                    phase=EventPhase.FINAL_RESPONSE,
                    payload=phase_payload(
                        {"delta": SAFE_FAILURE_MESSAGE}, EventPhase.FINAL_RESPONSE
                    ),
                )
            )
            yield sequencer.stamp(
                AgentEvent(
                    type=EventType.ERROR,
                    conversation_id=conversation_id,
                    message_id=response_message_id,
                    trace_id=trace_id_value,
                    phase=EventPhase.FINAL_RESPONSE,
                    payload={
                        "code": error.code,
                        "message": SAFE_FAILURE_MESSAGE,
                        "recoverable": True,
                        "phase": EventPhase.FINAL_RESPONSE.value,
                    },
                )
            )
            yield sequencer.stamp(
                AgentEvent(
                    type=EventType.RESPONSE_COMPLETED,
                    conversation_id=conversation_id,
                    message_id=response_message_id,
                    trace_id=trace_id_value,
                    phase=EventPhase.FINAL_RESPONSE,
                    payload=phase_payload(
                        {"status": "failed"}, EventPhase.FINAL_RESPONSE
                    ),
                )
            )
            return

        user_message = add_message(
            self.db,
            conversation,
            "user",
            content,
            message_id=user_message_id,
        )
        context = AgentContext(
            db=self.db,
            customer=self.customer,
            conversation_id=conversation_id,
            message_id=user_message.id,
            trace_id=trace_id_value,
        )
        prompt = context_assembly.prompt
        context_audit = context_assembly.audit_fields()
        started = time.perf_counter()
        emitted_context_events = 0
        streamed_text: list[str] = []
        try:
            self.reliability_guard.before_request()
            provider = self.sdk_provider or sdk_model_provider_for(self.configuration)
            result = self.runner_streamed(
                self.agent,
                prompt,
                context=context,
                max_turns=self.configuration.max_turns,
                run_config=RunConfig(
                    model_provider=provider,
                    workflow_name="Harbor Support customer service",
                    group_id=conversation_id,
                    tool_execution=ToolExecutionConfig(
                        max_function_tool_concurrency=1
                    ),
                    tracing_disabled=self.configuration.provider != "openai",
                    trace_include_sensitive_data=(
                        settings.sensitive_tracing_enabled
                        if self.configuration.provider == "openai"
                        else False
                    ),
                ),
            )
            async with asyncio.timeout(self.configuration.timeout_seconds):
                async for sdk_event in result.stream_events():
                    while emitted_context_events < len(context.events):
                        yield sequencer.stamp(context.events[emitted_context_events])
                        emitted_context_events += 1
                    data = getattr(sdk_event, "data", None)
                    if (
                        getattr(sdk_event, "type", None) == "raw_response_event"
                        and getattr(data, "type", None) == "response.output_text.delta"
                    ):
                        delta = str(getattr(data, "delta", ""))
                        if delta:
                            streamed_text.append(delta)
                            yield sequencer.stamp(
                                AgentEvent(
                                    type=EventType.MESSAGE_DELTA,
                                    conversation_id=conversation_id,
                                    message_id=response_message_id,
                                    trace_id=context.trace_id,
                                    phase=EventPhase.FINAL_RESPONSE,
                                    payload=phase_payload(
                                        {"delta": delta}, EventPhase.FINAL_RESPONSE
                                    ),
                                )
                            )
            while emitted_context_events < len(context.events):
                yield sequencer.stamp(context.events[emitted_context_events])
                emitted_context_events += 1
            raw_answer = result.final_output
            answer = (
                str(raw_answer).strip()
                if raw_answer is not None
                else "".join(streamed_text).strip()
            )
            if not answer:
                raise RuntimeError("模型没有返回可用回答")
            if not streamed_text:
                yield sequencer.stamp(
                    AgentEvent(
                        type=EventType.MESSAGE_DELTA,
                        conversation_id=conversation_id,
                        message_id=response_message_id,
                        trace_id=context.trace_id,
                        phase=EventPhase.FINAL_RESPONSE,
                        payload=phase_payload(
                            {"delta": answer}, EventPhase.FINAL_RESPONSE
                        ),
                    )
                )
            add_message(
                self.db,
                conversation,
                "agent",
                answer,
                message_id=response_message_id,
            )
            usage = result.context_wrapper.usage
            duration_ms = max(1, int((time.perf_counter() - started) * 1000))
            record_model_invocation(
                self.db,
                trace_id=context.trace_id,
                conversation_id=conversation_id,
                message_id=user_message.id,
                provider=self.configuration.provider,
                model_name=self.configuration.model_name,
                api_style=self.configuration.api_style,
                status="SUCCEEDED",
                duration_ms=duration_ms,
                **self.run_binding.as_audit_kwargs(),
                **context_audit,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
            )
            self.reliability_guard.record_success()
            log_request_event(
                logging.INFO,
                "model_invocation_completed",
                trace_id=context.trace_id,
                provider=self.configuration.provider,
                model=self.configuration.model_name,
                duration_ms=duration_ms,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
            )
            yield sequencer.stamp(
                AgentEvent(
                    type=EventType.RESPONSE_COMPLETED,
                    conversation_id=conversation_id,
                    message_id=response_message_id,
                    trace_id=context.trace_id,
                    phase=EventPhase.FINAL_RESPONSE,
                    payload=phase_payload(
                        {"status": "completed"}, EventPhase.FINAL_RESPONSE
                    ),
                )
            )
        except asyncio.CancelledError:
            duration_ms = max(1, int((time.perf_counter() - started) * 1000))
            record_model_invocation(
                self.db,
                trace_id=context.trace_id,
                conversation_id=conversation_id,
                message_id=user_message.id,
                provider=self.configuration.provider,
                model_name=self.configuration.model_name,
                api_style=self.configuration.api_style,
                status="FAILED",
                duration_ms=duration_ms,
                **self.run_binding.as_audit_kwargs(),
                **context_audit,
                error_type="MODEL_CLIENT_DISCONNECTED",
            )
            raise
        except Exception as error:
            error_type = classify_model_error(error)
            self.reliability_guard.record_failure(error)
            duration_ms = max(1, int((time.perf_counter() - started) * 1000))
            completed_write = any(
                event.type == EventType.TOOL_COMPLETED
                and event.payload.get("tool_name") in WRITE_TOOL_NAMES
                for event in context.events
            )
            use_fallback = (
                self.configuration.fallback_enabled
                and not streamed_text
                and not completed_write
            )
            record_model_invocation(
                self.db,
                trace_id=context.trace_id,
                conversation_id=conversation_id,
                message_id=user_message.id,
                provider=self.configuration.provider,
                model_name=self.configuration.model_name,
                api_style=self.configuration.api_style,
                status="FAILED",
                duration_ms=duration_ms,
                **self.run_binding.as_audit_kwargs(),
                **context_audit,
                error_type=error_type,
                fallback_used=use_fallback,
            )
            log_request_event(
                logging.WARNING,
                "model_invocation_failed",
                trace_id=context.trace_id,
                provider=self.configuration.provider,
                model=self.configuration.model_name,
                duration_ms=duration_ms,
                error_type=error_type,
                fallback_used=use_fallback,
            )
            while emitted_context_events < len(context.events):
                yield sequencer.stamp(context.events[emitted_context_events])
                emitted_context_events += 1
            if use_fallback:
                yield sequencer.stamp(
                    AgentEvent(
                        type=EventType.MODEL_FALLBACK,
                        conversation_id=conversation_id,
                        message_id=user_message.id,
                        trace_id=context.trace_id,
                        payload={
                            "provider": self.configuration.provider,
                            "model": self.configuration.model_name,
                            "reason": "temporarily_unavailable",
                            "message": "模型服务暂时不可用，已切换到基础服务模式。",
                        },
                    )
                )
                for event in DeterministicSupportAgent(self.db, self.customer).run(
                    conversation_id,
                    content,
                    trace_id=context.trace_id,
                    _user_message=user_message,
                    include_progress=False,
                    stamp_events=False,
                ):
                    yield sequencer.stamp(event)
                return
            failure_message = "模型服务暂时不可用，当前请求没有继续自动执行，请稍后重试。"
            add_message(
                self.db,
                conversation,
                "agent",
                failure_message,
                message_id=response_message_id,
            )
            yield sequencer.stamp(
                AgentEvent(
                    type=EventType.MESSAGE_DELTA,
                    conversation_id=conversation_id,
                    message_id=response_message_id,
                    trace_id=context.trace_id,
                    phase=EventPhase.FINAL_RESPONSE,
                    payload=phase_payload(
                        {"delta": SAFE_FAILURE_MESSAGE}, EventPhase.FINAL_RESPONSE
                    ),
                )
            )
            yield sequencer.stamp(
                AgentEvent(
                    type=EventType.ERROR,
                    conversation_id=conversation_id,
                    message_id=response_message_id,
                    trace_id=context.trace_id,
                    phase=EventPhase.FINAL_RESPONSE,
                    payload={
                        "code": error_type,
                        "message": SAFE_FAILURE_MESSAGE,
                        "recoverable": True,
                        "phase": EventPhase.FINAL_RESPONSE.value,
                    },
                )
            )
            yield sequencer.stamp(
                AgentEvent(
                    type=EventType.RESPONSE_COMPLETED,
                    conversation_id=conversation_id,
                    message_id=response_message_id,
                    trace_id=context.trace_id,
                    phase=EventPhase.FINAL_RESPONSE,
                    payload=phase_payload(
                        {"status": "failed"}, EventPhase.FINAL_RESPONSE
                    ),
                )
            )

    async def run(
        self,
        conversation_id: str,
        content: str,
        *,
        trace_id: str | None = None,
    ) -> list[AgentEvent]:
        return [
            event
            async for event in self.stream(
                conversation_id,
                content,
                trace_id=trace_id,
            )
        ]


class OpenAISupportAgent(ModelSupportAgent):
    """Backward-compatible wrapper for the previous OpenAI-specific mode."""

    def __init__(self, db: Session, customer: Customer, model: str):
        settings = get_settings()
        configuration = ModelProviderConfiguration(
            provider="openai",
            api_style="responses",
            base_url="https://api.openai.com/v1",
            model_name=model,
            api_key=settings.openai_api_key,
            timeout_seconds=settings.model_timeout_seconds,
            max_retries=settings.model_max_retries,
            requests_per_minute=settings.model_requests_per_minute,
            circuit_failure_threshold=settings.model_circuit_failure_threshold,
            circuit_cooldown_seconds=settings.model_circuit_cooldown_seconds,
            fallback_enabled=settings.model_fallback_enabled,
            max_turns=settings.model_max_turns,
        ).validated()
        super().__init__(db, customer, configuration)
