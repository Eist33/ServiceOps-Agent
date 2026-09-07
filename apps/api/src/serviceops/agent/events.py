from collections.abc import Iterable

from serviceops.shared.schemas import AgentEvent, EventPhase, EventType

SAFE_ACK_MESSAGE = "已收到，我会先核实相关信息。"
SAFE_THINKING_MESSAGE = "正在分析并准备查询。"
SAFE_FAILURE_MESSAGE = "当前请求未能完成，已安全停止处理；请稍后重试或转人工客服。"

SAFE_TOOL_LABELS = {
    "search_knowledge_base": "知识库查询",
    "list_recent_orders": "订单列表查询",
    "get_order": "订单查询",
    "get_shipping_status": "物流查询",
    "create_ticket": "工单创建",
    "get_current_ticket": "当前工单查询",
    "get_ticket": "工单查询",
    "request_human_handoff": "人工转接",
    "create_refund_request": "退款申请登记",
}


def safe_tool_label(tool_name: str) -> str:
    return SAFE_TOOL_LABELS.get(tool_name, "业务服务")


def phase_payload(payload: dict, phase: EventPhase) -> dict:
    """Copy a payload and add a stable, non-sensitive phase marker."""

    return {**payload, "phase": phase.value}


def progress_event(
    *,
    event_type: EventType,
    conversation_id: str,
    message_id: str,
    trace_id: str,
    phase: EventPhase,
    message: str,
) -> AgentEvent:
    return AgentEvent(
        type=event_type,
        conversation_id=conversation_id,
        message_id=message_id,
        trace_id=trace_id,
        phase=phase,
        payload=phase_payload({"message": message}, phase),
    )


class EventSequencer:
    """Assign deterministic IDs and monotonic sequence numbers within a trace."""

    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        self._next_sequence = 0

    def stamp(self, event: AgentEvent) -> AgentEvent:
        if event.event_id is not None:
            return event
        sequence = self._next_sequence
        self._next_sequence += 1
        return event.model_copy(
            update={
                "event_id": f"{self.trace_id}:{sequence}",
                "sequence": sequence,
            }
        )

    def stamp_all(self, events: Iterable[AgentEvent]) -> list[AgentEvent]:
        return [self.stamp(event) for event in events]
