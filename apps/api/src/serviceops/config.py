from functools import lru_cache

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
    # Legacy OpenAI-specific settings remain supported during migration.
    openai_model: str = "gpt-5.4-mini"
    openai_api_key: str | None = None
    sensitive_tracing_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
