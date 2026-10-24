"""Keep the Telegram bot token out of the logs.

The token is part of every Bot API URL (https://api.telegram.org/bot<token>/<method>), so it
leaks wherever a URL is logged: httpx logs each request at INFO, and httpx errors such as
HTTPStatusError carry the URL in their message and in tracebacks.
"""

from __future__ import annotations

import logging
import re

# A bot token is "<bot id>:<secret>". No \b: in a URL it directly follows "bot".
_TOKEN = re.compile(r"(?<!\d)\d{6,}:[A-Za-z0-9_-]{30,}")


def redact(text: str) -> str:
    return _TOKEN.sub("<redacted-bot-token>", text)


class RedactingFormatter(logging.Formatter):
    """Redacts the fully formatted record, so messages, arguments and tracebacks are all covered."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(level: str | int) -> None:
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    for handler in logging.getLogger().handlers:
        handler.setFormatter(RedactingFormatter(handler.formatter._fmt if handler.formatter else None))
    # Per-request lines add nothing but the URL; keep their warnings and errors.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
