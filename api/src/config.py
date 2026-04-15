"""Runtime configuration loaded from environment."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required for agents to work; web still starts without it.
    anthropic_api_key: str = ""

    # Access control
    domain: str = "localhost"
    access_pin: str = ""

    # Data sources
    oura_personal_access_token: str = ""

    # Telegram
    telegram_bot_token: str = ""

    # Models
    agent_model: str = "claude-sonnet-4-6"
    synthesis_model: str = "claude-opus-4-6"

    # Internal
    database_url: str = "sqlite:///data/health.db"
    log_level: str = "INFO"
    timezone: str = "Europe/Amsterdam"

    data_dir: Path = Path("data")
    uploads_dir: Path = Path("uploads")

    @property
    def has_llm(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_oura(self) -> bool:
        return bool(self.oura_personal_access_token)

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    return settings
