from functools import lru_cache
from typing import Self
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Harbor Support API"
    app_env: str = "development"
    database_url: str = "sqlite:///./serviceops.db"
    web_origin: str = "http://localhost:3000"
    agent_mode: str = "deterministic"
    model_provider: str = "deepseek"
    model_api_style: str = "responses"
    model_base_url: str = "https://api.deepseek.com"
    model_name: str = "deepseek-v4-flash"
    model_api_key: str | None = None
    deepseek_api_key: str | None = None
    model_timeout_seconds: float = 30.0
    model_max_retries: int = 1
    model_requests_per_minute: int = 30
    model_circuit_failure_threshold: int = 3
    model_circuit_cooldown_seconds: float = 60.0
    model_fallback_enabled: bool = True
    model_max_turns: int = 8
    demo_mode_enabled: bool = True
    api_docs_enabled: bool = True
    demo_login_password: str = "serviceops"
    auth_session_hours: int = 12
    # Legacy OpenAI-specific settings remain supported during migration.
    openai_model: str = "gpt-5.4-mini"
    openai_api_key: str | None = None
    embedding_provider: str = "not_configured"
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str | None = None
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 32
    embedding_max_retries: int = 2
    embedding_requests_per_minute: int = 60
    embedding_cost_per_1k_tokens: float = 0.0
    embedding_normalization_version: str = "l2-v1"
    sensitive_tracing_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        if self.app_env.strip().lower() != "production":
            return self

        errors: list[str] = []
        if self.demo_mode_enabled:
            errors.append("DEMO_MODE_ENABLED must be false")
        if self.api_docs_enabled:
            errors.append("API_DOCS_ENABLED must be false")
        if self.sensitive_tracing_enabled:
            errors.append("SENSITIVE_TRACING_ENABLED must be false")
        if self.database_url.lower().startswith("sqlite"):
            errors.append("DATABASE_URL must use PostgreSQL")
        if "serviceops:serviceops@" in self.database_url.lower():
            errors.append("DATABASE_URL must not use demonstration credentials")

        origins = [origin.strip() for origin in self.web_origin.split(",") if origin.strip()]
        if not origins:
            errors.append("WEB_ORIGIN must contain at least one HTTPS origin")
        for origin in origins:
            parsed = urlparse(origin)
            if (
                origin == "*"
                or parsed.scheme != "https"
                or parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            ):
                errors.append(f"WEB_ORIGIN is not production-safe: {origin}")

        if errors:
            raise ValueError("Production security validation failed: " + "; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
