"""Python client for the local WhatsApp bridge (Node.js / whatsapp-web.js).

The bridge runs on http://127.0.0.1:3000 and exposes:
  GET  /healthz  — liveness check
  POST /send     — send a WhatsApp message {to, body}
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

BRIDGE_URL = "http://127.0.0.1:3000"


class WhatsAppBridgeError(RuntimeError):
    pass


def send_whatsapp_message(to: str, body: str) -> None:
    """Send a WhatsApp message via the local bridge.

    Raises WhatsAppBridgeError if the bridge is unreachable or returns an error.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{BRIDGE_URL}/send", json={"to": to, "body": body})
        data = resp.json()
        if not data.get("ok"):
            raise WhatsAppBridgeError(f"Bridge send failed: {data.get('error')}")
    except httpx.TransportError as e:
        raise WhatsAppBridgeError(
            f"WhatsApp bridge unreachable at {BRIDGE_URL} — is it running? ({e})"
        ) from e


def bridge_is_healthy() -> bool:
    """Return True if the WhatsApp bridge is up and connected."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{BRIDGE_URL}/healthz")
        return resp.json().get("ok", False)
    except Exception:  # noqa: BLE001
        return False
