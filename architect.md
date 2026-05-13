# Personal Assistant — Architecture

A standalone, self-hosted **personal morning briefing agent** that runs every
day at **08:00 America/New_York** and produces one consolidated brief
covering:

1. New videos (since yesterday) on a curated list of YouTube channels
2. All Gmail inbox messages from yesterday + today
3. Today's events on the user's primary Google Calendar

The brief is delivered as a **Telegram DM**.

This document is the source of truth for *how it's built*. The user-facing
setup walkthrough lives in `backend/README.md`.

---

## 1. High-level diagram

```
                 ┌────────────────────┐
                 │   launchd (08:00)  │   macOS scheduled job
                 └─────────┬──────────┘
                           │ POST /run-now (or direct python entrypoint)
                           ▼
   ┌────────────────────────────────────────────────────────────┐
   │  FastAPI (uvicorn)  —  backend/app/main.py                 │
   │    /healthz   /run-now   /history   /history/{id}          │
   │                                                            │
   │  APScheduler (in-process backup trigger @ 08:00)           │
   └─────────────────────────┬──────────────────────────────────┘
                             │ run_morning_brief(trigger)
                             ▼
   ┌────────────────────────────────────────────────────────────┐
   │  Workflow / Orchestrator   (app/workflow.py)               │
   │  Step 7+ : LangGraph StateGraph with parallel branches.    │
   │  Today  : sequential calls (Calendar -> Compose -> TG)     │
   │                                                            │
   │   ┌──── youtube_agent ────┐                                │
   │   │                       │                                │
   │ ──┼──── gmail_agent  ─────┼──► compose_agent ──► telegram  │
   │   │                       │                                │
   │   └──── calendar_agent ───┘                                │
   └─────────────────────────┬──────────────────────────────────┘
                             │
                  ┌──────────┴──────────────┐
                  ▼                         ▼
       Google APIs (read-only)        Telegram Bot API
       Calendar / Gmail / YouTube     (sendMessage)
                  │
                  ▼
            OpenAI API (summarization, step 5+)

   Persistent state (SQLite) ── runs, briefs, seen_items
```

## 2. Component map

| Path | Responsibility |
|------|----------------|
| `app/main.py` | FastAPI app: lifespan (DB + scheduler), HTTP endpoints. |
| `app/scheduler.py` | APScheduler in-process daily cron. |
| `app/workflow.py` | Orchestrator entry point: `run_morning_brief(trigger)`. |
| `app/config.py` | `Settings` from `.env` via pydantic-settings. |
| `app/db.py` | SQLAlchemy engine + `session_scope()` context manager. |
| `app/models.py` | `Run`, `Brief`, `SeenItem` ORM tables. |
| `app/agents/calendar_agent.py` | Today's calendar → markdown section. |
| `app/agents/gmail_agent.py` | (step 5) Yesterday+today emails → summary. |
| `app/agents/youtube_agent.py` | (step 6) New uploads → per-video TL;DR. |
| `app/agents/compose_agent.py` | Merges sections into the final brief body. |
| `app/tools/google_oauth.py` | Shared OAuth: load+refresh, interactive bootstrap. |
| `app/tools/calendar.py` | Calendar Data API client + `CalendarEvent` model. |
| `app/tools/gmail.py` | (step 5) Gmail API client. |
| `app/tools/youtube.py` | (step 6) YouTube Data API + transcript fetch. |
| `app/tools/telegram.py` | Telegram Bot API client (Markdown + chunking). |
| `scripts/google_login.py` | One-time browser OAuth flow. |
| `scripts/test_telegram.py` | Verify bot token, discover chat_id, send test msg. |
| `config/channels.yaml` | List of YouTube channels to watch. |
| `launchd/com.personalassistant.morning.plist` | macOS daily 08:00 trigger. |

## 3. Data model (SQLite)

```
runs(id PK, started_at, finished_at, status, trigger, error)
briefs(id PK, run_id FK, created_at, body_markdown, delivered_to)
seen_items(id PK, kind, external_id, seen_at)
```

`seen_items` is the dedup primitive. The YouTube agent writes
`(kind="video", external_id=video_id)` after summarizing so the same upload
isn't summarized twice across runs. The Gmail agent could do the same with
`messageId` if we ever shorten the lookback window.

## 4. Auth & secrets

- **OpenAI**: `OPENAI_API_KEY` in `.env`. Used by Gmail + YouTube summarizers
  (steps 5+). Calendar agent today is deterministic, no LLM.
- **Google**: One-time desktop OAuth flow (`scripts/google_login.py`) writes
  a refresh token to `data/token.json`. Runtime calls
  `google_oauth.load_credentials()` and silently refreshes the access token
  using `google.auth.transport.requests.Request`.
- **Telegram**: Bot token + numeric chat id in `.env`. Chat id can be
  auto-discovered via `scripts/test_telegram.py`'s call to `getUpdates`.

