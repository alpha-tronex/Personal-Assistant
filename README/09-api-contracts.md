# API Contracts (MVP)

This document defines stable request and response shapes for the initial backend.

## Conventions

- Base path: `/api/v1`
- Auth: bearer session or cookie session (implementation choice)
- Content type: `application/json`
- Time format: ISO-8601 UTC (`2026-03-23T07:00:00Z`)
- IDs: UUID unless noted

## Standard error shape

```json
{
  "error": {
    "code": "STRING_CODE",
    "message": "Human readable message",
    "details": {}
  }
}
```

Common error codes:
- `UNAUTHORIZED`
- `FORBIDDEN`
- `VALIDATION_ERROR`
- `NOT_FOUND`
- `CONFLICT`
- `RATE_LIMITED`
- `UPSTREAM_ERROR`
- `INTERNAL_ERROR`

---

## Auth

### `POST /auth/google/start`

Starts OAuth flow and returns redirect URL.

Request body:

```json
{
  "return_to": "/dashboard"
}
```

Response `200`:

```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "opaque-state-token"
}
```

### `GET /auth/google/callback`

Google redirects here with `code` and `state`.

Query params:
- `code` (required)
- `state` (required)

Response `302`:
- Redirect to app URL (`return_to` or default dashboard)

Failure response `400`:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid OAuth state"
  }
}
```

---

## Sync

### `POST /sync/gmail`

Triggers Gmail ingestion job for current user.

Request body:

```json
{
  "lookback_days": 14,
  "query": "in:inbox newer_than:14d"
}
```

Response `202`:

```json
{
  "job_id": "6a60caec-5d56-4fc2-b4e6-b6fa6f5a7f31",
  "status": "queued"
}
```

### `POST /sync/calendar`

Triggers calendar ingestion for current user.

Request body:

```json
{
  "range_start": "2026-03-22T00:00:00Z",
  "range_end": "2026-04-06T00:00:00Z"
}
```

Response `202`:

```json
{
  "job_id": "4f1c56aa-8870-4ab5-b145-23164c2fba99",
  "status": "queued"
}
```

### `GET /sync/jobs/:job_id`

Returns sync job status and metrics.

Response `200`:

```json
{
  "job_id": "6a60caec-5d56-4fc2-b4e6-b6fa6f5a7f31",
  "provider": "gmail",
  "status": "completed",
  "started_at": "2026-03-23T06:58:00Z",
  "finished_at": "2026-03-23T06:58:08Z",
  "metrics": {
    "fetched": 128,
    "written": 126,
    "failed": 2
  }
}
```

---

## Tasks

### `POST /tasks/recompute`

Re-derives and rescoring tasks for current user.

Request body:

```json
{
  "scope": "changed_only"
}
```

Allowed `scope`:
- `changed_only`
- `all_recent`

Response `200`:

```json
{
  "recomputed": 84,
  "updated": 39
}
```

### `GET /tasks`

Lists tasks with filters and pagination.

Query params:
- `status` (`Open|Done|Snoozed`)
- `urgency` (`Today|ThisWeek|Later`)
- `category` (`Development|Customer|Finance|Marketing|Admin`)
- `limit` (default 50, max 200)
- `cursor` (optional)

Response `200`:

```json
{
  "items": [
    {
      "id": "6e3a9b61-e954-42e3-b20e-11985af6f252",
      "source_type": "email",
      "source_id": "4deef4f1-8848-4506-b486-f307a2fc463a",
      "category": "Customer",
      "action_type": "Reply",
      "urgency": "Today",
      "title": "Reply to Acme onboarding blocker",
      "details": "Customer is blocked on API key setup.",
      "due_at": "2026-03-23T16:00:00Z",
      "priority_score": 72,
      "status": "Open",
      "created_at": "2026-03-23T06:58:12Z",
      "updated_at": "2026-03-23T06:58:12Z"
    }
  ],
  "next_cursor": null
}
```

### `PATCH /tasks/:task_id`

Updates task state (done/snooze/edit fields).

Request body examples:

Mark done:
```json
{
  "status": "Done"
}
```

Snooze:
```json
{
  "status": "Snoozed",
  "snoozed_until": "2026-03-24"
}
```

Response `200`:

```json
{
  "id": "6e3a9b61-e954-42e3-b20e-11985af6f252",
  "status": "Done",
  "updated_at": "2026-03-23T10:10:00Z"
}
```

---

## Briefings

### `GET /briefing/today`

Returns today briefing object (creates on demand if configured).

Response `200`:

```json
{
  "briefing_date": "2026-03-23",
  "content_markdown": "### Today's Focus (Top 3)\n- ...",
  "generated_at": "2026-03-23T07:00:03Z",
  "sent_at": "2026-03-23T07:00:06Z"
}
```

### `POST /briefing/generate`

Generates (or regenerates) today briefing.

Request body:

```json
{
  "force": false
}
```

Response `200`:

```json
{
  "briefing_date": "2026-03-23",
  "generated": true
}
```

### `POST /briefing/send`

Sends briefing via configured channel.

Request body:

```json
{
  "channel": "email"
}
```

Allowed channel values:
- `email`
- `slack` (future-ready, optional MVP)

Response `200`:

```json
{
  "sent": true,
  "channel": "email",
  "sent_at": "2026-03-23T07:00:06Z"
}
```

---

## Dashboard summary

### `GET /dashboard/summary`

Returns the compact payload needed by the main dashboard page.

Response `200`:

```json
{
  "today_focus": [
    {
      "task_id": "670e86ff-8f73-4a30-88bd-75e57f33bc99",
      "title": "Ship billing retry fix",
      "category": "Development",
      "priority_score": 79
    }
  ],
  "customers": {
    "open_replies": 7,
    "top_items": []
  },
  "finance": {
    "due_next_7_days": 3,
    "top_items": []
  },
  "calendar": {
    "meetings_today": 4,
    "next_event_start": "2026-03-23T09:00:00Z"
  },
  "last_sync": {
    "gmail": "2026-03-23T06:58:08Z",
    "calendar": "2026-03-23T06:58:10Z"
  }
}
```

---

## Webhook and scheduler (optional MVP)

### `POST /internal/jobs/daily-briefing`

Internal endpoint for scheduler trigger at 07:00.

Headers:
- `X-Internal-Token: <secret>`

Response `200`:

```json
{
  "ok": true,
  "briefing_date": "2026-03-23"
}
```

---

## Versioning and compatibility

- Keep additive changes backward compatible within `v1`.
- Do not remove or rename fields without introducing `v2`.
- Document every contract change in `07-decision-log.md`.
