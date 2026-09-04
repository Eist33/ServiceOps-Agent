from serviceops.agent.openai_runtime import (
    CUSTOMER_AGENT_TOOLS,
    create_refund_request,
    create_ticket,
    get_current_ticket,
    get_order,
    get_shipping_status,
    get_ticket,
    list_recent_orders,
    request_human_handoff,
    search_knowledge_base,
)


def test_agents_sdk_tool_names_and_schemas_are_stable():
    tools = [
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
    assert [tool.name for tool in tools] == [
        "search_knowledge_base",
        "list_recent_orders",
        "get_order",
        "get_shipping_status",
        "create_ticket",
        "get_current_ticket",
        "get_ticket",
        "request_human_handoff",
        "create_refund_request",
    ]
    assert set(get_order.params_json_schema["properties"]) == {"order_number"}
    assert "user_id" not in str([tool.params_json_schema for tool in tools])


def test_confirm_refund_is_not_an_agent_tool():
    tool_names = {
        search_knowledge_base.name,
        list_recent_orders.name,
        get_order.name,
        get_shipping_status.name,
        create_ticket.name,
        get_current_ticket.name,
        get_ticket.name,
        request_human_handoff.name,
        create_refund_request.name,
    }
    assert "confirm_refund" not in tool_names


def test_customer_agent_allowlist_excludes_staff_and_operations_tools():
    tool_names = {tool.name for tool in CUSTOMER_AGENT_TOOLS}
    assert {
        "accept_agent_ticket",
        "add_agent_ticket_note",
        "resolve_agent_ticket",
        "publish_knowledge_article",
        "operations_dashboard",
        "confirm_refund",
    }.isdisjoint(tool_names)
