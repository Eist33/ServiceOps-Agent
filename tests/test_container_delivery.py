from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_native_dependency_builds_are_explicitly_allowed() -> None:
    workspace_config = (ROOT / "demo" / "pnpm-workspace.yaml").read_text(
        encoding="utf-8"
    )

    for dependency in ("esbuild", "sharp", "workerd"):
        assert f"  {dependency}: true" in workspace_config
    assert "set this to true or false" not in workspace_config


def test_frontend_docker_context_excludes_generated_artifacts() -> None:
    ignored = {
        line.strip()
        for line in (ROOT / "demo" / ".dockerignore").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert {"node_modules", ".vinext", "dist", ".pnpm-store"} <= ignored
    assert {"test-results", "playwright-report", ".env", ".env.*"} <= ignored


def test_frontend_runtime_supports_cloudflare_workerd() -> None:
    dockerfile = (ROOT / "demo" / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM node:22-bookworm-slim AS base" in dockerfile
    assert "apt-get install -y --no-install-recommends libc++1" in dockerfile
    assert "FROM base AS build" in dockerfile
    assert "FROM base AS runtime" in dockerfile
    assert "node:22-alpine" not in dockerfile
    assert (
        'CMD ["pnpm", "exec", "wrangler", "dev", "--config", '
        '"dist/server/wrangler.json", "--ip", "0.0.0.0", "--port", "3000"]'
        in dockerfile
    )
    assert '"pnpm", "run", "start", "--"' not in dockerfile


def test_verification_script_is_non_interactive_and_fails_fast() -> None:
    script = (ROOT / "scripts" / "verify.ps1").read_text(encoding="utf-8")

    assert "$env:CI = 'true'" in script
    assert "(Join-Path $root 'tests')" in script
    assert "if ($ExitCode -ne 0)" in script
    assert script.count("Assert-Succeeded -Step") == 6
    assert "C:\\Users\\12494" not in script
    assert "oxlint.CMD" in script
    assert "vinext.CMD" in script
    assert "playwright.CMD" in script


def test_one_click_start_waits_for_docker_and_checks_both_services() -> None:
    script = (ROOT / "scripts" / "start-product.ps1").read_text(encoding="utf-8")

    assert "docker info" in script
    assert "docker compose up -d --wait" in script
    assert "http://127.0.0.1:8000/health" in script
    assert "http://127.0.0.1:3000/" in script
    assert "[switch]$NoBrowser" in script


def test_release_verification_covers_cold_start_migration_routes_and_reset() -> None:
    script = (ROOT / "scripts" / "verify-release.ps1").read_text(
        encoding="utf-8"
    )

    assert "[switch]$ColdStart" in script
    assert "docker compose stop" in script
    assert "docker compose up -d --build --wait" in script
    assert "docker compose exec -T api alembic current" in script
    for route in ("3000/", "3000/agent", "3000/knowledge", "3000/operations"):
        assert route in script
    assert "Join-Path $PSScriptRoot 'verify.ps1'" in script
    assert "/api/demo/reset" in script


def test_compose_allows_both_local_browser_origins() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert (
        "WEB_ORIGIN: http://localhost:3000,http://127.0.0.1:3000" in compose
    )


def test_compose_services_restart_after_docker_desktop_recovers() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert compose.count("restart: unless-stopped") == 3


def test_non_powershell_start_checks_docker_api_and_web() -> None:
    script = (ROOT / "scripts" / "start-product.cmd").read_text(encoding="utf-8")

    assert "docker info" in script
    assert "docker compose up -d --wait" in script
    assert "http://127.0.0.1:8000/health" in script
    assert "http://127.0.0.1:3000/" in script
    assert "--no-browser" in script
    assert "powershell" not in script.lower()


def test_non_powershell_verification_covers_complete_release_gate() -> None:
    verification = (ROOT / "scripts" / "verify.cmd").read_text(encoding="utf-8")
    release = (ROOT / "scripts" / "verify-release.cmd").read_text(encoding="utf-8")
    e2e = (ROOT / "scripts" / "verify-e2e.cmd").read_text(encoding="utf-8")

    for command in ("ruff.exe", "pytest.exe", "oxlint.CMD", "vinext.CMD", "verify-e2e.cmd"):
        assert command in verification
    for command in (
        "docker compose up -d --build --wait",
        "alembic current",
        "evaluate-knowledge",
        "evaluate-agent",
        "scripts\\verify.cmd",
        "verify_model_provider.py",
        "--runtime model",
        "/api/demo/reset",
    ):
        assert command in release
    for route in ("3000/", "3000/staff/agent", "3000/staff/knowledge", "3000/staff/operations"):
        assert route in release
    assert "powershell" not in verification.lower()
    assert "powershell" not in release.lower()
    assert "playwright.CMD test" in e2e
    assert "docker-compose.e2e.yml up -d --build --wait" in e2e
    assert "docker-compose.e2e.yml down -v" in e2e
    assert "powershell" not in e2e.lower()


def test_playwright_release_gate_is_isolated_from_running_docker_product() -> None:
    config = (ROOT / "demo" / "playwright.config.ts").read_text(encoding="utf-8")
    scenarios = (ROOT / "demo" / "e2e" / "core-flows.spec.ts").read_text(
        encoding="utf-8"
    )

    assert "http://127.0.0.1:8100" in config
    assert "http://127.0.0.1:3100" in config
    assert "reuseExistingServer: !process.env.CI" in config
    assert "E2E_EXTERNAL_SERVER" in config
    assert "serviceops-e2e-${process.pid}.db" in config
    assert "DATABASE_URL: `sqlite:///${databasePath}`" in config
    assert "--timeout-graceful-shutdown 2" in config
    assert "const API_BASE_URL = 'http://127.0.0.1:8100'" in scenarios
    assert "http://127.0.0.1:8000" not in scenarios


def test_compose_explicitly_marks_local_runtime_as_demo() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert 'DEMO_MODE_ENABLED: "true"' in compose
    assert 'API_DOCS_ENABLED: "true"' in compose


def test_e2e_compose_is_deterministic_and_does_not_publish_postgres() -> None:
    compose = (ROOT / "docker-compose.e2e.yml").read_text(encoding="utf-8")

    assert "AGENT_MODE: deterministic" in compose
    assert "WEB_ORIGIN: http://127.0.0.1:3100" in compose
    assert '"8100:8000"' in compose
    assert '"3100:3000"' in compose
    assert "fetch('http://localhost:3000')" in compose
    postgres_section = compose.split("  api:", maxsplit=1)[0]
    assert "ports:" not in postgres_section


def test_initial_migration_uses_a_frozen_schema_snapshot() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260831_0001_initial.py"
    ).read_text(encoding="utf-8")

    assert "from serviceops.database import Base" not in migration
    assert "Base.metadata" not in migration
    assert "def _initial_metadata()" in migration
    assert '"operators"' not in migration
    assert '"model_invocations"' not in migration
    assert '"priority"' not in migration
