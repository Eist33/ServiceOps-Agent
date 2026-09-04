from serviceops.agent.intent import (
    CustomerIntent,
    plan_customer_intents,
    refund_reason_from,
    refund_reason_reply_from,
)


def test_natural_language_intents_do_not_depend_on_scenario_names():
    assert plan_customer_intents("快递到哪儿了") == [CustomerIntent.SHIPPING]
    assert plan_customer_intents("看看我刚买的东西") == [
        CustomerIntent.ORDER_LOOKUP
    ]
    assert plan_customer_intents("我要找真人客服") == [
        CustomerIntent.HUMAN_HANDOFF
    ]


def test_shipping_ticket_is_planned_before_refund_in_multi_intent_message():
    assert plan_customer_intents("物流一直没动，帮我催一下，而且我不想要了") == [
        CustomerIntent.SHIPPING_TICKET,
        CustomerIntent.REFUND,
    ]


def test_ticket_status_is_not_misclassified_as_ticket_creation():
    assert plan_customer_intents("刚才的工单处理了吗？") == [
        CustomerIntent.TICKET_STATUS
    ]


def test_refund_reason_requires_customer_supplied_evidence():
    assert refund_reason_from("帮我申请退款") is None
    assert refund_reason_from("商品破损了，我要退款") == "商品破损了，我要退款"
    assert refund_reason_from("退款，因为买错颜色了") == "买错颜色了"


def test_refund_reason_follow_up_accepts_free_form_but_rejects_small_talk():
    assert refund_reason_reply_from("尺码不合适") == "尺码不合适"
    assert refund_reason_reply_from("你好") is None
    assert refund_reason_reply_from("好") is None
