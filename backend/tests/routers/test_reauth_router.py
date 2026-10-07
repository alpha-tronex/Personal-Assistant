from __future__ import annotations

import base64
import hashlib

from app.routers import reauth


def test_reauth_rejects_a_wrong_secret(client):
    assert client.get("/reauth", params={"secret": "guess"}).status_code == 403


def test_reauth_requires_a_configured_secret(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "reauth_secret", "")
    assert client.get("/reauth", params={"secret": ""}).status_code == 500


def test_reauth_without_web_credentials_explains_what_is_missing(client, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "google_web_credentials_path", str(tmp_path / "missing.json"))
    r = client.get("/reauth", params={"secret": "test-reauth-secret"})
    assert r.status_code == 500 and "Web credentials not found" in r.text


def test_callback_with_unknown_state_is_rejected(client):
    assert client.get("/reauth/callback", params={"code": "c", "state": "forged"}).status_code == 400


def test_pkce_challenge_is_the_s256_of_the_verifier():
    verifier, challenge = reauth._generate_pkce()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected and len(verifier) >= 43


def test_expired_states_are_purged(monkeypatch):
    reauth._pending.clear()
    reauth._pending["old"] = {"ts": 0}
    reauth._pending["new"] = {"ts": 9e12}
    reauth._purge_expired()
    assert list(reauth._pending) == ["new"]
    reauth._pending.clear()
