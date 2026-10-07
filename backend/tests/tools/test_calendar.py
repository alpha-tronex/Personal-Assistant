from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.tools import calendar
from app.tools.calendar import CalendarEvent

NY = ZoneInfo("America/New_York")


def test_parse_event_dt_converts_timed_events_to_local_time():
    dt, all_day = calendar._parse_event_dt({"dateTime": "2026-10-07T14:00:00Z"}, NY)
    assert (dt.hour, all_day) == (10, False)


def test_parse_event_dt_treats_date_only_nodes_as_all_day_local_midnight():
    dt, all_day = calendar._parse_event_dt({"date": "2026-10-07"}, NY)
    assert dt == datetime(2026, 10, 7, tzinfo=NY)
    assert all_day is True


def test_parse_event_dt_rejects_unknown_shapes():
    with pytest.raises(ValueError):
        calendar._parse_event_dt({}, NY)


def test_holiday_calendars_are_detected_by_id():
    assert calendar._is_holiday_calendar({"id": "en.usa#holiday@group.v.calendar.google.com"})
    assert not calendar._is_holiday_calendar({"id": "me@gmail.com"})


def test_format_time_range():
    start = datetime(2026, 10, 7, 9, 0, tzinfo=NY)
    end = datetime(2026, 10, 7, 9, 30, tzinfo=NY)
    timed = CalendarEvent("x", start, end, False, None, [], None, None)
    all_day = CalendarEvent("x", start, end, True, None, [], None, None)
    assert timed.format_time_range() == "09:00–09:30"
    assert all_day.format_time_range() == "all day"
