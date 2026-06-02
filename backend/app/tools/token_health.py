"""Google token age check.

Sends a Telegram warning each morning when the Google token is getting
old, so you have time to re-authenticate before the brief breaks.

Why token.json mtime?
  Every time `scripts/google_login.py` runs it overwrites token.json with
  a fresh token. The file's modification time is therefore a reliable
  proxy for "when was the last successful login".

Warning threshold: 7 days. Based on observed behaviour, the token
survives ~12 days on an unverified app with sensitive scopes, so 7 days
gives a ~5-day buffer before the brief actually fails.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..config import get_settings
from .telegram import send_telegram_message

logger = logging.getLogger(__name__)

WARNING_DAYS = 7

_WARN_MSG = """\
⚠️ Google token health warning

Your Google token is {age} day{s} old and may be revoked soon \
(typically around day 12).

Re-authenticate now to avoid a broken brief:

  cd "/Users/alphathiam/Documents/Development/GitHub/Personal Assistant/backend"
  .venv/bin/python scripts/google_login.py

You will receive this reminder each morning until the token is refreshed.\
"""


def token_age_days() -> int | None:
    """Return how many days old the token file is, or None if it doesn't exist."""
    token_path = get_settings().google_token_file
    if not token_path.exists():
        return None
    mtime = datetime.fromtimestamp(token_path.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(timezone.utc) - mtime).days


def check_and_warn_token_age() -> None:
    """Send a Telegram warning if the token is >= WARNING_DAYS old.

    Swallows all exceptions so a glitch here never breaks the brief run.
    """
    try:
        age = token_age_days()
        if age is None or age < WARNING_DAYS:
            return
        msg = _WARN_MSG.format(age=age, s="s" if age != 1 else "")
        send_telegram_message(msg)
        logger.warning("Token is %d days old — warning sent via Telegram.", age)
    except Exception:  # noqa: BLE001
        logger.exception("token_health check failed (non-fatal).")
