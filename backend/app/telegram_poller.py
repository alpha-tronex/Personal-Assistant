"""Telegram long-poll loop — handles WhatsApp reply approvals.

Runs as a daemon thread inside the FastAPI process. On each update:
  - If the user replies 'ok'/'send' to a notification message → send the
    AI suggestion via WhatsApp.
  - If the user replies with custom text → send that text instead.
  - If the user replies 'skip'/'dismiss' → dismiss the pending reply.

Matching logic: Telegram lets users reply-to a specific message. We store
the Telegram message_id in PendingReply.telegram_message_id. When a reply
arrives, we look up the pending record by that id.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

import httpx

from .config import get_settings
from .db import session_scope
from .models import PendingReply
from .tools.whatsapp import WhatsAppBridgeError, send_whatsapp_message

logger = logging.getLogger(__name__)

_SEND_KEYWORDS = {"ok", "send", "yes", "y", "✓", "👍", "sure"}
_DISMISS_KEYWORDS = {"skip", "dismiss", "no", "n", "cancel", "ignore"}

_running = False
_thread: threading.Thread | None = None
_offset = 0


# ---------------------------------------------------------------------------
# Telegram polling (own httpx client — needs timeout > 30s for long-poll)
# ---------------------------------------------------------------------------

def _get_updates() -> list[dict]:
    global _offset
    settings = get_settings()
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates"
    with httpx.Client(timeout=35.0) as client:
        r = client.post(url, json={
            "offset": _offset,
            "timeout": 30,
            "allowed_updates": ["message"],
        })
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"getUpdates failed: {data}")
    updates = data.get("result", [])
    if updates:
        _offset = updates[-1]["update_id"] + 1
    return updates


# ---------------------------------------------------------------------------
# Update processing
# ---------------------------------------------------------------------------

def _process_update(update: dict) -> None:
    msg = update.get("message")
    if not msg:
        return

    text = (msg.get("text") or "").strip()
    if not text:
        return

    # Only handle messages that are replies to another message
    reply_to = msg.get("reply_to_message")
    if not reply_to:
        return
    tg_msg_id: int = reply_to["message_id"]

    with session_scope() as s:
        pending = s.execute(
            __import__("sqlalchemy", fromlist=["select"])
            .select(PendingReply)
            .where(
                PendingReply.telegram_message_id == tg_msg_id,
                PendingReply.status == "pending",
            )
        ).scalar_one_or_none()

        if not pending:
            return  # not our notification, ignore

        lower = text.lower()

        if lower in _DISMISS_KEYWORDS:
            pending.status = "dismissed"
            logger.info("Dismissed reply to %s (#%d)", pending.contact_name, pending.id)
            return   # session commits "dismissed"

        reply_body = pending.suggested_reply if lower in _SEND_KEYWORDS else text

        try:
            send_whatsapp_message(pending.wa_from, reply_body)
            pending.status = "sent"
            pending.sent_reply = reply_body
            pending.sent_at = datetime.utcnow()
            logger.info(
                "Sent WhatsApp reply to %s: %s",
                pending.contact_name,
                reply_body[:60],
            )
        except WhatsAppBridgeError as e:
            logger.error("WhatsApp send failed for pending #%d: %s", pending.id, e)
            # Leave status as "pending" so the user can retry
            raise   # causes session rollback — status stays "pending"


# ---------------------------------------------------------------------------
# Thread lifecycle
# ---------------------------------------------------------------------------

def _poll_loop() -> None:
    logger.info("Telegram approval poller started.")
    while _running:
        try:
            updates = _get_updates()
            for update in updates:
                try:
                    _process_update(update)
                except Exception:  # noqa: BLE001
                    logger.exception("Error processing Telegram update %s", update.get("update_id"))
        except Exception:  # noqa: BLE001
            logger.exception("Telegram poll error — retrying in 5s.")
            time.sleep(5)
    logger.info("Telegram approval poller stopped.")


def start_poller() -> None:
    global _running, _thread
    _running = True
    _thread = threading.Thread(target=_poll_loop, name="telegram-poller", daemon=True)
    _thread.start()


def stop_poller() -> None:
    global _running
    _running = False
