from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "production"] = "development"
    app_name: str = "SafeRoute"
    app_version: str = "0.1.0"

    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # Developer auth token
    auth_header_name: str = "X-Developer-Token"
    dev_token_prefix: str = "dev-"

    # LLM routing via LiteLLM
    openrouter_api_key: str = ""
    default_model: str = "openrouter/google/gemma-4-27b-it:free"
    llm_timeout: int = 300
    llm_max_tokens: int = 1600

    # SpaCy NER model
    spacy_model: str = "en_core_web_sm"

    # Database — SQLite for dev, set DATABASE_URL env var for PostgreSQL in prod
    database_url: str = "sqlite+aiosqlite:///./saferoute.db"

    # Logging
    log_fmt: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_file: Path = Path("app.log")

    # CORS — override in production
    allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
