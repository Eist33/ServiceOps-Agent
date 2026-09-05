import asyncio
from types import SimpleNamespace

import pytest
from agents.usage import Usage
from sqlalchemy import select

from serviceops.agent.openai_runtime import ModelSupportAgent
from serviceops.agent.providers import (
    LocalModelRateLimitError,
    ModelCircuitOpenError,
    ModelConfigurationError,
    ModelProviderConfiguration,
    ModelReliabilityGuard,
)
from serviceops.config import Settings
from serviceops.conversations.service import create_conversation
from serviceops.identity.service import resolve_customer
from serviceops.models import Message, ModelInvocation
from serviceops.seed import DEMO_SESSION_TOKEN
from serviceops.shared.schemas import AgentEvent, EventType


def configuration(**overrides):
    values = {
        "provider": "deepseek",
        "api_style": "responses",
        "base_url": "https://api.deepseek.com",
        "model_name": "deepseek-v4-flash",
        "api_key": "sk-test-secret",
        "timeout_seconds": 2.0,
        "max_retries": 1,
        "requests_per_minute": 30,
        "circuit_failure_threshold": 3,
        "circuit_cooldown_seconds": 60.0,
        "fallback_enabled": True,
        "max_turns": 8,
    }
    values.update(overrides)
    return ModelProviderConfiguration(**values).validated()


class SuccessfulStream:
    final_output = "你好，我可以帮你处理售后问题。"
    context_wrapper = SimpleNamespace(
        usage=Usage(requests=1, input_tokens=18, output_tokens=9, total_tokens=27)
    )

    async def stream_events(self):
        for delta in ("你好，", "我可以帮你处理售后问题。"):
            yield SimpleNamespace(
                type="raw_response_event",
                data=SimpleNamespace(
                    type="response.output_text.delta",
                    delta=delta,
                ),
            )


class FailingStream:
    final_output = None
    context_wrapper = SimpleNamespace(usage=Usage())

    async def stream_events(self):
        raise TimeoutError("secret provider detail")
        yield  # pragma: no cover


class PartialFailingStream:
    final_output = None
    context_wrapper = SimpleNamespace(usage=Usage())

    async def stream_events(self):
        yield SimpleNamespace(
            type="raw_response_event",
            data=SimpleNamespace(
                type="response.output_text.delta",
                delta="正在处理",
            ),
        )
        raise RuntimeError("secret provider detail")


def collect(agent, conversation_id, content):
    async def run():
        return [
            event
            async for event in agent.stream(
                conversation_id,
                content,
                trace_id="model-test-trace",
            )
        ]

    return asyncio.run(run())


def test_deepseek_configuration_uses_generic_server_only_boundary():
    settings = Settings(
        agent_mode="model",
        model_provider="deepseek",
        model_api_style="responses",
        model_base_url="https://api.deepseek.com/",
        model_name="deepseek-v4-flash",
        model_api_key="sk-private",
    )
    configured = ModelProviderConfiguration.from_settings(settings)

    assert configured.provider == "deepseek"
    assert configured.base_url == "https://api.deepseek.com"
    assert configured.model_name == "deepseek-v4-flash"
    assert "sk-private" not in repr(configured)


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider": "unknown"},
        {"api_style": "legacy"},
        {"base_url": "http://api.deepseek.com"},
        {"base_url": "https://example.com"},
        {"max_retries": 4},
    ],
)
def test_invalid_or_non_official_deepseek_configuration_is_rejected(overrides):
    with pytest.raises(ModelConfigurationError):
        configuration(**overrides)


def test_local_rate_limit_and_circuit_breaker_are_independent():
    now = [100.0]
    rate_guard = ModelReliabilityGuard(
        requests_per_minute=1,
        failure_threshold=3,
        cooldown_seconds=30,
        clock=lambda: now[0],
    )
    rate_guard.before_request()
    with pytest.raises(LocalModelRateLimitError):
        rate_guard.before_request()
    now[0] += 61
    rate_guard.before_request()

    circuit_guard = ModelReliabilityGuard(
        requests_per_minute=20,
        failure_threshold=2,
        cooldown_seconds=30,
        clock=lambda: now[0],
    )
    circuit_guard.record_failure(TimeoutError())
    circuit_guard.record_failure(TimeoutError())
    with pytest.raises(ModelCircuitOpenError):
        circuit_guard.before_request()
    now[0] += 31
    circuit_guard.before_request()


