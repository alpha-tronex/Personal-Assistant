from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agents import reminders_agent
from app.db import session_scope
from app.models import Reminder

# Wednesday 7 Oct 2026, 08:00 New York.
FROZEN = datetime(2026, 10, 7, 8, 0, tzinfo=ZoneInfo("America/New_York"))


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN.astimezone(tz) if tz else FROZEN

    monkeypatch.setattr(reminders_agent, "datetime", FrozenDatetime)


def _add(**kw):
    with session_scope() as s:
        s.add(Reminder(**kw))


def test_no_due_reminders_returns_empty_so_the_section_is_omitted():
    _add(label="Rent", frequency="monthly", day_of_month=1)
    assert reminders_agent.summarize_reminders() == ""


def test_daily_weekly_and_monthly_reminders_are_due_on_the_right_day():
    _add(label="Meds", frequency="daily", time="08:00")
    _add(label="Gym", frequency="weekly", day_of_week="wednesday", time="18:00", time_end="19:00")
    _add(label="Trash", frequency="weekly", day_of_week="thursday")
    _add(label="Invoice", frequency="monthly", day_of_month=7)
    out = reminders_agent.summarize_reminders()
    assert out.splitlines() == [
        "🔁 *REMINDERS*  (3)",
        "• *Meds*  _08:00_",
        "• *Gym*  _18:00–19:00_",
        "• *Invoice*",
    ]


def test_disabled_reminders_are_skipped():
    _add(label="Meds", frequency="daily", enabled=False)
    assert reminders_agent.summarize_reminders() == ""


@pytest.mark.parametrize(("n", "suffix"), [(1, "st"), (2, "nd"), (3, "rd"), (4, "th"), (11, "th"), (12, "th"), (13, "th"), (21, "st"), (22, "nd")])
def test_ordinal(n, suffix):
    assert reminders_agent._ordinal(n) == suffix
