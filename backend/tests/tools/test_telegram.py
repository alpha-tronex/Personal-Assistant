from __future__ import annotations

import json

import httpx
import pytest

from app.tools import telegram


def _mock_client(monkeypatch, handler):
    """Route telegram._post's httpx.Client through an in-memory transport."""
    real_client = httpx.Client
    monkeypatch.setattr(
        telegram.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )


def test_md_escape_escapes_markdownv2_punctuation_but_keeps_formatting_chars():
    assert telegram._md_escape("a.b!(c)") == r"a\.b\!\(c\)"
    assert telegram._md_escape("*bold* _it_ `code`") == "*bold* _it_ `code`"


def test_chunk_returns_short_text_unchanged():
    assert list(telegram._chunk("hello", n=10)) == ["hello"]


def test_chunk_splits_on_paragraph_boundaries_without_exceeding_the_limit():
    text = "\n\n".join(["a" * 40, "b" * 40, "c" * 40])
    chunks = list(telegram._chunk(text, n=90))
    assert chunks == ["a" * 40 + "\n\n" + "b" * 40, "c" * 40]
    assert all(len(c) <= 90 for c in chunks)


def test_post_sends_to_the_bot_url_and_returns_result(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    _mock_client(monkeypatch, handler)
    assert telegram._post("sendMessage", {"chat_id": "1"}) == {"message_id": 7}
    assert seen["url"] == "https://api.telegram.org/bottest-token/sendMessage"
    assert seen["body"] == {"chat_id": "1"}


def test_post_raises_telegram_error_when_api_says_not_ok(monkeypatch):
    _mock_client(monkeypatch, lambda r: httpx.Response(400, json={"ok": False, "description": "bad"}))
    with pytest.raises(telegram.TelegramError):
        telegram._post("sendMessage", {})


def test_post_refuses_to_run_without_a_bot_token(monkeypatch, settings):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    with pytest.raises(telegram.TelegramError, match="TELEGRAM_BOT_TOKEN"):
        telegram._post("sendMessage", {})


def test_send_telegram_message_falls_back_to_plain_text_when_markdown_is_rejected(monkeypatch):
    calls = []

    def fake_post(method, payload):
        calls.append(payload)
        if payload.get("parse_mode") == "MarkdownV2":
            raise telegram.TelegramError("can't parse entities")
        return {}

    monkeypatch.setattr(telegram, "_post", fake_post)
    assert telegram.send_telegram_message("hi.") == "1000"
    assert [c.get("parse_mode") for c in calls] == ["MarkdownV2", None]
    assert calls[1]["text"] == "hi."  # unescaped in the fallback


def test_send_telegram_message_numbers_chunks_when_the_brief_is_long(monkeypatch):
    texts = []
    monkeypatch.setattr(telegram, "_post", lambda m, p: texts.append(p["text"]) or {})
    telegram.send_telegram_message("\n\n".join(["x" * 3000] * 3))
    assert [t.split(" ")[0] for t in texts] == [r"\(1/3\)", r"\(2/3\)", r"\(3/3\)"]


def test_send_telegram_message_requires_a_chat_id(monkeypatch, settings):
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    with pytest.raises(telegram.TelegramError, match="TELEGRAM_CHAT_ID"):
        telegram.send_telegram_message("hi")


def test_send_wa_notification_returns_message_id_and_wires_buttons_to_the_pending_id(monkeypatch):
    sent = {}

    def fake_post(method, payload):
        sent.update(payload)
        return {"message_id": 42}

    monkeypatch.setattr(telegram, "_post", fake_post)
    msg_id = telegram.send_wa_notification(
        "Ana", "hey", "hi Ana!", pending_id=5, position=2, total=3
    )
    assert msg_id == 42
    assert "(2/3) WhatsApp from Ana" in sent["text"]
    buttons = [b["callback_data"] for b in sent["reply_markup"]["inline_keyboard"][0]]
    assert buttons == ["wa_send:5", "wa_edit:5", "wa_skip:5"]
    assert "parse_mode" not in sent  # plain text: arbitrary WA content can't break MarkdownV2


def test_answer_callback_query_swallows_telegram_errors(monkeypatch):
    def boom(method, payload):
        raise telegram.TelegramError("expired")

    monkeypatch.setattr(telegram, "_post", boom)
    telegram.answer_callback_query("cq1", "ok")  # must not raise