All secrets stay on the local Mac. `data/` is `.gitignore`d. Outbound traffic
is limited to:
- `googleapis.com` (Calendar, Gmail, YouTube Data, OAuth refresh)
- `api.telegram.org` (delivery)
- `api.openai.com` (summarization, steps 5+)

## 5. Scheduling strategy

We run **two** triggers, by design:

1. **launchd** (`launchd/com.personalassistant.morning.plist`) — the source of
   truth. Fires at 08:00 even if the FastAPI server isn't already running:
   it tries `curl POST /run-now` and falls back to invoking the Python
   workflow directly via `.venv/bin/python -c "from app.workflow import ..."`.
2. **APScheduler** in `app/scheduler.py` — a no-op in production, but useful
   if you happen to be running the server at 08:00 anyway and don't want to
   bother with launchd. It will *not* double-fire because launchd hits
   `/run-now`, which is just another way to call the same function (each run
   creates its own `Run` row, but in practice only one of the two triggers
   fires per day depending on which path you use).

If your laptop is asleep at 08:00, launchd queues the job and runs it at
next wake. Adding `pmset repeat wakeorpoweron MTWRFSU 07:55:00` solves that
deterministically.

## 6. Workflow / agent runtime

For steps 1–4 the orchestrator is plain Python: fetch → compose → deliver.
Once Gmail and YouTube agents land (steps 5–6) we promote it to a
**LangGraph `StateGraph`** with:

```python
class BriefState(TypedDict):
    calendar_md: str
    gmail_md: str
    youtube_md: str
    body: str
    delivered_to: str | None
    error: str | None
```

…and three branches that fan out from `START` in parallel, then converge on
a `compose` node followed by `deliver`. LangGraph's checkpointer will be
SQLite (same DB as ours), enabling resumable runs and a partial-failure UX
(e.g. Calendar succeeded, YouTube failed → still send the brief with a note).

Why LangGraph at all if today's flow is linear? Because:
- Parallelism comes for free (3 Google APIs hit concurrently → ~3× faster).
- Each node is independently retryable / observable.
- Human-in-the-loop interrupts (e.g. "approve before sending") drop in.

## 7. LLM usage (steps 5+)

| Section | Model | Prompt summary | Approx daily tokens |
|---------|-------|----------------|---------------------|
| Gmail summary | `gpt-4o-mini` | "Bucket into Action / FYI / Skim. Quote sender + 1-line gist." | 20–60k |
| YouTube TL;DRs | `gpt-4o-mini` | "TL;DR + 3 key points + recommended skip." | 5–20k per video |
| Compose (optional) | `gpt-4o-mini` | "Tighten transitions; keep markdown structure." | 5–10k |

We use OpenAI's tool-calling-free `chat.completions` for cheapest path.
Estimated cost: **$0.05–0.20 / day**.

## 8. Failure handling

- Each agent returns a markdown string. On exception, it returns a
  `_(failed: ...)_` placeholder so other sections still ship.
- Top-level `run_morning_brief` catches anything else and posts a Telegram
  message of the form ``⚠️ Morning brief failed: ...`` so silent failures
  are impossible to miss.
- Every run is rowed in `runs` with `status` ∈ {`running`, `ok`, `error`}
  and the full traceback in `runs.error`.

## 9. Delivery format

A single Telegram message (split if > ~4000 chars) using **MarkdownV2**.
We escape punctuation conservatively and fall back to plain text if Telegram
rejects the formatted body.

```
🌅 Morning Brief — Mon, May 11

📅 TODAY'S CALENDAR  (3 events)
• 09:30–10:00 — 1:1 with Sam (Meet)
• 13:00–14:00 — Sprint planning
• 18:00 — Dentist (3210 Main St)

📧 EMAIL (yesterday + today, 14 messages)
Action required: ...
FYI: ...

📺 NEW VIDEOS
• Fireship — "Bun 2.0 changes everything" (8 min)
   TL;DR: ...
```

## 10. Build phases

| Phase | Status | Deliverable |
|-------|--------|-------------|
| 1 | ✅ done | Scaffold (FastAPI, SQLite, settings, README skeleton). |
| 2 | ✅ done | Google OAuth bootstrap + login script. |
| 3 | ✅ done | Calendar agent (today's events as markdown). |
| 4 | ✅ done | Telegram delivery + chat-id discovery + `/run-now` end-to-end. |
| 5 | ⏳ next | Gmail agent + summarizer. |
| 6 | ⏳ | YouTube agent (channel uploads + caption-only transcripts). |
| 7 | ⏳ | Replace `app/workflow.py` body with a LangGraph parallel graph. |
| 8 | ⏳ | launchd install instructions + `pmset` wake. |
| 9 | ⏳ | `/history` HTML polish, run-history index page. |
| 10 | ⏳ | README troubleshooting + Docker option. |

## 11. Non-goals (for now)

- Multi-user. This is a single-user personal agent.
- Visual workflow builder. (That was an earlier shape; we're shipping the
  focused use case instead.)
- Pushing data anywhere except Telegram and the local SQLite DB.
- Hosted deployment. Local Mac only — `host = local` per the build spec.