def test_model_stream_persists_answer_and_metadata_only_audit(db):
    customer = resolve_customer(db, DEMO_SESSION_TOKEN)
    conversation = create_conversation(db, customer)
    guard = ModelReliabilityGuard(
        requests_per_minute=30,
        failure_threshold=3,
        cooldown_seconds=60,
    )
    captured = {}

    def runner(*args, **kwargs):
        captured.update(kwargs)
        return SuccessfulStream()

    agent = ModelSupportAgent(
        db,
        customer,
        configuration(),
        sdk_provider=object(),
        reliability_guard=guard,
        runner_streamed=runner,
    )

    events = collect(agent, conversation.id, "你好")

    assert [
        event.payload["delta"]
        for event in events
        if event.type == EventType.MESSAGE_DELTA
    ] == ["你好，", "我可以帮你处理售后问题。"]
    assert agent.agent.model_settings.parallel_tool_calls is False
    assert (
        captured["run_config"].tool_execution.max_function_tool_concurrency
        == 1
    )
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at)
        )
    )
    assert [(item.role, item.content) for item in messages] == [
        ("user", "你好"),
        ("agent", SuccessfulStream.final_output),
    ]
    audit = db.scalar(select(ModelInvocation))
    assert audit is not None
    assert audit.status == "SUCCEEDED"
    assert audit.provider == "deepseek"
    assert audit.total_tokens == 27
    assert not hasattr(audit, "input_summary")
    assert not hasattr(audit, "output_summary")
    assert "sk-test-secret" not in str(audit.__dict__)


def test_provider_timeout_falls_back_without_duplicate_user_message(db):
    customer = resolve_customer(db, DEMO_SESSION_TOKEN)
    conversation = create_conversation(db, customer)
    agent = ModelSupportAgent(
        db,
        customer,
        configuration(),
        sdk_provider=object(),
        reliability_guard=ModelReliabilityGuard(
            requests_per_minute=30,
            failure_threshold=3,
            cooldown_seconds=60,
        ),
        runner_streamed=lambda *args, **kwargs: FailingStream(),
    )

    events = collect(agent, conversation.id, "收到商品后几天能退货？")

    assert EventType.MODEL_FALLBACK in [event.type for event in events]
    assert EventType.TOOL_COMPLETED in [event.type for event in events]
    messages = list(
        db.scalars(select(Message).where(Message.conversation_id == conversation.id))
    )
    assert sum(item.role == "user" for item in messages) == 1
    audit = db.scalar(select(ModelInvocation))
    assert audit is not None
    assert audit.status == "FAILED"
    assert audit.error_type == "MODEL_TIMEOUT"
    assert audit.fallback_used is True


def test_provider_failure_after_write_does_not_replay_with_fallback(db):
    customer = resolve_customer(db, DEMO_SESSION_TOKEN)
    conversation = create_conversation(db, customer)

    def runner(*args, **kwargs):
        context = kwargs["context"]
        context.events.append(
            AgentEvent(
                type=EventType.TOOL_COMPLETED,
                conversation_id=conversation.id,
                message_id=context.message_id,
                trace_id=context.trace_id,
                payload={"tool_name": "create_ticket", "status": "succeeded"},
            )
        )
        return PartialFailingStream()

    agent = ModelSupportAgent(
        db,
        customer,
        configuration(),
        sdk_provider=object(),
        reliability_guard=ModelReliabilityGuard(
            requests_per_minute=30,
            failure_threshold=3,
            cooldown_seconds=60,
        ),
        runner_streamed=runner,
    )

    events = collect(agent, conversation.id, "帮我创建工单")

    assert EventType.MODEL_FALLBACK not in [event.type for event in events]
    assert EventType.ERROR in [event.type for event in events]
    delta = next(event for event in events if event.type == EventType.MESSAGE_DELTA)
    error = next(event for event in events if event.type == EventType.ERROR)
    completed = next(
        event for event in events if event.type == EventType.RESPONSE_COMPLETED
    )
    assert error.message_id == delta.message_id == completed.message_id
    messages = list(
        db.scalars(select(Message).where(Message.conversation_id == conversation.id))
    )
    assert sum(item.role == "agent" for item in messages) == 1
    assert "模型服务暂时不可用" in next(
        item.content for item in messages if item.role == "agent"
    )
    audit = db.scalar(select(ModelInvocation))
    assert audit is not None
    assert audit.fallback_used is False
