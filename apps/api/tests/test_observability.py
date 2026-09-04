import asyncio
import json
import logging
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from serviceops.agent import openai_runtime
from serviceops.conversations.service import create_conversation
from serviceops.identity.service import resolve_customer
from serviceops.main import create_app
from serviceops.observability import redact
from serviceops.seed import DEMO_SESSION_TOKEN


def _new_conversation(client) -> str:
    return client.post("/api/conversations").json()["id"]


def test_request_trace_id_correlates_agent_events_and_safe_json_log(client, caplog):
    trace_id = "acceptance-trace-001"
    conversation_id = _new_conversation(client)

    with caplog.at_level(logging.INFO, logger="serviceops.request"):
        response = client.post(
            f"/api/conversations/{conversation_id}/messages",
            headers={"X-Trace-ID": trace_id},
            json={"content": "退货政策"},
        )

    assert response.status_code == 200
    assert response.headers["X-Trace-ID"] == trace_id
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events
    assert {event["trace_id"] for event in events} == {trace_id}

    request_logs = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "serviceops.request"
        and json.loads(record.message).get("event") == "request_completed"
    ]
    assert request_logs[-1] == {
        "event": "request_completed",
        "trace_id": trace_id,
        "method": "POST",
        "path": f"/api/conversations/{conversation_id}/messages",
        "status_code": 200,
        "duration_ms": request_logs[-1]["duration_ms"],
    }
    assert "demo-linmu-session" not in caplog.text


def test_invalid_incoming_trace_id_is_replaced(client):
    response = client.get("/health", headers={"X-Trace-ID": "not safe trace id"})

    assert response.status_code == 200
    assert response.headers["X-Trace-ID"] != "not safe trace id"
    assert len(response.headers["X-Trace-ID"]) == 36


def test_recursive_redaction_covers_nested_and_case_insensitive_fields():
    value = {
        "query": "物流",
        "context": {
            "Authorization": "Bearer secret-value",
            "credentials": [{"session-token": "session-secret"}],
        },
        "api_secret": "api-secret",
    }

    assert redact(value) == {
        "query": "物流",
        "context": {
            "Authorization": "[REDACTED]",
            "credentials": [{"session-token": "[REDACTED]"}],
        },
        "api_secret": "[REDACTED]",
    }


def test_unhandled_errors_return_generic_traceable_response(caplog):
    app: FastAPI = create_app()

    @app.get("/test-unhandled-error")
    def fail():
        raise RuntimeError("private-token-should-not-appear")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        with caplog.at_level(logging.INFO, logger="serviceops.request"):
            response = test_client.get(
                "/test-unhandled-error",
                headers={"X-Trace-ID": "failure-trace-001"},
            )

    assert response.status_code == 500
    assert response.headers["X-Trace-ID"] == "failure-trace-001"
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "服务暂时不可用，请稍后重试",
        },
        "trace_id": "failure-trace-001",
    }
    assert "private-token-should-not-appear" not in caplog.text
    assert '"error_type":"RuntimeError"' in caplog.text


def test_openai_runtime_uses_explicit_sensitive_tracing_setting(db, monkeypatch):
    captured = {}

    async def fake_run(agent, content, *, context, run_config):
        captured["run_config"] = run_config
        return SimpleNamespace(final_output="已根据工具证据回答")

    monkeypatch.setattr(openai_runtime.Runner, "run", fake_run)
    monkeypatch.setattr(
        openai_runtime,
        "get_settings",
        lambda: SimpleNamespace(sensitive_tracing_enabled=False),
    )
    customer = resolve_customer(db, DEMO_SESSION_TOKEN)
    conversation = create_conversation(db, customer)
    runtime = openai_runtime.OpenAISupportAgent(db, customer, "gpt-5.4-mini")

    events = asyncio.run(
        runtime.run(
            conversation.id,
            "退货政策",
            trace_id="openai-runtime-trace-001",
        )
    )

    assert captured["run_config"].trace_include_sensitive_data is False
    assert captured["run_config"].group_id == conversation.id
    assert {event.trace_id for event in events} == {"openai-runtime-trace-001"}
