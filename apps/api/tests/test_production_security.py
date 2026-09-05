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

    with TestClient(app) as client:
        health = client.get("/health")
        me = client.get("/api/me", headers={"X-Demo-Session": "demo-linmu-session"})

    assert health.status_code == 200
    assert health.headers["cache-control"] == "no-store"
    assert health.headers["referrer-policy"] == "no-referrer"
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert health.headers["strict-transport-security"].startswith("max-age=31536000")
    assert me.status_code == 403
    assert me.json()["error"]["message"] == "当前环境未启用演示身份认证"
