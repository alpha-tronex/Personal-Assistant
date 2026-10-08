"""Public demo mode (DEMO_MODE=true) — the app with fake data and no integrations.

Runs as a separate container (demo.alphatronex.com) with its own throwaway
SQLite file and no .env, so it has no Telegram/OpenAI/Google/WhatsApp
credentials at all. In demo mode:

* no login is required, but the OAuth and WhatsApp routes and project editing
  are switched off (see DEMO_BLOCKED in app/routers/login.py);
* the Telegram poller doesn't start and the 08:00 brief isn't scheduled —
  instead the data is reset to the sample set on startup and nightly;
* "Generate a sample brief" composes a brief from canned sections and the demo
  reminders, saves it to history, and sends nothing.
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .agents.compose_agent import compose_brief
from .agents.reminders_agent import summarize_reminders
from .config import get_settings
from .db import Base, _engine, session_scope
from .models import AppSetting, Brief, Reminder, Run, YoutubeChannel

REPO_URL = "https://github.com/alpha-tronex/Personal-Assistant"

SAMPLE_REMINDERS = [
    dict(label="Stand-up notes for the platform team", frequency="daily", time="09:15"),
    dict(label="Gym — leg day", frequency="weekly", day_of_week="monday", time="18:00", time_end="19:00"),
    dict(label="Review open pull requests", frequency="weekly", day_of_week="wednesday"),
    dict(label="Pay the electricity bill", frequency="monthly", day_of_month=15),
    dict(label="Call the dentist to reschedule", frequency="weekly", day_of_week="friday", enabled=False),
]

SAMPLE_CHANNELS = [("@Fireship", True), ("@veritasium", True), ("@3blue1brown", True), ("@TechWithTim", False)]

CALENDAR_MD = """📅 *TODAY'S CALENDAR*  (4 events)
• 09:30–10:00 — *Daily stand-up*
  ([Meet](https://meet.google.com/demo) · 6 attendees)
• 10:00–11:00 — *Design review: notifications service*
  (Room 4B · 3 attendees)
• 11:00–11:30 — *1:1 with Priya*
• 15:00–16:00 — *Interview loop debrief*
⚠️ Heads up: 3 back-to-back blocks today."""

GMAIL_MD = """📧 *EMAIL* (yesterday + today, 9 messages)
**Action required**
• *Dana Kim (Recruiting)* — confirm a 45-min system-design slot by Thursday (offered Tue 2pm / Wed 11am)
• *City Utilities* — bill of $84.20 due Oct 15
**FYI**
• *GitHub* — your PR "Add retry budget to the sync worker" was approved by 2 reviewers
• *Sam Ortiz* — shared the Q4 roadmap draft; feedback welcome before Friday
**Skim**
• *Changelog Weekly*, *Product Hunt Daily*, *Medium Digest* — newsletters"""

YOUTUBE_MD = """📺 *NEW VIDEOS*  (2)

*Fireship* — [Rust in 100 seconds, revisited](https://youtube.com/@Fireship)
TL;DR: A fast tour of what changed in Rust's ergonomics this year.
• Async traits are now stable and simplify library APIs
• Compile times improved noticeably for large workspaces
• The borrow checker gives clearer suggestions
Skip if: you already follow the Rust release notes.

*3Blue1Brown* — [Why gradient descent works](https://youtube.com/@3blue1brown)
TL;DR: A visual intuition for loss landscapes and step sizes.
• Gradients point uphill; we step the other way
• Learning rate trades speed for stability
• Momentum helps across flat regions
Skip if: you've taken an optimization course."""


def is_demo() -> bool:
    return get_settings().demo_mode


def _now() -> datetime:
    return datetime.now(ZoneInfo(get_settings().app_timezone))


def sample_brief(now: datetime | None = None) -> str:
    """A full brief built from canned sections plus the demo DB's reminders."""
    return compose_brief(
        calendar_md=CALENDAR_MD,
        reminders_md=summarize_reminders(),
        gmail_md=GMAIL_MD,
        youtube_md=YOUTUBE_MD,
        now=now,
    )


def reset_demo_data(now: datetime | None = None) -> None:
    """Wipe the demo database and load the sample data set."""
    now = now or _now()
    from . import models  # noqa: F401  (register tables)

    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    with session_scope() as s:
        s.add_all(Reminder(**r) for r in SAMPLE_REMINDERS)
        s.add_all(YoutubeChannel(handle=h, enabled=e) for h, e in SAMPLE_CHANNELS)
        s.add_all([AppSetting(key="gmail_enabled", value="true"), AppSetting(key="youtube_enabled", value="true")])
        # A short, mostly-green history, like a real week of briefs.
        for days_ago, status in [(3, "ok"), (2, "ok"), (1, "error"), (0, "ok")]:
            started = (now - timedelta(days=days_ago)).replace(hour=8, minute=0, second=0, microsecond=0)
            started = started.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            run = Run(started_at=started, finished_at=started + timedelta(seconds=41), status=status, trigger="schedule")
            if status == "error":
                run.error = "TimeoutError: Gmail API did not respond (sample failure; Telegram alert was sent)"
            s.add(run)
            s.flush()
            if status == "ok":
                day = now - timedelta(days=days_ago)
                s.add(Brief(run_id=run.id, body_markdown=sample_brief(day), delivered_to="demo"))


def generate_sample_brief() -> int:
    """Record a demo run + brief (nothing is sent anywhere). Returns the run id."""
    started = datetime.utcnow()
    with session_scope() as s:
        run = Run(started_at=started, finished_at=started, status="ok", trigger="manual")
        s.add(run)
        s.flush()
        s.add(Brief(run_id=run.id, body_markdown=sample_brief(), delivered_to="demo (not sent)"))
        return run.id


_BANNER = """<div style="background:#1c2a3d;color:#cfe3ff;font:14px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
padding:.7rem 1rem;display:flex;flex-wrap:wrap;gap:.5rem 1rem;align-items:center;border-bottom:1px solid #2b4466">
<span><strong>Demo</strong> with sample data — resets nightly. The real assistant runs at 08:00 and delivers to Telegram.</span>
<form method="post" action="/demo/brief" style="margin:0"><button style="background:#0a84ff;color:#fff;border:0;border-radius:8px;
padding:.4rem .75rem;font:inherit;cursor:pointer">Generate a sample brief</button></form>
<a href="/history" style="color:#8ec5ff">Brief history (JSON)</a>
<a href="/docs" style="color:#8ec5ff">API docs</a>
<a href="{repo}" style="color:#8ec5ff">Source on GitHub</a>
</div>"""


def with_banner(page: str) -> str:
    """Insert the demo banner right after <body> (no-op outside demo mode)."""
    if not is_demo():
        return page
    return page.replace("<body>", "<body>" + _BANNER.format(repo=html.escape(REPO_URL)), 1)
