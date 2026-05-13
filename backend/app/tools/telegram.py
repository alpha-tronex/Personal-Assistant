"""Telegram Bot API client.

We use the raw HTTP API via httpx to keep dependencies light. Markdown is
sent as MarkdownV2 with conservative escaping; if formatting fails Telegram
will return 400 — we fall back to plain text in that case.

Rate limit: a single Telegram message body is capped at 4096 chars. We split
on paragraph boundaries when the brief is longer than that.
"""

from __future__ import annotations

import logging
from typing import Iterable

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import get_settings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_MESSAGE_CHARS = 4000  # < 4096 to leave headroom for the chunk header


class TelegramError(RuntimeError):
    pass


# MarkdownV2 special chars that must be backslash-escaped *outside* of
# entities. We are conservative and escape the punctuation Telegram cares
# about while leaving asterisks/underscores/backticks (used for formatting).
_MD_ESCAPE = str.maketrans({c: f"\\{c}" for c in r"[]()~>#+-=|{}.!"})


def _md_escape(text: str) -> str:
    return text.translate(_MD_ESCAPE)


def _chunk(text: str, n: int = MAX_MESSAGE_CHARS) -> Iterable[str]:
    if len(text) <= n:
        yield text
        return
    # Split on blank lines first so we don't cut formatting in half.
    buf = ""
    for paragraph in text.split("\n\n"):
        candidate = (buf + "\n\n" + paragraph).strip() if buf else paragraph
        if len(candidate) > n and buf:
            yield buf
            buf = paragraph
        else:
            buf = candidate
    if buf:
        yield buf


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=8),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
)
def _post(method: str, payload: dict) -> dict:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise TelegramError("TELEGRAM_BOT_TOKEN is not set in .env")
    url = f"{TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/{method}"
    with httpx.Client(timeout=15.0) as client:
        r = client.post(url, json=payload)
    if r.status_code >= 500:
        r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise TelegramError(f"Telegram {method} failed: {data}")
    return data["result"]


def send_telegram_message(body_markdown: str, *, chat_id: str | None = None) -> str:
    """Send a (possibly long) markdown message. Returns the chat_id used."""
    settings = get_settings()
    target = chat_id or settings.telegram_chat_id
    if not target:
        raise TelegramError(
            "TELEGRAM_CHAT_ID is not set. Run `python scripts/test_telegram.py` once "
            "to discover and save it."
        )

    chunks = list(_chunk(body_markdown))
    for i, chunk in enumerate(chunks, start=1):
        prefix = f"({i}/{len(chunks)}) " if len(chunks) > 1 else ""
        text = _md_escape(prefix + chunk)
        try:
            _post(
                "sendMessage",
                {
                    "chat_id": target,
                    "text": text,
                    "parse_mode": "MarkdownV2",
                    "disable_web_page_preview": True,
                },
            )
        except TelegramError as e:
            logger.warning("MarkdownV2 send failed (%s); falling back to plain text.", e)
            _post(
                "sendMessage",
                {
                    "chat_id": target,
                    "text": prefix + chunk,
                    "disable_web_page_preview": True,
                },
            )
    return target


def discover_chat_id() -> str | None:
    """Inspect getUpdates and return the chat_id of the most recent inbound DM.

    The user must send at least one message to the bot first; otherwise
    Telegram returns an empty update list and we have nothing to discover.
    """
    updates = _post("getUpdates", {"timeout": 0, "limit": 50})
    if not isinstance(updates, list):
        return None
    for update in reversed(updates):
        msg = update.get("message") or update.get("channel_post") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id:
            return str(chat_id)
    return None
