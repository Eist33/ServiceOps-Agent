from dataclasses import replace
from pathlib import Path

import pytest

from serviceops.agent.context import (
    ContextAssembler,
    ContextAssemblyError,
    ContextBudget,
    ContextMessage,
    TrustedBusinessState,
)
from serviceops.agent.release import (
    CUSTOMER_TOOL_NAMES,
    DEFAULT_AGENT_RELEASE,
    governance_snapshot,
)
from serviceops.models import ModelInvocation
from serviceops.seed import AGENT_SESSION_TOKEN, OPS_SESSION_TOKEN


def _message(message_id: str, content: str, *, role: str = "user") -> ContextMessage:
    return ContextMessage(
        message_id=message_id,
        role=role,
        content=content,
        source_id=f"fixture:{message_id}",
    )


def test_release_binding_is_immutable_compatible_and_idempotent() -> None:
    first = DEFAULT_AGENT_RELEASE.bind(
        runtime_mode="model",
        provider="deepseek",
        model_name="deepseek-v4-flash",
        tool_names=CUSTOMER_TOOL_NAMES,
    )
    second = DEFAULT_AGENT_RELEASE.bind(
        runtime_mode="model",
        provider="deepseek",
        model_name="deepseek-v4-flash",
        tool_names=CUSTOMER_TOOL_NAMES,
    )

    assert first == second
    assert first.agent_release_id == "agent-support-v1"
    assert first.knowledge_release_version == "lexical_v1"
    assert "system_prompt" not in governance_snapshot()["agent_release"]
    assert DEFAULT_AGENT_RELEASE.rollout_mode == "LOCAL_ONLY"
    assert DEFAULT_AGENT_RELEASE.canary_percentage == 0


def test_unapproved_rollout_fails_closed() -> None:
    canary = replace(
        DEFAULT_AGENT_RELEASE,
        rollout_mode="CANARY",
        canary_percentage=10,
    )
    with pytest.raises(ValueError, match="尚未批准") as error:
        canary.bind(
            runtime_mode="model",
            provider="deepseek",
            model_name="deepseek-v4-flash",
            tool_names=CUSTOMER_TOOL_NAMES,
        )
    assert error.value.code == "AGENT_ROLLOUT_NOT_APPROVED"


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"runtime_mode": "shadow"}, "AGENT_RUNTIME_INCOMPATIBLE"),
        ({"tool_names": CUSTOMER_TOOL_NAMES[:-1]}, "AGENT_TOOL_SCHEMA_MISMATCH"),
        ({"knowledge_release_version": "hybrid_rrf_v1"}, "KNOWLEDGE_RELEASE_MISMATCH"),
    ],
)
def test_release_mismatch_fails_closed(kwargs: dict, code: str) -> None:
    base = {
        "runtime_mode": "model",
        "provider": "deepseek",
        "model_name": "deepseek-v4-flash",
        "tool_names": CUSTOMER_TOOL_NAMES,
    }
    base.update(kwargs)
    with pytest.raises(ValueError) as error:
        DEFAULT_AGENT_RELEASE.bind(**base)
    assert error.value.code == code


def test_context_assembly_deduplicates_current_message_and_records_sources() -> None:
    current = _message("current", "查询订单状态")
    assembly = ContextAssembler(
        ContextBudget(total_tokens=256, trusted_tokens=40, history_tokens=100, current_tokens=40)
    ).assemble(
        trusted_state=TrustedBusinessState(
            source_id="conversation:fixture",
            active_order_number="ORD-1",
        ),
        recent_messages=[
            _message("old", "之前的物流消息", role="user"),
            _message("current", "查询订单状态"),
        ],
        current_message=current,
    )

    assert assembly.prompt.count("查询订单状态") == 1
    assert assembly.omitted_history_count == 1
    assert assembly.sources[-1].source_id == "fixture:current"
    assert assembly.sources[-1].trust == "untrusted"
    assert assembly.estimated_tokens <= 256


