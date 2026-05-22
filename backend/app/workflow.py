"""Top-level orchestrator: open a Run row, invoke the graph, persist the Brief.

The actual fetch → compose → deliver pipeline lives in `app/graph.py` as a
LangGraph `StateGraph`. This module is intentionally thin: its only jobs
are persistence (the `Run` and `Brief` rows) and surfacing failures via
the Telegram fallback ping.

Keeping persistence outside the graph lets LangGraph Studio re-invoke the
graph against real credentials during development without polluting the
`runs` table on every click.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .db import session_scope
from .graph import graph
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
    delivered_to: str | None = None
    try:
        result = graph.invoke({})
        body = result.get("body", "")
        delivered_to = result.get("delivered_to")
        graph_error = result.get("error")
        if graph_error and not delivered_to:
            # The deliver node short-circuited (e.g. empty body). Treat as a
            # run-level failure so the Telegram fallback fires below.
            raise RuntimeError(graph_error)

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
                # Save whatever we composed even if delivery failed — useful
                # for the /history view.
                s.add(Brief(run_id=run_id, body_markdown=body, delivered_to=None))
        try:
            send_telegram_message(f"⚠️ Morning brief failed:\n```\n{error}\n```")
        except Exception:  # noqa: BLE001
            pass
    return run_id
