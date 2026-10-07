from __future__ import annotations

import base64

from app.tools import gmail


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_decode_body_tolerates_missing_padding():
    assert gmail._decode_body(_b64("héllo")) == "héllo"


def test_extract_plain_text_walks_multipart_trees():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<b>hi</b>")}},
            {"mimeType": "multipart/mixed", "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("plain hi")}},
            ]},
        ],
    }
    assert gmail._extract_plain_text(payload) == "plain hi"


def test_extract_plain_text_returns_empty_when_there_is_no_plain_part():
    assert gmail._extract_plain_text({"mimeType": "text/html", "body": {"data": _b64("x")}}) == ""


def test_strip_quoted_reply_drops_the_on_wrote_tail_and_quote_lines():
    text = "Sounds good.\n> earlier line\nThanks\n\nOn Wed, May 10, 2026 at 09:14 Al <a@b.com> wrote:\n> old"
    assert gmail._strip_quoted_reply(text) == "Sounds good.\n\nThanks"


def test_header_lookup_is_case_insensitive():
    headers = [{"name": "From", "value": "Ana <ana@x.com>"}]
    assert gmail._header(headers, "from") == "Ana <ana@x.com>"
    assert gmail._header(headers, "Subject") == ""


def test_parse_ignore_list_lowercases_trims_and_drops_empties():
    assert gmail._parse_ignore_list(" No-Reply@, ,@Substack.com ") == ["no-reply@", "@substack.com"]
    assert gmail._parse_ignore_list("") == []
