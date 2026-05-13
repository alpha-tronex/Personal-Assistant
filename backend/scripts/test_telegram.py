"""Telegram bootstrap + smoke test.

Usage:
  cd backend
  python scripts/test_telegram.py

Steps it performs:
  1. Verifies TELEGRAM_BOT_TOKEN works (calls getMe).
  2. If TELEGRAM_CHAT_ID is missing, calls getUpdates to discover it from
     the most recent message you sent to the bot, and prints what to add
     to your .env file.
  3. Sends a test message so you can confirm delivery on your phone.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.tools.telegram import (  # noqa: E402
    TelegramError,
    _post,
    discover_chat_id,
    send_telegram_message,
)


def main() -> int:
    settings = get_settings()
    if not settings.telegram_bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set in .env", file=sys.stderr)
        return 2

    try:
        me = _post("getMe", {})
    except TelegramError as e:
        print(f"ERROR talking to Telegram: {e}", file=sys.stderr)
        return 2
    print(f"Bot OK: @{me.get('username')} (id={me.get('id')})")

    chat_id = settings.telegram_chat_id
    if not chat_id:
        print("\nNo TELEGRAM_CHAT_ID configured. Discovering from recent updates...")
        print("  (If this fails: open Telegram, send any message to your bot, then re-run.)")
        chat_id = discover_chat_id()
        if not chat_id:
            print(
                "\nNo recent messages to the bot were found. "
                "Send '/start' (or any text) to your bot in Telegram, then run this script again.",
                file=sys.stderr,
            )
            return 3
        print(f"\nDiscovered chat_id: {chat_id}")
        print("Add this line to backend/.env :\n")
        print(f"    TELEGRAM_CHAT_ID={chat_id}\n")

    print("Sending test message...")
    send_telegram_message(
        "✅ Personal Assistant test message.\n\n"
        "If you see this, your bot token + chat_id are configured correctly.",
        chat_id=chat_id,
    )
    print("Done. Check Telegram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
