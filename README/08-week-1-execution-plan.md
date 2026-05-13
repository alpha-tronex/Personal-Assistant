# Week 1 Execution Plan

This plan maps implementation tasks to milestones so progress is visible and measurable each day.

## Day 1 - Foundation and auth (Milestone 1)

### Objectives

- Create backend project scaffold.
- Set up Google OAuth for Gmail and Calendar read access.
- Implement secure token persistence.

### Tasks

- [ ] Initialize backend app and environment config.
- [ ] Register Google OAuth app and configure redirect URIs.
- [ ] Implement `/auth/google/start` and `/auth/google/callback`.
- [ ] Create `users` and `oauth_tokens` tables.
- [ ] Store encrypted refresh token and expiry metadata.
- [ ] Add basic health check endpoint.

### Exit criteria

- User can connect Google account successfully.
- Token row exists and can be refreshed without manual login.

---

## Day 2 - Gmail ingestion (Milestone 2)

### Objectives

- Pull Gmail messages and persist normalized records.

### Tasks

- [ ] Implement Gmail sync service with query window (`newer_than:14d`).
- [ ] Normalize message payload into `email_messages`.
- [ ] Add idempotent upsert by `provider_message_id`.
- [ ] Capture labels, unread status, and timestamps.
- [ ] Add sync log output (fetched, written, failed).

### Exit criteria

- Manual sync pulls messages and writes them without duplicates.

---

## Day 3 - Calendar ingestion (Milestone 2)

### Objectives

- Pull upcoming events and persist normalized records.

### Tasks

- [ ] Implement Calendar sync service for now-1d to now+14d.
- [ ] Normalize event payload into `calendar_events`.
- [ ] Add idempotent upsert by `provider_event_id`.
- [ ] Persist title, attendees, location, and event times.
- [ ] Include sync metrics in logs.

### Exit criteria

- Manual sync pulls and updates events correctly on repeated runs.

---

## Day 4 - Task derivation engine v1 (Milestone 3)

### Objectives

- Convert emails/events into actionable tasks.

### Tasks

- [ ] Create task derivation pipeline for changed sources.
- [ ] Map categories: Development, Customer, Finance, Marketing, Admin.
- [ ] Map action types: Reply, Pay, Build, Schedule, Review.
- [ ] Assign urgency buckets: Today, ThisWeek, Later.
- [ ] Write derived items into `tasks` with source references.

### Exit criteria

- New emails/events produce sensible tasks with category and urgency.

---

## Day 5 - Prioritization and ranking (Milestone 3)

### Objectives

- Score and rank tasks so only high-value work surfaces daily.

### Tasks

- [ ] Implement base scoring rules from `04-prioritization-rules.md`.
- [ ] Add penalties for newsletters and non-actionable notifications.
- [ ] Enforce output constraints (max 10 for Today).
- [ ] Ensure required mix (top dev, top customer, finance due soon).
- [ ] Add recompute endpoint (`/tasks/recompute`).

### Exit criteria

- Ranked Today list is concise, actionable, and stable across reruns.

---

## Day 6 - Daily briefing generation (Milestone 4)

### Objectives

- Generate and store a concise daily briefing.

### Tasks

- [ ] Implement briefing assembler using ranked tasks and calendar.
- [ ] Create `daily_briefings` writer for today’s markdown.
- [ ] Build `/briefing/today` and `/briefing/send`.
- [ ] Add scheduled run at 07:00 (local timezone).
- [ ] Validate formatting against `05-briefing-template.md`.

### Exit criteria

- Briefing is generated automatically and readable in under 2 minutes.

---

## Day 7 - Dashboard starter UI (Milestone 5)

### Objectives

- Ship usable UI for daily execution.

### Tasks

- [ ] Build simple dashboard with 4 panels: Develop, Customers, Finance, Calendar.
- [ ] Display ranked tasks and key event prep items.
- [ ] Add actions: mark done, snooze, open source item.
- [ ] Add empty/error/loading states.
- [ ] Verify full end-to-end flow from sync to UI.

### Exit criteria

- User can run the day from dashboard and briefing only.

---

## Daily operating cadence

- Morning (10-15 min): review briefing, commit top 3 outcomes.
- Midday (5 min): quick resync and reprioritize.
- End of day (10 min): mark done/snooze and prepare tomorrow.

## Week 1 success definition

- OAuth and sync are reliable.
- Task derivation and scoring produce useful priorities.
- Daily briefing arrives on schedule.
- Basic dashboard supports daily execution workflow.
