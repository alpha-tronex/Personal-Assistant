"""Reminders agent.

Reads today's due recurring reminders from the DB and produces a
🔁 REMINDERS section for the morning brief. No LLM call — purely deterministic.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import get_settings
from ..db import session_scope
from ..models import Reminder

logger = logging.getLogger(__name__)


def _ordinal(n: int) -> str:
    if 11 <= n <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def summarize_reminders() -> str:
    """Return a markdown section for today's due reminders, or '' if none."""
    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)
    now = datetime.now(tz)
    today_dow = now.strftime("%A").lower()   # "monday" … "sunday"
    today_dom = now.day                       # 1–31

    try:
        with session_scope() as s:
            all_reminders = (
                s.query(Reminder).filter(Reminder.enabled.is_(True)).all()
            )
            # Detach from session before closing
            due = []
            for r in all_reminders:
                if r.frequency == "daily":
                    due.append((r.label, r.time))
                elif r.frequency == "weekly" and r.day_of_week == today_dow:
                    due.append((r.label, r.time))
                elif r.frequency == "monthly" and r.day_of_month == today_dom:
                    due.append((r.label, r.time))
    except Exception as e:  # noqa: BLE001
        logger.exception("Reminders fetch failed.")
        return f"🔁 *REMINDERS*\n_(failed to load: {e})_"

    if not due:
        return ""

    lines = [f"🔁 *REMINDERS*  ({len(due)})"]
    for label, time in due:
        line = f"• *{label}*"
        if time:
            line += f"  _{time}_"
        lines.append(line)

    return "\n".join(lines)
