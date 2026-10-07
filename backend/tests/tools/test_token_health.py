from __future__ import annotations

import os
import time

import pytest

from app.tools import token_health


@pytest.fixture
def token_file(settings):
    path = settings.google_token_file
    path.write_text("{}")
    yield path
    path.unlink(missing_ok=True)


def _age(path, days: float) -> None:
    t = time.time() - days * 86400
    os.utime(path, (t, t))


def test_token_age_is_none_without_a_token_file(settings):
    settings.google_token_file.unlink(missing_ok=True)
    assert token_health.token_age_days() is None


def test_token_age_counts_whole_days_since_last_login(token_file):
    _age(token_file, 3.5)
    assert token_health.token_age_days() == 3


def test_no_warning_before_the_threshold(monkeypatch, token_file):
    sent = []
    monkeypatch.setattr(token_health, "send_telegram_message", sent.append)
    _age(token_file, token_health.WARNING_DAYS - 1)
    token_health.check_and_warn_token_age()
    assert sent == []


def test_warns_once_the_token_reaches_the_threshold(monkeypatch, token_file):
    sent = []
    monkeypatch.setattr(token_health, "send_telegram_message", sent.append)
    _age(token_file, 8.2)
    token_health.check_and_warn_token_age()
    assert len(sent) == 1 and "8 days old" in sent[0]


def test_a_failing_warning_never_breaks_the_brief(monkeypatch, token_file):
    def boom(msg):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(token_health, "send_telegram_message", boom)
    _age(token_file, 30)
    token_health.check_and_warn_token_age()  # must not raise
