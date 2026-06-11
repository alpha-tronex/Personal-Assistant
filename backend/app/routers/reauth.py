"""Google OAuth re-authorization flow — web-based.

Endpoints:
  GET /reauth          → redirects to Google consent screen (requires ?secret=)
  GET /reauth/callback → receives the auth code, saves token.json, shows success

Security: the /reauth endpoint requires a REAUTH_SECRET query param that
matches the value in .env. This prevents anyone else from triggering a
re-auth from the public URL.

Setup (one-time):
  1. Google Cloud Console → Credentials → Create OAuth 2.0 Client ID
     Application type: Web application
     Authorized redirect URI: https://assistant.alphatronex.com/reauth/callback
  2. Download the JSON and save it as data/credentials_web.json on the server
  3. Set GOOGLE_WEB_CREDENTIALS_PATH in .env to point to that file
  4. Set REAUTH_SECRET in .env to any strong random string
"""

from __future__ import annotations

import logging
import secrets
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from google_auth_oauthlib.flow import Flow

from ..config import get_settings
from ..tools.google_oauth import DEFAULT_SCOPES

logger = logging.getLogger(__name__)
router = APIRouter()

REDIRECT_URI = "https://assistant.alphatronex.com/reauth/callback"

# In-memory state store: {state_token: {"ts": float, "flow": Flow}}
# We keep the original Flow object so the PKCE code_verifier is preserved
# between the authorization URL and the token exchange.
# State tokens expire after 10 minutes.
_pending: dict[str, dict] = {}


def _purge_expired() -> None:
    cutoff = time.time() - 600
    expired = [k for k, v in _pending.items() if v["ts"] < cutoff]
    for k in expired:
        del _pending[k]


@router.get("/reauth")
def reauth_start(secret: str = Query(...)):
    """Start the Google OAuth flow. Visit this URL in a browser to re-authorize."""
    settings = get_settings()

    if not settings.reauth_secret:
        raise HTTPException(500, "REAUTH_SECRET is not configured in .env")
    if not secrets.compare_digest(secret, settings.reauth_secret):
        raise HTTPException(403, "Invalid secret")
    if not settings.google_web_credentials_file.exists():
        raise HTTPException(
            500,
            f"Web credentials not found at {settings.google_web_credentials_file}. "
            "Download a Web application OAuth client JSON from Google Cloud Console "
            "and save it to that path."
        )

    _purge_expired()

    flow = Flow.from_client_secrets_file(
        str(settings.google_web_credentials_file),
        scopes=list(DEFAULT_SCOPES),
        redirect_uri=REDIRECT_URI,
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",   # force refresh_token to be returned
        include_granted_scopes="true",
    )
    # Store the whole flow object so the PKCE code_verifier survives into the callback
    _pending[state] = {"ts": time.time(), "flow": flow}
    logger.info("Re-auth flow started (state=%s…)", state[:8])
    return RedirectResponse(auth_url)


@router.get("/reauth/callback", response_class=HTMLResponse)
def reauth_callback(code: str = Query(...), state: str = Query(...)):
    """Google redirects here after the user approves. Exchanges code for tokens."""
    settings = get_settings()

    _purge_expired()
    pending = _pending.pop(state, None)
    if pending is None:
        raise HTTPException(400, "Invalid or expired OAuth state. Please start over.")

    try:
        flow: Flow = pending["flow"]
        flow.fetch_token(code=code)
        creds = flow.credentials
    except Exception as e:
        logger.exception("Token exchange failed")
        raise HTTPException(500, f"Token exchange failed: {e}") from e

    token_path = settings.google_token_file
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    logger.info("Google token refreshed and saved to %s", token_path)

    return HTMLResponse("""
<!doctype html>
<html>
<head>
  <title>Re-authorized ✅</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: -apple-system, sans-serif; max-width: 480px;
           margin: 4rem auto; padding: 0 1rem; text-align: center; }
    h1 { font-size: 2rem; }
    p  { color: #555; }
  </style>
</head>
<body>
  <h1>✅ Google re-authorized!</h1>
  <p>Your token has been saved. The assistant will use it for the next brief.</p>
  <p>You can close this tab.</p>
</body>
</html>""")
