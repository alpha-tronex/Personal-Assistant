# Architecture

## High-level components

1. Ingestion layer
   - Gmail sync job
   - Calendar sync job
2. Normalization layer
   - Convert API payloads into consistent internal models
3. Task derivation layer
   - Extract actionable items from messages and events
   - Assign category, action type, and urgency
4. Prioritization layer
   - Score and rank tasks for the day
5. Delivery layer
   - Daily briefing message
   - Dashboard API and UI

## Data flow

1. Scheduler triggers sync jobs.
2. Raw data is fetched from Google APIs.
3. Data is normalized and stored.
4. Task derivation generates and updates tasks.
5. Prioritization computes scores.
6. Briefing generator produces a daily summary.
7. User views dashboard and receives morning briefing.

## Suggested stack

- Backend: FastAPI (Python) or Node/Express
- Database: Postgres (SQLite acceptable for local prototype)
- Scheduler: cron or cloud scheduler
- Frontend: Next.js minimal UI
- Auth: Google OAuth2
