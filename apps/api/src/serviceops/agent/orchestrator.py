import re
import time
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from serviceops.audit.service import record_invocation
from serviceops.conversations.service import (
    add_message,
    get_conversation,
    order_snapshot,
    request_order_selection,
    set_active_order,
)
from serviceops.knowledge.service import search_knowledge_base
from serviceops.models import Customer, Order
from serviceops.orders.service import get_order, list_recent_orders
from serviceops.refunds.service import create_refund_request
from serviceops.shared.errors import DomainError
from serviceops.shared.schemas import AgentEvent, EventType
from serviceops.shipping.service import get_shipping_status
from serviceops.tickets.service import create_ticket

ORDER_PATTERN = re.compile(r"ORD-[A-Z0-9-]+", re.IGNORECASE)


class DeterministicSupportAgent:
    """A predictable offline runner used for demos and automated tests.

    It chooses the same application tools exposed to the OpenAI Agents SDK runtime;
    deterministic business rules remain in the domain services in both modes.
    """

    def __init__(self, db: Session, customer: Customer):
        self.db = db
        self.customer = customer

    def run(
        self,
        conversation_id: str,
        content: str,
        *,
        trace_id: str | None = None,
    ) -> list[AgentEvent]:
        conversation = get_conversation(self.db, self.customer, conversation_id)
        user_message = add_message(self.db, conversation, "user", content)
        trace_id = trace_id or str(uuid.uuid4())
        events: list[AgentEvent] = []
        normalized = content.lower()
        try:
            if any(term in normalized for term in ["退款", "退掉", "不想要", "退钱"]):
                answer = self._refund_flow(
                    events, trace_id, conversation_id, user_message.id, content
                )
            elif any(
                term in normalized
                for term in ["物流", "快递", "到哪", "没更新", "催", "工单"]
            ):
                answer = self._shipping_flow(
                    events, trace_id, conversation_id, user_message.id, content
                )
            elif any(term in normalized for term in ["退货", "几天", "政策", "规则", "换货"]):
                answer = self._policy_flow(
                    events, trace_id, conversation_id, user_message.id, content
                )
            else:
                answer = "我可以协助查询退换货政策、订单物流、创建异常工单或发起待确认退款。请提供订单号或说明你遇到的问题。"
            agent_message = add_message(self.db, conversation, "agent", answer)
            events.append(
                AgentEvent(
                    type=EventType.MESSAGE_DELTA,
                    conversation_id=conversation_id,
                    message_id=agent_message.id,
                    trace_id=trace_id,
                    payload={"delta": answer},
                )
            )
            events.append(
                AgentEvent(
                    type=EventType.RESPONSE_COMPLETED,
                    conversation_id=conversation_id,
                    message_id=agent_message.id,
                    trace_id=trace_id,
                    payload={"status": "completed"},
                )
            )
        except DomainError as exc:
            events.append(
                AgentEvent(
                    type=EventType.ERROR,
                    conversation_id=conversation_id,
                    message_id=user_message.id,
                    trace_id=trace_id,
                    payload={
                        "code": exc.code,
                        "message": exc.message,
                        "recoverable": exc.status_code < 500,
                    },
                )
            )
            events.append(
                AgentEvent(
                    type=EventType.RESPONSE_COMPLETED,
                    conversation_id=conversation_id,
                    message_id=user_message.id,
                    trace_id=trace_id,
                    payload={"status": "failed"},
                )
            )
        return events

    def _resolve_order(
        self,
        events: list[AgentEvent],
        *,
        trace_id: str,
        conversation_id: str,
        message_id: str,
        content: str,
    ) -> tuple[Order | None, str | None]:
        conversation = get_conversation(self.db, self.customer, conversation_id)
        match = ORDER_PATTERN.search(content)
        if match:
            order_number = match.group(0).upper()
            order, _ = self._invoke(
                events,
                trace_id=trace_id,
                conversation_id=conversation_id,
                message_id=message_id,
                name="get_order",
                input_summary={"order_number": order_number},
                callback=lambda: get_order(self.db, self.customer, order_number),
            )
            set_active_order(self.db, self.customer, conversation_id, order.order_number)
            self._emit_active_order(
                events, trace_id, conversation_id, message_id, order
            )
            return order, None

        if conversation.active_order_id:
            active_order = self.db.get(Order, conversation.active_order_id)
            if active_order and active_order.customer_id == self.customer.id:
                order, _ = self._invoke(
                    events,
                    trace_id=trace_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    name="get_order",
                    input_summary={"order_number": active_order.order_number},
                    callback=lambda: get_order(
                        self.db, self.customer, active_order.order_number
                    ),
                )
                return order, None

        orders, _ = self._invoke(
            events,
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            name="list_recent_orders",
            input_summary={"limit": 3},
            callback=lambda: list_recent_orders(self.db, self.customer),
        )
        if not orders:
            return None, "当前账号没有可用订单，我暂时无法继续执行订单相关操作。"
        if len(orders) == 1:
            order = orders[0]
            set_active_order(self.db, self.customer, conversation_id, order.order_number)
            self._emit_active_order(
                events, trace_id, conversation_id, message_id, order
            )
            return order, None

        request_order_selection(self.db, self.customer, conversation_id)
        events.append(
            AgentEvent(
                type=EventType.ORDER_SELECTION_REQUIRED,
                conversation_id=conversation_id,
                message_id=message_id,
                trace_id=trace_id,
                payload={
                    "reason": "multiple_recent_orders",
                    "orders": [order_snapshot(item) for item in orders],
                },
            )
        )
        return None, "我找到了你最近的 3 笔订单，请先选择这次需要处理的订单。"

    @staticmethod
    def _emit_active_order(
        events: list[AgentEvent],
        trace_id: str,
        conversation_id: str,
        message_id: str,
        order: Order,
    ) -> None:
        events.append(
            AgentEvent(
                type=EventType.ACTIVE_ORDER_CHANGED,
                conversation_id=conversation_id,
                message_id=message_id,
                trace_id=trace_id,
                order_id=order.id,
                payload={"order": order_snapshot(order)},
            )
        )

    def _invoke(
        self,
        events: list[AgentEvent],
        *,
        trace_id: str,
        conversation_id: str,
        message_id: str,
        name: str,
        input_summary: dict,
        callback: Callable[[], Any],
    ) -> tuple[Any, str]:
        tool_call_id = str(uuid.uuid4())
        events.append(
            AgentEvent(
                type=EventType.TOOL_STARTED,
                conversation_id=conversation_id,
                message_id=message_id,
                tool_call_id=tool_call_id,
                trace_id=trace_id,
                payload={"tool_name": name},
            )
        )
        started = time.perf_counter()
        try:
            result = callback()
            duration_ms = max(1, int((time.perf_counter() - started) * 1000))
            output = self._summary(result)
            record_invocation(
                self.db,
                trace_id=trace_id,
                conversation_id=conversation_id,
                message_id=message_id,
                tool_call_id=tool_call_id,
                tool_name=name,
                input_summary=input_summary,
                output_summary=output,
                duration_ms=duration_ms,
                order_id=output.get("order_id") or getattr(result, "id", None)
                if isinstance(result, Order)
                else output.get("order_id"),
                ticket_id=output.get("ticket_id"),
                refund_request_id=output.get("refund_request_id"),
            )
            events.append(
                AgentEvent(
                    type=EventType.TOOL_COMPLETED,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    tool_call_id=tool_call_id,
                    trace_id=trace_id,
                    order_id=output.get("order_id"),
                    ticket_id=output.get("ticket_id"),
                    refund_request_id=output.get("refund_request_id"),
                    payload={
                        "tool_name": name,
                        "status": "succeeded",
                        "duration_ms": duration_ms,
                        "result": output,
                    },
                )
            )
            return result, tool_call_id
        except DomainError as exc:
            duration_ms = max(1, int((time.perf_counter() - started) * 1000))
            record_invocation(
                self.db,
                trace_id=trace_id,
                conversation_id=conversation_id,
                message_id=message_id,
                tool_call_id=tool_call_id,
                tool_name=name,
                input_summary=input_summary,
                output_summary={"code": exc.code},
                status="FAILED",
                duration_ms=duration_ms,
                error_type=exc.code,
            )
            raise

    @staticmethod
    def _summary(result: Any) -> dict:
        if hasattr(result, "model_dump"):
            data = result.model_dump(mode="json")
            if "id" in data and "refund_number" in data:
                data["refund_request_id"] = data.pop("id")
            return data
        if isinstance(result, Order):
            return {
                "order_id": result.id,
                "order_number": result.order_number,
                "product_name": result.product_name,
                "status": result.status,
                "paid_amount": str(result.paid_amount),
                "refundable_amount": str(result.refundable_amount),
            }
        if isinstance(result, list) and all(isinstance(item, Order) for item in result):
            return {"orders": [order_snapshot(item) for item in result]}
        if hasattr(result, "ticket_number"):
            return {
                "ticket_id": result.id,
                "ticket_number": result.ticket_number,
                "status": result.status,
                "ticket_type": result.ticket_type,
            }
        if hasattr(result, "refund_number"):
            return {
                "refund_request_id": result.id,
                "refund_number": result.refund_number,
                "ticket_id": result.ticket_id,
                "order_id": result.order_id,
                "status": result.status,
                "amount": str(result.amount),
                "method": result.method,
                "reason": result.reason,
            }
        return result if isinstance(result, dict) else {"result": str(result)}

    def _policy_flow(self, events, trace_id, conversation_id, message_id, content) -> str:
        result, _ = self._invoke(
            events,
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            name="search_knowledge_base",
            input_summary={"query": content},
            callback=lambda: search_knowledge_base(self.db, content),
        )
        if not result["confident"]:
            return "知识库中没有足够依据确认这个问题。我不会猜测答案，建议创建人工跟进工单。"
        source = result["results"][0]
        return f"{source['content']}（来源：{source['title']} {source['version']}，{source['section']}）"

    def _shipping_flow(self, events, trace_id, conversation_id, message_id, content) -> str:
        order, blocker = self._resolve_order(
            events,
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            content=content,
        )
        if order is None:
            return blocker or "请先选择需要处理的订单。"
        order_number = order.order_number
        shipping, _ = self._invoke(
            events,
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            name="get_shipping_status",
            input_summary={"order_number": order_number},
            callback=lambda: get_shipping_status(self.db, self.customer, order_number),
        )
        wants_ticket = any(term in content for term in ["催", "工单", "帮我处理", "创建"])
        if wants_ticket and shipping.abnormal:
            ticket, _ = self._invoke(
                events,
                trace_id=trace_id,
                conversation_id=conversation_id,
                message_id=message_id,
                name="create_ticket",
                input_summary={"order_number": order_number, "ticket_type": "SHIPPING"},
                callback=lambda: create_ticket(
                    self.db,
                    self.customer,
                    conversation_id=conversation_id,
                    order_number=order_number,
                    ticket_type="SHIPPING",
                    reason="物流长时间未更新",
                    evidence={
                        "abnormal_reason": shipping.abnormal_reason,
                        "stale_hours": shipping.stale_hours,
                    },
                ),
            )
            events.append(
                AgentEvent(
                    type=EventType.BUSINESS_STATE_CHANGED,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    trace_id=trace_id,
                    order_id=order.id,
                    ticket_id=ticket.id,
                    payload={
                        "object": "ticket",
                        "status": ticket.status,
                        "ticket_number": ticket.ticket_number,
                    },
                )
            )
            return f"已创建物流异常工单 {ticket.ticket_number}。物流已停滞 {shipping.stale_hours} 小时，客服会继续跟进。"
        latest = shipping.nodes[0] if shipping.nodes else None
        location = latest["location"] if latest else "暂无物流节点"
        if shipping.abnormal:
            return f"订单 {order.order_number} 当前停留在{location}，已 {shipping.stale_hours} 小时没有更新，系统规则判定为运输停滞。需要的话我可以创建物流异常工单。"
        return f"订单 {order.order_number} 当前物流正常，最新节点是{location}。"

    def _refund_flow(self, events, trace_id, conversation_id, message_id, content) -> str:
        order, blocker = self._resolve_order(
            events,
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            content=content,
        )
        if order is None:
            return blocker or "请先选择需要处理的订单。"
        order_number = order.order_number
        self._invoke(
            events,
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            name="search_knowledge_base",
            input_summary={"query": "运输中退款规则"},
            callback=lambda: search_knowledge_base(self.db, "运输中退款规则"),
        )
        refund, _ = self._invoke(
            events,
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            name="create_refund_request",
            input_summary={"order_number": order_number, "reason": "用户不再需要商品"},
            callback=lambda: create_refund_request(
                self.db,
                self.customer,
                conversation_id=conversation_id,
                order_number=order_number,
                reason="不想要了",
                requested_amount=Decimal(order.refundable_amount),
            ),
        )
        events.append(
            AgentEvent(
                type=EventType.APPROVAL_REQUIRED,
                conversation_id=conversation_id,
                message_id=message_id,
                trace_id=trace_id,
                order_id=order.id,
                ticket_id=refund.ticket_id,
                refund_request_id=refund.id,
                payload={
                    "approval_type": "refund_confirmation",
                    "refund_number": refund.refund_number,
                    "amount": str(refund.amount),
                    "method": refund.method,
                    "reason": refund.reason,
                    "status": refund.status,
                },
            )
        )
        return f"已为订单 {order.order_number} 创建待确认退款申请 {refund.refund_number}，金额 ¥{refund.amount}。只有你明确确认后，后端才会模拟执行退款。"
