"""WhatsApp reply suggestion agent.

Given an incoming WhatsApp message, uses gpt-4o-mini to draft a concise,
tone-matched reply for the user to approve, edit, or discard.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..config import get_settings

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-4o-mini"

SYSTEM_PROMPT = """\
You are a personal assistant drafting WhatsApp replies on behalf of the user.

Rules:
- Match the tone of the incoming message (casual if casual, formal if formal).
- Be concise — WhatsApp messages should feel natural, not like emails.
- Draft exactly ONE reply. No preamble, no explanation, no alternatives.
- Write as if you are the user replying directly.
- Do not make up facts, commitments, or appointments the user hasn't agreed to.
- If the message is a greeting, reply warmly and briefly.
- If a question is asked, answer it naturally or indicate you'll follow up.\
"""

USER_TEMPLATE = """\
Contact: {contact_name}
Their message: {message}

Draft a reply.\
"""


def suggest_reply(contact_name: str, message: str) -> str:
    """Return an AI-drafted reply suggestion for an incoming WhatsApp message."""
    settings = get_settings()
    if not settings.openai_api_key:
        return "(AI suggestion unavailable — OPENAI_API_KEY not set)"

    try:
        llm = ChatOpenAI(
            model=MODEL_NAME,
            api_key=settings.openai_api_key,
            temperature=0.4,
        )
        resp = llm.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=USER_TEMPLATE.format(
                        contact_name=contact_name,
                        message=message,
                    )
                ),
            ]
        )
        return (resp.content or "").strip()
    except Exception as e:  # noqa: BLE001
        logger.exception("WhatsApp suggestion failed for message from %s", contact_name)
        return f"(suggestion failed: {type(e).__name__}: {e})"
