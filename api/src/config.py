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
    # "pin" (single-user) | "oauth" (multi-user via OAuth provider).
    auth_mode: str = "pin"
    # Secret used to sign session cookies in oauth mode; auto-generated on first start if empty.
    session_secret: str = ""

    # OAuth (when auth_mode=oauth)
    oauth_google_client_id: str = ""
    oauth_google_client_secret: str = ""
    # Comma-separated list of allowed emails. Empty = anyone can sign up.
    oauth_allowed_emails: str = ""

    # Data sources
    oura_personal_access_token: str = ""

    # Evidence
    semantic_scholar_api_key: str = ""

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

    @property
    def has_oauth(self) -> bool:
        return (
            self.auth_mode == "oauth"
            and bool(self.oauth_google_client_id)
            and bool(self.oauth_google_client_secret)
        )

    @property
    def allowed_email_list(self) -> list[str]:
        if not self.oauth_allowed_emails.strip():
            return []
        return [e.strip().lower() for e in self.oauth_allowed_emails.split(",") if e.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    # Ensure a stable session secret exists in oauth mode — auto-generate if missing
    if settings.auth_mode == "oauth" and not settings.session_secret:
        secret_file = settings.data_dir / "session_secret"
        if secret_file.exists():
            settings.session_secret = secret_file.read_text().strip()
        else:
            import secrets as _s
            settings.session_secret = _s.token_urlsafe(48)
            secret_file.write_text(settings.session_secret)
    return settings
