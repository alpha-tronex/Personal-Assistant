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
    google_token_path: str = Field(default="./data/token.json", alias="GOOGLE_TOKEN_PATH")

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
    def google_token_file(self) -> Path:
        return self.resolve_path(self.google_token_path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
