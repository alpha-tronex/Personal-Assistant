"""Compose the final brief.

Currently a deterministic concatenation. In step 7+ this can become an LLM
node that reads all three sections and produces a more cohesive narrative.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import get_settings


def compose_brief(*, calendar_md: str, gmail_md: str, youtube_md: str) -> str:
    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)
    today = datetime.now(tz).strftime("%a, %b %-d")
    header = f"🌅 *Morning Brief — {today}*"
    return "\n\n".join([header, calendar_md, gmail_md, youtube_md])
