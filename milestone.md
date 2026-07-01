# Personal Assistant — Milestones

A realistic week-by-week plan assuming **3–5 hours/week** of focused time.

The plan is built around three principles:

1. **One sitting per week.** Every weekly task is sized so you can finish it
   in a single ~3-hour block. No multi-evening checkpoints.
2. **Always shippable.** After every milestone the app still runs end-to-end
   and delivers *something* to Telegram. You're never left with a half-broken
   branch over a busy week.
3. **Buffer weeks are real.** Life happens. Roughly every 3rd week is a
   "catch-up / polish" slot rather than new functionality.

Steps 1–4 from the original build plan are **already done** (see
[`architect.md`](./architect.md) §10). This document covers what's left.

---

## Snapshot

| Phase | Weeks | Status | Outcome |
|------|-------|--------|---------|
| 0. Personal setup (you only) | 1 | ✅ done | OAuth + Telegram working, calendar brief arrives daily |
| 1. Gmail agent | 2–4 | ✅ done (Week 4 = ongoing tuning) | Email summary added to the daily brief |
| 2. YouTube agent | 5–7 | ✅ done | Video TL;DRs added to the daily brief |
| 3. Orchestration + scheduling | 8–9 | ✅ done | LangGraph parallel runs (+ Studio visual debugger) + 08:00 launchd job |
| R1. Reminders | — | ✅ done | `/settings` UI + full CRUD API for recurring reminders |
| R2. WhatsApp assistant | — | ✅ done | AI reply suggestions via Telegram inline buttons, approval loop |
| 4. Polish (optional) | 10–12 | ⏳ | History UI, observability, docs, Dockerize |

**Total realistic timeline: ~10 weeks to a fully-working daily brief, ~12 weeks with polish.**
**Total effort: ~35–50 hours.**

> Phases R1 and R2 were built outside the original plan and represent significant
> scope expansion. They're tracked here for completeness.

If you only have 3 hours in a given week, skip the "stretch" tasks and just
hit the **must-do** ones — every week is structured that way.

---

## Phase 0 — Personal setup

You don't need to write any code in this phase; everything you need was
delivered in steps 1–4. This is **your one-time onboarding** to the agent.

### Week 1 — Onboarding (~3 hrs)  ✅ done

**Must-do** (~2 hrs)
- [x] Create a Python 3.11 venv in `backend/` and `pip install -e .`
- [x] Copy `.env.example` → `.env` and fill in `OPENAI_API_KEY`
- [x] Create a Telegram bot via `@BotFather`, run `scripts/test_telegram.py`,
      paste the discovered `TELEGRAM_CHAT_ID` back into `.env`
- [x] Create the Google Cloud project, enable **Calendar API** (Gmail +
      YouTube enabled at the same time for convenience), download
      `credentials.json`, run `scripts/google_login.py`
- [x] `uvicorn app.main:app --reload` + `curl -X POST /run-now` → confirm a
      Telegram message arrives with today's calendar

**Stretch** (~1 hr) — *handled in Week 9 instead*
- [x] Install the launchd plist *(done — installed via `launchctl bootstrap
      gui/$(id -u)`)*
- [ ] ~~If your Mac sleeps overnight: `sudo pmset repeat wakeorpoweron MTWRFSU 07:55:00`~~
      *(opted out — happy to receive the brief whenever the Mac next wakes)*

**Definition of done**
You wake up the next morning and the Telegram message arrives at 08:00 with
your real calendar. No code written yet.

> Why this matters: phase 0 catches 90% of "it doesn't work on my machine"
> issues *before* you start building the agents that depend on the same
> plumbing. Don't skip it.

---

## Phase 1 — Gmail agent (Weeks 2–4)

### Week 2 — Gmail data layer (~4 hrs)  ✅ done

**Must-do**
- [x] Enable **Gmail API** in Google Cloud Console
- [x] Delete `data/token.json` and re-run `scripts/google_login.py` so the
      Gmail scope is added to the cached token
- [x] Implement `app/tools/gmail.py`
- [x] Add a `scripts/test_gmail.py` smoke-test script

**Stretch**
- [x] Quoted-reply stripper (regex on `On ... wrote:` and `>` lines)
- [x] Skip messages from yourself

**DOD**: `python scripts/test_gmail.py` prints clean sender/subject/body for
recent mail. ✅

