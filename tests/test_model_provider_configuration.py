from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compose_keeps_model_key_on_api_service_only() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    api_section, web_section = compose.split("  web:", 1)

    assert "MODEL_PROVIDER:" in api_section
    assert "MODEL_API_KEY:" in api_section
    assert "DEEPSEEK_API_KEY:" in api_section
    assert "MODEL_API_KEY:" not in web_section
    assert "DEEPSEEK_API_KEY:" not in web_section


def test_example_environment_defaults_to_safe_deterministic_mode() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "AGENT_MODE=deterministic" in example
    assert "MODEL_PROVIDER=deepseek" in example
    assert "MODEL_API_STYLE=responses" in example
    assert "MODEL_BASE_URL=https://api.deepseek.com" in example
    assert "MODEL_NAME=deepseek-v4-flash" in example
    assert "MODEL_API_KEY=" in example


def test_model_audit_migration_is_reversible() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260904_0008_model_invocation_audit.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "20260904_0007"' in migration
    assert 'op.create_table(\n        "model_invocations"' in migration
    assert 'op.drop_table("model_invocations")' in migration


def test_customer_stream_accumulates_deltas_and_discloses_fallback() -> None:
    client = (ROOT / "demo" / "app" / "demo-client.tsx").read_text(
        encoding="utf-8"
    )
    api_contract = (ROOT / "demo" / "lib" / "api.ts").read_text(
        encoding="utf-8"
    )

    assert "event.type === 'model_fallback'" in client
    assert "text: `${item.text}${delta}`" in client
    assert "id: event.message_id" in client
    assert "id: `error-${event.trace_id}`" not in client
    assert "| 'model_fallback'" in api_contract


def test_openai_client_is_a_direct_backend_dependency() -> None:
    project = (ROOT / "apps" / "api" / "pyproject.toml").read_text(encoding="utf-8")

    assert '"openai>=3,<4"' in project


def test_real_provider_smoke_script_never_reads_or_prints_the_key() -> None:
    script = (ROOT / "scripts" / "verify-model-provider.ps1").read_text(
        encoding="utf-8"
    )

    assert "key_configured" in script
    assert "model_fallback" in script
    assert "search_knowledge_base" in script
    assert "get_shipping_status" in script
    assert "MODEL_API_KEY" not in script
    assert "DEEPSEEK_API_KEY" not in script
    assert "OPENAI_API_KEY" not in script
