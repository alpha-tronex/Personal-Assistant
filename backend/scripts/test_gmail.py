"""Gmail bootstrap + smoke test.

Usage:
  cd backend
  python scripts/test_gmail.py

Lists the most recent inbox messages from the past 2 days and prints
sender / subject / first 200 chars of body so you can verify auth +
parsing without spending OpenAI tokens. If this works end-to-end, the
Gmail agent will work too.

If you see ``insufficient authentication scopes`` (or similar), the Gmail
scope wasn't part of the cached token. Fix:

  rm data/token.json
  python scripts/google_login.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.gmail import fetch_recent_messages  # noqa: E402
from app.tools.google_oauth import GoogleAuthError  # noqa: E402


def main() -> int:
    try:
        messages = fetch_recent_messages(max_results=10)
    except GoogleAuthError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 3

    if not messages:
        print("No inbox messages in the last 2 days.")
        return 0

    print(f"Found {len(messages)} message(s):\n")
    for i, m in enumerate(messages, start=1):
        date_str = m.date.strftime("%a %b %d %H:%M") if m.date else "—"
        body_preview = (m.body or "").replace("\n", " ").strip()[:200]
        ellipsis = "…" if len(m.body or "") > 200 else ""
        print(f"[{i}] {date_str}")
        print(f"    From:    {m.sender}")
        print(f"    Subject: {m.subject}")
        print(f"    Body:    {body_preview}{ellipsis}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
