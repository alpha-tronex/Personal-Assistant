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

| Phase | Weeks | Outcome |
|------|-------|---------|
| 0. Personal setup (you only) | 1 | OAuth + Telegram working, calendar brief arrives daily |
| 1. Gmail agent | 2–4 | Email summary added to the daily brief |
| 2. YouTube agent | 5–7 | Video TL;DRs added to the daily brief |
| 3. Orchestration + scheduling | 8–9 | LangGraph parallel runs + 08:00 launchd job |
| 4. Polish (optional) | 10–12 | History UI, observability, docs, Dockerize |

**Total realistic timeline: ~10 weeks to a fully-working daily brief, ~12 weeks with polish.**
**Total effort: ~35–50 hours.**

If you only have 3 hours in a given week, skip the "stretch" tasks and just
hit the **must-do** ones — every week is structured that way.

---

## Phase 0 — Personal setup

You don't need to write any code in this phase; everything you need was
delivered in steps 1–4. This is **your one-time onboarding** to the agent.

### Week 1 — Onboarding (~3 hrs)

**Must-do** (~2 hrs)
- [ ] Create a Python 3.11 venv in `backend/` and `pip install -e .`
- [ ] Copy `.env.example` → `.env` and fill in `OPENAI_API_KEY`
- [ ] Create a Telegram bot via `@BotFather`, run `scripts/test_telegram.py`,
      paste the discovered `TELEGRAM_CHAT_ID` back into `.env`
- [ ] Create the Google Cloud project, enable **Calendar API only** (for now),
      download `credentials.json`, run `scripts/google_login.py`
- [ ] `uvicorn app.main:app --reload` + `curl -X POST /run-now` → confirm a
      Telegram message arrives with today's calendar

**Stretch** (~1 hr)
- [ ] Install the launchd plist (see `launchd/com.personalassistant.morning.plist`)
      so the brief runs at 08:00 every day — calendar-only is already useful
- [ ] If your Mac sleeps overnight: `sudo pmset repeat wakeorpoweron MTWRFSU 07:55:00`

**Definition of done**
You wake up the next morning and the Telegram message arrives at 08:00 with
your real calendar. No code written yet.

> Why this matters: phase 0 catches 90% of "it doesn't work on my machine"
> issues *before* you start building the agents that depend on the same
> plumbing. Don't skip it.

---

## Phase 1 — Gmail agent (Weeks 2–4)

### Week 2 — Gmail data layer (~4 hrs)

**Must-do**
- [ ] Enable **Gmail API** in Google Cloud Console
- [ ] Delete `data/token.json` and re-run `scripts/google_login.py` so the
      Gmail scope is added to the cached token
- [ ] Implement `app/tools/gmail.py`:
  - List messages with `q="newer_than:2d in:inbox"`
  - For each message, fetch `From`, `Subject`, `Date`, snippet, and plain-text
    body (decode `text/plain` part; strip if HTML-only)
  - Return a typed `GmailMessage` dataclass list
- [ ] Add a `scripts/test_gmail.py` that just prints the last 10 messages so
      you can verify auth + parsing without touching the LLM

**Stretch**
- [ ] Quoted-reply stripper (regex on `On ... wrote:` and `>` lines)
- [ ] Skip messages from yourself (don't summarize your own sent mail that
      ends up in the inbox via lists)

**DOD**: `python scripts/test_gmail.py` prints clean sender/subject/body for
recent mail.

### Week 3 — Gmail summarizer + integration (~4 hrs)

**Must-do**
- [ ] Implement `app/agents/gmail_agent.py`:
  - Call the tool, drop empty/auto-generated mail (e.g. calendar invites
    you already see in the calendar section)
  - Send everything in **one** OpenAI call with a structured prompt:
    *"Bucket each message into Action / FYI / Skim. Output markdown."*
  - Use `gpt-4o-mini` (cheap, plenty smart for this)
- [ ] Replace the `gmail_section = "_(not wired)_"` placeholder in
      `app/workflow.py` with a call to `summarize_gmail()`
- [ ] Trigger `/run-now` and confirm Telegram now shows real email summaries

**Stretch**
- [ ] Cost guardrail: cap the prompt at ~30 messages; if more, summarize in
      batches of 20

**DOD**: Telegram message tomorrow morning includes Gmail summary.

### Week 4 — Iterate on Gmail (~3 hrs, buffer-friendly)

You'll be unhappy with the first few briefs. That's expected and totally
fine. Spend the week tuning.

**Must-do**
- [ ] Tighten the prompt based on the actual output you've seen for a few days
- [ ] Filter out promotions/notifications more aggressively (or don't — your
      call). Easy lever: add Gmail labels to exclude in the search query
- [ ] Add basic error handling: if Gmail returns 0 messages, return *"📧 No
      new email"* instead of an empty section

**Stretch**
- [ ] Add a configurable `IGNORE_FROM` list in `.env` for senders you never
      want summarized (recruiters, your weekly newsletter, etc.)

**DOD**: Look at three consecutive morning briefs. If you'd send them to a
friend as "what's happening", phase 1 is done. If not, spend more time here
before moving on.

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

### Week 8 — LangGraph rewrite (~4 hrs)

The three agents work sequentially today. Promoting to LangGraph makes them
run in parallel (≈3× faster) and gives you proper observability + graceful
partial-failure handling.

**Must-do**
- [ ] Create `app/graph.py` with a `BriefState` TypedDict and a `StateGraph`
      that fans `START → [calendar | gmail | youtube] → compose → deliver → END`
- [ ] Compile the graph at module load
- [ ] Update `workflow.run_morning_brief()` to invoke the graph instead of
      calling functions in sequence
- [ ] Each agent node should catch its own exceptions and write a
      `_(section failed: …)_` placeholder into state — never crash the graph

**Stretch**
- [ ] Wire LangGraph's SQLite checkpointer to the same DB so failed runs are
      resumable (overkill for this app, but the pattern is useful)
- [ ] Add a `langgraph.json` at `backend/` so you can open the graph
      in **LangGraph Studio** and watch state flow node-by-node (n8n-style
      visual debugger). Once `app/graph.py` exports a compiled `graph`
      symbol, this file is all you need:

      ```json
      {
        "dependencies": ["."],
        "graphs": {
          "morning_brief": "./app/graph.py:graph"
        },
        "env": ".env"
      }
      ```

      Then `langgraph dev` from `backend/` opens Studio in the
      browser. Useful while iterating on the graph; not needed at runtime.

**DOD**: `/run-now` produces the same Telegram message as before, but you
can see in logs that the three fetches ran in parallel.

### Week 9 — Bulletproof scheduling (~3 hrs)

**Must-do**
- [ ] If you didn't already in week 1: install the launchd plist and verify
      it runs at 08:00 next morning
- [ ] Add structured logs to `data/launchd.out.log` so you can see what
      happened overnight
- [ ] Failure alarm: if `run_morning_brief()` raises, the Telegram fallback
      ping already exists — make sure you've actually seen it work by
      temporarily breaking something on purpose

**Stretch**
- [ ] Add a `GET /history.html` index page so you can scroll past briefs
      from your phone

**DOD**: A full week with zero manual `/run-now` calls. The brief just shows
up at 08:00.

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
