from serviceops.agent.openai_runtime import (
    create_refund_request,
    create_ticket,
    get_order,
    get_shipping_status,
    get_ticket,
    search_knowledge_base,
)


def test_agents_sdk_tool_names_and_schemas_are_stable():
    tools = [
        search_knowledge_base,
        get_order,
        get_shipping_status,
        create_ticket,
        get_ticket,
        create_refund_request,
    ]
    assert [tool.name for tool in tools] == [
        "search_knowledge_base",
        "get_order",
        "get_shipping_status",
        "create_ticket",
        "get_ticket",
        "create_refund_request",
    ]
    assert set(get_order.params_json_schema["properties"]) == {"order_number"}
    assert "user_id" not in str([tool.params_json_schema for tool in tools])


def test_confirm_refund_is_not_an_agent_tool():
    tool_names = {
        search_knowledge_base.name,
        get_order.name,
        get_shipping_status.name,
        create_ticket.name,
        get_ticket.name,
        create_refund_request.name,
    }
    assert "confirm_refund" not in tool_names
