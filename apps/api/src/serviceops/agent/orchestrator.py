import re
import time
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from serviceops.agent.intent import (
    CustomerIntent,
    plan_customer_intents,
    refund_reason_from,
    refund_reason_reply_from,
)
from serviceops.audit.service import record_invocation
from serviceops.conversations.service import (
    add_message,
    clear_pending_action,
    get_conversation,
    order_snapshot,
    request_order_selection,
    set_active_order,
    set_pending_action,
)
from serviceops.knowledge.service import search_knowledge_base
from serviceops.models import Customer, Message, Order
from serviceops.orders.service import get_order, list_recent_orders
from serviceops.refunds.service import create_refund_request
from serviceops.shared.errors import DomainError
from serviceops.shared.schemas import AgentEvent, EventType
from serviceops.shipping.service import get_shipping_status
from serviceops.tickets.service import (
    create_ticket,
    get_current_ticket,
    request_human_handoff,
)

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
        _user_message: Message | None = None,
    ) -> list[AgentEvent]:
        conversation = get_conversation(self.db, self.customer, conversation_id)
        if _user_message is not None and _user_message.conversation_id != conversation_id:
            raise ValueError("预先持久化的消息不属于当前会话")
        user_message = _user_message or add_message(self.db, conversation, "user", content)
        trace_id = trace_id or str(uuid.uuid4())
        events: list[AgentEvent] = []
        normalized = content.lower()
        planned_intents = plan_customer_intents(content)
        try:
            if conversation.pending_action and normalized.strip() in {
                "算了",
                "不用了",
                "暂时不用",
                "取消刚才的操作",
            }:
                clear_pending_action(
                    self.db,
                    self.customer,
                    conversation_id,
                    clear_order_selection=True,
                )
                answer = "好的，已取消刚才尚未完成的操作，没有产生新的业务写入。"
            elif conversation.pending_action and (
                "继续处理刚才的问题" in normalized
            ):
                answer = self._resume_pending_action(
                    events,
                    trace_id,
                    conversation_id,
                    user_message.id,
                    content,
                    conversation.pending_action,
                    conversation.pending_action_payload or {},
                )
            elif (
                conversation.pending_action == "REFUND_REASON"
                and not planned_intents
            ):
                reason = refund_reason_reply_from(content)
                if reason:
                    answer = self._refund_flow(
                        events,
                        trace_id,
                        conversation_id,
                        user_message.id,
                        content,
                        supplied_reason=reason,
                    )
                else:
                    answer = (
                        "退款申请仍在等待原因。请说明商品或履约方面的具体问题；"
                        "如果不再申请，可以回复“算了”。"
                    )
            else:
                intents = planned_intents
                if not intents:
                    answer = (
                        "我还不能确定你希望处理什么。可以直接描述商品、订单、快递、"
                        "退款或人工客服方面的问题。"
                    )
                else:
                    preserve_refund_reason = (
                        conversation.pending_action == "REFUND_REASON"
                        and CustomerIntent.REFUND not in intents
                    )
                    answers: list[str] = []
                    for intent in intents:
                        answers.append(
                            self._dispatch_intent(
                                intent,
                                events,
                                trace_id,
                                conversation_id,
                                user_message.id,
                                content,
                            )
                        )
                        current = get_conversation(
                            self.db, self.customer, conversation_id
                        )
                        if current.order_selection_pending or (
                            current.pending_action == "REFUND_REASON"
                            and not preserve_refund_reason
                        ):
                            break
                    if preserve_refund_reason:
                        current = get_conversation(
                            self.db, self.customer, conversation_id
                        )
                        if current.pending_action is None:
                            set_pending_action(
                                self.db,
                                self.customer,
                                conversation_id,
                                "REFUND_REASON",
                            )
                        answers.append(
                            "另外，刚才的退款申请仍在等待你补充退款原因。"
                        )
                    answer = "\n\n".join(item for item in answers if item)
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

    def _dispatch_intent(
        self,
        intent: CustomerIntent,
        events: list[AgentEvent],
        trace_id: str,
        conversation_id: str,
        message_id: str,
        content: str,
    ) -> str:
        if intent == CustomerIntent.POLICY:
            return self._policy_flow(
                events, trace_id, conversation_id, message_id, content
            )
        if intent == CustomerIntent.ORDER_LOOKUP:
            return self._order_flow(
                events, trace_id, conversation_id, message_id, content
            )
        if intent == CustomerIntent.SHIPPING:
            return self._shipping_flow(
                events, trace_id, conversation_id, message_id, content
            )
        if intent == CustomerIntent.SHIPPING_TICKET:
            return self._shipping_flow(
                events,
                trace_id,
                conversation_id,
                message_id,
                content,
                force_ticket=True,
            )
        if intent == CustomerIntent.TICKET_STATUS:
            return self._ticket_status_flow(
                events, trace_id, conversation_id, message_id
            )
        if intent == CustomerIntent.HUMAN_HANDOFF:
            return self._handoff_flow(events, trace_id, conversation_id, message_id)
        return self._refund_flow(
            events,
            trace_id,
            conversation_id,
            message_id,
            content,
            supplied_reason=refund_reason_from(content),
        )

    def _resume_pending_action(
        self,
        events: list[AgentEvent],
        trace_id: str,
        conversation_id: str,
        message_id: str,
        content: str,
        action: str,
        payload: dict,
    ) -> str:
        if action == "SHIPPING_QUERY":
            return self._shipping_flow(
                events, trace_id, conversation_id, message_id, content
            )
        if action == "SHIPPING_TICKET":
            return self._shipping_flow(
                events,
                trace_id,
                conversation_id,
                message_id,
                content,
                force_ticket=True,
            )
        if action == "ORDER_LOOKUP":
            return self._order_flow(
                events, trace_id, conversation_id, message_id, content
            )
        if action in {"REFUND_REQUEST", "REFUND_REASON"}:
            reason = payload.get("reason")
            if action == "REFUND_REASON" and "继续处理刚才的问题" not in content:
                reason = refund_reason_reply_from(content)
            return self._refund_flow(
                events,
                trace_id,
                conversation_id,
                message_id,
                content,
                supplied_reason=reason,
            )
        clear_pending_action(self.db, self.customer, conversation_id)
        return "已选择订单。请继续说明需要处理的具体问题。"

    def _resolve_order(
        self,
        events: list[AgentEvent],
        *,
        trace_id: str,
        conversation_id: str,
        message_id: str,
        content: str,
        pending_action: str,
        pending_payload: dict | None = None,
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
            clear_pending_action(self.db, self.customer, conversation_id)
            return None, "当前账号没有可用订单，我暂时无法继续执行订单相关操作。"
        if len(orders) == 1:
            order = orders[0]
            set_active_order(self.db, self.customer, conversation_id, order.order_number)
            self._emit_active_order(
                events, trace_id, conversation_id, message_id, order
            )
            return order, None

        set_pending_action(
            self.db,
            self.customer,
            conversation_id,
            pending_action,
            pending_payload,
        )
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

    def _order_flow(self, events, trace_id, conversation_id, message_id, content) -> str:
        order, blocker = self._resolve_order(
            events,
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            content=content,
            pending_action="ORDER_LOOKUP",
        )
        if order is None:
            return blocker or "请先选择需要查询的订单。"
        clear_pending_action(self.db, self.customer, conversation_id)
        return (
            f"当前处理的是订单 {order.order_number}，商品为{order.product_name}，"
            f"订单状态为 {order.status}，实付金额 ¥{order.paid_amount}。"
        )

    def _shipping_flow(
        self,
        events,
        trace_id,
        conversation_id,
        message_id,
        content,
        *,
        force_ticket: bool = False,
    ) -> str:
        pending_action = "SHIPPING_TICKET" if force_ticket else "SHIPPING_QUERY"
        order, blocker = self._resolve_order(
            events,
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            content=content,
            pending_action=pending_action,
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
        wants_ticket = force_ticket or any(
            term in content for term in ["催", "工单", "帮我处理", "创建"]
        )
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
            clear_pending_action(self.db, self.customer, conversation_id)
            return f"已创建物流异常工单 {ticket.ticket_number}。物流已停滞 {shipping.stale_hours} 小时，客服会继续跟进。"
        latest = shipping.nodes[0] if shipping.nodes else None
        location = latest["location"] if latest else "暂无物流节点"
        clear_pending_action(self.db, self.customer, conversation_id)
        if shipping.abnormal:
            return f"订单 {order.order_number} 当前停留在{location}，已 {shipping.stale_hours} 小时没有更新，系统规则判定为运输停滞。需要的话我可以创建物流异常工单。"
        return f"订单 {order.order_number} 当前物流正常，最新节点是{location}。"

    def _ticket_status_flow(
        self, events, trace_id, conversation_id, message_id
    ) -> str:
        ticket, _ = self._invoke(
            events,
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            name="get_current_ticket",
            input_summary={},
            callback=lambda: get_current_ticket(
                self.db, self.customer, conversation_id
            ),
        )
        if ticket is None:
            return "当前会话还没有关联工单。请先描述需要处理的问题。"
        assignee = ticket.assignee_name or "Agent 自动处理"
        return (
            f"工单 {ticket.ticket_number} 当前状态为 {ticket.status}，"
            f"处理方是{assignee}。"
        )

    def _handoff_flow(self, events, trace_id, conversation_id, message_id) -> str:
        ticket, _ = self._invoke(
            events,
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            name="get_current_ticket",
            input_summary={},
            callback=lambda: get_current_ticket(
                self.db, self.customer, conversation_id
            ),
        )
        if ticket is None:
            return "当前会话还没有可转人工的工单。请先说明具体问题，我会先查询并处理。"
        handed_off, _ = self._invoke(
            events,
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            name="request_human_handoff",
            input_summary={"ticket_id": ticket.id},
            callback=lambda: request_human_handoff(
                self.db, self.customer, ticket.id
            ),
        )
        events.append(
            AgentEvent(
                type=EventType.BUSINESS_STATE_CHANGED,
                conversation_id=conversation_id,
                message_id=message_id,
                trace_id=trace_id,
                ticket_id=handed_off.id,
                payload={
                    "object": "ticket",
                    "status": handed_off.status,
                    "handoff_status": handed_off.handoff_status,
                    "assignee_name": handed_off.assignee_name,
                },
            )
        )
        return (
            f"工单 {handed_off.ticket_number} 已转交{handed_off.assignee_name}，"
            "人工客服会在 SLA 时限内继续处理。"
        )

    def _refund_flow(
        self,
        events,
        trace_id,
        conversation_id,
        message_id,
        content,
        *,
        supplied_reason: str | None = None,
    ) -> str:
        order, blocker = self._resolve_order(
            events,
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            content=content,
            pending_action="REFUND_REQUEST",
            pending_payload={"reason": supplied_reason},
        )
        if order is None:
            return blocker or "请先选择需要处理的订单。"
        order_number = order.order_number
        reason = supplied_reason or refund_reason_from(content)
        if not reason:
            set_pending_action(
                self.db,
                self.customer,
                conversation_id,
                "REFUND_REASON",
            )
            return "请告诉我申请退款的原因。原因确认后，我只会创建待你确认的退款申请。"
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
            input_summary={"order_number": order_number, "reason": reason},
            callback=lambda: create_refund_request(
                self.db,
                self.customer,
                conversation_id=conversation_id,
                order_number=order_number,
                reason=reason,
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
                    "approval_type": "refund_human_approval",
                    "refund_number": refund.refund_number,
                    "amount": str(refund.amount),
                    "method": refund.method,
                    "reason": refund.reason,
                    "status": refund.status,
                },
            )
        )
        clear_pending_action(self.db, self.customer, conversation_id)
        return f"已为订单 {order.order_number} 创建待人工审批退款申请 {refund.refund_number}，金额 ¥{refund.amount}。客服人工审批通过后，还需要你明确确认，后端才会模拟执行退款。"
