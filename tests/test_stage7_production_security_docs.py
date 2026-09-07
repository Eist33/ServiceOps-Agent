from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "企业客服与工单执行Agent_生产化开发流程_v1.0.md"
DOCUMENT = ROOT / "docs" / "阶段7-生产安全基线与发布工具.md"


def test_stage7_document_matches_the_delivery_plan_and_is_docker_only() -> None:
    plan = PLAN.read_text(encoding="utf-8")
    document = DOCUMENT.read_text(encoding="utf-8")

    assert "阶段 7：生产安全基线与发布工具" in plan
    for marker in (
        "APP_ENV=production",
        "DEMO_MODE_ENABLED=false",
        "API_DOCS_ENABLED=false",
        "SENSITIVE_TRACING_ENABLED=false",
        "DATABASE_URL",
        "WEB_ORIGIN",
        "PostgreSQL",
        "HTTPS origin",
        "CORS",
        "Permissions-Policy",
        "start-product.cmd",
        "verify.cmd",
        "verify-release.cmd",
        "70 条",
        "Docker-only",
        "网页验收",
        "external_requests_enabled",
        "Cookie",
        "Token",
        "自动发送",
    ):
        assert marker in document
    assert "PowerShell" not in document


def test_stage7_environment_examples_expose_safe_runtime_switches() -> None:
    for path in (ROOT / ".env.example", ROOT / "apps" / "api" / ".env.example"):
        text = path.read_text(encoding="utf-8")
        for marker in (
            "APP_ENV=",
            "DATABASE_URL=",
            "WEB_ORIGIN=",
            "DEMO_MODE_ENABLED=",
            "API_DOCS_ENABLED=",
            "SENSITIVE_TRACING_ENABLED=",
        ):
            assert marker in text


def test_stage7_cmd_verification_stays_inside_docker() -> None:
    verify = (ROOT / "scripts" / "verify.cmd").read_text(encoding="utf-8")
    e2e = (ROOT / "scripts" / "verify-e2e.cmd").read_text(encoding="utf-8")
    release = (ROOT / "scripts" / "verify-release.cmd").read_text(encoding="utf-8")

    for marker in (
        "docker info --format",
        "docker compose -f docker-compose.yml -f docker-compose.stage3.yml run --rm api-test",
        "python -m pytest /workspace/tests",
        "docker compose -f docker-compose.e2e.yml run --rm --no-deps e2e pnpm lint",
        "docker compose -f docker-compose.e2e.yml run --rm --no-deps e2e pnpm run build",
        "verify-e2e.cmd",
    ):
        assert marker in verify
    for marker in (
        "docker compose -f docker-compose.e2e.yml config --quiet",
        "docker compose -f docker-compose.e2e.yml up -d --build --wait postgres api web",
        "docker compose -f docker-compose.e2e.yml run --rm --no-deps e2e pnpm test:e2e",
        "docker compose -f docker-compose.e2e.yml down -v",
    ):
        assert marker in e2e
    for marker in (
        "docker compose config --quiet",
        "docker compose up -d --build --wait",
        "alembic current",
        "evaluate-knowledge",
        "evaluate-agent",
        "docker compose exec -T api python -c",
        "docker compose exec -T api python - --api-base-url",
        "scripts\\verify.cmd",
    ):
        assert marker in release
    assert "node_modules\\.bin" not in verify
    assert "playwright.CMD" not in e2e
    for script in (verify, e2e, release):
        assert "powershell" not in script.lower()
    assert "curl.exe" not in release.lower()
    assert ".venv" not in release.lower()


def test_stage7_docs_keep_later_external_stages_out_of_scope() -> None:
    document = DOCUMENT.read_text(encoding="utf-8")

    for marker in (
        "阶段 8",
        "阶段 9",
        "阶段 10",
        "阶段 11",
        "阶段 12",
        "保持原有未配置或待审批状态",
    ):
        assert marker in document
    for forbidden in (
        "fetch(",
        "axios",
        "websocket",
        "selenium",
        "验证码输入",
        "代填验证码",
    ):
        assert forbidden not in document.lower()