### Week 3 — Gmail summarizer + integration (~4 hrs)  ✅ done

**Must-do**
- [x] Implement `app/agents/gmail_agent.py` (Action / FYI / Skim buckets,
      `gpt-4o-mini`, structured prompt)
- [x] Wire `summarize_gmail()` into `app/graph.py` (the placeholder lived
      there, not `workflow.py`, after the LangGraph rewrite)
- [x] Trigger `/run-now` and confirm Telegram shows real email summaries

**Stretch**
- [x] Cost guardrail: 20-per-batch × 2 batches = 40 messages max per run

**DOD**: Telegram message includes Gmail summary. ✅

### Week 4 — Iterate on Gmail (~3 hrs, buffer-friendly)  🟡 ongoing

You'll be unhappy with the first few briefs. That's expected and totally
fine. Spend the week tuning.

**Must-do**
- [ ] Tighten the prompt based on the actual output you've seen for a few days
      *(needs 2–3 real briefs to evaluate)*
- [x] Filter out promotions/notifications more aggressively — `GMAIL_QUERY`
      now excludes `category:promotions` by default
- [x] Empty-inbox path returns "No new inbox messages. ✨" instead of an
      empty section

**Stretch**
- [x] `GMAIL_IGNORE_FROM` env list for senders you never want summarized

**DOD**: Look at three consecutive morning briefs. If you'd send them to a
friend as "what's happening", phase 1 is done. *(in progress — first brief
landed today)*

---

## Phase 2 — YouTube agent (Weeks 5–7)

### Week 5 — YouTube data layer (~4 hrs)

**Must-do**
- [ ] Enable **YouTube Data API v3** in Google Cloud Console
- [ ] Re-run `scripts/google_login.py` to add the YouTube scope
- [ ] Populate `config/channels.yaml` with 3–5 channels you actually watch
- [ ] Implement `app/tools/youtube.py`:
  - Resolve channel handles (`@fireship`) → uploads playlist
  - Fetch videos `publishedAfter = yesterday 00:00 local`
  - For each video, try `youtube-transcript-api` for captions
  - Skip videos with no captions (per your earlier choice)
- [ ] `scripts/test_youtube.py` that prints `[channel] [title] [has_transcript]`

**Stretch**
- [ ] Cache `(handle → channel_id)` lookups in SQLite so you don't burn quota
      on `channels.list` every run

**DOD**: You can list yesterday's new videos with transcript availability
without ever calling the LLM.

### Week 6 — YouTube summarizer + dedup (~4 hrs)

**Must-do**
- [ ] Implement `app/agents/youtube_agent.py`:
  - For each new video with a transcript, one OpenAI call per video with the
    prompt *"TL;DR in 1 sentence, then 3 key bullets, then 'skip if X'"*
  - Use `gpt-4o-mini`. Truncate transcripts to ~15k tokens with a "...middle
    elided..." marker so 3-hour podcasts don't break the bank
- [ ] Insert a row into `seen_items(kind="video", external_id=video_id)`
      after each summary so the same video is never summarized twice
- [ ] Replace the YouTube placeholder in `workflow.py`

**Stretch**
- [ ] Sort by channel, then by published time (more predictable formatting)

**DOD**: Telegram message includes YouTube TL;DRs and re-running `/run-now`
twice in a row produces the same brief the second time (dedup works).

### Week 7 — Polish + transcripts edge cases (~3 hrs, buffer-friendly)

**Must-do**
- [ ] Handle the case where `youtube-transcript-api` raises
      `TranscriptsDisabled`, `NoTranscriptFound`, `VideoUnavailable` — return
      `None` cleanly and skip the video
- [ ] If *no* channels had new uploads, return *"📺 No new uploads"* instead
      of an empty section
- [ ] Decide your real channel list. You probably picked 5 in week 5 and have
      since realized 2 of them post 10 videos/day. Trim.

**Stretch**
- [ ] Add the published date + duration to the brief line
- [ ] Add `youtube.url` (`https://youtu.be/{id}`) for one-tap access

**DOD**: A full week of briefs where the YouTube section is consistently
useful (not too long, not too sparse).

---

## Phase 3 — Orchestration + reliable scheduling (Weeks 8–9)

### Week 8 — LangGraph rewrite + Studio (~4 hrs)  ✅ done

