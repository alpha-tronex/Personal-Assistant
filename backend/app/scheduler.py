"""APScheduler — runs the morning brief daily at the configured local time.

In production (the always-on Docker container on the Hetzner box) this is the
only trigger. For local development on a Mac, the launchd job
(see launchd/com.personalassistant.morning.plist) can also fire the brief
when the FastAPI server isn't running; this scheduler then only matters if
the server happens to be up at brief time.
"""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import get_settings
from .workflow import run_morning_brief

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)
    _scheduler = BackgroundScheduler(timezone=tz)
    if settings.demo_mode:
        # The public demo never runs the real brief; it just goes back to the
        # sample data every night so visitors' edits don't pile up.
        from .demo import reset_demo_data

        _scheduler.add_job(
            reset_demo_data,
            CronTrigger(hour=3, minute=0, timezone=tz),
            id="demo_reset",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info("Scheduler started (demo): sample data resets daily @ 03:00 %s", settings.app_timezone)
        return
    _scheduler.add_job(
        run_morning_brief,
        CronTrigger(hour=settings.app_brief_hour, minute=settings.app_brief_minute, timezone=tz),
        kwargs={"trigger": "schedule"},
        id="morning_brief",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started: morning_brief @ %02d:%02d %s",
        settings.app_brief_hour,
        settings.app_brief_minute,
        settings.app_timezone,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
