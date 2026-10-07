"""Shared pytest setup — hermetic settings, a throwaway DB, and no network.

Order matters: `app.db` builds its engine from settings at import time, so the
environment below must be in place before anything under `app` is imported.
"""

from __future__ import annotations

import os
import socket
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="pa-tests-"))

os.environ.update(
    {
        "APP_DB_URL": f"sqlite:///{_TMP / 'test.db'}",
        "APP_TIMEZONE": "America/New_York",
        "TELEGRAM_BOT_TOKEN": "test-token",
        "TELEGRAM_CHAT_ID": "1000",
        "OPENAI_API_KEY": "",
        "REAUTH_SECRET": "test-reauth-secret",
        "WHATSAPP_BRIDGE_URL": "http://bridge.test:3000",
        "GOOGLE_TOKEN_PATH": str(_TMP / "token.json"),
        "GMAIL_IGNORE_FROM": "",
    }
)

from app import config  # noqa: E402

# Never read a developer's real backend/.env during tests.
config.Settings.model_config["env_file"] = None
config.get_settings.cache_clear()

from app import db  # noqa: E402
from app import models  # noqa: E402, F401  (registers tables on Base.metadata)


class NetworkBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail loudly if a test reaches for the real internet (Telegram, OpenAI, Google…)."""

    def guard(*args, **kwargs):
        raise NetworkBlocked(f"test tried to open a network connection: {args!r}")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    monkeypatch.setattr(socket, "getaddrinfo", guard)


@pytest.fixture(autouse=True)
def fresh_db():
    """Every test starts from empty tables."""
    db.Base.metadata.drop_all(bind=db._engine)
    db.Base.metadata.create_all(bind=db._engine)
    yield
    db.Base.metadata.drop_all(bind=db._engine)


@pytest.fixture
def client():
    """FastAPI test client WITHOUT the lifespan.

    Entering the lifespan (`with TestClient(app)`) would start the APScheduler
    job and the Telegram long-poll thread, so it is never used in tests — the
    audit script enforces that.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def settings():
    return config.get_settings()
