from enum import StrEnum


class CustomerIntent(StrEnum):
    POLICY = "POLICY"
    ORDER_LOOKUP = "ORDER_LOOKUP"
    SHIPPING = "SHIPPING"
    SHIPPING_TICKET = "SHIPPING_TICKET"
    TICKET_STATUS = "TICKET_STATUS"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"
    REFUND = "REFUND"


POLICY_TERMS = ("退货", "换货", "几天", "政策", "规则", "运费", "发票", "赠品")
SHIPPING_TERMS = (
    "物流",
    "快递",
    "包裹",
    "配送",
    "运单",
    "到哪",
    "没更新",
    "没动",
    "运输",
    "派送",
)
TICKET_CREATE_TERMS = ("催", "创建工单", "建单", "帮我处理", "物流异常")
TICKET_STATUS_TERMS = (
    "工单进度",
    "工单状态",
    "工单处理",
    "工单怎么样",
    "处理了吗",
    "处理结果",
)
REFUND_ACTION_TERMS = (
    "申请退款",
    "我要退款",
    "帮我退款",
    "执行退款",
    "退钱",
    "退掉",
    "不想要",
)
REFUND_INFORMATION_TERMS = (
    "退款多久到账",
    "退款要多久",
    "退款退到哪里",
    "退到哪里",
    "原路退回",
    "可以退款吗",
    "能退款吗",
    "退款规则",
    "退款政策",
)
HANDOFF_TERMS = ("人工", "真人客服", "找客服", "转客服")
ORDER_LOOKUP_TERMS = ("查订单", "查询订单", "订单状态", "我的订单", "买的东西", "购买记录", "最近订单", "最近买")


def plan_customer_intents(content: str) -> list[CustomerIntent]:
    """Plan customer intents in a stable, safety-first execution order."""
    normalized = content.strip().lower()
    intents: list[CustomerIntent] = []

    asks_refund_information = any(
        term in normalized for term in REFUND_INFORMATION_TERMS
    ) and not any(term in normalized for term in REFUND_ACTION_TERMS)
    if any(term in normalized for term in POLICY_TERMS) or asks_refund_information:
        intents.append(CustomerIntent.POLICY)

    has_shipping = any(term in normalized for term in SHIPPING_TERMS) and not (
        asks_refund_information
        and not any(term in normalized for term in ("查物流", "查快递", "物流到哪"))
    )
    wants_ticket = any(term in normalized for term in TICKET_CREATE_TERMS)
    wants_ticket_status = any(term in normalized for term in TICKET_STATUS_TERMS)
    wants_refund = any(term in normalized for term in REFUND_ACTION_TERMS) or (
        "退款" in normalized and not asks_refund_information
    )
    explicit_order_lookup = any(
        term in normalized for term in ORDER_LOOKUP_TERMS
    ) or (
        "订单" in normalized
        and any(term in normalized for term in ("查", "看看", "什么状态"))
    )

    if wants_ticket_status and not wants_ticket:
        intents.append(CustomerIntent.TICKET_STATUS)
    elif has_shipping or wants_ticket:
        intents.append(
            CustomerIntent.SHIPPING_TICKET if wants_ticket else CustomerIntent.SHIPPING
        )
    if (
        not (has_shipping or wants_ticket or wants_ticket_status)
        and explicit_order_lookup
        and not wants_refund
    ):
        intents.append(CustomerIntent.ORDER_LOOKUP)

    if any(term in normalized for term in HANDOFF_TERMS):
        intents.append(CustomerIntent.HUMAN_HANDOFF)

    if wants_refund:
        intents.append(CustomerIntent.REFUND)

    return list(dict.fromkeys(intents))


def refund_reason_from(content: str) -> str | None:
    normalized = content.strip()
    for marker in ("因为", "原因是", "退款原因"):
        if marker in normalized:
            reason = normalized.split(marker, 1)[1].strip(" ：:，,。")
            return reason[:500] if reason else None
    reason_terms = (
        "不想要",
        "质量",
        "破损",
        "损坏",
        "错发",
        "重复购买",
        "买错",
        "没有收到",
        "未收到",
        "延迟",
        "太慢",
    )
    if any(term in normalized for term in reason_terms):
        return normalized[:500]
    return None


def refund_reason_reply_from(content: str) -> str | None:
    """Accept a free-form reason only when the customer is answering that question."""
    explicit_reason = refund_reason_from(content)
    if explicit_reason:
        return explicit_reason
    normalized = content.strip(" \t\r\n，,。.!！?？")
    non_reason_replies = {
        "你好",
        "您好",
        "在吗",
        "谢谢",
        "好的",
        "好",
        "嗯",
        "哦",
    }
    if len(normalized) < 2 or normalized in non_reason_replies:
        return None
    return normalized[:500]
