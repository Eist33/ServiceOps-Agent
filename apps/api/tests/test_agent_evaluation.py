import pytest

from serviceops.agent.evaluation import (
    DEFAULT_AGENT_CASES,
    AgentEvaluationCase,
    evaluate_agent_orchestration,
)
from serviceops.agent.intent import CustomerIntent
from serviceops.agent.providers import ModelConfigurationError


def test_release_gate_has_required_size_and_scenario_coverage():
    assert len(DEFAULT_AGENT_CASES) >= 60
    categories = {case.category for case in DEFAULT_AGENT_CASES}
    assert {
        "policy",
        "order",
        "shipping",
        "ticket",
        "ticket_status",
        "handoff",
        "refund",
        "multi_intent",
        "safety",
    }.issubset(categories)
    tags = set().union(*(case.safety_tags for case in DEFAULT_AGENT_CASES))
    assert {
        "multiple_orders",
        "new_conversation",
        "prompt_injection",
        "cross_customer",
        "refund_confirmation",
        "repeat_ticket",
        "repeat_refund",
    }.issubset(tags)


def test_agent_orchestration_release_gate_passes_all_cases():
    report = evaluate_agent_orchestration()

    assert report["total_cases"] == len(DEFAULT_AGENT_CASES)
    assert report["metrics"] == {
        "primary_intent_accuracy": 1.0,
        "tool_selection_accuracy": 1.0,
        "tool_parameter_validity": 1.0,
        "safety_failure_count": 0,
        "backend_tool_exposure_count": 0,
    }
    assert report["passed"] is True
    assert report["failures"] == []


def test_release_gate_fails_closed_when_corpus_is_too_small():
    report = evaluate_agent_orchestration(
        [
            AgentEvaluationCase(
                case_id="too-small",
                category="policy",
                utterance="退货政策",
                expected_intents=(CustomerIntent.POLICY,),
                expected_tools=("search_knowledge_base",),
            )
        ]
    )

    assert report["metrics"]["primary_intent_accuracy"] == 1.0
    assert report["passed"] is False


def test_real_model_gate_requires_a_server_side_key(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(ModelConfigurationError, match="API Key"):
        evaluate_agent_orchestration(runtime="model", max_cases=1)
