from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.tools import youtube

NY = ZoneInfo("America/New_York")


class _Req:
    def __init__(self, result):
        self.result = result

    def execute(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeYouTube:
    """Just enough of googleapiclient's YouTube resource for fetch_new_videos."""

    def __init__(self, channels, playlist_items, search=None):
        self._channels, self._items, self._search = channels, playlist_items, search or {}

    def channels(self):
        return SimpleNamespace(list=lambda **kw: _Req(self._channels.get(kw.get("forHandle") or kw.get("id"), {})))

    def search(self):
        return SimpleNamespace(list=lambda **kw: _Req(self._search.get(kw["q"], {})))

    def playlistItems(self):  # noqa: N802 — mirrors the Google API name
        return SimpleNamespace(list=lambda **kw: _Req(self._items[kw["playlistId"]]))


def _channel(title, uploads):
    return {"items": [{"snippet": {"title": title}, "contentDetails": {"relatedPlaylists": {"uploads": uploads}}}]}


def _upload(vid, published):
    return {"snippet": {"resourceId": {"videoId": vid}, "title": f"T {vid}"},
            "contentDetails": {"videoPublishedAt": published}}


@pytest.fixture
def frozen(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 7, 8, 0, tzinfo=NY)

    monkeypatch.setattr(youtube, "datetime", FrozenDatetime)
    monkeypatch.setattr(youtube, "load_credentials", lambda: None)
    monkeypatch.setattr(youtube, "_get_transcript", lambda vid: f"transcript {vid}")


def test_fetch_keeps_only_uploads_since_yesterday_midnight_and_caps_per_channel(frozen, monkeypatch):
    items = {"items": [
        _upload("new1", "2026-10-07T11:00:00Z"),
        _upload("new2", "2026-10-06T05:00:00Z"),   # 01:00 NY yesterday → in window
        _upload("old", "2026-10-06T03:00:00Z"),    # 23:00 NY two days ago → out
        _upload("new3", "2026-10-06T20:00:00Z"),
        _upload("new4", "2026-10-06T21:00:00Z"),   # over MAX_VIDEOS_PER_CHANNEL
    ]}
    service = FakeYouTube({"@c": _channel("Chan", "UU1")}, {"UU1": items})
    monkeypatch.setattr(youtube, "build", lambda *a, **k: service)

    videos = youtube.fetch_new_videos(["@c"])

    assert sorted(v.video_id for v in videos) == ["new1", "new2", "new3"]
    assert all(v.transcript == f"transcript {v.video_id}" for v in videos)


def test_unresolvable_channels_are_skipped(frozen, monkeypatch):
    service = FakeYouTube({}, {})
    monkeypatch.setattr(youtube, "build", lambda *a, **k: service)
    assert youtube.fetch_new_videos(["@ghost"]) == []


def test_resolve_channel_falls_back_to_search_when_the_handle_lookup_misses():
    service = FakeYouTube(
        {"UCid": _channel("Found", "UUx")}, {},
        search={"fireship": {"items": [{"snippet": {"channelId": "UCid"}}]}},
    )
    assert youtube._resolve_channel(service, "@fireship") == ("Found", "UUx")


def test_get_transcript_prefers_english_and_elides_huge_transcripts(monkeypatch):
    class Track:
        def __init__(self, lang, text):
            self.language_code, self._text = lang, text

        def fetch(self):
            return [SimpleNamespace(text=self._text)]

    long_text = "x" * (youtube.TRANSCRIPT_CHAR_LIMIT + 10)
    tracks = [Track("fr", "bonjour"), Track("en-US", long_text)]
    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", lambda: SimpleNamespace(list=lambda vid: tracks))

    text = youtube._get_transcript("v")

    marker = "\n\n[…middle elided…]\n\n"
    assert marker in text and "bonjour" not in text
    assert len(text) == youtube.TRANSCRIPT_CHAR_LIMIT + len(marker)


def test_get_transcript_returns_none_when_captions_are_disabled(monkeypatch):
    def disabled(vid):
        raise RuntimeError("TranscriptsDisabled")

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", lambda: SimpleNamespace(list=disabled))
    assert youtube._get_transcript("v") is None
