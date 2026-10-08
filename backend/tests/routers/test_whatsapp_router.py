from __future__ import annotations

import pytest

from app.db import session_scope
from app.models import PendingReply
from app.routers import whatsapp as wa


@pytest.fixture
def notify(monkeypatch):
    sent = []
    monkeypatch.setattr(wa, "suggest_reply", lambda name, body: f"reply to {name}")

    def fake_notify(**kw):
        sent.append(kw)
        return 555

    monkeypatch.setattr(wa, "send_wa_notification", fake_notify)
    return sent


def _incoming(message_id="m1", body="hey there"):
    return {"wa_from": "1555@c.us", "contact_name": "Ana", "body": body, "timestamp": 1, "message_id": message_id}


def _pending():
    with session_scope() as s:
        return [(p.wa_message_id, p.suggested_reply, p.telegram_message_id, p.status) for p in s.query(PendingReply)]


def test_incoming_dm_creates_a_pending_reply_and_notifies_telegram(client, notify):
    r = client.post("/whatsapp/incoming", json=_incoming())
    assert r.status_code == 202
    assert _pending() == [("m1", "reply to Ana", 555, "pending")]
    assert notify[0]["pending_id"] and (notify[0]["position"], notify[0]["total"]) == (1, 1)


def test_duplicate_deliveries_from_the_bridge_are_ignored(client, notify):
    client.post("/whatsapp/incoming", json=_incoming())
    client.post("/whatsapp/incoming", json=_incoming())
    assert len(_pending()) == 1 and len(notify) == 1


def test_queue_position_counts_other_pending_replies(client, notify):
    client.post("/whatsapp/incoming", json=_incoming("m1"))
    client.post("/whatsapp/incoming", json=_incoming("m2"))
    assert (notify[1]["position"], notify[1]["total"]) == (2, 2)


def test_telegram_failure_still_keeps_the_pending_reply(client, monkeypatch):
    monkeypatch.setattr(wa, "suggest_reply", lambda n, b: "s")

    def down(**kw):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(wa, "send_wa_notification", down)
    client.post("/whatsapp/incoming", json=_incoming())
    assert _pending() == [("m1", "s", None, "pending")]


def test_silence_alert_forwards_to_telegram(client, monkeypatch):
    sent = []
    monkeypatch.setattr(wa, "send_telegram_message", sent.append)
    r = client.post("/whatsapp/silence-alert", json={"silent_for_hours": 6.5})
    assert r.status_code == 202 and "6.5 hours" in sent[0]


def test_disconnected_alert_tells_you_messages_are_not_arriving(client, monkeypatch):
    sent = []
    monkeypatch.setattr(wa, "send_telegram_message", sent.append)
    r = client.post("/whatsapp/disconnected-alert", json={"disconnected_for_minutes": 12})
    assert r.status_code == 202
    assert "disconnected for 12 min" in sent[0] and "aren't reaching Telegram" in sent[0]


def test_recovered_notice(client, monkeypatch):
    sent = []
    monkeypatch.setattr(wa, "send_telegram_message", sent.append)
    client.post("/whatsapp/disconnected-alert", json={"disconnected_for_minutes": 40, "recovered": True})
    assert sent == ["✅ WhatsApp bridge reconnected after about 40 min. New messages are flowing again."]


def test_disconnected_alert_survives_telegram_being_down(client, monkeypatch):
    from app.tools.telegram import TelegramError

    def down(text):
        raise TelegramError("down")

    monkeypatch.setattr(wa, "send_telegram_message", down)
    assert client.post("/whatsapp/disconnected-alert", json={"disconnected_for_minutes": 15}).status_code == 202
