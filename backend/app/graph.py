"""LangGraph `StateGraph` for the morning brief.

Topology:

    START ─┬─► calendar ─┐
           ├─► gmail ────┼─► compose ─► deliver ─► END
           └─► youtube ──┘

The three source nodes run in parallel (LangGraph fans out automatically
when multiple edges leave the same node). Each source node catches its own
exceptions and writes a `_(section failed: …)_` placeholder so a single
flaky API never crashes the whole brief.

The graph is **pure**: it does not write to the application DB. Persistence
(the `Run` row, the `Brief` row, status transitions) lives in
`workflow.run_morning_brief()`, which invokes this graph. That separation
matters because LangGraph Studio re-invokes the graph against your real
credentials while you iterate — we don't want every Studio click to leave
a row in `runs`.

This module exposes a top-level `graph` symbol so `langgraph.json` (at the
repo root) can point at `./backend/app/graph.py:graph`.
"""

from __future__ import annotations

import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .agents.calendar_agent import summarize_today_calendar
from .agents.compose_agent import compose_brief
from .agents.gmail_agent import summarize_gmail
from .agents.reminders_agent import summarize_reminders
from .agents.youtube_agent import summarize_youtube_uploads
from .tools.telegram import send_telegram_message

logger = logging.getLogger(__name__)


class BriefState(TypedDict, total=False):
    """Shared state for the morning brief graph.

    All fields are optional (`total=False`) because LangGraph merges partial
    updates from each node into the same state dict.
    """

    calendar_md: str
    gmail_md: str
    youtube_md: str
    reminders_md: str
    body: str
    delivered_to: str | None
    error: str | None


def _safe_section(name: str, fn) -> str:
    """Run a section producer; on failure return a visible placeholder.

    Keeps a single agent's transient outage from killing the whole brief.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — we intentionally swallow here.
        logger.exception("%s section failed", name)
        return f"_(section failed: {type(exc).__name__}: {exc})_"


def calendar_node(state: BriefState) -> BriefState:
    return {"calendar_md": _safe_section("calendar", summarize_today_calendar)}


def gmail_node(state: BriefState) -> BriefState:
    return {"gmail_md": _safe_section("gmail", summarize_gmail)}


def youtube_node(state: BriefState) -> BriefState:
    return {"youtube_md": _safe_section("youtube", summarize_youtube_uploads)}


def reminders_node(state: BriefState) -> BriefState:
    return {"reminders_md": _safe_section("reminders", summarize_reminders)}


def compose_node(state: BriefState) -> BriefState:
    body = compose_brief(
        calendar_md=state.get("calendar_md", ""),
        reminders_md=state.get("reminders_md", ""),
        gmail_md=state.get("gmail_md", ""),
        youtube_md=state.get("youtube_md", ""),
    )
    return {"body": body}


def deliver_node(state: BriefState) -> BriefState:
    body = state.get("body", "")
    if not body:
        return {"delivered_to": None, "error": "compose produced empty body"}
    delivered_to = send_telegram_message(body)
    return {"delivered_to": delivered_to}


def build_graph():
    builder = StateGraph(BriefState)
    builder.add_node("calendar", calendar_node)
    builder.add_node("gmail", gmail_node)
    builder.add_node("youtube", youtube_node)
    builder.add_node("reminders", reminders_node)
    builder.add_node("compose", compose_node)
    builder.add_node("deliver", deliver_node)

    builder.add_edge(START, "calendar")
    builder.add_edge(START, "gmail")
    builder.add_edge(START, "youtube")
    builder.add_edge(START, "reminders")
    builder.add_edge("calendar", "compose")
    builder.add_edge("gmail", "compose")
    builder.add_edge("youtube", "compose")
    builder.add_edge("reminders", "compose")
    builder.add_edge("compose", "deliver")
    builder.add_edge("deliver", END)

    return builder.compile()


graph = build_graph()
