"""Public demo mode: sample data, no login, integrations and risky routes off."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app import demo, main, scheduler
from app.db import session_scope
from app.models import Brief, Reminder, Run, YoutubeChannel

NOW = datetime(2026, 10, 7, 9, 0, tzinfo=ZoneInfo("America/New_York"))


@pytest.fixture
def demo_on(settings, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)

    def must_not_send(*a, **kw):
        raise AssertionError("the demo tried to send a Telegram message")

    # Belt and braces on top of the socket guard: nothing may reach Telegram.
    for mod in ("app.workflow", "app.graph", "app.routers.whatsapp"):
        monkeypatch.setattr(f"{mod}.send_telegram_message", must_not_send)
    demo.reset_demo_data(now=NOW)


@pytest.fixture
def visitor(anon_client, demo_on):
    """A demo visitor: no session cookie."""
    return anon_client


def _counts():
    with session_scope() as s:
        return {
            "reminders": s.query(Reminder).count(),
            "channels": s.query(YoutubeChannel).count(),
            "runs": s.query(Run).count(),
            "briefs": s.query(Brief).count(),
        }


def test_reset_loads_the_sample_set_with_a_realistic_history(demo_on):
    assert _counts() == {"reminders": 5, "channels": 4, "runs": 4, "briefs": 3}
    with session_scope() as s:
        statuses = [r.status for r in s.query(Run).order_by(Run.started_at)]
        headers = [b.body_markdown.splitlines()[0] for b in s.query(Brief).order_by(Brief.run_id)]
    assert statuses == ["ok", "ok", "error", "ok"]
    assert headers == [  # each sample brief is dated its own day
        "🌅 *Morning Brief — Sun, Oct 4*",
        "🌅 *Morning Brief — Mon, Oct 5*",
        "🌅 *Morning Brief — Wed, Oct 7*",
    ]


def test_reset_throws_away_visitor_changes(visitor):
    visitor.post("/reminders", json={"label": "graffiti", "frequency": "daily"})
    visitor.delete("/channels/1")
    demo.reset_demo_data(now=NOW)
    assert _counts()["reminders"] == 5 and _counts()["channels"] == 4


def test_visitors_need_no_login_and_see_the_banner(visitor):
    page = visitor.get("/settings", headers={"accept": "text/html"})
    assert page.status_code == 200
    assert "Demo</strong> with sample data" in page.text
    assert 'href="/logout"' not in page.text
    assert visitor.get("/reminders").status_code == 200
    assert "Demo</strong>" in visitor.get("/projects").text


def test_sample_brief_button_saves_a_brief_and_shows_it(visitor):
    r = visitor.post("/demo/brief", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/history/")
    page = visitor.get(r.headers["location"])
    assert "Design review: notifications service" in page.text
    assert "Demo</strong>" in page.text
    with session_scope() as s:
        assert s.query(Brief).order_by(Brief.id.desc()).first().delivered_to == "demo (not sent)"


def test_run_now_in_the_demo_never_starts_the_real_pipeline(visitor, monkeypatch):
    def real_brief(trigger):
        raise AssertionError("demo ran the real brief")

    monkeypatch.setattr(main, "run_morning_brief", real_brief)
    r = visitor.post("/run-now")
    assert r.json()["status"] == "done" and "nothing sent" in r.json()["message"]


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/reauth?secret=x"), ("GET", "/reauth/callback?code=c&state=s"),
     ("POST", "/whatsapp/incoming"), ("POST", "/whatsapp/silence-alert"),
     ("POST", "/whatsapp/disconnected-alert"),
     ("PATCH", "/projects/FAIS")],
)
def test_credential_bridge_and_project_edit_routes_are_off(visitor, method, path):
    r = visitor.request(method, path, json={})
    assert r.status_code == 404 and r.json() == {"detail": "Not available in the demo"}


def test_project_commit_refresh_still_works_in_the_demo(visitor, monkeypatch):
    from app.routers import projects

    projects._commit_cache.clear()
    monkeypatch.setattr(projects, "_fetch_latest_commit", lambda repo: None)
    r = visitor.get("/projects/FAIS/commits")  # FAIS is in the committed projects.yaml
    assert r.status_code == 200 and r.json()["commits"][0]["error"] is True


def test_demo_brief_route_does_not_exist_outside_the_demo(client):
    assert client.post("/demo/brief").status_code == 404
    assert "Demo</strong>" not in client.get("/settings").text


def test_demo_startup_seeds_data_and_skips_the_telegram_poller(settings, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    started = []
    monkeypatch.setattr(main, "start_scheduler", lambda: started.append("scheduler"))
    monkeypatch.setattr(main, "start_poller", lambda: started.append("poller"))

    main.start_background_jobs()

    assert started == ["scheduler"]
    assert _counts()["reminders"] == 5


def test_production_startup_starts_both_jobs(monkeypatch):
    started = []
    monkeypatch.setattr(main, "start_scheduler", lambda: started.append("scheduler"))
    monkeypatch.setattr(main, "start_poller", lambda: started.append("poller"))
    main.start_background_jobs()
    assert started == ["scheduler", "poller"]


def test_demo_scheduler_only_registers_the_nightly_reset(settings, monkeypatch):
    jobs = []

    class FakeScheduler:
        def __init__(self, timezone):
            pass

        def add_job(self, fn, trigger, **kw):
            jobs.append((fn, kw["id"], str(trigger.fields[5])))

        def start(self):
            pass

        def shutdown(self, wait):
            pass

    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(scheduler, "BackgroundScheduler", FakeScheduler)
    monkeypatch.setattr(scheduler, "_scheduler", None)
    scheduler.start_scheduler()
    assert jobs == [(demo.reset_demo_data, "demo_reset", "3")]
    scheduler.stop_scheduler()
