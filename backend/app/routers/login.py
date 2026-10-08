"""Login page, logout, and the middleware that guards every private route.

See app/auth.py for the rules (public allow-list, cookie format, throttle).
"""

from __future__ import annotations

import html
import logging
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from .. import auth
from ..config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()
throttle = auth.LoginThrottle()


def _client_ip(request: Request) -> str:
    # nginx sets X-Real-IP; the container is only reachable through nginx or
    # from the host itself.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def _is_authenticated(request: Request) -> bool:
    s = get_settings()
    return auth.verify_session_token(
        request.cookies.get(auth.COOKIE_NAME), s.session_secret, s.admin_password_hash
    )


def demo_blocked(method: str, path: str) -> bool:
    """Routes switched off on the public demo: anything touching real
    credentials or the bridge, and writes to the shared projects file."""
    if path in ("/reauth", "/reauth/callback") or path.startswith("/whatsapp/"):
        return True
    return method != "GET" and path.startswith("/projects/")


async def require_login(request: Request, call_next):
    """HTTP middleware: private routes need a valid session cookie.

    In demo mode there is no login; a few routes are disabled instead.
    """
    if get_settings().demo_mode:
        if demo_blocked(request.method, request.url.path):
            return JSONResponse({"detail": "Not available in the demo"}, status_code=404)
        return await call_next(request)
    if auth.is_public(request.url.path) or _is_authenticated(request):
        return await call_next(request)
    if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/login?next={quote(target, safe='')}", status_code=303)
    return JSONResponse({"detail": "Not authenticated"}, status_code=401)


_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Personal Assistant — Sign in</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>
  :root {{ --bg:#0d0d0d; --surface:#161616; --border2:#2e2e2e; --text:#e5e5e5;
          --label:#999; --accent:#0a84ff; --red:#ff453a; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg);
         color:var(--text); min-height:100vh; display:grid; place-items:center; padding:1rem; }}
  form {{ background:var(--surface); border:1px solid var(--border2); border-radius:14px;
         padding:1.75rem; width:100%; max-width:360px; display:grid; gap:0.9rem; }}
  h1 {{ font-size:1.1rem; }}
  label {{ font-size:0.8rem; color:var(--label); display:grid; gap:0.35rem; }}
  input {{ background:var(--bg); color:var(--text); border:1px solid var(--border2); border-radius:9px;
          padding:0.7rem 0.8rem; font-size:1rem; }}
  button {{ background:var(--accent); color:#fff; border:0; border-radius:9px; padding:0.75rem;
           font-size:1rem; font-weight:600; cursor:pointer; }}
  .error {{ color:var(--red); font-size:0.85rem; }}
</style></head>
<body><form method="post" action="/login">
  <h1>Personal Assistant</h1>
  {error}
  <input type="hidden" name="next" value="{next}">
  <label>Password<input type="password" name="password" autocomplete="current-password" autofocus required></label>
  <button type="submit">Sign in</button>
</form></body></html>"""


def _page(next_url: str, error: str = "", status: int = 200) -> HTMLResponse:
    err = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return HTMLResponse(_PAGE.format(error=err, next=html.escape(next_url, quote=True)), status_code=status)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str | None = None) -> Response:
    target = auth.safe_next(next)
    if _is_authenticated(request):
        return RedirectResponse(target, status_code=303)
    return _page(target)


@router.post("/login")
async def login_submit(request: Request) -> Response:
    # Parsed by hand to avoid a python-multipart dependency for one field.
    form = parse_qs((await request.body()).decode(errors="replace"))
    password = (form.get("password") or [""])[0]
    target = auth.safe_next((form.get("next") or [None])[0])
    ip = _client_ip(request)
    s = get_settings()

    if not s.admin_password_hash or not s.session_secret:
        logger.error("Login attempted but ADMIN_PASSWORD_HASH / SESSION_SECRET are not set.")
        return _page(target, "Login is not configured on the server yet.", status=503)
    if throttle.is_locked(ip):
        logger.warning("Login locked out for %s.", ip)
        return _page(target, "Too many attempts. Try again in 15 minutes.", status=429)
    if not auth.verify_password(password, s.admin_password_hash):
        throttle.record_failure(ip)
        logger.warning("Failed login from %s.", ip)
        return _page(target, "Wrong password.", status=401)

    throttle.reset(ip)
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.make_session_token(s.session_secret, s.admin_password_hash),
        max_age=auth.SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@router.get("/logout")
def logout() -> Response:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(auth.COOKIE_NAME, httponly=True, secure=True, samesite="lax")
    return response
