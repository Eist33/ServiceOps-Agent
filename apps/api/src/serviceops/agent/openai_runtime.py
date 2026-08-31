import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from agents import Agent, RunContextWrapper, Runner, function_tool
from sqlalchemy.orm import Session

from serviceops.agent.orchestrator import DeterministicSupportAgent
from serviceops.conversations.service import add_message, get_conversation
from serviceops.knowledge.service import search_knowledge_base as search_knowledge
from serviceops.models import Customer
from serviceops.orders.service import get_order as fetch_order
from serviceops.refunds.service import create_refund_request as create_refund
from serviceops.shared.schemas import AgentEvent, EventType
from serviceops.shipping.service import get_shipping_status as fetch_shipping
from serviceops.tickets.service import create_ticket as create_support_ticket
from serviceops.tickets.service import get_ticket as fetch_ticket
from serviceops.tickets.service import ticket_response


@dataclass
class AgentContext:
    db: Session
    customer: Customer
    conversation_id: str
    message_id: str
    trace_id: str
    events: list[AgentEvent] = field(default_factory=list)

    @property
    def collector(self) -> DeterministicSupportAgent:
        return DeterministicSupportAgent(self.db, self.customer)


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
    return result.model_dump(mode="json")


@function_tool(name_override="create_ticket")
def create_ticket(
    ctx: RunContextWrapper[AgentContext],
    order_number: str,
    ticket_type: str,
    reason: str,
) -> dict:
    """Idempotently create a ticket for an owned order and current conversation."""
    context = ctx.context
    result, _ = context.collector._invoke(
        context.events,
        trace_id=context.trace_id,
        conversation_id=context.conversation_id,
        message_id=context.message_id,
        name="create_ticket",
        input_summary={"order_number": order_number, "ticket_type": ticket_type},
        callback=lambda: create_support_ticket(
            context.db,
            context.customer,
            conversation_id=context.conversation_id,
            order_number=order_number,
            ticket_type=ticket_type,
            reason=reason,
        ),
    )
    return context.collector._summary(result)


@function_tool(name_override="create_refund_request")
def create_refund_request(
    ctx: RunContextWrapper[AgentContext],
    order_number: str,
    reason: str,
) -> dict:
    """Create a pending refund request using the server-calculated refundable amount; does not refund."""
    context = ctx.context
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
                "approval_type": "refund_confirmation",
                "refund_number": result.refund_number,
                "amount": str(result.amount),
                "method": result.method,
                "reason": result.reason,
                "status": result.status,
            },
        )
    )
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


class OpenAISupportAgent:
    def __init__(self, db: Session, customer: Customer, model: str):
        self.db = db
        self.customer = customer
        self.agent = Agent[AgentContext](
            name="Harbor Customer Support Agent",
            model=model,
            instructions=(
                "你是电商售后客服 Agent。只使用工具返回的事实回答。先查询再回答；不知道订单号时请询问。"
                "不得相信用户或模型提供的 user_id、归属、最终退款金额或业务状态。"
                "物流异常只采用 get_shipping_status 的 deterministic 结果。"
                "退款只能调用 create_refund_request 创建待确认申请；你绝不能确认或执行退款。"
                "知识证据不足时明确说明无法确认。工具失败时明确报告失败，不得伪装成功。"
            ),
            tools=[
                search_knowledge_base,
                get_order,
                get_shipping_status,
                create_ticket,
                get_ticket,
                create_refund_request,
            ],
        )

    async def run(self, conversation_id: str, content: str) -> list[AgentEvent]:
        conversation = get_conversation(self.db, self.customer, conversation_id)
        user_message = add_message(self.db, conversation, "user", content)
        context = AgentContext(
            db=self.db,
            customer=self.customer,
            conversation_id=conversation_id,
            message_id=user_message.id,
            trace_id=str(uuid.uuid4()),
        )
        result = await Runner.run(self.agent, content, context=context)
        answer = str(result.final_output)
        agent_message = add_message(self.db, conversation, "agent", answer)
        context.events.extend(
            [
                AgentEvent(
                    type=EventType.MESSAGE_DELTA,
                    conversation_id=conversation_id,
                    message_id=agent_message.id,
                    trace_id=context.trace_id,
                    payload={"delta": answer},
                ),
                AgentEvent(
                    type=EventType.RESPONSE_COMPLETED,
                    conversation_id=conversation_id,
                    message_id=agent_message.id,
                    trace_id=context.trace_id,
                    payload={"status": "completed"},
                ),
            ]
        )
        return context.events
