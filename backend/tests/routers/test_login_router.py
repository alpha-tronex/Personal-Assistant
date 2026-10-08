"""Login flow and the guard middleware, end to end through the app."""

from __future__ import annotations

import re

import pytest

from app import auth
from app.main import app

HTML = {"accept": "text/html"}


@pytest.fixture
def login(anon_client, test_password):
    def _do(password=test_password, next_url="/projects", ip="9.9.9.9"):
        return _login(anon_client, password, next_url, ip)
    return _do


def _login(c, password, next_url="/projects", ip="9.9.9.9"):
    return c.post(
        "/login",
        content=f"password={password}&next={next_url}".replace(" ", "+"),
        headers={"content-type": "application/x-www-form-urlencoded", "x-real-ip": ip},
        follow_redirects=False,
    )


def _all_operations():
    """Every (method, path) the app serves. Taken from the OpenAPI schema, which
    flattens included routers (iterating app.routes doesn't on this FastAPI),
    plus the routes hidden from the schema."""
    ops = [("GET", "/favicon.svg"), ("GET", "/docs"), ("GET", "/openapi.json")]
    for path, methods in app.openapi()["paths"].items():
        concrete = re.sub(r"\{[^}]+\}", "1", path)
        ops += [(m.upper(), concrete) for m in methods]
    return ops


def test_every_route_except_the_allow_list_requires_login(anon_client):
    """Walks the real route table so a newly added route can't slip out public."""
    ops = _all_operations()
    assert len(ops) > 25  # sanity: the walk actually found the routers' routes
    open_routes = set()
    for method, path in ops:
        r = anon_client.request(method, path, headers=HTML, follow_redirects=False)
        # The middleware's own answers: a login redirect for browser GETs,
        # a 401 "Not authenticated" for everything else.
        guarded = (
            r.status_code == 303 and r.headers["location"].startswith("/login?next=")
        ) or (r.status_code == 401 and r.headers.get("content-type") == "application/json"
              and r.json() == {"detail": "Not authenticated"})
        if not guarded:
            open_routes.add(path)
    assert open_routes == {
        "/healthz", "/favicon.svg", "/login", "/logout",
        "/reauth", "/reauth/callback", "/whatsapp/incoming", "/whatsapp/silence-alert",
        "/whatsapp/disconnected-alert",
    }


def test_browsers_are_redirected_to_login_with_a_return_path(anon_client):
    r = anon_client.get("/history/3?a=1", headers=HTML, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=%2Fhistory%2F3%3Fa%3D1"


def test_api_calls_get_401_not_a_redirect(anon_client):
    assert anon_client.get("/reminders").status_code == 401
    assert anon_client.post("/run-now").status_code == 401


def test_correct_password_sets_a_secure_cookie_and_redirects_back(anon_client, login):
    r = login()
    assert r.status_code == 303 and r.headers["location"] == "/projects"
    cookie = r.headers["set-cookie"]
    for flag in ("pa_session=", "HttpOnly", "Secure", "SameSite=lax", "Max-Age=2592000"):
        assert flag.lower() in cookie.lower()
    assert anon_client.get("/reminders").status_code == 200  # cookie now works


def test_wrong_password_is_rejected(anon_client, login):
    r = login(password="nope")
    assert r.status_code == 401 and "Wrong password" in r.text
    assert "set-cookie" not in r.headers


def test_login_redirect_target_cannot_leave_the_site(anon_client, login):
    assert login(next_url="https://evil.com").headers["location"] == "/settings"


def test_repeated_failures_lock_out_that_ip_even_for_the_right_password(anon_client, login):
    for _ in range(5):
        login(password="nope", ip="6.6.6.6")
    assert login(ip="6.6.6.6").status_code == 429
    assert login(ip="7.7.7.7").status_code == 303  # other IPs unaffected


def test_unconfigured_server_fails_closed(anon_client, settings, monkeypatch, login):
    monkeypatch.setattr(settings, "admin_password_hash", "")
    assert login().status_code == 503
    assert anon_client.get("/reminders").status_code == 401


def test_logged_in_users_skip_the_login_page(client):
    r = client.get("/login?next=/projects", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/projects"


def test_login_page_escapes_the_next_value(anon_client):
    r = anon_client.get('/login?next=/x"><script>')
    assert '"><script>' not in r.text


def test_logout_clears_the_cookie(client):
    r = client.get("/logout", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert 'pa_session=""' in r.headers["set-cookie"] or "Max-Age=0" in r.headers["set-cookie"]


def test_changing_the_password_invalidates_existing_sessions(client, settings, monkeypatch):
    assert client.get("/reminders").status_code == 200
    monkeypatch.setattr(settings, "admin_password_hash", auth.hash_password("brand-new-pass", iterations=1_000))
    assert client.get("/reminders").status_code == 401


@pytest.mark.parametrize("path", ["/healthz", "/favicon.svg"])
def test_health_and_favicon_stay_public(anon_client, path):
    assert anon_client.get(path).status_code == 200
