"""Shared Google OAuth helper.

Handles a one-time browser-based login (Installed App / Desktop flow), then
caches the long-lived refresh token to disk. Subsequent calls silently refresh
the access token without user interaction.

Scopes are union'd across all three Google agents we plan to use.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from ..config import get_settings

logger = logging.getLogger(__name__)

# All scopes we will ever ask for, in one consent screen.
DEFAULT_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
)


class GoogleAuthError(RuntimeError):
    pass


def load_credentials(scopes: Iterable[str] = DEFAULT_SCOPES) -> Credentials:
    """Load cached credentials, refresh if needed.

    Raises GoogleAuthError if no valid token is cached. Run
    `python scripts/google_login.py` to perform the one-time browser login.
    """
    settings = get_settings()
    token_path: Path = settings.google_token_file

    if not token_path.exists():
        raise GoogleAuthError(
            f"No Google token cached at {token_path}. "
            "Run `python scripts/google_login.py` once to authorize."
        )

    creds = Credentials.from_authorized_user_file(str(token_path), list(scopes))
    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        logger.info("Refreshing Google access token.")
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
        return creds

    raise GoogleAuthError(
        "Cached Google credentials are invalid and cannot be refreshed. "
        "Delete data/token.json and re-run scripts/google_login.py."
    )


def perform_interactive_login(scopes: Iterable[str] = DEFAULT_SCOPES) -> Credentials:
    """One-time browser login. Persists the refresh token for future runs."""
    settings = get_settings()
    creds_path: Path = settings.google_credentials_file
    token_path: Path = settings.google_token_file

    if not creds_path.exists():
        raise GoogleAuthError(
            f"OAuth client credentials not found at {creds_path}.\n"
            "Download them from Google Cloud Console:\n"
            "  APIs & Services -> Credentials -> Create OAuth client ID\n"
            "  Application type: Desktop\n"
            "Save the downloaded JSON to that path (see GOOGLE_CREDENTIALS_PATH)."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), list(scopes))
    creds = flow.run_local_server(port=0, prompt="consent")

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    logger.info("Saved Google token to %s", token_path)
    return creds
