from __future__ import annotations

from app import config, scheduler


def test_relative_paths_resolve_against_the_backend_root(settings):
    assert settings.resolve_path("./data/x.json") == config.BACKEND_ROOT / "data" / "x.json"
    assert str(settings.resolve_path("/abs/x.json")) == "/abs/x.json"


def test_scheduler_registers_one_daily_job_at_the_configured_local_time(monkeypatch):
    created = []

    class FakeScheduler:
        def __init__(self, timezone):
            self.timezone, self.jobs, self.running = timezone, [], False
            created.append(self)

        def add_job(self, fn, trigger, **kw):
            self.jobs.append((fn, trigger, kw))

        def start(self):
            self.running = True

        def shutdown(self, wait):
            self.running = False

    monkeypatch.setattr(scheduler, "BackgroundScheduler", FakeScheduler)
    monkeypatch.setattr(scheduler, "_scheduler", None)

    scheduler.start_scheduler()
    scheduler.start_scheduler()  # idempotent: a second call must not add a second job

    assert len(created) == 1
    (fn, trigger, kw), = created[0].jobs
    assert fn is scheduler.run_morning_brief and kw["kwargs"] == {"trigger": "schedule"}
    assert str(trigger.fields[5]) == "8" and str(trigger.fields[6]) == "0"  # hour, minute
    assert str(created[0].timezone) == "America/New_York"

    scheduler.stop_scheduler()
    assert created[0].running is False and scheduler._scheduler is None
