# Alembic Migrations Guide (FastAPI + SQLModel)

This guide covers initial Alembic setup and your first schema migration for MVP tables.

## 1) Install requirements

Ensure these are installed in your backend environment:

- alembic
- sqlalchemy
- sqlmodel
- psycopg[binary]

## 2) Initialize Alembic

From `backend/`:

```bash
alembic init alembic
```

This creates:
- `alembic.ini`
- `alembic/`
- `alembic/env.py`
- `alembic/versions/`

## 3) Configure DB URL

In `alembic.ini`, set a placeholder URL (can be overridden in `env.py`):

```ini
sqlalchemy.url = postgresql+psycopg://postgres:postgres@localhost:5432/personal_assistant
```

Recommended: wire it to your app settings in `alembic/env.py` instead of hardcoding.

## 4) Connect Alembic to SQLModel metadata

In `alembic/env.py`:

1. Import app settings and SQLModel.
2. Import all model modules so metadata is populated.
3. Set `target_metadata = SQLModel.metadata`.

Conceptually:

```python
from sqlmodel import SQLModel
from app.core.config import settings
from app.models import user, oauth_token, email_message, calendar_event, task, daily_briefing

target_metadata = SQLModel.metadata
config.set_main_option("sqlalchemy.url", settings.database_url)
```

Important:
- If models are not imported, autogenerate may miss tables.

## 5) Create first migration

From `backend/`:

```bash
alembic revision --autogenerate -m "create core mvp tables"
```

Review generated migration in `alembic/versions/*_create_core_mvp_tables.py`.

Check:
- correct table names
- proper nullability
- indexes and uniqueness constraints

## 6) Apply migration

```bash
alembic upgrade head
```

Rollback one step if needed:

```bash
alembic downgrade -1
```

## 7) MVP tables expected in first migration

- `users`
- `oauth_tokens`
- `email_messages`
- `calendar_events`
- `tasks`
- `daily_briefings`

## 8) Constraints and indexes to enforce

### Uniqueness

- `users.email` unique
- `email_messages.provider_message_id` unique
- `calendar_events.provider_event_id` unique
- `daily_briefings (user_id, briefing_date)` unique composite

### Indexes

- `tasks(user_id, status, due_at)`
- `tasks(user_id, priority_score DESC)`
- `email_messages(user_id, received_at DESC)`
- `calendar_events(user_id, starts_at)`

## 9) Common migration pitfalls

### Autogenerate misses tables

Cause:
- Model modules not imported in `env.py`.

Fix:
- Import all table model modules before `target_metadata`.

### Wrong timestamp defaults

Cause:
- Python-side default used where DB-side default expected.

Fix:
- Decide explicitly:
  - app-managed timestamps (simpler MVP), or
  - DB-managed timestamps (`server_default=now()`).

### Enum drift

Cause:
- Storing enums as free text with inconsistent casing.

Fix:
- Keep fixed string constants in code and validation schemas.

### Breaking changes in one migration

Cause:
- Renames/drops mixed with logic changes.

Fix:
- Keep each migration small and single-purpose.

## 10) Migration workflow recommendations

- One migration per logical change.
- Never edit old applied migrations in shared environments.
- Add migration ID and purpose to `07-decision-log.md`.
- Run upgrade/downgrade locally before committing.

## 11) Suggested first migration checklist

- [ ] `alembic/env.py` points to app `database_url`.
- [ ] SQLModel metadata loaded with all models.
- [ ] Initial revision generated and reviewed.
- [ ] Upgrade succeeds on empty database.
- [ ] Downgrade one step succeeds.
- [ ] Re-upgrade succeeds cleanly.
- [ ] Constraints/indexes match `02-database-schema.md`.
