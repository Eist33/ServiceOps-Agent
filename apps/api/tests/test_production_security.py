import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import serviceops.main as main_module
from serviceops.config import Settings, get_settings


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://serviceops_app:strong-password@db/serviceops",
        "web_origin": "https://support.example.com",
        "demo_mode_enabled": False,
        "api_docs_enabled": False,
        "sensitive_tracing_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"demo_mode_enabled": True}, "DEMO_MODE_ENABLED"),
        ({"api_docs_enabled": True}, "API_DOCS_ENABLED"),
        ({"sensitive_tracing_enabled": True}, "SENSITIVE_TRACING_ENABLED"),
        ({"database_url": "sqlite:///production.db"}, "PostgreSQL"),
        (
            {
                "database_url": (
                    "postgresql+psycopg://serviceops:serviceops@db/serviceops"
                )
            },
            "demonstration credentials",
        ),
        ({"web_origin": "http://support.example.com"}, "WEB_ORIGIN"),
        ({"web_origin": "https://localhost:3000"}, "WEB_ORIGIN"),
        ({"web_origin": "*"}, "WEB_ORIGIN"),
        ({"web_origin": "https://support.example.com/path"}, "WEB_ORIGIN"),
        ({"web_origin": "https://user:password@support.example.com"}, "WEB_ORIGIN"),
        ({"web_origin": "https://support.example.com/?debug=true"}, "WEB_ORIGIN"),
        ({"web_origin": "https://[invalid"}, "WEB_ORIGIN"),
    ],
)
def test_production_settings_fail_closed(
    overrides: dict[str, object], expected: str
) -> None:
    with pytest.raises(ValidationError, match=expected):
        production_settings(**overrides)


def test_production_settings_accept_hardened_configuration() -> None:
    settings = production_settings(
        web_origin="https://support.example.com,https://staff.example.com"
    )

    assert settings.app_env == "production"
    assert settings.demo_mode_enabled is False
    assert settings.api_docs_enabled is False


def test_production_app_omits_demo_seed_reset_and_api_docs(monkeypatch) -> None:
    settings = production_settings()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)

    def unexpected_seed(_db) -> None:
        pytest.fail("production startup must not seed demonstration data")

    monkeypatch.setattr(main_module, "seed_database", unexpected_seed)
    app = main_module.create_app()
    app.dependency_overrides[get_settings] = lambda: settings

    assert app.openapi_url is None
    assert all(route.path != "/api/demo/reset" for route in app.routes)
    assert all(
        route.path not in {"/api/auth/development-accounts", "/api/auth/login"}
        for route in app.routes
    )

    with TestClient(app) as client:
        health = client.get("/health")
        me = client.get("/api/me", headers={"X-Demo-Session": "demo-linmu-session"})

    assert health.status_code == 200
    assert health.headers["cache-control"] == "no-store"
    assert health.headers["referrer-policy"] == "no-referrer"
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert health.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert health.headers["strict-transport-security"].startswith("max-age=31536000")
    assert me.status_code == 403
    assert me.json()["error"]["message"] == "当前环境未启用开发身份认证"


def test_production_cors_accepts_only_declared_origin_method_and_header(monkeypatch) -> None:
    settings = production_settings()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    app = main_module.create_app()
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as client:
        allowed = client.options(
            "/health",
            headers={
                "Origin": "https://support.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Trace-ID",
            },
        )
        forbidden = client.options(
            "/health",
            headers={
                "Origin": "https://support.example.com",
                "Access-Control-Request-Method": "DELETE",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://support.example.com"
    assert "GET" in allowed.headers["access-control-allow-methods"]
    assert "x-trace-id" in allowed.headers["access-control-allow-headers"].lower()
    assert forbidden.status_code == 400
