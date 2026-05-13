"""Google Calendar fetch helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from ..config import get_settings
from .google_oauth import load_credentials

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    summary: str
    start: datetime  # tz-aware
    end: datetime  # tz-aware
    is_all_day: bool
    location: str | None
    attendees: list[str]
    hangout_link: str | None
    description: str | None

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def format_time_range(self) -> str:
        if self.is_all_day:
            return "all day"
        return f"{self.start.strftime('%H:%M')}–{self.end.strftime('%H:%M')}"


def _parse_event_dt(node: dict[str, Any], tz: ZoneInfo) -> tuple[datetime, bool]:
    """Parse a Google Calendar event start/end node into (dt, is_all_day)."""
    if "dateTime" in node:
        # ISO 8601 with offset
        return datetime.fromisoformat(node["dateTime"].replace("Z", "+00:00")).astimezone(tz), False
    if "date" in node:
        return datetime.combine(datetime.fromisoformat(node["date"]).date(), time(0, 0), tz), True
    raise ValueError(f"Unrecognized event time node: {node}")


def fetch_today_events(calendar_id: str = "primary") -> list[CalendarEvent]:
    """Return events on the user's primary calendar for today (local time)."""
    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)

    creds = load_credentials()
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now_local = datetime.now(tz)
    day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    logger.info(
        "Fetching calendar events %s -> %s (%s)",
        day_start.isoformat(),
        day_end.isoformat(),
        settings.app_timezone,
    )

    resp = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=day_start.isoformat(),
            timeMax=day_end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        )
        .execute()
    )

    events: list[CalendarEvent] = []
    for item in resp.get("items", []):
        try:
            start_dt, is_all_day = _parse_event_dt(item["start"], tz)
            end_dt, _ = _parse_event_dt(item["end"], tz)
        except (KeyError, ValueError) as e:
            logger.warning("Skipping event %s: %s", item.get("id"), e)
            continue

        attendees = [
            a.get("email") for a in item.get("attendees", []) if a.get("email") and not a.get("self")
        ]
        events.append(
            CalendarEvent(
                summary=item.get("summary", "(no title)"),
                start=start_dt,
                end=end_dt,
                is_all_day=is_all_day,
                location=item.get("location"),
                attendees=[a for a in attendees if a],
                hangout_link=item.get("hangoutLink"),
                description=item.get("description"),
            )
        )
    return events
