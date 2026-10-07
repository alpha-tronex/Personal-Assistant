from __future__ import annotations

from datetime import datetime, timezone

from app.agents import gmail_agent
from app.db import session_scope
from app.models import AppSetting
from app.tools.gmail import GmailMessage


def _msg(i: int, body: str = "hello") -> GmailMessage:
    return GmailMessage(
        id=str(i), thread_id=str(i), sender=f"S{i} <s{i}@x.com>", sender_email=f"s{i}@x.com",
        subject=f"Subject {i}", date=datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc),
        snippet="", body=body,
    )


def test_disabled_flag_skips_gmail_entirely(monkeypatch):
    with session_scope() as s:
        s.add(AppSetting(key="gmail_enabled", value="false"))

    def must_not_fetch():
        raise AssertionError("fetched Gmail while disabled")

    monkeypatch.setattr(gmail_agent, "fetch_recent_messages", must_not_fetch)
    assert gmail_agent.summarize_gmail() == ""


def test_empty_inbox(monkeypatch):
    monkeypatch.setattr(gmail_agent, "fetch_recent_messages", lambda: [])
    assert "No new inbox messages" in gmail_agent.summarize_gmail()


def test_messages_are_summarized_in_batches_and_overflow_is_acknowledged(monkeypatch):
    batches = []
    monkeypatch.setattr(gmail_agent, "fetch_recent_messages", lambda: [_msg(i) for i in range(45)])
    monkeypatch.setattr(gmail_agent, "_llm_summarize", lambda b: batches.append(len(b)) or f"batch of {len(b)}")
    out = gmail_agent.summarize_gmail()
    assert batches == [20, 20]
    assert out.startswith("📧 *EMAIL* (yesterday + today, 45 messages)")
    assert out.endswith("_…and 5 older message(s) not summarized._")


def test_a_failed_batch_is_reported_inline_and_the_other_batch_still_ships(monkeypatch):
    calls = iter([RuntimeError("rate limited"), "second ok"])

    def flaky(batch):
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(gmail_agent, "fetch_recent_messages", lambda: [_msg(i) for i in range(25)])
    monkeypatch.setattr(gmail_agent, "_llm_summarize", flaky)
    out = gmail_agent.summarize_gmail()
    assert "_(batch failed: RuntimeError: rate limited)_" in out
    assert "second ok" in out


def test_long_bodies_are_truncated_to_the_char_budget():
    out = gmail_agent._truncate("x" * 1000)
    assert out == "x" * gmail_agent.BODY_CHAR_BUDGET + " […]"


def test_llm_summarize_refuses_without_an_openai_key():
    try:
        gmail_agent._llm_summarize([_msg(1)])
    except RuntimeError as e:
        assert "OPENAI_API_KEY" in str(e)
    else:
        raise AssertionError("expected RuntimeError")
