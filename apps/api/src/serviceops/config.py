from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Harbor Support API"
    app_env: str = "development"
    database_url: str = "sqlite:///./serviceops.db"
    web_origin: str = "http://localhost:3000"
    agent_mode: str = "deterministic"
    openai_model: str = "gpt-5.4-mini"
    openai_api_key: str | None = None
    sensitive_tracing_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
