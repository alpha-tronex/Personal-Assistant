# Personal Assistant

[![CI / CD](https://github.com/alpha-tronex/Personal-Assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/alpha-tronex/Personal-Assistant/actions/workflows/ci.yml)

A self-hosted AI assistant that I use every day. Each morning at 08:00 it
reads my calendar, inbox and YouTube subscriptions, and sends a single
Telegram brief. It also drafts replies to WhatsApp messages, which I approve,
edit or skip from Telegram.

**▶ Live demo: [demo.alphatronex.com](https://demo.alphatronex.com)**. It
runs the same code on sample data, so you can click around, edit reminders
and generate a brief. It resets nightly and sends nothing.

## What it does

- **Morning brief.** A LangGraph graph fetches four sections in parallel and
  composes them:
  - Google Calendar: today's events, with back-to-back warnings.
  - Gmail: grouped into *Action required / FYI / Skim* by `gpt-4o-mini`,
    with a per-run cost cap.
  - New YouTube uploads: a TL;DR from each transcript.
  - My recurring reminders.

  A failing source becomes a visible placeholder instead of killing the
  brief. A failed run alerts me on Telegram.
- **WhatsApp reply assistant.** A Node.js bridge (Baileys) forwards incoming
  DMs. The backend drafts a reply and posts it to Telegram with
  ✅ Send / ✏️ Edit / ❌ Skip buttons. Nothing is sent without my approval.
- **Settings portal and projects dashboard.** A mobile-friendly web UI for
  reminders, YouTube channels and feature flags, plus a dashboard of my
  projects with live GitHub commit activity.

## How it's built

```
WhatsApp ─► Node bridge (pm2) ─┐            ┌─► Telegram (brief, approvals)
                               ▼            │
          FastAPI + LangGraph + APScheduler ┼─► OpenAI gpt-4o-mini
          SQLite · Docker · nginx · TLS     └─► Google Calendar / Gmail / YouTube
```

- **Stack:** Python 3.11, FastAPI, LangGraph, SQLAlchemy/SQLite, APScheduler,
  httpx, Node.js (Baileys), Docker Compose, nginx and Let's Encrypt on a
  Hetzner VPS.
- **Design notes:** [`architect.md`](./architect.md) covers the component
  map, data model, scheduling, failure handling and each subsystem.
- **Security:**
  - Single-user login with a PBKDF2 password hash and signed HttpOnly
    cookies.
  - Per-IP throttling of failed logins.
  - Fails closed when the login isn't configured.
  - A test walks every route anonymously so a new endpoint can't
    accidentally go public.
- **Testing:** about 200 hermetic pytest tests (no network, no real
  credentials, fresh database per test), with one mocked seam per layer.
  `backend/scripts/testability-audit.sh` enforces the layering rules in CI.
  See [`backend/tests/README.md`](./backend/tests/README.md).
- **CI/CD:** every push runs lint, tests, the audit and shellcheck. `main`
  deploys to the VPS over a forced-command SSH key, and the smoke test checks
  that `/healthz` on both the app and the demo reports the pushed commit. See
  [`backend/deploy/README.md`](./backend/deploy/README.md).

## Running it yourself

Setup walkthrough and API reference: [`backend/README.md`](./backend/README.md).
Build log: [`milestone.md`](./milestone.md). The older notes in
[`README/`](./README/) describe an earlier stack and are kept for reference
only.
