"""Generate the login settings for the web UI (see app/auth.py).

Prompts for a password (never echoed or stored) and prints two lines to add to
the server's /opt/assistant/.env, then redeploy (or restart the container):

    python3 scripts/set_admin_password.py

Uses only the standard library, so it runs with any Python 3.9+, no venv needed.
Re-running it with a new password logs out every existing session.
"""

from __future__ import annotations

import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import hash_password  # noqa: E402  (app.auth is stdlib-only)


def main() -> None:
    password = getpass.getpass("New admin password (12+ chars): ")
    if len(password) < 12:
        sys.exit("Too short — use at least 12 characters.")
    if getpass.getpass("Repeat it: ") != password:
        sys.exit("Passwords didn't match.")
    print()
    print(f"ADMIN_PASSWORD_HASH={hash_password(password)}")
    print(f"SESSION_SECRET={secrets.token_urlsafe(32)}")


if __name__ == "__main__":
    main()
