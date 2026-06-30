"""Python client for the local WhatsApp bridge (Node.js / Baileys).

The bridge exposes:
  GET  /healthz  — liveness check
  POST /send     — send a WhatsApp message {to, body}

The URL defaults to http://127.0.0.1:3000 for local dev, but when the backend
runs inside Docker the bridge is on the host — set WHATSAPP_BRIDGE_URL=http://172.17.0.1:3000
in .env (172.17.0.1 is the Docker gateway / host IP).
"""

from __future__ import annotations

import logging

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)


class WhatsAppBridgeError(RuntimeError):
    pass


def send_whatsapp_message(to: str, body: str) -> None:
    """Send a WhatsApp message via the local bridge.

    Raises WhatsAppBridgeError if the bridge is unreachable or returns an error.
    """
    bridge_url = get_settings().whatsapp_bridge_url.rstrip("/")
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{bridge_url}/send", json={"to": to, "body": body})
        data = resp.json()
        if not data.get("ok"):
            raise WhatsAppBridgeError(f"Bridge send failed: {data.get('error')}")
    except httpx.TransportError as e:
        raise WhatsAppBridgeError(
            f"WhatsApp bridge unreachable at {bridge_url} — is it running? ({e})"
        ) from e


def bridge_is_healthy() -> bool:
    """Return True if the WhatsApp bridge is up and connected."""
    bridge_url = get_settings().whatsapp_bridge_url.rstrip("/")
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{bridge_url}/healthz")
        return resp.json().get("ok", False)
    except Exception:  # noqa: BLE001
        return False