The three agents work sequentially today. Promoting to LangGraph makes them
run in parallel (≈3× faster), gives you proper observability + graceful
partial-failure handling, **and** unlocks LangGraph Studio as a free visual
debugger.

**Must-do**
- [x] Create `backend/app/graph.py` with a `BriefState` TypedDict and a
      `StateGraph` that fans
      `START → [calendar | gmail | youtube] → compose → deliver → END`.
      Export the compiled graph at module scope as `graph = builder.compile()`.
- [x] Each agent node catches its own exceptions and writes a
      `_(section failed: …)_` placeholder into state — never crashes the graph.
- [x] Refactor `workflow.run_morning_brief()` to call `graph.invoke({})`
      instead of calling functions in sequence. Keep the `Run`/`Brief`
      DB bookkeeping in `workflow.py` — the graph stays pure.
- [x] Add `langgraph-cli[inmem]>=0.1.55` to the `dev` extras in
      `backend/pyproject.toml`.
- [x] Create `langgraph.json` at the **repo root**:

      ```json
      {
        "dependencies": ["./backend"],
        "graphs": { "morning_brief": "./backend/app/graph.py:graph" },
        "env": "./backend/.env",
        "python_version": "3.11"
      }
      ```

- [ ] *(optional — only when you want it)* `pip install -e ".[dev]"` from
      `backend/`, then `langgraph dev` from the repo root. Click the printed
      Studio URL and confirm you can see the graph render, submit `{}`, and
      watch all five nodes execute.

**Stretch**
- [ ] Wire LangGraph's SQLite checkpointer to the same DB so failed runs are
      resumable and Studio gets time-travel debugging:
      `from langgraph.checkpoint.sqlite import SqliteSaver` → pass to
      `.compile(checkpointer=...)`. Overkill for this app, but the pattern
      is useful.
- [ ] Sign up for a free LangSmith account and set
      `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY=...` in `.env` so
      every run (including production 08:00 launchd runs) shows up as a
      trace alongside the graph view.

**DOD**: `/run-now` produces the same Telegram message as before, you can
see in logs that the three fetches ran in parallel, **and** `langgraph dev`
opens Studio with a clickable graph that runs end-to-end against your real
credentials.

### Week 9 — Bulletproof scheduling (~3 hrs)  ✅ done (alarm test pending)

**Must-do**
- [x] Install the launchd plist and verify it runs — confirmed via
      `launchctl kickstart` test-fire delivering a real Telegram brief
- [x] `data/launchd.out.log` / `data/launchd.err.log` are getting written
- [ ] Failure alarm: temporarily break something on purpose (e.g. set
      `OPENAI_API_KEY=sk-bad`) and confirm the ⚠️ fallback Telegram fires.
      *(quick test, do this whenever convenient)*

**Notes on the install**
- macOS deprecated `launchctl load`; use
  `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<plist>` instead.
- A copied plist may carry the `com.apple.quarantine` extended attribute;
  clear with `xattr -c <plist>` before bootstrap.
- If `bootstrap` says "Input/output error", the service may already be
  loaded (silent earlier success). Verify with
  `launchctl print gui/$(id -u)/com.personalassistant.morning` and clean
  up with `launchctl bootout gui/$(id -u)/com.personalassistant.morning`.

**Stretch**
- [ ] Add a `GET /history.html` index page so you can scroll past briefs
      from your phone

**DOD**: A full week with zero manual `/run-now` calls. The brief just shows
up at 08:00. *(in progress — first automated run scheduled tomorrow)*

---

## Phase 4 — Polish & options (Weeks 10–12)

Everything in this phase is **optional**. By the end of week 9 the app
already does what you originally asked for.

