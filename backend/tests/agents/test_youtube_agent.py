from __future__ import annotations

from datetime import datetime, timezone

from app.agents import youtube_agent
from app.db import session_scope
from app.models import AppSetting, SeenItem, YoutubeChannel
from app.tools.youtube import YouTubeVideo


def _video(vid: str, transcript: str | None = "words") -> YouTubeVideo:
    return YouTubeVideo(
        video_id=vid, channel_title="Chan", title=f"Video {vid}",
        published_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
        url=f"https://youtu.be/{vid}", transcript=transcript,
    )


def _channels(*handles: str, paused: tuple[str, ...] = ()):
    with session_scope() as s:
        for h in handles:
            s.add(YoutubeChannel(handle=h, enabled=h not in paused))


def test_disabled_flag_skips_youtube(monkeypatch):
    with session_scope() as s:
        s.add(AppSetting(key="youtube_enabled", value="false"))
    assert youtube_agent.summarize_youtube_uploads() == ""


def test_no_channels_points_the_user_at_settings():
    assert "add handles via /settings" in youtube_agent.summarize_youtube_uploads()


def test_paused_channels_are_not_fetched(monkeypatch):
    _channels("@live", "@paused", paused=("@paused",))
    fetched = []
    monkeypatch.setattr(youtube_agent, "fetch_new_videos", lambda handles: fetched.extend(handles) or [])
    youtube_agent.summarize_youtube_uploads()
    assert fetched == ["@live"]


def test_already_seen_videos_are_dropped_and_new_ones_marked_seen(monkeypatch):
    _channels("@c")
    with session_scope() as s:
        s.add(SeenItem(kind="video", external_id="old"))
    monkeypatch.setattr(youtube_agent, "fetch_new_videos", lambda h: [_video("old"), _video("new")])
    monkeypatch.setattr(youtube_agent, "_summarize_video", lambda v: f"summary {v.video_id}")

    out = youtube_agent.summarize_youtube_uploads()

    assert out == "📺 *NEW VIDEOS*  (1)\n\nsummary new"
    assert youtube_agent._is_seen("new")


def test_nothing_new_since_yesterday(monkeypatch):
    _channels("@c")
    monkeypatch.setattr(youtube_agent, "fetch_new_videos", lambda h: [])
    assert "No new uploads since yesterday" in youtube_agent.summarize_youtube_uploads()


def test_fetch_failure_becomes_a_placeholder(monkeypatch):
    _channels("@c")

    def boom(handles):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(youtube_agent, "fetch_new_videos", boom)
    assert "failed to load: quota exceeded" in youtube_agent.summarize_youtube_uploads()


def test_videos_without_transcripts_skip_the_llm():
    out = youtube_agent._summarize_video(_video("v", transcript=None))
    assert out == "*Chan* — [Video v](https://youtu.be/v)\n_(no transcript available)_"
