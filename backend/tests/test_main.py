"""HTTP API in app/main.py — reminders, flags, channels, history, seeding."""

from __future__ import annotations

import pytest

from app import main
from app.db import session_scope
from app.models import AppSetting, Brief, Run, YoutubeChannel


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.json()["version"] == "dev"  # CD smoke test compares this to the pushed SHA


def test_root_redirects_to_settings(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/settings"


def test_settings_portal_renders(client):
    r = client.get("/settings")
    assert r.status_code == 200 and "<html" in r.text.lower()


def test_run_now_schedules_the_brief_in_the_background(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "run_morning_brief", lambda trigger: calls.append(trigger))
    assert client.post("/run-now").json()["status"] == "scheduled"
    assert calls == ["manual"]


# --- reminders -------------------------------------------------------------

def test_reminder_crud_round_trip(client):
    created = client.post("/reminders", json={"label": "Gym", "frequency": "weekly", "day_of_week": "monday"})
    assert created.status_code == 201
    rid = created.json()["id"]

    assert [r["label"] for r in client.get("/reminders").json()] == ["Gym"]
    assert client.patch(f"/reminders/{rid}", json={"enabled": False}).json()["enabled"] is False
    assert client.delete(f"/reminders/{rid}").status_code == 204
    assert client.get("/reminders").json() == []


def test_reminder_rejects_unknown_frequency(client):
    assert client.post("/reminders", json={"label": "x", "frequency": "hourly"}).status_code == 422


@pytest.mark.parametrize(("method", "kwargs"), [("patch", {"json": {"enabled": True}}), ("delete", {})])
def test_missing_reminder_is_404(client, method, kwargs):
    assert getattr(client, method)("/reminders/999", **kwargs).status_code == 404


# --- feature flags ---------------------------------------------------------

def test_flags_default_to_enabled_and_can_be_toggled(client):
    assert client.get("/settings/flags").json() == {"gmail_enabled": True, "youtube_enabled": True}
    client.patch("/settings/flags/gmail_enabled", json={"value": False})
    assert client.get("/settings/flags").json()["gmail_enabled"] is False
    with session_scope() as s:
        assert s.get(AppSetting, "gmail_enabled").value == "false"


def test_unknown_flag_is_rejected(client):
    assert client.patch("/settings/flags/evil", json={"value": True}).status_code == 422


# --- youtube channels ------------------------------------------------------

def test_channel_add_pause_and_delete(client):
    cid = client.post("/channels", json={"handle": "  @fireship "}).json()["id"]
    assert client.get("/channels").json()[0]["handle"] == "@fireship"
    assert client.patch(f"/channels/{cid}", json={"enabled": False}).json()["enabled"] is False
    assert client.get("/channels").json()[0]["enabled"] is False
    assert client.delete(f"/channels/{cid}").status_code == 204


def test_duplicate_and_blank_channels_are_rejected(client):
    client.post("/channels", json={"handle": "@a"})
    assert client.post("/channels", json={"handle": "@a"}).status_code == 409
    assert client.post("/channels", json={"handle": "   "}).status_code == 422


def test_missing_channel_is_404(client):
    assert client.patch("/channels/999", json={"enabled": True}).status_code == 404


# --- history ---------------------------------------------------------------

def test_history_lists_runs_and_shows_one_brief(client):
    with session_scope() as s:
        run = Run(status="ok", trigger="schedule")
        s.add(run)
        s.flush()
        s.add(Brief(run_id=run.id, body_markdown="hello brief"))
        rid = run.id

    assert [r["status"] for r in client.get("/history").json()] == ["ok"]
    page = client.get(f"/history/{rid}")
    assert page.status_code == 200 and "hello brief" in page.text
    assert client.get("/history/999").status_code == 404


# --- first-boot seeding ----------------------------------------------------

def test_seed_defaults_creates_flags_and_migrates_channels_yaml_once(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "channels.yaml").write_text("channels:\n  - '@one'\n  - ' '\n  - '@two'\n")
    monkeypatch.setattr(main, "BACKEND_ROOT", tmp_path)

    main._seed_defaults()
    main._seed_defaults()  # second boot must not duplicate anything

    with session_scope() as s:
        assert sorted(c.handle for c in s.query(YoutubeChannel)) == ["@one", "@two"]
        assert {a.key: a.value for a in s.query(AppSetting)} == {"gmail_enabled": "true", "youtube_enabled": "true"}


def test_seed_defaults_keeps_existing_flag_values():
    with session_scope() as s:
        s.add(AppSetting(key="gmail_enabled", value="false"))
    main._seed_defaults()
    with session_scope() as s:
        assert s.get(AppSetting, "gmail_enabled").value == "false"


def test_history_page_escapes_brief_content(client):
    """Brief bodies quote incoming email text, so it must not render as HTML."""
    with session_scope() as s:
        run = Run(status="ok", trigger="manual")
        s.add(run)
        s.flush()
        s.add(Brief(run_id=run.id, body_markdown="<script>alert(1)</script>"))
        rid = run.id
    page = client.get(f"/history/{rid}").text
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
