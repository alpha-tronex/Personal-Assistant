# Day 1 Task Board

Focus: foundations, auth, and database readiness.

## Priority legend

- P0: Must complete today
- P1: Should complete today
- P2: Nice to have

## Time budget (target)

- Total: 6 to 8 focused hours
- Buffer: 60 minutes for setup/debugging

## Board

## 1) Environment and runtime

- [ ] **P0** Create `backend/` structure and Python virtual environment (30 min)
- [ ] **P0** Install core dependencies and verify imports (30 min)
- [ ] **P1** Add `.env` from template and validate config loading (20 min)

Done when:
- You can run `uvicorn app.main:app --reload` without errors.

## 2) Base API scaffold

- [ ] **P0** Add `app/main.py` with `/health` endpoint (20 min)
- [ ] **P0** Add v1 router modules (`auth`, `sync`, `tasks`, `briefing`, `dashboard`) (40 min)
- [ ] **P1** Confirm `/docs` loads and shows your routes (10 min)

Done when:
- `GET /health` returns success and Swagger UI is accessible.

## 3) Database readiness

- [ ] **P0** Configure SQLModel engine/session (25 min)
- [ ] **P0** Initialize Alembic and wire metadata imports (35 min)
- [ ] **P0** Generate and apply first migration (40 min)
- [ ] **P1** Verify tables exist and constraints match schema doc (25 min)

Done when:
- `alembic upgrade head` runs cleanly and core tables are present.

## 4) Google OAuth foundation

- [ ] **P0** Create Google Cloud project and enable Gmail + Calendar APIs (20 min)
- [ ] **P0** Set OAuth consent screen and add your account as test user (20 min)
- [ ] **P0** Create OAuth web credentials and set callback URI (15 min)
- [ ] **P0** Implement `POST /api/v1/auth/google/start` (30 min)
- [ ] **P0** Implement callback skeleton `GET /api/v1/auth/google/callback` with state validation (35 min)
- [ ] **P1** Persist placeholder token payload to `oauth_tokens` table (30 min)

Done when:
- Start endpoint returns valid auth URL and callback validates state flow.

## 5) Risk controls and hygiene

- [ ] **P1** Add central error response shape (`error.code`, `error.message`) (20 min)
- [ ] **P1** Add basic request logging (15 min)
- [ ] **P2** Add pre-commit style checks (ruff/black optional) (20 min)

Done when:
- Common failures return predictable JSON error format.

## End-of-day demo checklist

- [ ] Show `/health` response
- [ ] Show `/docs` route list
- [ ] Run migration status and current head
- [ ] Hit `/auth/google/start` and open returned URL
- [ ] Complete OAuth callback once and verify DB row written

## If blocked, fallback sequence

1. Skip token encryption temporarily (store plain in local only) and continue flow.
2. Mock callback token exchange response and complete DB persistence.
3. Move to Day 2 only after auth request/response contract is stable.

## Day 1 success criteria

- App boots locally.
- DB migrations are working.
- OAuth route flow is functional end to end at skeleton level.
- Foundation is ready for Day 2 Gmail ingestion.
