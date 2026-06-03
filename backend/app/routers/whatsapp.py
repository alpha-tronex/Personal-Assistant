"""FastAPI router — WhatsApp incoming message handler.

The Node.js bridge POSTs here whenever a new DM arrives. We:
  1. Deduplicate on wa_message_id.
  2. Generate an AI reply suggestion.
  3. Persist a PendingReply row.
  4. Send a Telegram notification with the suggestion.
  5. Store the Telegram message_id so the poller can match the user's approval.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import func, select

from ..agents.whatsapp_agent import suggest_reply
from ..db import session_scope
from ..models import PendingReply
from ..tools.telegram import send_wa_notification

logger = logging.getLogger(__name__)
router = APIRouter()


class WAIncoming(BaseModel):
    wa_from: str
    contact_name: str
    body: str
    timestamp: int
    message_id: str


@router.post("/whatsapp/incoming", status_code=202)
def whatsapp_incoming(payload: WAIncoming, background_tasks: BackgroundTasks):
    """Receive a new WhatsApp DM from the Node.js bridge."""
    background_tasks.add_task(_process, payload)
    return {"status": "queued"}


def _process(payload: WAIncoming) -> None:
    # --- Deduplicate ---
    with session_scope() as s:
        exists = s.execute(
            select(PendingReply).where(PendingReply.wa_message_id == payload.message_id)
        ).scalar_one_or_none()
    if exists:
        logger.debug("Duplicate WA message %s — skipped.", payload.message_id)
        return

    logger.info("Processing WA message from %s: %s", payload.contact_name, payload.body[:60])

    # --- Generate suggestion ---
    suggestion = suggest_reply(payload.contact_name, payload.body)

    # --- Persist pending reply ---
    with session_scope() as s:
        pending = PendingReply(
            wa_from=payload.wa_from,
            contact_name=payload.contact_name,
            wa_message_id=payload.message_id,
            incoming_body=payload.body,
            suggested_reply=suggestion,
            status="pending",
            created_at=datetime.utcnow(),
        )
        s.add(pending)
        s.flush()
        pending_id = pending.id
        # Count pending (including this new row) for the queue label
        total_pending: int = s.execute(
            select(func.count()).select_from(PendingReply).where(PendingReply.status == "pending")
        ).scalar() or 1
        position: int = s.execute(
            select(func.count()).select_from(PendingReply).where(
                PendingReply.status == "pending",
                PendingReply.id <= pending_id,
            )
        ).scalar() or 1

    # --- Notify via Telegram ---
    try:
        tg_msg_id = send_wa_notification(
            contact_name=payload.contact_name,
            incoming_body=payload.body,
            suggested_reply=suggestion,
            pending_id=pending_id,
            position=position,
            total=total_pending,
        )
        # Store the Telegram message_id for reply matching
        with session_scope() as s:
            row = s.get(PendingReply, pending_id)
            if row:
                row.telegram_message_id = tg_msg_id
        logger.info(
            "Notified via Telegram (msg_id=%d) for pending reply #%d",
            tg_msg_id,
            pending_id,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to send Telegram notification for pending reply #%d: %s", pending_id, e)
