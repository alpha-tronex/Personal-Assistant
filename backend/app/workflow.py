"""Top-level orchestrator: gather sources -> compose brief -> deliver.

Steps 1-4 implementation: only Calendar is wired. Gmail and YouTube agents
will be added in later steps. Once all three are in, this will be replaced
by a proper LangGraph (parallel) graph in app/graph.py.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .agents.calendar_agent import summarize_today_calendar
from .agents.compose_agent import compose_brief
from .db import session_scope
from .models import Brief, Run
from .tools.telegram import send_telegram_message

logger = logging.getLogger(__name__)


def run_morning_brief(trigger: str = "manual") -> int:
    """Run the morning brief pipeline. Returns the Run id.

    `trigger` is one of "manual" | "schedule".
    """
    with session_scope() as s:
        run = Run(started_at=datetime.utcnow(), status="running", trigger=trigger)
        s.add(run)
        s.flush()
        run_id = run.id

    logger.info("Run %d started (trigger=%s).", run_id, trigger)
    error: str | None = None
    body = ""
    try:
        calendar_section = summarize_today_calendar()

        # Placeholders for sources we'll wire up later.
        gmail_section = "_(Gmail agent not yet wired — coming in step 5.)_"
        youtube_section = "_(YouTube agent not yet wired — coming in step 6.)_"

        body = compose_brief(
            calendar_md=calendar_section,
            gmail_md=gmail_section,
            youtube_md=youtube_section,
        )

        delivered_to = send_telegram_message(body)
        with session_scope() as s:
            s.add(Brief(run_id=run_id, body_markdown=body, delivered_to=delivered_to))
            r = s.get(Run, run_id)
            if r:
                r.status = "ok"
                r.finished_at = datetime.utcnow()
        logger.info("Run %d finished OK (delivered to %s).", run_id, delivered_to)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("Run %d failed.", run_id)
        with session_scope() as s:
            r = s.get(Run, run_id)
            if r:
                r.status = "error"
                r.error = error
                r.finished_at = datetime.utcnow()
            if body:
                s.add(Brief(run_id=run_id, body_markdown=body, delivered_to=None))
        # Best-effort: also try to ping Telegram with the error so you know.
        try:
            send_telegram_message(f"⚠️ Morning brief failed:\n```\n{error}\n```")
        except Exception:  # noqa: BLE001
            pass
    return run_id
