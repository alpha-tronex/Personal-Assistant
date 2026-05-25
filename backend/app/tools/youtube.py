"""YouTube Data API helpers.

Resolves channel handles, fetches recent uploads, and retrieves transcripts.
No LLM calls here — this is the pure data layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

from ..config import get_settings
from .google_oauth import load_credentials

logger = logging.getLogger(__name__)

# Transcript budget: ~15k tokens. Split evenly if over limit so we keep
# both the beginning and end of long videos.
TRANSCRIPT_CHAR_LIMIT = 60_000


@dataclass
class YouTubeVideo:
    video_id: str
    channel_title: str
    title: str
    published_at: datetime   # tz-aware
    url: str
    transcript: str | None   # None = captions unavailable


def _get_transcript(video_id: str) -> str | None:
    """Return cleaned transcript text, or None if captions are unavailable.

    Strategy:
    1. List all available transcripts for the video.
    2. Prefer a manual or auto-generated English transcript.
    3. Fall back to any other language — gpt-4o-mini handles multilingual input.
    """
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)

        # Collect available transcripts, prefer English
        transcripts = list(transcript_list)
        english = [t for t in transcripts if t.language_code.startswith("en")]
        chosen = (english or transcripts)
        if not chosen:
            return None

        entries = chosen[0].fetch()
        text = " ".join(e.text for e in entries).strip()
        if not text:
            return None
        if len(text) > TRANSCRIPT_CHAR_LIMIT:
            half = TRANSCRIPT_CHAR_LIMIT // 2
            text = text[:half] + "\n\n[…middle elided…]\n\n" + text[-half:]
        return text
    except Exception:  # noqa: BLE001 — TranscriptsDisabled, NoTranscriptFound, etc.
        return None


def _resolve_channel(service, handle: str) -> tuple[str, str] | None:
    """Return (channel_title, uploads_playlist_id) for a handle, or None."""
    try:
        resp = service.channels().list(
            part="snippet,contentDetails",
            forHandle=handle,   # works with or without leading @
        ).execute()
        items = resp.get("items", [])

        if not items:
            # Fallback: text search (costs a search quota unit)
            logger.info("forHandle lookup missed %s — falling back to search", handle)
            search_resp = service.search().list(
                part="snippet",
                q=handle.lstrip("@"),
                type="channel",
                maxResults=1,
            ).execute()
            search_items = search_resp.get("items", [])
            if not search_items:
                logger.warning("Could not resolve channel: %s", handle)
                return None
            channel_id = search_items[0]["snippet"]["channelId"]
            resp = service.channels().list(
                part="snippet,contentDetails",
                id=channel_id,
            ).execute()
            items = resp.get("items", [])
            if not items:
                return None

        item = items[0]
        title = item["snippet"]["title"]
        uploads_playlist = item["contentDetails"]["relatedPlaylists"]["uploads"]
        return title, uploads_playlist

    except Exception as e:  # noqa: BLE001
        logger.warning("Error resolving channel %s: %s", handle, e)
        return None


def fetch_new_videos(handles: list[str]) -> list[YouTubeVideo]:
    """Return videos published since yesterday midnight (local time).

    Results are sorted by channel title then publish time.
    """
    settings = get_settings()
    tz = ZoneInfo(settings.app_timezone)
    now = datetime.now(tz)
    since_dt = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    creds = load_credentials()
    service = build("youtube", "v3", credentials=creds, cache_discovery=False)

    all_videos: list[YouTubeVideo] = []

    for handle in handles:
        resolved = _resolve_channel(service, handle)
        if not resolved:
            continue
        channel_title, playlist_id = resolved

        try:
            resp = service.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=10,   # newest 10 uploads; filter by date below
            ).execute()
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not fetch uploads for %s: %s", handle, e)
            continue

        for item in resp.get("items", []):
            # contentDetails.videoPublishedAt is the actual publish time
            published_str = (
                item.get("contentDetails", {}).get("videoPublishedAt")
                or item.get("snippet", {}).get("publishedAt", "")
            )
            if not published_str:
                continue

            published_at = datetime.fromisoformat(
                published_str.replace("Z", "+00:00")
            ).astimezone(tz)

            if published_at < since_dt:
                continue   # older than our window — playlist is newest-first so we could break,
                           # but a simple continue is safer for edge cases

            video_id = item["snippet"]["resourceId"]["videoId"]
            title = item["snippet"].get("title", "(no title)")
            url = f"https://youtu.be/{video_id}"
            transcript = _get_transcript(video_id)

            logger.info(
                "Video: [%s] %s — transcript: %s",
                channel_title,
                title,
                f"{len(transcript)} chars" if transcript else "none",
            )

            all_videos.append(
                YouTubeVideo(
                    video_id=video_id,
                    channel_title=channel_title,
                    title=title,
                    published_at=published_at,
                    url=url,
                    transcript=transcript,
                )
            )

    all_videos.sort(key=lambda v: (v.channel_title, v.published_at))
    return all_videos
