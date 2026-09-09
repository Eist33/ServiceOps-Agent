from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_compose_hides_api_and_web_ports_behind_gateway() -> None:
    compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")

    assert "APP_ENV: production" in compose
    assert 'DEMO_MODE_ENABLED: "false"' in compose
    assert 'API_DOCS_ENABLED: "false"' in compose
    assert "serviceops-gateway:production" in compose
    assert '"${GATEWAY_HTTP_PORT:-80}:80"' in compose
    assert '"${GATEWAY_HTTPS_PORT:-443}:443"' in compose
    assert "serviceops-production-postgres" in compose

    api_block = compose.split("  api:", maxsplit=1)[1].split("  web:", maxsplit=1)[0]
    web_block = compose.split("  web:", maxsplit=1)[1].split("  gateway:", maxsplit=1)[0]
    assert "ports:" not in api_block
    assert "ports:" not in web_block
    assert '"8000"' in api_block
    assert '"3000"' in web_block


def test_gateway_routes_api_and_web_on_the_internal_network() -> None:
    config = (ROOT / "deploy" / "nginx" / "production.conf").read_text(
        encoding="utf-8"
    )

    assert "server api:8000" in config
    assert "server web:3000" in config
    assert "location /api/" in config
    assert "proxy_pass http://serviceops_api;" in config
    assert "proxy_pass http://serviceops_web;" in config
    assert "ssl_certificate /etc/nginx/tls/fullchain.pem" in config
    assert "return 308 https://$host$request_uri" in config


def test_production_frontend_is_built_for_external_identity_and_relative_api() -> None:
    dockerfile = (ROOT / "demo" / "Dockerfile").read_text(encoding="utf-8")
    auth_gate = (ROOT / "demo" / "components" / "auth-gate.tsx").read_text(
        encoding="utf-8"
    )

    assert "NEXT_PUBLIC_AUTH_MODE" in dockerfile
    assert "AUTH_MODE === 'external'" in auth_gate
    assert "正式环境" in auth_gate


def test_api_container_does_not_seed_production_data() -> None:
    dockerfile = (ROOT / "apps" / "api" / "Dockerfile").read_text(encoding="utf-8")

    assert r'if [ \"$APP_ENV\" != \"production\" ]' in dockerfile
    assert "python -m serviceops.cli seed" in dockerfile


def test_production_packaging_script_builds_gateway_and_external_auth_image() -> None:
    script = (ROOT / "scripts" / "package-production-portainer.ps1").read_text(
        encoding="utf-8"
    )

    assert "docker-compose.production.yml" in script
    assert "serviceops-gateway" in script
    assert "NEXT_PUBLIC_API_URL=" in script
    assert "NEXT_PUBLIC_AUTH_MODE=external" in script
    assert '"save"' in script
    assert "serviceops-production-package-" in script
