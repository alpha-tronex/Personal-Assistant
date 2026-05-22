"""Gmail fetch helpers.

Lists messages in the user's inbox over a recent window (default: last
2 days), parses headers + plain-text bodies, and applies light cleanups
so the downstream LLM prompt is cheap and clean:

  * Skip self-sent mail (your own address as ``From``).
  * Skip promotional / marketing mail. Two layered filters:
      1. Gmail-side: the search query excludes ``category:promotions``
         by default (see ``GMAIL_QUERY`` in ``.env``).
      2. Local: any sender whose address contains a substring listed
         in ``GMAIL_IGNORE_FROM`` is dropped after fetch — handy for
         promo mail that slipped into the Primary tab.
  * Strip ``"On ... wrote:"`` quoted-reply tails.
  * Strip ``>``-prefixed quote lines.
  * Fall back to the API snippet when the message has no plain-text part.

Read-only — uses the ``gmail.readonly`` scope already granted by the
shared ``google_oauth`` helper.
"""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime
from functools import lru_cache
from typing import Any, Iterable

from googleapiclient.discovery import build

from ..config import get_settings
from .google_oauth import load_credentials

logger = logging.getLogger(__name__)

# Cap on messages pulled from the API in one call.
MAX_LIST_RESULTS = 50

# "On Wed, May 10, 2026 at 09:14 Alice <a@b.com> wrote:" — start of the quoted reply.
_QUOTED_REPLY_RE = re.compile(r"\n*On .{0,200}?wrote:\s*\n", re.DOTALL)
# Lines that begin with ">" are quoted text from a prior message.
_QUOTED_LINE_RE = re.compile(r"^\s*>.*$", re.MULTILINE)


@dataclass
class GmailMessage:
    """A normalized inbox message ready for prompt rendering."""

    id: str
    thread_id: str
    sender: str          # Raw "From" header (display name + email).
    sender_email: str    # Parsed email-only, lowercased.
    subject: str
    date: datetime | None  # tz-aware if parseable; None otherwise.
    snippet: str         # Short API-provided summary.
    body: str            # Cleaned plain-text body (or snippet fallback).


# ---------- internal helpers ----------


def _decode_body(data: str) -> str:
    """Gmail base64url-encodes message bodies; decode tolerantly."""
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _extract_plain_text(payload: dict[str, Any]) -> str:
    """Walk the MIME tree and return the first ``text/plain`` part."""
    mime = payload.get("mimeType", "")
    body = payload.get("body", {}) or {}
    if mime == "text/plain" and body.get("data"):
        return _decode_body(body["data"])
    for part in payload.get("parts", []) or []:
        text = _extract_plain_text(part)
        if text:
            return text
    return ""


def _strip_quoted_reply(text: str) -> str:
    """Remove ``On ... wrote:`` tails and any ``>`` quote lines."""
    if not text:
        return ""
    m = _QUOTED_REPLY_RE.search(text)
    if m:
        text = text[: m.start()]
    text = _QUOTED_LINE_RE.sub("", text)
    # Collapse 3+ blank lines into 2.
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _header(headers: list[dict[str, str]], name: str) -> str:
    target = name.lower()
    for h in headers:
        if h.get("name", "").lower() == target:
            return h.get("value", "") or ""
    return ""


@lru_cache(maxsize=1)
def _self_email() -> str:
    """Resolve the authenticated user's own Gmail address (cached)."""
    creds = load_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    return (profile.get("emailAddress") or "").lower()


# ---------- public API ----------


def _parse_ignore_list(raw: str) -> list[str]:
    """Comma-separated -> lowercased, trimmed substrings (empties dropped)."""
    return [s.strip().lower() for s in (raw or "").split(",") if s.strip()]


def fetch_recent_messages(
    query: str | None = None,
    *,
    max_results: int = MAX_LIST_RESULTS,
    skip_self: bool = True,
    ignore_from: Iterable[str] | None = None,
) -> list[GmailMessage]:
    """Return parsed inbox messages matching ``query``.

    Newest first, capped at ``max_results``. Two filters apply by default:

    * Messages whose ``From`` matches the authenticated user's own address
      are skipped (controlled by ``skip_self``).
    * Messages whose sender address contains any substring in
      ``ignore_from`` are skipped (defaults to ``GMAIL_IGNORE_FROM`` from
      ``.env``).

    When ``query`` is ``None``, ``GMAIL_QUERY`` from ``.env`` is used —
    which excludes ``category:promotions`` out of the box.
    """
    settings = get_settings()
    effective_query = query if query is not None else settings.gmail_query
    ignore_patterns = (
        list(ignore_from)
        if ignore_from is not None
        else _parse_ignore_list(settings.gmail_ignore_from)
    )

    creds = load_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    logger.info(
        "Listing Gmail messages: q=%r maxResults=%d ignore_from=%s",
        effective_query,
        max_results,
        ignore_patterns or "[]",
    )
    resp = (
        service.users()
        .messages()
        .list(userId="me", q=effective_query, maxResults=max_results)
        .execute()
    )

    ids = [m["id"] for m in resp.get("messages", [])]
    if not ids:
        return []

    self_email = _self_email() if skip_self else ""

    out: list[GmailMessage] = []
    for mid in ids:
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=mid, format="full")
                .execute()
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Skipping message %s: %s", mid, e)
            continue

        payload = msg.get("payload", {}) or {}
        headers = payload.get("headers", []) or []
        sender = _header(headers, "From")
        sender_email = parseaddr(sender)[1].lower()

        if skip_self and self_email and sender_email == self_email:
            continue

        if ignore_patterns and any(p in sender_email for p in ignore_patterns):
            logger.debug("Skipping %s (matches ignore_from)", sender_email)
            continue

        date_raw = _header(headers, "Date")
        try:
            date = parsedate_to_datetime(date_raw) if date_raw else None
        except (TypeError, ValueError):
            date = None

        body = _strip_quoted_reply(_extract_plain_text(payload))
        if not body:
            body = (msg.get("snippet") or "").strip()

        out.append(
            GmailMessage(
                id=mid,
                thread_id=msg.get("threadId", ""),
                sender=sender,
                sender_email=sender_email,
                subject=_header(headers, "Subject") or "(no subject)",
                date=date,
                snippet=msg.get("snippet", "") or "",
                body=body,
            )
        )

    logger.info("Fetched %d Gmail message(s) (after self-skip)", len(out))
    return out


__all__ = ["GmailMessage", "fetch_recent_messages"]