### Week 10 — History UI + observability (~3 hrs)
- [ ] Pretty up `/history` to a real HTML index instead of JSON
- [ ] Add per-agent timing in the `Run` row (so you can see "Gmail took
      6.2s today")
- [ ] Add a `/metrics` endpoint with run counts, success rate, last-error

### Week 11 — Robustness (~3 hrs)
- [ ] Tighten the MarkdownV2 escaper for Telegram (long-standing minor
      annoyance — emoji + parentheses sometimes confuse it)
- [ ] Token-budget guardrails: log estimated OpenAI cost per run; alert if a
      single run exceeds $0.50
- [ ] OAuth health check: a tiny endpoint that proves all three Google scopes
      still work, so you find out about an expired token at lunch instead of
      tomorrow at 8 AM

### Week 12 — Choose your adventure (~3–5 hrs)
Pick whichever of these matters most to you:
- **Dockerize**: single `docker compose up` for the whole thing
- **Hosted**: move to Fly.io / Railway so it runs even with the laptop closed
- **More sources**: weather (OpenWeather), news (Hacker News API), GitHub
  notifications, Slack DMs
- **Conversational brief**: replace the deterministic `compose_agent` with
  an LLM that smooths the three sections into a single narrative

---

## What "done enough" looks like

You can stop after **Phase 2 (Week 7)** and still have a valuable daily
brief if you commit to running `/run-now` manually. Phase 3 makes it
zero-touch. Phase 4 is polish for its own sake.

Realistic completion targets:

| If you put in… | …you'll have | …by week |
|---------------|--------------|----------|
| 3 hrs/week minimum | Calendar + Gmail working | Week 4 |
| 3 hrs/week minimum | Calendar + Gmail + YouTube working | Week 8 |
| 4 hrs/week average | Fully scheduled, hands-off daily brief | Week 9 |
| 5 hrs/week average | Polished v1 with history UI | Week 11 |

---

---

## Phase R1 — Reminders  ✅ done

Built outside the original milestone plan.

**What was built**
- `Reminder` ORM model (`reminders` table): `label`, `frequency` (daily/weekly/monthly),
  `day_of_week`, `day_of_month`, `time`, `time_end`, `enabled`, `created_at`.
- Full CRUD REST API in `main.py`: `GET/POST /reminders`, `PATCH /reminders/{id}`,
  `DELETE /reminders/{id}`.
- Mobile-friendly `/settings` HTML page (self-contained, no JS framework): toggle
  switches to enable/disable, trash-icon delete, inline add form with frequency picker.
- Root `/` redirects to `/settings`.

**What remains**
- [ ] Wire enabled reminders into `compose_agent` so they appear in the morning brief.
- [ ] Reminder-specific Telegram alerts (fire at the reminder's configured time, not
      only at 08:00 briefing time).

---

## Phase R2 — WhatsApp reply assistant  ✅ done

Built outside the original milestone plan.

**What was built**
- Node.js bridge integration: `POST /whatsapp/incoming` (new DM) and
  `POST /whatsapp/silence-alert` (watchdog).
- `app/agents/whatsapp_agent.py`: calls `gpt-4o-mini` to draft a contextual reply.
- `PendingReply` ORM model: tracks incoming message, AI suggestion, approval status,
  and the Telegram `message_id` used for reply matching.
- `app/tools/whatsapp.py`: HTTP client for `send_whatsapp_message()` to the bridge.
- `app/tools/telegram.py` extended: `send_wa_notification()` with inline keyboard
  (✅ Send / ✏️ Edit / ❌ Skip buttons), `answer_callback_query()`,
  `edit_message_reply_markup()`.
- `app/telegram_poller.py`: daemon thread long-polling `getUpdates`; handles button
  taps (`wa_send`, `wa_edit`, `wa_skip`), reply-to-message approvals, and `/pending`
  command.
- Started at FastAPI lifespan alongside the scheduler.

**What remains**
- [ ] `/pending` UI: add a `/settings`-style web view of open pending replies.
- [ ] Failure alarm test: confirm silence-alert fires correctly end-to-end.
- [ ] Configurable silence threshold (`WHATSAPP_SILENCE_HOURS` env var).

---

## Risks & how the plan handles them

| Risk | Mitigation in the plan |
|------|------------------------|
| You skip a week | Phase boundaries are buffer-friendly; every "Week N+2" is iteration, not new code |
| Google OAuth verification flow changes | All three Google APIs use the same Desktop OAuth flow — debug once in Phase 0 |
| OpenAI costs balloon | Per-video summarization caps + `gpt-4o-mini` baseline keep daily cost < $0.20 |
| You realize you want a feature mid-build | Phase 4 is intentionally a "pick your own" slot |
| You lose motivation around week 5 | By then Gmail summaries are already arriving daily — you have something real to come back to |

---

## Tracking

Open this file when you sit down each weekend. Check the boxes as you go.
If you fall a week behind, do not re-plan — just slide everything by a week.
The plan assumes that.
