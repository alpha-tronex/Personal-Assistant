from __future__ import annotations

import pytest

from app.tools import google_oauth


class FakeCreds:
    def __init__(self, valid=False, expired=False, refresh_token=None):
        self.valid, self.expired, self.refresh_token = valid, expired, refresh_token
        self.refreshed = False

    def refresh(self, request):
        self.refreshed = True
        self.valid = True

    def to_json(self):
        return '{"refreshed": true}'


@pytest.fixture
def token(settings):
    path = settings.google_token_file
    path.write_text("{}")
    yield path
    path.unlink(missing_ok=True)


def _use(monkeypatch, creds):
    monkeypatch.setattr(
        google_oauth.Credentials, "from_authorized_user_file", classmethod(lambda cls, p, s: creds)
    )


def test_missing_token_tells_you_to_log_in(settings):
    settings.google_token_file.unlink(missing_ok=True)
    with pytest.raises(google_oauth.GoogleAuthError, match="google_login.py"):
        google_oauth.load_credentials()


def test_valid_token_is_returned_as_is(monkeypatch, token):
    creds = FakeCreds(valid=True)
    _use(monkeypatch, creds)
    assert google_oauth.load_credentials() is creds and not creds.refreshed


def test_expired_token_is_refreshed_and_saved(monkeypatch, token):
    creds = FakeCreds(expired=True, refresh_token="r")
    _use(monkeypatch, creds)
    monkeypatch.setattr(google_oauth, "Request", lambda: None)
    google_oauth.load_credentials()
    assert creds.refreshed and token.read_text() == '{"refreshed": true}'


def test_unrefreshable_token_raises(monkeypatch, token):
    _use(monkeypatch, FakeCreds(expired=True, refresh_token=None))
    with pytest.raises(google_oauth.GoogleAuthError, match="cannot be refreshed"):
        google_oauth.load_credentials()


def test_calendar_scope_is_read_write_for_reminders():
    assert "https://www.googleapis.com/auth/calendar" in google_oauth.DEFAULT_SCOPES
