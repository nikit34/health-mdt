"""Runtime configuration loaded from environment."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # One of the two must be set for agents to work. Setup token is preferred —
    # it uses a Claude Pro/Max subscription (no pay-per-use API billing).
    #
    # Generate with:  claude setup-token
    # Then paste output into CLAUDE_CODE_OAUTH_TOKEN.
    claude_code_oauth_token: str = ""
    # Pay-per-use API key — fallback if no setup token is configured.
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

    # Email notifications (SMTP)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""  # "Health MDT <noreply@example.com>"
    smtp_tls: bool = True

    # Web Push (VAPID) — auto-generated on first start if empty
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_mailto: str = ""  # "mailto:admin@example.com"

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
        """True if either auth method is configured."""
        return bool(self.claude_code_oauth_token) or bool(self.anthropic_api_key)

    @property
    def llm_auth_mode(self) -> str:
        """Reports which auth the client will use. Useful for UI hints."""
        if self.claude_code_oauth_token:
            return "setup_token"
        if self.anthropic_api_key:
            return "api_key"
        return "none"

    @property
    def has_smtp(self) -> bool:
        return bool(self.smtp_host) and bool(self.smtp_from)

    @property
    def has_vapid(self) -> bool:
        return bool(self.vapid_private_key) and bool(self.vapid_public_key)

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


def anthropic_client_kwargs(settings: "Settings") -> dict:
    """Return kwargs for `Anthropic(...)` — setup token preferred, api_key fallback.

    Kept outside Settings so integrations don't import the SDK just to type-hint.
    """
    if settings.claude_code_oauth_token:
        return {"auth_token": settings.claude_code_oauth_token}
    if settings.anthropic_api_key:
        return {"api_key": settings.anthropic_api_key}
    raise RuntimeError(
        "No LLM credentials. Set CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY in .env."
    )


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
    # Auto-generate VAPID keys for Web Push if not set
    if not settings.vapid_private_key:
        vapid_file = settings.data_dir / "vapid_keys.json"
        if vapid_file.exists():
            import json as _json
            keys = _json.loads(vapid_file.read_text())
            settings.vapid_private_key = keys["private"]
            settings.vapid_public_key = keys["public"]
        else:
            try:
                from pywebpush import webpush  # noqa: F401
                from py_vapid import Vapid
                v = Vapid()
                v.generate_keys()
                settings.vapid_private_key = v.private_pem().decode()
                settings.vapid_public_key = v.public_key_urlsafe_base64()
                import json as _json
                vapid_file.write_text(_json.dumps({
                    "private": settings.vapid_private_key,
                    "public": settings.vapid_public_key,
                }))
            except ImportError:
                pass  # pywebpush not installed — push disabled
    return settings
