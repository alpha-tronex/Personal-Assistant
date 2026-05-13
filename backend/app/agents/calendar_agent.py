"""Calendar agent.

Step 3 produces a deterministic markdown summary (no LLM call) so we can
verify Google OAuth + Telegram end-to-end first. We can swap in an LLM
flourish later if you want a more conversational tone.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from ..tools.calendar import CalendarEvent, fetch_today_events

logger = logging.getLogger(__name__)

# How tight is "back to back"?
BACK_TO_BACK_GAP = timedelta(minutes=15)


def _detect_back_to_back(events: list[CalendarEvent]) -> list[tuple[CalendarEvent, CalendarEvent]]:
    pairs: list[tuple[CalendarEvent, CalendarEvent]] = []
    timed = [e for e in events if not e.is_all_day]
    for a, b in zip(timed, timed[1:]):
        if b.start - a.end <= BACK_TO_BACK_GAP:
            pairs.append((a, b))
    return pairs


def _format_event_line(e: CalendarEvent) -> str:
    bits: list[str] = [f"• {e.format_time_range()} — *{e.summary}*"]
    extras: list[str] = []
    if e.hangout_link:
        extras.append(f"[Meet]({e.hangout_link})")
    elif e.location:
        extras.append(e.location)
    if e.attendees:
        n = len(e.attendees)
        extras.append(f"{n} attendee{'s' if n != 1 else ''}")
    if extras:
        bits.append(f"  ({' · '.join(extras)})")
    return "\n".join(bits)


def summarize_today_calendar() -> str:
    """Return a markdown section for today's calendar."""
    try:
        events = fetch_today_events()
    except Exception as e:  # noqa: BLE001
        logger.exception("Calendar fetch failed.")
        return f"📅 *TODAY'S CALENDAR*\n_(failed to load: {e})_"

    if not events:
        return "📅 *TODAY'S CALENDAR*\nNothing on the calendar today. 🎉"

    n_events = len(events)
    lines = [f"📅 *TODAY'S CALENDAR*  ({n_events} event{'s' if n_events != 1 else ''})"]
    lines.extend(_format_event_line(e) for e in events)

    b2b = _detect_back_to_back(events)
    if len(b2b) >= 2:
        lines.append(f"⚠️ Heads up: {len(b2b) + 1} back-to-back blocks today.")

    return "\n".join(lines)
