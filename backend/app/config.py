from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./service_desk.db"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "local-development-only-change-me"
    ai_provider: str = "demo"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    sync_jobs: bool = True
    sla_timezone: str = "Asia/Kolkata"
    cookie_secure: bool = False
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

