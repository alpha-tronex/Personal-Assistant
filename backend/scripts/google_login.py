"""One-time bootstrap to grant the agentic app access to your Google data.

Usage:
  cd backend
  python scripts/google_login.py

What it does:
  1. Reads OAuth client credentials from $GOOGLE_CREDENTIALS_PATH.
  2. Opens a browser tab; you sign in to your Google account and approve
     read-only access to Calendar, Gmail, and YouTube.
  3. Caches the refresh token to $GOOGLE_TOKEN_PATH so future runs are silent.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the `app` package importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.google_oauth import (  # noqa: E402
    DEFAULT_SCOPES,
    GoogleAuthError,
    perform_interactive_login,
)


def main() -> int:
    print("Requesting scopes:")
    for s in DEFAULT_SCOPES:
        print(f"  - {s}")
    print()
    try:
        creds = perform_interactive_login()
    except GoogleAuthError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print("Login successful.")
    print(f"  refresh_token cached: {bool(creds.refresh_token)}")
    print(f"  scopes: {', '.join(creds.scopes or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
