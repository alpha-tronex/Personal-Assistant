from __future__ import annotations

import json

import httpx
import pytest

from app.tools import whatsapp


def _mock_client(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(
        whatsapp.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )


def test_send_posts_to_the_bridge_send_endpoint(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    _mock_client(monkeypatch, handler)
    whatsapp.send_whatsapp_message("1555@c.us", "hello")
    assert seen == {"url": "http://bridge.test:3000/send", "body": {"to": "1555@c.us", "body": "hello"}}


def test_send_raises_when_the_bridge_reports_failure(monkeypatch):
    _mock_client(monkeypatch, lambda r: httpx.Response(500, json={"ok": False, "error": "not connected"}))
    with pytest.raises(whatsapp.WhatsAppBridgeError, match="not connected"):
        whatsapp.send_whatsapp_message("x", "y")


def test_send_raises_a_bridge_error_when_the_bridge_is_unreachable(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    _mock_client(monkeypatch, handler)
    with pytest.raises(whatsapp.WhatsAppBridgeError, match="unreachable"):
        whatsapp.send_whatsapp_message("x", "y")


@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (lambda r: httpx.Response(200, json={"ok": True, "connected": True}), True),
        (lambda r: httpx.Response(200, json={"ok": False}), False),
        (lambda r: httpx.Response(200, text="not json"), False),
    ],
)
def test_bridge_is_healthy(monkeypatch, handler, expected):
    _mock_client(monkeypatch, handler)
    assert whatsapp.bridge_is_healthy() is expected
