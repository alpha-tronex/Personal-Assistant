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
| `app/main.py` | FastAPI app: lifespan (DB + scheduler + Telegram poller), HTTP endpoints including reminders CRUD and `/settings` UI. |
| `app/scheduler.py` | APScheduler in-process daily cron. |
| `app/workflow.py` | Thin wrapper: opens a `Run` row, invokes the graph, persists the `Brief`. |
| `app/graph.py` | LangGraph `StateGraph`: source nodes → compose → deliver. Exports compiled `graph`. |
| `app/config.py` | `Settings` from `.env` via pydantic-settings. |
| `app/db.py` | SQLAlchemy engine + `session_scope()` context manager. |
| `app/models.py` | `Run`, `Brief`, `SeenItem`, `Reminder`, `PendingReply` ORM tables. |
| `app/agents/calendar_agent.py` | Today's calendar → markdown section. |
| `app/agents/gmail_agent.py` | Yesterday+today emails → summary. |
| `app/agents/youtube_agent.py` | (step 6) New uploads → per-video TL;DR. |
| `app/agents/compose_agent.py` | Merges sections into the final brief body. |
| `app/agents/whatsapp_agent.py` | Generates an AI reply suggestion for an incoming WhatsApp DM. |
| `app/routers/whatsapp.py` | `POST /whatsapp/incoming` + `POST /whatsapp/silence-alert` — receives events from the Node.js bridge. |
| `app/routers/reauth.py` | Google re-auth flow endpoint. |
| `app/telegram_poller.py` | Long-poll daemon: handles WhatsApp reply approvals via inline buttons (`wa_send`, `wa_edit`, `wa_skip`) and `/pending` command. |
| `app/tools/google_oauth.py` | Shared OAuth: load+refresh, interactive bootstrap. |
| `app/tools/calendar.py` | Calendar Data API client + `CalendarEvent` model. |
| `app/tools/gmail.py` | Gmail API client. |
| `app/tools/youtube.py` | (step 6) YouTube Data API + transcript fetch. |
| `app/tools/telegram.py` | Telegram Bot API client (Markdown + chunking, inline keyboards, WA notifications). |
| `app/tools/whatsapp.py` | HTTP client for the Node.js WhatsApp bridge (`send_whatsapp_message`). |
| `scripts/google_login.py` | One-time browser OAuth flow. |
| `scripts/test_telegram.py` | Verify bot token, discover chat_id, send test msg. |
| `config/channels.yaml` | List of YouTube channels to watch. |
| `launchd/com.personalassistant.morning.plist` | macOS daily 08:00 trigger. |
| `langgraph.json` (repo root) | Points LangGraph CLI / Studio at `app/graph.py:graph`. |

## 3. Data model (SQLite)

```
runs(id PK, started_at, finished_at, status, trigger, error)
briefs(id PK, run_id FK, created_at, body_markdown, delivered_to)
seen_items(id PK, kind, external_id, seen_at)
reminders(id PK, label, frequency, day_of_week, day_of_month, time, time_end, enabled, created_at)
pending_replies(id PK, wa_from, contact_name, wa_message_id UNIQUE, incoming_body,
                suggested_reply, sent_reply, telegram_message_id, status, created_at, sent_at)
```

`seen_items` is the dedup primitive. The YouTube agent writes
`(kind="video", external_id=video_id)` after summarizing so the same upload
isn't summarized twice across runs. The Gmail agent could do the same with
`messageId` if we ever shorten the lookback window.

`reminders` stores user-defined recurring reminders managed via the `/settings` UI.
Frequency is one of `daily | weekly | monthly`, with optional `day_of_week`, `day_of_month`,
and time window fields.

`pending_replies` tracks every incoming WhatsApp DM that has been surfaced to the user
for approval. Status flows: `pending → sent | dismissed`.

## 4. Auth & secrets

- **OpenAI**: `OPENAI_API_KEY` in `.env`. Used by Gmail, YouTube, and WhatsApp reply summarizers.
  Calendar agent is deterministic, no LLM.
- **Google**: One-time desktop OAuth flow (`scripts/google_login.py`) writes
  a refresh token to `data/token.json`. Runtime calls
  `google_oauth.load_credentials()` and silently refreshes the access token
  using `google.auth.transport.requests.Request`.
- **Telegram**: Bot token + numeric chat id in `.env`. Chat id can be
  auto-discovered via `scripts/test_telegram.py`'s call to `getUpdates`.
  The poller also uses the bot token for long-polling (`getUpdates`) and
  answering inline keyboard callbacks (`answerCallbackQuery`).
- **WhatsApp bridge**: A local Node.js process (port 3000) that bridges
  WhatsApp Web to this FastAPI server. No external credential needed beyond
  the QR-code scan that authenticates the WhatsApp session.

All secrets stay on the local Mac. `data/` is `.gitignore`d. Outbound traffic
is limited to:
- `googleapis.com` (Calendar, Gmail, YouTube Data, OAuth refresh)
- `api.telegram.org` (delivery + long-poll)
- `api.openai.com` (summarization)
- `127.0.0.1:3000` (WhatsApp bridge — local only)

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
**LangGraph `StateGraph`** in `app/graph.py` with:

