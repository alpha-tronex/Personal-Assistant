# Local Dev Setup (FastAPI + Postgres)

This guide helps you get a reliable local environment running quickly.

## 1) Prerequisites

- Python 3.11+ installed
- Docker Desktop installed and running
- Git installed

Optional:
- `make` for shortcut commands

## 2) Project layout expectation

```text
Personal Assistant/
  README/
  backend/
```

If `backend/` does not exist yet, create it first.

## 3) Start PostgreSQL with Docker

From `backend/` (or repo root), run:

```bash
docker run --name pa-postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=personal_assistant \
  -p 5432:5432 \
  -d postgres:16
```

Useful commands:

```bash
docker ps
docker logs pa-postgres
docker stop pa-postgres
docker start pa-postgres
```

## 4) Create Python virtual environment

From `backend/`:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## 5) Install backend dependencies

If you already have `requirements.txt`:

```bash
pip install -r requirements.txt
```

If you are still bootstrapping, install core packages:

```bash
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings sqlmodel sqlalchemy alembic "psycopg[binary]" httpx apscheduler cryptography python-jose tenacity python-dotenv pytest pytest-asyncio
```

Then freeze:

```bash
pip freeze > requirements.txt
```

## 6) Configure environment variables

Create `.env` in `backend/` from your template:

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
INTERNAL_JOB_TOKEN=local-internal-token
```

Generate `TOKEN_ENCRYPTION_KEY` with a secure random value.

## 7) Initialize migrations and apply schema

From `backend/`:

```bash
alembic init alembic
alembic revision --autogenerate -m "create core mvp tables"
alembic upgrade head
```

If Alembic is already initialized, only run:

```bash
alembic revision --autogenerate -m "..."
alembic upgrade head
```

## 8) Run FastAPI app

From `backend/`:

```bash
uvicorn app.main:app --reload --port 8000
```

Verify:

- API health: `http://localhost:8000/health`
- Swagger docs: `http://localhost:8000/docs`

## 9) Quick smoke test checklist

- [ ] `GET /health` returns `{ "ok": true }`
- [ ] `/docs` page loads
- [ ] `POST /api/v1/auth/google/start` returns `auth_url` and `state`
- [ ] Database accepts writes for `users` and `oauth_tokens`
- [ ] `POST /api/v1/sync/gmail` returns queued job response
- [ ] `POST /api/v1/sync/calendar` returns queued job response

## 10) Common local issues

### Port 5432 already in use

Use another host port:

```bash
-p 5433:5432
```

And update `DATABASE_URL` accordingly.

### `ModuleNotFoundError: app`

Cause:
- Running commands outside `backend/`.

Fix:
- Run from `backend/` or set `PYTHONPATH` correctly.

### `psycopg` connection refused

Cause:
- Postgres container is not running or not ready.

Fix:
- Check `docker ps` and `docker logs pa-postgres`.

### OAuth redirect mismatch

Cause:
- Google Console redirect URI differs from `.env`.

Fix:
- Make them exactly identical.

## 11) Optional productivity shortcuts (Makefile)

You can add these targets:

- `make up-db` -> start Postgres container
- `make migrate` -> alembic upgrade head
- `make dev` -> run uvicorn reload server
- `make test` -> run pytest

This keeps your daily workflow fast and repeatable.
