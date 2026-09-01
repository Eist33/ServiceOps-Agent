import hashlib
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from serviceops.models import (
    Conversation,
    Customer,
    IdempotencyRecord,
    KnowledgeArticle,
    Message,
    Operator,
    Order,
    RefundRequest,
    ShippingEvent,
    Ticket,
    TicketEvent,
    ToolInvocation,
)

DEMO_SESSION_TOKEN = "demo-linmu-session"
SECONDARY_SESSION_TOKEN = "demo-other-session"
OPS_SESSION_TOKEN = "demo-knowledge-ops-session"
AGENT_SESSION_TOKEN = "demo-support-agent-session"


POLICIES = [
    (
        "第 2.1 条",
        "退货 无理由 几天 7天",
        "大多数商品支持签收后 7 天内无理由退货。商品、包装、吊牌和赠品需保持完整。",
    ),
    ("第 2.2 条", "定制 生鲜 贴身用品", "定制商品、生鲜商品和已拆封的贴身用品不适用无理由退货。"),
    (
        "第 3.1 条",
        "运输中 退款 拦截",
        "运输中的订单可申请拦截后退款，实际结果以承运商拦截状态为准。",
    ),
    (
        "第 3.2 条",
        "退款 原路退回 到账",
        "退款成功后按原支付路径退回，到账时间通常为 1 至 5 个工作日。",
    ),
    (
        "第 4.1 条",
        "换货 质量问题",
        "商品存在质量问题时，可在签收后 15 天内申请换货并上传问题凭证。",
    ),
    ("第 4.2 条", "运费 质量问题", "经核实属于商品质量问题的退换货，往返运费由平台承担。"),
    ("第 5.1 条", "物流 异常 停滞", "物流超过 36 小时没有新节点时，可创建物流异常工单跟进。"),
    ("第 5.2 条", "丢件 破损", "发生疑似丢件或运输破损时，客服将联系承运商核实并给出处理方案。"),
    ("第 6.1 条", "发票 退货", "已开具发票的订单退货时，应按页面提示完成发票冲红或退回。"),
    ("第 6.2 条", "赠品 退货", "参加赠品活动的订单办理整单退货时，需要一并退回赠品。"),
    ("第 7.1 条", "取消订单 未发货", "订单未发货时可直接申请取消，审核通过后按原路退款。"),
    (
        "第 7.2 条",
        "售后 工单 人工",
        "知识库无法确认或工具发生异常时，可以创建人工售后工单继续处理。",
    ),
]


def _add_seed_knowledge(db: Session) -> None:
    for section, keywords, content in POLICIES:
        db.add(
            KnowledgeArticle(
                title="平台退换货规则",
                version="2026-07",
                section=section,
                content=content,
                keywords=keywords.split(),
                embedding=None,
                source_uri=f"kb://after-sales/2026-07/{section.replace(' ', '-')}",
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                active=True,
                valid_from=datetime(2026, 7, 1, tzinfo=UTC),
            )
        )


def seed_database(db: Session) -> None:
    operator = db.scalar(select(Operator).where(Operator.session_token == OPS_SESSION_TOKEN))
    if not operator:
        db.add(
            Operator(
                name="许知夏",
                role="KNOWLEDGE_MANAGER",
                session_token=OPS_SESSION_TOKEN,
            )
        )
    support_agent = db.scalar(
        select(Operator).where(Operator.session_token == AGENT_SESSION_TOKEN)
    )
    if not support_agent:
        db.add(
            Operator(
                name="沈清禾",
                role="SUPPORT_AGENT",
                session_token=AGENT_SESSION_TOKEN,
            )
        )
    existing = db.scalar(select(Customer).where(Customer.session_token == DEMO_SESSION_TOKEN))
    if existing:
        db.commit()
        return
    customer = Customer(name="林沐", session_token=DEMO_SESSION_TOKEN)
    other = Customer(name="周远", session_token=SECONDARY_SESSION_TOKEN)
    db.add_all([customer, other])
    db.flush()
    order = Order(
        order_number="ORD-20260828-1042",
        customer_id=customer.id,
        product_name="城市通勤双肩包",
        paid_amount=Decimal("329.00"),
        refundable_amount=Decimal("329.00"),
        status="IN_TRANSIT",
        ordered_at=datetime(2026, 8, 28, 10, 15, tzinfo=UTC),
    )
    other_order = Order(
        order_number="ORD-20260827-9001",
        customer_id=other.id,
        product_name="旅行收纳套装",
        paid_amount=Decimal("119.00"),
        refundable_amount=Decimal("119.00"),
        status="DELIVERED",
        ordered_at=datetime(2026, 8, 27, 9, 30, tzinfo=UTC),
    )
    db.add_all([order, other_order])
    db.flush()
    db.add_all(
        [
            ShippingEvent(
                order_id=order.id,
                location="华东转运中心",
                description="到达华东转运中心",
                occurred_at=datetime(2026, 8, 29, 18, 20, tzinfo=UTC),
            ),
            ShippingEvent(
                order_id=order.id,
                location="杭州集散中心",
                description="离开杭州集散中心",
                occurred_at=datetime(2026, 8, 29, 9, 42, tzinfo=UTC),
            ),
            ShippingEvent(
                order_id=order.id,
                location="杭州余杭营业点",
                description="快件已揽收",
                occurred_at=datetime(2026, 8, 28, 21, 6, tzinfo=UTC),
            ),
        ]
    )
    _add_seed_knowledge(db)
    db.commit()


def reset_demo_state(db: Session) -> None:
    """Reset mutable demo state and restore fixed knowledge fixtures."""
    for model in [
        IdempotencyRecord,
        ToolInvocation,
        RefundRequest,
        TicketEvent,
        Ticket,
        Message,
        Conversation,
    ]:
        db.execute(delete(model))
    db.execute(delete(KnowledgeArticle))
    _add_seed_knowledge(db)
    order = db.scalar(select(Order).where(Order.order_number == "ORD-20260828-1042"))
    if order:
        order.refundable_amount = order.paid_amount
        order.status = "IN_TRANSIT"
    db.commit()