def test_context_history_truncates_oldest_messages_with_safe_marker() -> None:
    assembly = ContextAssembler(
        ContextBudget(total_tokens=120, trusted_tokens=30, history_tokens=12, current_tokens=20)
    ).assemble(
        trusted_state=TrustedBusinessState(source_id="conversation:fixture"),
        recent_messages=[
            _message("first", "第一条历史消息" * 8),
            _message("second", "第二条历史消息" * 8),
        ],
        current_message=_message("current", "继续处理"),
    )

    assert assembly.truncated is True
    assert assembly.omitted_history_count >= 1
    assert "历史上下文已截断" in assembly.prompt
    assert assembly.estimated_tokens <= 120


@pytest.mark.parametrize(
    ("case", "code"),
    [
        (
            lambda: ContextAssembler().assemble(
                trusted_state=TrustedBusinessState(source_id=""),
                recent_messages=[],
                current_message=_message("current", "你好"),
            ),
            "CONTEXT_SOURCE_MISSING",
        ),
        (
            lambda: ContextAssembler().assemble(
                trusted_state=TrustedBusinessState(source_id="conversation:fixture"),
                recent_messages=[],
                current_message=_message("current", "验证码: 123456"),
            ),
            "CONTEXT_SENSITIVE_INPUT",
        ),
        (
            lambda: ContextAssembler().assemble(
                trusted_state={"source_id": "conversation:fixture", "api_key": "secret"},
                recent_messages=[],
                current_message=_message("current", "你好"),
            ),
            "CONTEXT_SENSITIVE_FIELD",
        ),
        (
            lambda: ContextAssembler(
                ContextBudget(total_tokens=20, trusted_tokens=8, history_tokens=4, current_tokens=4)
            ).assemble(
                trusted_state=TrustedBusinessState(source_id="conversation:fixture"),
                recent_messages=[],
                current_message=_message("current", "x" * 40),
            ),
            "CONTEXT_BUDGET_EXCEEDED",
        ),
    ],
)
def test_context_safety_errors_fail_closed(case, code: str) -> None:
    with pytest.raises(ContextAssemblyError) as error:
        case()
    assert error.value.code == code


def test_governance_snapshot_has_permission_matrix_and_no_external_side_effects() -> None:
    snapshot = governance_snapshot()
    names = {item["name"] for item in snapshot["tool_matrix"]}

    assert names == set(CUSTOMER_TOOL_NAMES)
    assert "confirm_refund" not in names
    assert snapshot["external_requests_enabled"] is False
    assert snapshot["stage"] == "stage-1-agent-release-context-governance"
    assert "embedding" in snapshot["not_implemented"]
    assert all(item["allowed_principals"] == ["CUSTOMER"] for item in snapshot["tool_matrix"])


def test_governance_endpoint_is_operator_only_and_repeatable(client) -> None:
    customer_response = client.get("/api/ops/agent-governance")
    assert customer_response.status_code == 403

    agent_response = client.get(
        "/api/ops/agent-governance",
        headers={"X-Agent-Session": AGENT_SESSION_TOKEN},
    )
    assert agent_response.status_code == 403

    first = client.get(
        "/api/ops/agent-governance",
        headers={"X-Ops-Session": OPS_SESSION_TOKEN},
    )
    second = client.get(
        "/api/ops/agent-governance",
        headers={"X-Ops-Session": OPS_SESSION_TOKEN},
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["external_requests_enabled"] is False


def test_model_invocation_model_contains_stage1_audit_binding() -> None:
    expected = {
        "agent_release_id",
        "agent_release_version",
        "prompt_version",
        "tool_schema_version",
        "knowledge_release_version",
        "evaluation_dataset_version",
        "context_policy_version",
        "context_token_count",
        "context_source_count",
        "context_truncated",
    }
    assert expected.issubset(ModelInvocation.__table__.columns.keys())


def test_stage1_migration_and_document_exist() -> None:
    api_root = Path(__file__).resolve().parents[1]
    repo_root = Path(__file__).resolve().parents[3]
    migration = (
        api_root
        / "alembic"
        / "versions"
        / "20260906_0011_agent_release_context_governance.py"
    )
    document = repo_root / "docs" / "阶段1-模块边界、Agent发布与上下文治理.md"
    assert migration.exists()
    assert document.exists()
