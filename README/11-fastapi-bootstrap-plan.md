# FastAPI Bootstrap Plan

This guide is a practical starting point for implementing the MVP backend using FastAPI.

## 1) Stack choices (MVP)

- FastAPI + Uvicorn
- Pydantic (request/response models)
- SQLModel (or SQLAlchemy) + Alembic
- PostgreSQL
- httpx (Google API calls)
- APScheduler (daily briefing trigger)

## 2) Suggested project structure

```text
backend/
  app/
    api/
      v1/
        auth.py
        sync.py
        tasks.py
        briefing.py
        dashboard.py
    core/
      config.py
      security.py
      database.py
      logging.py
    models/
      user.py
      oauth_token.py
      email_message.py
      calendar_event.py
      task.py
      daily_briefing.py
    schemas/
      common.py
      auth.py
      sync.py
      task.py
      briefing.py
      dashboard.py
    services/
      google_oauth_service.py
      gmail_service.py
      calendar_service.py
      task_derivation_service.py
      prioritization_service.py
      briefing_service.py
    jobs/
      scheduler.py
      daily_briefing_job.py
    main.py
  alembic/
  tests/
  requirements.txt
  .env.example
```

## 3) Initial package set

Use this as a starting list:

- fastapi
- uvicorn[standard]
- pydantic
- pydantic-settings
- sqlmodel
- sqlalchemy
- alembic
- psycopg[binary]
- httpx
- python-dotenv
- apscheduler
- cryptography
- python-jose
- tenacity
- pytest
- pytest-asyncio

## 4) Environment variables (`.env.example`)

```env
APP_ENV=development
APP_PORT=8000
APP_BASE_URL=http://localhost:8000
FRONTEND_BASE_URL=http://localhost:3000

DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/personal_assistant

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
GOOGLE_SCOPES=https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/calendar.readonly

TOKEN_ENCRYPTION_KEY=
INTERNAL_JOB_TOKEN=

BRIEFING_SEND_CHANNEL=email
BRIEFING_RUN_HOUR=7
BRIEFING_RUN_MINUTE=0
USER_TIMEZONE=UTC
```

## 5) Day 1 implementation checklist

### Foundation

- [ ] Create `backend/` app structure.
- [ ] Add `main.py` and health endpoint (`GET /health`).
- [ ] Set up config loader from environment.
- [ ] Configure DB session and base models.

### Auth

- [ ] Implement `POST /api/v1/auth/google/start`.
- [ ] Implement `GET /api/v1/auth/google/callback`.
- [ ] Persist `users` and `oauth_tokens`.
- [ ] Encrypt refresh tokens before storing.

### Data

- [ ] Create first Alembic migration for core tables.
- [ ] Verify migration up/down locally.

### Validation

- [ ] Confirm OpenAPI docs load (`/docs`).
- [ ] Ensure route response schemas match `09-api-contracts.md`.

## 6) First routes to build (in order)

1. `POST /auth/google/start`
2. `GET /auth/google/callback`
3. `POST /sync/gmail`
4. `POST /sync/calendar`
5. `POST /tasks/recompute`
6. `GET /briefing/today`

Keep all routes behind a temporary single-user context in MVP (simpler and faster).

## 7) Service boundaries to keep clean

- `gmail_service`: fetch and normalize Gmail records only.
- `calendar_service`: fetch and normalize calendar records only.
- `task_derivation_service`: create/update tasks from normalized sources.
- `prioritization_service`: compute scores and rank outputs.
- `briefing_service`: format and persist daily briefing.

Do not mix API code with business logic; route handlers should remain thin.

## 8) Minimal testing strategy (Week 1)

- Unit test scoring rules with fixed fixtures.
- Integration test:
  - sync insert/upsert behavior
  - task recompute behavior
  - briefing generation output shape
- Add one regression test for dedupe (`provider_message_id` uniqueness).

## 9) Week 1 done criteria

- Google auth works end to end.
- Gmail and calendar sync write normalized records.
- Task derivation and priority scoring produce useful Today list.
- Daily briefing endpoint returns structured markdown content.
- Core API contracts are stable and documented.
