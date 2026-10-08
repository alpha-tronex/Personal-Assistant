from __future__ import annotations

import pytest

from app import auth

HASH = auth.hash_password("s3cret-passphrase", iterations=1_000)


def test_password_round_trip_and_rejection():
    assert auth.verify_password("s3cret-passphrase", HASH)
    assert not auth.verify_password("wrong", HASH)


def test_hashes_are_salted_and_have_no_dollar_signs_for_env_files():
    other = auth.hash_password("s3cret-passphrase", iterations=1_000)
    assert other != HASH
    assert "$" not in HASH and HASH.startswith("pbkdf2_sha256:1000:")


@pytest.mark.parametrize("bad", ["", "garbage", "md5:1:a:b", "pbkdf2_sha256:notanint:a:b"])
def test_malformed_hashes_never_verify(bad):
    assert not auth.verify_password("anything", bad)


def test_session_token_valid_until_expiry():
    token = auth.make_session_token("k", HASH, now=1_000)
    assert auth.verify_session_token(token, "k", HASH, now=1_000 + auth.SESSION_TTL_SECONDS - 1)
    assert not auth.verify_session_token(token, "k", HASH, now=1_000 + auth.SESSION_TTL_SECONDS + 1)


def test_session_token_is_bound_to_the_secret_and_the_password():
    token = auth.make_session_token("k", HASH, now=0)
    assert not auth.verify_session_token(token, "other-secret", HASH, now=1)
    new_hash = auth.hash_password("new-passphrase", iterations=1_000)
    assert not auth.verify_session_token(token, "k", new_hash, now=1)  # password change logs everyone out


@pytest.mark.parametrize("token", [None, "", "abc", "9999999999.forged", "9999999999"])
def test_forged_or_malformed_tokens_are_rejected(token):
    assert not auth.verify_session_token(token, "k", HASH, now=0)


def test_no_configured_secret_means_no_valid_session():
    token = auth.make_session_token("", HASH, now=0)
    assert not auth.verify_session_token(token, "", HASH, now=1)


@pytest.mark.parametrize(
    ("target", "expected"),
    [("/projects", "/projects"), ("/history/3?x=1", "/history/3?x=1"), (None, "/settings"),
     ("https://evil.com", "/settings"), ("//evil.com", "/settings"), ("/\\evil.com", "/settings")],
)
def test_safe_next_blocks_open_redirects(target, expected):
    assert auth.safe_next(target) == expected


def test_public_paths():
    assert auth.is_public("/healthz") and auth.is_public("/whatsapp/incoming")
    assert not auth.is_public("/settings") and not auth.is_public("/healthz/x")
    assert not auth.is_public("/whatsappx")


def test_throttle_locks_after_max_failures_and_expires():
    now = [0.0]
    t = auth.LoginThrottle(max_failures=3, window=60, clock=lambda: now[0])
    for _ in range(3):
        assert not t.is_locked("1.2.3.4")
        t.record_failure("1.2.3.4")
    assert t.is_locked("1.2.3.4") and not t.is_locked("5.6.7.8")
    now[0] = 61
    assert not t.is_locked("1.2.3.4")


def test_throttle_reset_clears_an_ip():
    t = auth.LoginThrottle(max_failures=1)
    t.record_failure("ip")
    t.reset("ip")
    assert not t.is_locked("ip")
