from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "demo" / "app" / "demo-client.tsx"
E2E = ROOT / "demo" / "e2e" / "core-flows.spec.ts"
MIGRATION = (
    ROOT
    / "apps"
    / "api"
    / "alembic"
    / "versions"
    / "20260904_0007_conversation_pending_action.py"
)


def test_customer_page_has_one_natural_language_entry_not_scenario_navigation() -> None:
    text = CLIENT.read_text(encoding="utf-8")

    assert "SuggestionPrompts" in text
    assert "你可以这样问" in text
    assert "sendSuggestion" in text
    assert "runPrompt(conversationId, prompt)" in text
    assert "ScenarioNav" not in text
    assert "activeScenario" not in text
    assert "验收场景" not in text
    assert "点击运行真实业务闭环" not in text


def test_order_choice_resumes_server_recorded_pending_action() -> None:
    text = CLIENT.read_text(encoding="utf-8")

    assert "state?.conversation.pending_action" in text
    assert "请继续处理刚才的问题" in text
    assert "selectActiveOrder(conversationId, orderNumber)" in text


def test_e2e_uses_natural_language_instead_of_scenario_buttons() -> None:
    text = E2E.read_text(encoding="utf-8")

    assert "sendNaturalLanguage" in text
    assert "咨询退货政策" not in text
    assert "查询订单物流" not in text
    assert "物流异常建单/" not in text


def test_pending_action_has_forward_and_reverse_migration() -> None:
    text = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "20260904_0007"' in text
    assert 'down_revision = "20260904_0006"' in text
    assert '"pending_action"' in text
    assert '"pending_action_payload"' in text
    assert "def downgrade()" in text
