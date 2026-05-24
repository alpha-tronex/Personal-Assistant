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


def _is_holiday_calendar(cal: dict) -> bool:
    """Return True for read-only holiday group calendars we want to skip."""
    cal_id: str = cal.get("id", "")
    return "holiday@group.v.calendar.google.com" in cal_id


def _fetch_events_for_calendar(
    service,
    calendar_id: str,
    time_min: str,
    time_max: str,
    tz: ZoneInfo,
) -> list[CalendarEvent]:
    """Fetch and parse events from a single calendar."""
    resp = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
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


def fetch_today_events() -> list[CalendarEvent]:
    """Return today's events merged from all personal calendars (local time).

    Holiday group calendars are skipped automatically. Events are sorted by
    start time across all calendars.
    """
    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)

    creds = load_credentials()
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now_local = datetime.now(tz)
    day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    time_min = day_start.isoformat()
    time_max = day_end.isoformat()

    # Collect all calendars, skip holiday group calendars
    cal_list = service.calendarList().list().execute()
    calendars = [c for c in cal_list.get("items", []) if not _is_holiday_calendar(c)]

    logger.info(
        "Fetching events %s -> %s across %d calendar(s): %s",
        time_min,
        time_max,
        len(calendars),
        [c.get("summary", c["id"]) for c in calendars],
    )

    all_events: list[CalendarEvent] = []
    for cal in calendars:
        try:
            events = _fetch_events_for_calendar(service, cal["id"], time_min, time_max, tz)
            all_events.extend(events)
        except Exception as e:  # noqa: BLE001
            logger.warning("Skipping calendar %s: %s", cal.get("summary", cal["id"]), e)

    # Sort merged results by start time (all-day events sort to top via midnight)
    all_events.sort(key=lambda e: e.start)
    return all_events
