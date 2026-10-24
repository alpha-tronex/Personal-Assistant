"""app/log_redaction.py — the Telegram bot token never reaches a log line."""

from __future__ import annotations

import logging

import httpx

from app.log_redaction import RedactingFormatter, configure_logging, redact

FAKE_TOKEN = "1234567890:AAFakeTokenFakeTokenFakeTokenFake123"
URL = f"https://api.telegram.org/bot{FAKE_TOKEN}/getUpdates"


def _format(msg, *args, exc_info=None):
    record = logging.LogRecord("t", logging.WARNING, __file__, 1, msg, args, exc_info)
    return RedactingFormatter("%(message)s").format(record)


def test_redact_removes_token_from_url():
    out = redact(f'HTTP Request: POST {URL} "HTTP/1.1 200 OK"')
    assert FAKE_TOKEN not in out and "bot<redacted-bot-token>/getUpdates" in out


def test_formatter_redacts_arguments():
    assert FAKE_TOKEN not in _format("send failed: %s", URL)


def test_formatter_redacts_httpx_error_tracebacks():
    request = httpx.Request("POST", URL)
    try:
        httpx.Response(401, request=request).raise_for_status()
    except httpx.HTTPStatusError as e:
        assert FAKE_TOKEN in str(e)  # why the redaction is needed
        out = _format("Telegram call raised: %s", e, exc_info=(type(e), e, e.__traceback__))
    assert FAKE_TOKEN not in out


def test_configure_logging_quiets_httpx_request_lines():
    configure_logging("INFO")
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
    assert logging.getLogger("httpx").isEnabledFor(logging.WARNING)
