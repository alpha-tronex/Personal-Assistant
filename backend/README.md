# Personal Assistant — Morning Briefing Agent

A personal agent that, every morning at **08:00 ET**, pulls together:

- 📅 Today's events on your **Google Calendar**
- 📧 Yesterday + today's **Gmail** inbox messages
- 📺 New uploads from a curated list of **YouTube** channels

…then summarizes them and DMs the brief to you via a **Telegram bot**.

> **Status:** Steps 1–4 are implemented (scaffold, Google OAuth, Calendar
> agent, Telegram delivery). Gmail and YouTube agents come in steps 5–6.

See `../architect.md` for the architecture and `../launchd/` for the macOS
scheduled-job plist.

---

## Quick start (local Mac)

### 1. Python env

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Environment variables

```bash
cp .env.example .env
# Open .env in your editor and fill in OPENAI_API_KEY for now.
# (Telegram + Google paths come in the next two steps.)
```

### 3. Telegram bot

1. In Telegram, open a chat with `@BotFather`, run `/newbot`, follow the
   prompts. It will give you a **bot token** like `1234567:ABC-...`.
2. Open a chat with your new bot and send any message (e.g. `/start`).
3. Paste the token into `.env` as `TELEGRAM_BOT_TOKEN=...`.
4. Discover your chat id and send a smoke-test message:

   ```bash
   python scripts/test_telegram.py
   ```

   The script will:
   - call `getMe` to verify the token,
   - call `getUpdates` to find your chat id from the message you just sent,
   - print the line to add to `.env` (`TELEGRAM_CHAT_ID=...`),
   - send a confirmation message to your phone.

   Add the printed `TELEGRAM_CHAT_ID=...` to `.env`, then re-run the script
   to confirm it now sends without needing discovery.

### 4. Google credentials (Calendar today; Gmail/YouTube next)

1. Go to https://console.cloud.google.com/, create a project.
2. **APIs & Services → Library**, enable:
   - Google Calendar API
   - Gmail API *(only required when step 5 lands)*
   - YouTube Data API v3 *(only required when step 6 lands)*
3. **APIs & Services → OAuth consent screen**: User type = **External**;
   add yourself under **Test users**. Scopes can be left at default — we
   request them at runtime.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Desktop app**
   - Download the JSON, save it to `backend/data/credentials.json`
     (or wherever `GOOGLE_CREDENTIALS_PATH` points).
5. Run the one-time login:

   ```bash
   python scripts/google_login.py
   ```

   A browser tab opens; sign in with the Google account you want the agent
   to read from. You may see "Google hasn't verified this app" — that's
   expected for a personal Desktop app. Click **Advanced → Go to (unsafe)**
   to continue. The token gets cached at `data/token.json` and silently
   refreshes from then on.

### 5. Smoke test the brief

```bash
uvicorn app.main:app --reload --port 8000
# in another terminal:
curl -X POST http://127.0.0.1:8000/run-now
```

You should receive a Telegram DM that looks like:

```
🌅 Morning Brief — Mon, May 11

📅 TODAY'S CALENDAR  (N events)
• 09:30–10:00 — 1:1 with Sam (Meet)
...

📧 EMAIL ...
(Gmail agent not yet wired — coming in step 5.)

📺 NEW VIDEOS ...
(YouTube agent not yet wired — coming in step 6.)
```

If the Telegram message arrives, **steps 1–4 are working end-to-end**. 🎉

### 6. Scheduling at 08:00 (when ready)

The in-process APScheduler will fire if FastAPI is already running. For
reliability when you're not sitting at the terminal, install the launchd
job:

```bash
cp ../launchd/com.personalassistant.morning.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.personalassistant.morning.plist
```

If your Mac is usually asleep at 08:00, schedule a wake-up:

```bash
sudo pmset repeat wakeorpoweron MTWRFSU 07:55:00
```

---

## HTTP endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/healthz` | Liveness check |
| POST | `/run-now` | Trigger a brief immediately (background task) |
| GET | `/history?limit=20` | List recent runs as JSON |
| GET | `/history/{run_id}` | Render a past brief as HTML |

## Project layout

```
backend/
├── app/
│   ├── main.py              FastAPI app + lifespan
│   ├── workflow.py          run_morning_brief() orchestrator
│   ├── scheduler.py         APScheduler 08:00 cron
│   ├── config.py            Settings (.env loader)
│   ├── db.py                SQLAlchemy engine + session_scope()
│   ├── models.py            Run, Brief, SeenItem
│   ├── agents/
│   │   ├── calendar_agent.py
│   │   ├── compose_agent.py
│   │   ├── gmail_agent.py    (step 5)
│   │   └── youtube_agent.py  (step 6)
│   └── tools/
│       ├── google_oauth.py
│       ├── calendar.py
│       ├── telegram.py
│       ├── gmail.py          (step 5)
│       └── youtube.py        (step 6)
├── config/channels.yaml      YouTube channel handles
├── scripts/
│   ├── google_login.py       One-time OAuth bootstrap
│   └── test_telegram.py      Token sanity + chat_id discovery
├── data/                     SQLite + token.json + credentials.json (gitignored)
├── pyproject.toml
├── .env.example
└── README.md (this file)
```

---

## Troubleshooting

**`No Google token cached at .../token.json`**
You haven't run the OAuth bootstrap yet. `python scripts/google_login.py`.

**`google.auth.exceptions.RefreshError: invalid_grant`**
Refresh token expired (Google sometimes invalidates them after long inactivity
or password changes). Delete `data/token.json` and re-run `google_login.py`.

**`Telegram getUpdates returns []`**
You haven't sent your bot any message yet. Open the chat with the bot and
send anything (`hi`, `/start`, …), then re-run `scripts/test_telegram.py`.

**Telegram `400 Bad Request: can't parse entities`**
The MarkdownV2 escaper missed a character in your event titles or email
subjects. The client falls back to plain text automatically — message will
still arrive, just unformatted. Open an issue with the offending text.

**launchd fires but nothing happens at 08:00**
- Check `data/launchd.out.log` and `data/launchd.err.log`.
- Verify the absolute paths in the plist match your machine.
- Confirm `.venv/bin/python` exists at the path the plist expects.
