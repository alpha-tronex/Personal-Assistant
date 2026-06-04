"""Telegram long-poll loop — handles WhatsApp reply approvals.

Runs as a daemon thread inside the FastAPI process. Supports three interaction
styles for each pending WhatsApp reply:

  Inline buttons (tap):
    ✅ Send  — forwards the AI-suggested reply to WhatsApp immediately.
    ✏️ Edit  — prompts the user to reply-to the notification with custom text.
    ❌ Skip  — dismisses the pending reply without sending.

  Reply-to-message (legacy / Edit flow):
    'ok' / 'send' / 'yes' / '✓' / '👍' / 'sure'  → send the AI suggestion.
    'skip' / 'dismiss' / 'no' / 'cancel'            → dismiss.
    Anything else                                    → send that text instead.

  /pending command:
    Lists all currently pending WhatsApp replies with a numbered preview.

Matching: Telegram inline keyboards embed pending_id in callback_data
(e.g. "wa_send:42"). Reply-to matching uses PendingReply.telegram_message_id.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

import httpx
from sqlalchemy import func, select

from .config import get_settings
from .db import session_scope
from .models import PendingReply
from .tools.telegram import (
    TelegramError,
    answer_callback_query,
    edit_message_reply_markup,
)
from .tools.whatsapp import WhatsAppBridgeError, send_whatsapp_message

logger = logging.getLogger(__name__)

_SEND_KEYWORDS = {"ok", "send", "yes", "y", "✓", "👍", "sure"}
_DISMISS_KEYWORDS = {"skip", "dismiss", "no", "n", "cancel", "ignore"}

_running = False
_thread: threading.Thread | None = None
_offset = 0


# ---------------------------------------------------------------------------
# Telegram polling (own httpx client — needs timeout > 30 s for long-poll)
# ---------------------------------------------------------------------------

def _get_updates() -> list[dict]:
    global _offset
    settings = get_settings()
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates"
    with httpx.Client(timeout=35.0) as client:
        r = client.post(url, json={
            "offset": _offset,
            "timeout": 30,
            "allowed_updates": ["message", "callback_query"],
        })
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"getUpdates failed: {data}")
    updates = data.get("result", [])
    if updates:
        _offset = updates[-1]["update_id"] + 1
    return updates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _raw_post(method: str, payload: dict) -> dict | None:
    """Fire-and-forget Telegram call used inside the poller thread."""
    settings = get_settings()
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(url, json=payload)
        data = r.json()
        if not data.get("ok"):
            logger.warning("Telegram %s failed: %s", method, data)
            return None
        return data.get("result")
    except Exception:  # noqa: BLE001
        logger.exception("Telegram %s raised an exception.", method)
        return None


def _clear_buttons(chat_id: str, message_id: int, *, status: str | None = None) -> None:
    """Remove inline keyboard from a notification and optionally append a status line."""
    if status:
        # editMessageText isn't safe without the original text, so just clear buttons
        # and let answerCallbackQuery's toast show the status.
        pass
    edit_message_reply_markup(chat_id, message_id)


def _send_text(chat_id: str, text: str) -> None:
    _raw_post("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    })


# ---------------------------------------------------------------------------
# /pending command
# ---------------------------------------------------------------------------

def _handle_pending_command(msg: dict) -> None:
    """Reply with a numbered list of all pending WhatsApp replies."""
    chat_id = str(msg["chat"]["id"])

    with session_scope() as s:
        rows = s.execute(
            select(PendingReply)
            .where(PendingReply.status == "pending")
            .order_by(PendingReply.created_at)
        ).scalars().all()

        if not rows:
            _send_text(chat_id, "✅ No pending WhatsApp replies.")
            return

        lines = [f"📋 {len(rows)} pending WhatsApp {'reply' if len(rows) == 1 else 'replies'}:\n"]
        for i, r in enumerate(rows, 1):
            preview = r.incoming_body[:80].replace("\n", " ")
            if len(r.incoming_body) > 80:
                preview += "…"
            lines.append(f"{i}. {r.contact_name}: {preview}")

        _send_text(chat_id, "\n".join(lines))


# ---------------------------------------------------------------------------
# Inline keyboard button handler
# ---------------------------------------------------------------------------

def _handle_callback_query(cq: dict) -> None:
    """Process a button tap from an inline keyboard."""
    cq_id: str = cq["id"]
    data: str = cq.get("data", "")
    msg: dict = cq.get("message") or {}
    chat_id: str | None = str(msg["chat"]["id"]) if msg.get("chat") else None
    tg_message_id: int | None = msg.get("message_id")

    # Only handle our own callback data
    if not data.startswith("wa_"):
        answer_callback_query(cq_id)
        return

    action, _, pending_id_str = data.partition(":")
    try:
        pending_id = int(pending_id_str)
    except ValueError:
        answer_callback_query(cq_id, "Invalid action.", alert=True)
        return

    with session_scope() as s:
        pending = s.get(PendingReply, pending_id)

        if not pending:
            answer_callback_query(cq_id, "Pending reply not found.", alert=True)
            return

        if pending.status != "pending":
            answer_callback_query(cq_id, f"Already {pending.status}.", alert=True)
            if chat_id and tg_message_id:
                _clear_buttons(chat_id, tg_message_id)
            return

        # ── ❌ Skip ──────────────────────────────────────────────────────────
        if action == "wa_skip":
            pending.status = "dismissed"
            logger.info("Dismissed reply to %s (#%d) via button.", pending.contact_name, pending.id)
            answer_callback_query(cq_id, "Skipped ✓")
            if chat_id and tg_message_id:
                _clear_buttons(chat_id, tg_message_id)

        # ── ✅ Send ──────────────────────────────────────────────────────────
        elif action == "wa_send":
            try:
                send_whatsapp_message(pending.wa_from, pending.suggested_reply)
                pending.status = "sent"
                pending.sent_reply = pending.suggested_reply
                pending.sent_at = datetime.utcnow()
                logger.info(
                    "Sent WA reply to %s via button (#%d): %s",
                    pending.contact_name,
                    pending.id,
                    pending.suggested_reply[:60],
                )
                answer_callback_query(cq_id, "Sent ✓")
                if chat_id and tg_message_id:
                    _clear_buttons(chat_id, tg_message_id)
            except WhatsAppBridgeError as e:
                logger.error("WA send failed for pending #%d: %s", pending.id, e)
                answer_callback_query(cq_id, "Send failed — try again.", alert=True)
                raise  # triggers session rollback → status stays "pending"

        # ── ✏️ Edit ──────────────────────────────────────────────────────────
        elif action == "wa_edit":
            # Send the suggested reply as a copyable message so the user can
            # long-press → copy → modify it, then reply to the notification.
            answer_callback_query(cq_id, "Copy the text below, edit it, then reply to the notification.")
            if chat_id:
                _send_text(
                    chat_id,
                    f"✏️ Suggested reply for {pending.contact_name} "
                    f"(copy, modify, then reply to the notification above ↑):\n\n"
                    f"{pending.suggested_reply}",
                )
            logger.debug("Edit requested for pending #%d — suggestion sent as copyable text.", pending_id)

        else:
            answer_callback_query(cq_id, "Unknown action.", alert=True)


# ---------------------------------------------------------------------------
# Reply-to-message handler (legacy + Edit flow)
# ---------------------------------------------------------------------------

def _handle_reply_message(msg: dict) -> None:
    """Process a text message that is a reply to one of our notifications."""
    text = (msg.get("text") or "").strip()
    reply_to = msg.get("reply_to_message")
    if not reply_to:
        return
    tg_msg_id: int = reply_to["message_id"]
    chat_id = str(msg["chat"]["id"])

    with session_scope() as s:
        pending = s.execute(
            select(PendingReply).where(
                PendingReply.telegram_message_id == tg_msg_id,
                PendingReply.status == "pending",
            )
        ).scalar_one_or_none()

        if not pending:
            return  # not our notification — ignore

        lower = text.lower()

        if lower in _DISMISS_KEYWORDS:
            pending.status = "dismissed"
            logger.info("Dismissed reply to %s (#%d) via text.", pending.contact_name, pending.id)
            _clear_buttons(chat_id, tg_msg_id)
            return

        reply_body = pending.suggested_reply if lower in _SEND_KEYWORDS else text

        try:
            send_whatsapp_message(pending.wa_from, reply_body)
            pending.status = "sent"
            pending.sent_reply = reply_body
            pending.sent_at = datetime.utcnow()
            logger.info(
                "Sent WA reply to %s via text (#%d): %s",
                pending.contact_name,
                pending.id,
                reply_body[:60],
            )
            _clear_buttons(chat_id, tg_msg_id)
        except WhatsAppBridgeError as e:
            logger.error("WA send failed for pending #%d: %s", pending.id, e)
            raise  # triggers session rollback → status stays "pending"


# ---------------------------------------------------------------------------
# Top-level update dispatcher
# ---------------------------------------------------------------------------

def _process_update(update: dict) -> None:
    # Button taps
    if "callback_query" in update:
        _handle_callback_query(update["callback_query"])
        return

    msg = update.get("message")
    if not msg:
        return

    text = (msg.get("text") or "").strip()
    if not text:
        return

    # /pending command (with or without @botname suffix)
    if text.startswith("/pending"):
        _handle_pending_command(msg)
        return

    # Reply-to-message approvals
    _handle_reply_message(msg)


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
            logger.exception("Telegram poll error — retrying in 5 s.")
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
