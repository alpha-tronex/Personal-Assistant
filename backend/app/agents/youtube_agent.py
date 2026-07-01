"""YouTube agent.

Channels are loaded from the youtube_channels DB table (managed via /settings).
On first boot, channels.yaml is migrated into the table automatically.
Fetches new uploads since yesterday midnight, summarises each with gpt-4o-mini
(TL;DR + 3 bullets + skip-if), and deduplicates via seen_items.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy import select

from ..config import get_settings
from ..db import session_scope
from ..models import AppSetting, SeenItem, YoutubeChannel
from ..tools.youtube import YouTubeVideo, fetch_new_videos

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-4o-mini"

SYSTEM_PROMPT = """\
You are a terse morning-briefing assistant. Summarise one YouTube video from its transcript.

Output exactly this markdown — no preamble, no extra text:
TL;DR: [one sentence]
• [key point 1]
• [key point 2]
• [key point 3]
Skip if: [one-line reason a viewer might skip this]\
"""

USER_TEMPLATE = """\
Channel: {channel}
Title: {title}

Transcript:
{transcript}

Summarise now.\
"""


def _youtube_enabled() -> bool:
    with session_scope() as s:
        row = s.get(AppSetting, "youtube_enabled")
        return (row.value if row else "true") == "true"


def _load_channels() -> list[str]:
    with session_scope() as s:
        rows = s.execute(select(YoutubeChannel)).scalars().all()
        return [r.handle for r in rows]


def _is_seen(video_id: str) -> bool:
    with session_scope() as s:
        row = s.execute(
            select(SeenItem).where(
                SeenItem.kind == "video",
                SeenItem.external_id == video_id,
            )
        ).scalar_one_or_none()
    return row is not None


def _mark_seen(video_id: str) -> None:
    with session_scope() as s:
        s.add(SeenItem(kind="video", external_id=video_id))


def _summarize_video(video: YouTubeVideo) -> str:
    """Return a markdown block for one video (with or without transcript)."""
    header = f"*{video.channel_title}* — [{video.title}]({video.url})"

    if not video.transcript:
        return f"{header}\n_(no transcript available)_"

    settings = get_settings()
    try:
        llm = ChatOpenAI(
            model=MODEL_NAME,
            api_key=settings.openai_api_key,
            temperature=0.2,
        )
        resp = llm.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=USER_TEMPLATE.format(
                        channel=video.channel_title,
                        title=video.title,
                        transcript=video.transcript,
                    )
                ),
            ]
        )
        body = (resp.content or "").strip()
    except Exception as e:  # noqa: BLE001
        logger.exception("LLM summarise failed for %s", video.video_id)
        body = f"_(summary failed: {type(e).__name__}: {e})_"

    return f"{header}\n{body}"


def summarize_youtube_uploads() -> str:
    """Return the YouTube section of the morning brief (markdown)."""
    if not _youtube_enabled():
        return ""
    channels = _load_channels()
    if not channels:
        return (
            "📺 *NEW VIDEOS*\n"
            "_(No channels configured — add handles via /settings)_"
        )

    try:
        videos = fetch_new_videos(channels)
    except Exception as e:  # noqa: BLE001
        logger.exception("YouTube fetch failed.")
        return f"📺 *NEW VIDEOS*\n_(failed to load: {e})_"

    # Drop videos already summarised in a prior run
    new_videos = [v for v in videos if not _is_seen(v.video_id)]

    if not new_videos:
        return "📺 *NEW VIDEOS*\nNo new uploads since yesterday. 📭"

    sections: list[str] = []
    for video in new_videos:
        sections.append(_summarize_video(video))
        _mark_seen(video.video_id)   # mark seen whether summary succeeded or not

    header = f"📺 *NEW VIDEOS*  ({len(new_videos)})"
    return header + "\n\n" + "\n\n".join(sections)
