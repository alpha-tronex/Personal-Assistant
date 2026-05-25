"""Smoke test for the YouTube data layer.

Prints each new video with its transcript availability — no LLM calls,
no DB writes.

Usage:
  cd backend
  python scripts/test_youtube.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from app.config import BACKEND_ROOT
from app.tools.youtube import fetch_new_videos


def main() -> int:
    channels_file = BACKEND_ROOT / "config" / "channels.yaml"
    data = yaml.safe_load(channels_file.read_text()) or {}
    channels = [c for c in (data.get("channels") or []) if c]

    if not channels:
        print("No channels configured in config/channels.yaml")
        return 1

    print(f"Checking {len(channels)} channel(s) for new uploads...\n")
    videos = fetch_new_videos(channels)

    if not videos:
        print("No new videos since yesterday midnight.")
        return 0

    for v in videos:
        transcript_info = f"{len(v.transcript):,} chars" if v.transcript else "no transcript"
        print(f"[{v.channel_title}] {v.title}")
        print(f"  Published : {v.published_at.strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"  URL       : {v.url}")
        print(f"  Transcript: {transcript_info}")
        print()

    print(f"Total: {len(videos)} new video(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
