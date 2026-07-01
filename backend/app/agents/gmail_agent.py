"""Gmail agent — bucket recent inbox messages into Action / FYI / Skim.

Pulls the last 2 days of inbox via the Gmail tool, then asks ``gpt-4o-mini``
to produce a single markdown section ready to drop into the morning brief.

Cost guardrail: each LLM call sees at most ``MESSAGES_PER_BATCH`` messages,
and we run at most ``MAX_BATCHES`` calls per run. Anything beyond that is
acknowledged with a footer instead of being silently dropped.
"""

from __future__ import annotations

import logging
from typing import Iterable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from sqlalchemy import select

from ..config import get_settings
from ..db import session_scope
from ..models import AppSetting
from ..tools.gmail import GmailMessage, fetch_recent_messages

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-4o-mini"
MESSAGES_PER_BATCH = 20
MAX_BATCHES = 2           # 40 messages summarized, anything older is noted
BODY_CHAR_BUDGET = 800    # per message — keeps total tokens predictable


SYSTEM_PROMPT = """You are a terse morning-briefing assistant. You receive a list of recent inbox emails and produce a single markdown section.

Rules:
- Bucket each email into exactly one of: **Action required**, **FYI**, **Skim**.
  - Action required: the user must reply, decide, pay, RSVP, sign, or act by a deadline.
  - FYI: substantive update from a human or a service the user cares about; no action needed.
  - Skim: newsletters, marketing, automated notifications, status digests.
- Omit a bucket entirely if it has no items.
- For each email, output one bullet of the form:
  `• *Sender* — one-line gist (parenthetical subject if it adds info)`
- Be specific. Quote dollar amounts, dates, names, deadlines verbatim.
- No preamble, no closing, no headers other than the bucket names.
- Total output must stay under ~25 lines.
"""

USER_TEMPLATE = """{count} email(s) from the last 2 days:

{rendered}

Produce the markdown section now."""


def _truncate(text: str, n: int = BODY_CHAR_BUDGET) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[:n].rstrip() + " […]"


def _render(messages: Iterable[GmailMessage]) -> str:
    chunks: list[str] = []
    for i, m in enumerate(messages, start=1):
        date_str = m.date.strftime("%a %H:%M") if m.date else "—"
        chunks.append(
            f"--- Email {i} ---\n"
            f"From: {m.sender}\n"
            f"Subject: {m.subject}\n"
            f"Date: {date_str}\n"
            f"Body:\n{_truncate(m.body)}"
        )
    return "\n\n".join(chunks)


def _llm_summarize(messages: list[GmailMessage]) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in .env")
    llm = ChatOpenAI(
        model=MODEL_NAME,
        api_key=settings.openai_api_key,
        temperature=0.2,
    )
    user_msg = USER_TEMPLATE.format(count=len(messages), rendered=_render(messages))
    resp = llm.invoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_msg)]
    )
    return (resp.content or "").strip()


def _gmail_enabled() -> bool:
    with session_scope() as s:
        row = s.get(AppSetting, "gmail_enabled")
        return (row.value if row else "true") == "true"


def summarize_gmail() -> str:
    """Return the Gmail section of the morning brief (markdown)."""
    if not _gmail_enabled():
        return ""
    try:
        messages = fetch_recent_messages()
    except Exception as e:  # noqa: BLE001
        logger.exception("Gmail fetch failed.")
        return f"📧 *EMAIL*\n_(failed to load: {e})_"

    if not messages:
        return "📧 *EMAIL*\nNo new inbox messages. ✨"

    count = len(messages)
    header = (
        f"📧 *EMAIL* (yesterday + today, "
        f"{count} message{'s' if count != 1 else ''})"
    )

    cap = MESSAGES_PER_BATCH * MAX_BATCHES
    truncated = count > cap
    work = messages[:cap] if truncated else messages

    batched_md: list[str] = []
    for start in range(0, len(work), MESSAGES_PER_BATCH):
        batch = work[start : start + MESSAGES_PER_BATCH]
        try:
            batched_md.append(_llm_summarize(batch))
        except Exception as e:  # noqa: BLE001
            logger.exception("Gmail summarizer failed for batch starting at %d", start)
            batched_md.append(f"_(batch failed: {type(e).__name__}: {e})_")

    body = "\n\n".join(b for b in batched_md if b)
    if truncated:
        body += f"\n\n_…and {count - cap} older message(s) not summarized._"
    return f"{header}\n{body}"


__all__ = ["summarize_gmail"]
