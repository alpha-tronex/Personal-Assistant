from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.agents import calendar_agent
from app.tools.calendar import CalendarEvent

NY = ZoneInfo("America/New_York")


def _event(summary, start_h, start_m, end_h, end_m, **kw) -> CalendarEvent:
    return CalendarEvent(
        summary=summary,
        start=datetime(2026, 10, 7, start_h, start_m, tzinfo=NY),
        end=datetime(2026, 10, 7, end_h, end_m, tzinfo=NY),
        is_all_day=kw.get("is_all_day", False),
        location=kw.get("location"),
        attendees=kw.get("attendees", []),
        hangout_link=kw.get("hangout_link"),
        description=None,
    )


def test_empty_calendar_says_so(monkeypatch):
    monkeypatch.setattr(calendar_agent, "fetch_today_events", lambda: [])
    assert "Nothing on the calendar today" in calendar_agent.summarize_today_calendar()


def test_fetch_failure_becomes_a_visible_placeholder_not_an_exception(monkeypatch):
    def boom():
        raise RuntimeError("token revoked")

    monkeypatch.setattr(calendar_agent, "fetch_today_events", boom)
    assert "failed to load: token revoked" in calendar_agent.summarize_today_calendar()


def test_event_lines_prefer_the_meet_link_over_location_and_count_attendees():
    line = calendar_agent._format_event_line(
        _event("Sync", 9, 0, 9, 30, hangout_link="https://meet/x", location="Room 1", attendees=["a@x"])
    )
    assert line == "• 09:00–09:30 — *Sync*\n  ([Meet](https://meet/x) · 1 attendee)"


def test_back_to_back_detection_uses_the_15_minute_gap_and_ignores_all_day_events():
    events = [
        _event("Holiday", 0, 0, 23, 59, is_all_day=True),
        _event("A", 9, 0, 10, 0),
        _event("B", 10, 15, 11, 0),   # 15 min gap → back to back
        _event("C", 11, 30, 12, 0),   # 30 min gap → not
    ]
    pairs = calendar_agent._detect_back_to_back(events)
    assert [(a.summary, b.summary) for a, b in pairs] == [("A", "B")]


def test_heads_up_appears_only_with_two_or_more_back_to_back_pairs(monkeypatch):
    chain = [_event("A", 9, 0, 10, 0), _event("B", 10, 0, 11, 0), _event("C", 11, 0, 12, 0)]
    monkeypatch.setattr(calendar_agent, "fetch_today_events", lambda: chain)
    out = calendar_agent.summarize_today_calendar()
    assert out.startswith("📅 *TODAY'S CALENDAR*  (3 events)")
    assert "3 back-to-back blocks" in out
