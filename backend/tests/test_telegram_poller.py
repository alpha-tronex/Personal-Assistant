"""Telegram approval flow: buttons, text replies, /pending — WhatsApp sends are mocked."""

from __future__ import annotations

import pytest

from app import telegram_poller as tp
from app.db import session_scope
from app.models import PendingReply
from app.tools.whatsapp import WhatsAppBridgeError


@pytest.fixture
def tg(monkeypatch):
    """Capture every outbound Telegram/WhatsApp side effect."""
    log = {"answers": [], "cleared": [], "texts": [], "wa": []}
    monkeypatch.setattr(tp, "answer_callback_query", lambda cq, text="", alert=False: log["answers"].append((text, alert)))
    monkeypatch.setattr(tp, "edit_message_reply_markup", lambda chat, mid, **kw: log["cleared"].append(mid))
    monkeypatch.setattr(tp, "_send_text", lambda chat, text: log["texts"].append(text))
    monkeypatch.setattr(tp, "send_whatsapp_message", lambda to, body: log["wa"].append((to, body)))
    return log


def _pending(status="pending", tg_id=77) -> int:
    with session_scope() as s:
        p = PendingReply(
            wa_from="1555@c.us", contact_name="Ana", wa_message_id=f"m-{tg_id}-{status}",
            incoming_body="hey", suggested_reply="hi Ana!", telegram_message_id=tg_id, status=status,
        )
        s.add(p)
        s.flush()
        return p.id


def _row(pid):
    with session_scope() as s:
        p = s.get(PendingReply, pid)
        return p.status, p.sent_reply


def _button(action, pid, message_id=77):
    return {"callback_query": {"id": "cq", "data": f"{action}:{pid}",
                               "message": {"chat": {"id": 1000}, "message_id": message_id}}}


def _text_reply(text, to_message_id=77):
    return {"message": {"chat": {"id": 1000}, "text": text, "reply_to_message": {"message_id": to_message_id}}}


# --- buttons ---------------------------------------------------------------

def test_send_button_sends_the_suggestion_and_marks_sent(tg):
    pid = _pending()
    tp._process_update(_button("wa_send", pid))
    assert tg["wa"] == [("1555@c.us", "hi Ana!")]
    assert _row(pid) == ("sent", "hi Ana!")
    assert tg["answers"] == [("Sent ✓", False)] and tg["cleared"] == [77]


def test_send_button_keeps_the_reply_pending_when_the_bridge_fails(tg, monkeypatch):
    pid = _pending()

    def bridge_down(to, body):
        raise WhatsAppBridgeError("unreachable")

    monkeypatch.setattr(tp, "send_whatsapp_message", bridge_down)
    with pytest.raises(WhatsAppBridgeError):
        tp._process_update(_button("wa_send", pid))
    assert _row(pid) == ("pending", None)
    assert tg["answers"] == [("Send failed — try again.", True)]


def test_skip_button_dismisses_without_sending(tg):
    pid = _pending()
    tp._process_update(_button("wa_skip", pid))
    assert _row(pid) == ("dismissed", None) and tg["wa"] == []


def test_edit_button_sends_the_suggestion_as_copyable_text_and_stays_pending(tg):
    pid = _pending()
    tp._process_update(_button("wa_edit", pid))
    assert "hi Ana!" in tg["texts"][0] and _row(pid) == ("pending", None)


def test_tapping_an_already_handled_reply_does_not_send_twice(tg):
    pid = _pending(status="sent")
    tp._process_update(_button("wa_send", pid))
    assert tg["wa"] == [] and tg["answers"] == [("Already sent.", True)]


@pytest.mark.parametrize("data", ["wa_send:abc", "wa_send:999", "other:1"])
def test_bad_or_foreign_callback_data_is_answered_and_ignored(tg, data):
    tp._process_update({"callback_query": {"id": "cq", "data": data, "message": {}}})
    assert tg["wa"] == [] and len(tg["answers"]) == 1


# --- text replies ----------------------------------------------------------

@pytest.mark.parametrize("word", ["ok", "Send", "👍"])
def test_send_keyword_reply_sends_the_suggestion(tg, word):
    pid = _pending()
    tp._process_update(_text_reply(word))
    assert _row(pid) == ("sent", "hi Ana!")


def test_free_text_reply_sends_the_edited_text(tg):
    pid = _pending()
    tp._process_update(_text_reply("Can't today, tomorrow?"))
    assert tg["wa"] == [("1555@c.us", "Can't today, tomorrow?")]
    assert _row(pid) == ("sent", "Can't today, tomorrow?")


def test_dismiss_keyword_reply_dismisses(tg):
    pid = _pending()
    tp._process_update(_text_reply("skip"))
    assert _row(pid) == ("dismissed", None) and tg["wa"] == []


def test_replies_to_unrelated_messages_are_ignored(tg):
    pid = _pending()
    tp._process_update(_text_reply("ok", to_message_id=12345))
    assert _row(pid) == ("pending", None) and tg["wa"] == []


# --- /pending --------------------------------------------------------------

def test_pending_command_lists_only_pending_items(tg):
    _pending(tg_id=1)
    _pending(status="sent", tg_id=2)
    tp._process_update({"message": {"chat": {"id": 1000}, "text": "/pending@mybot"}})
    assert tg["texts"][0].startswith("📋 1 pending WhatsApp reply:")


def test_pending_command_with_nothing_pending(tg):
    tp._process_update({"message": {"chat": {"id": 1000}, "text": "/pending"}})
    assert tg["texts"] == ["✅ No pending WhatsApp replies."]
