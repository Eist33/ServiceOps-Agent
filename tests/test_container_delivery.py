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