```python
class BriefState(TypedDict, total=False):
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
- **LangGraph Studio** gives us a free visual debugger — see §6a.

`workflow.run_morning_brief()` stays as the persistence boundary: it opens
a `Run` row, calls `graph.invoke({})`, then records the `Brief` and final
status. The graph itself is pure (no DB writes) so it can be safely
re-executed from Studio against your real Google/Telegram credentials
without polluting the run history.

### 6a. LangGraph Studio (visual debugger)

A `langgraph.json` at the repo root exposes the compiled graph to the
`langgraph` CLI:

```json
{
  "dependencies": ["./backend"],
  "graphs": { "morning_brief": "./backend/app/graph.py:graph" },
  "env": "./backend/.env",
  "python_version": "3.11"
}
```

`langgraph-cli[inmem]` is added to the `dev` extras. Running `langgraph dev`
from the repo root boots a local server on `:2024` and prints a Studio URL
that opens the graph in the browser — nodes are clickable, state is
inspectable at every step, and you can submit synthetic inputs without
going through `/run-now`. Studio is dev-only; production traffic still
flows through FastAPI → `workflow.run_morning_brief()` → `graph.invoke()`.

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
| 5 | ✅ done | Gmail agent + summarizer. |
| 6 | ⏳ next | YouTube agent (channel uploads + caption-only transcripts). |
| 7 | ✅ done | `app/graph.py` (LangGraph parallel graph) + `langgraph.json` for Studio. |
| 8 | ✅ done | launchd install + APScheduler backup trigger. |
| 9 | ⏳ | `/history` HTML polish, run-history index page. |
| 10 | ⏳ | README troubleshooting + Docker option. |
| R1 | ✅ done | Reminders — `Reminder` model, full CRUD API (`/reminders`), mobile-friendly `/settings` UI. |
| R2 | ✅ done | WhatsApp reply assistant — Node.js bridge integration, `whatsapp_agent` (AI suggestions), `PendingReply` model, Telegram inline-button approval flow (`wa_send` / `wa_edit` / `wa_skip`), `/pending` command, silence-alert watchdog. |

## 11. Reminders subsystem

A lightweight web UI at `/settings` (mobile-friendly, Apple-style design) lets the user
manage recurring reminders. The root `/` redirects here.

**API surface** (all JSON):
- `GET  /reminders` — list all reminders ordered by creation time.
- `POST /reminders` — create a reminder (`label`, `frequency`, optional `day_of_week` /
  `day_of_month` / `time` / `time_end`).
- `PATCH /reminders/{id}` — toggle `enabled` on/off.
- `DELETE /reminders/{id}` — remove a reminder.

Frequencies: `daily | weekly | monthly`. The UI renders inline toggle switches and a
trash-icon delete button per row, plus a toast for feedback.

Reminders are stored in `reminders` (SQLite). Delivery into the morning brief is the
intended next step (not yet wired into `compose_agent`).

## 12. WhatsApp reply assistant

An always-on second brain for WhatsApp DMs. Architecture:

```
WhatsApp Web ──► Node.js bridge (port 3000) ──► POST /whatsapp/incoming
                       │                               │
                       │ watchdog (silence > N hrs)    │ background task
                       ▼                               ▼
              POST /whatsapp/silence-alert    whatsapp_agent.suggest_reply()
                       │                               │
                       ▼                               ▼
              Telegram alert             PendingReply row + Telegram notification
                                                       │
                                         inline buttons: ✅ Send / ✏️ Edit / ❌ Skip
                                                       │
                                         telegram_poller.py (daemon thread)
                                                       │
                                         send_whatsapp_message() → bridge → WA
```

**Flow**:
1. Node.js bridge POSTs `{wa_from, contact_name, body, timestamp, message_id}` to
   `/whatsapp/incoming`.
2. Dedup on `wa_message_id` (idempotent).
3. `whatsapp_agent.suggest_reply()` calls `gpt-4o-mini` to draft a reply.
4. A `PendingReply` row is created (`status="pending"`).
5. A Telegram notification is sent with the incoming message + AI suggestion +
   three inline buttons.
6. The `telegram_poller` long-polls `getUpdates` in a daemon thread:
   - **✅ Send** (`wa_send:{id}`) → calls bridge, marks `sent`.
   - **✏️ Edit** (`wa_edit:{id}`) → sends the suggestion as copyable text; user
     replies to the notification with their edited version → bridge sends that.
   - **❌ Skip** (`wa_skip:{id}`) → marks `dismissed`, removes buttons.
   - `/pending` command → lists all unresolved items.
7. Silence-alert watchdog POSTs to `/whatsapp/silence-alert` if the bridge goes
   quiet for too long; the server forwards a Telegram warning.

**Non-goals for this subsystem**: autonomous sending without approval, group messages,
media attachments, multi-device.

## 13. Non-goals (for now)

- Multi-user. This is a single-user personal agent.
- A custom visual workflow *builder*. (That was an earlier shape — we're
  shipping the focused use case instead. LangGraph Studio gives us a
  read-mostly visual debugger for free; see §6a.)
- Pushing data anywhere except Telegram and the local SQLite DB.
- Hosted deployment. Local Mac only — `host = local` per the build spec.
