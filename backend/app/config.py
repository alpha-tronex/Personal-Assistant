"""Application configuration loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = the backend/ folder (one level up from app/)
BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Telegram
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    # Google
    google_credentials_path: str = Field(
        default="./data/credentials.json", alias="GOOGLE_CREDENTIALS_PATH"
    )
    google_web_credentials_path: str = Field(
        default="./data/credentials_web.json", alias="GOOGLE_WEB_CREDENTIALS_PATH"
    )
    google_token_path: str = Field(default="./data/token.json", alias="GOOGLE_TOKEN_PATH")

    # Re-auth secret — protects /reauth from public access
    reauth_secret: str = Field(default="", alias="REAUTH_SECRET")

    # Gmail filtering
    # Gmail search query for the email agent. By default we exclude the
    # Promotions tab so advertising / marketing mail never reaches the LLM.
    gmail_query: str = Field(
        default="newer_than:2d in:inbox -category:promotions",
        alias="GMAIL_QUERY",
    )
    # Comma-separated case-insensitive substrings. Any sender email whose
    # address contains one of these substrings will be skipped before the
    # LLM call. Useful for the few promotional senders that don't end up
    # in the Promotions tab (e.g. "no-reply@", "marketing@", "newsletter").
    gmail_ignore_from: str = Field(default="", alias="GMAIL_IGNORE_FROM")

    # App
    app_timezone: str = Field(default="America/New_York", alias="APP_TIMEZONE")
    app_db_url: str = Field(default="sqlite:///./data/agentic.db", alias="APP_DB_URL")
    app_log_level: str = Field(default="INFO", alias="APP_LOG_LEVEL")
    app_brief_hour: int = Field(default=8, alias="APP_BRIEF_HOUR")
    app_brief_minute: int = Field(default=0, alias="APP_BRIEF_MINUTE")

    def resolve_path(self, value: str) -> Path:
        """Resolve a possibly-relative path against the backend root."""
        p = Path(value)
        if not p.is_absolute():
            p = BACKEND_ROOT / p
        return p

    @property
    def google_credentials_file(self) -> Path:
        return self.resolve_path(self.google_credentials_path)

    @property
    def google_web_credentials_file(self) -> Path:
        return self.resolve_path(self.google_web_credentials_path)

    @property
    def google_token_file(self) -> Path:
        return self.resolve_path(self.google_token_path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
