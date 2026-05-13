"""APScheduler — runs the morning brief daily at the configured local time.

In production we recommend ALSO installing the launchd job
(see launchd/com.personalassistant.morning.plist) which can wake the process
even if the FastAPI server isn't running. This in-process scheduler is the
"already running" fallback.
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
