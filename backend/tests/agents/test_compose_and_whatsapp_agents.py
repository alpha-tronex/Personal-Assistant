from __future__ import annotations

from datetime import datetime

from app.agents import compose_agent, whatsapp_agent


def test_compose_orders_sections_and_omits_empty_reminders(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 7, 8, 0, tzinfo=tz)

    monkeypatch.setattr(compose_agent, "datetime", FrozenDatetime)
    body = compose_agent.compose_brief(calendar_md="CAL", reminders_md="", gmail_md="MAIL", youtube_md="YT")
    assert body == "🌅 *Morning Brief — Wed, Oct 7*\n\nCAL\n\nMAIL\n\nYT"


def test_compose_includes_reminders_after_the_calendar():
    body = compose_agent.compose_brief(calendar_md="CAL", reminders_md="REM", gmail_md="MAIL", youtube_md="YT")
    assert body.split("\n\n")[1:] == ["CAL", "REM", "MAIL", "YT"]


def test_whatsapp_suggestion_degrades_gracefully_without_an_openai_key():
    assert "OPENAI_API_KEY not set" in whatsapp_agent.suggest_reply("Ana", "hi")
