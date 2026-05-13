# Integration Flows

## Gmail sync flow

1. Load valid Google token for user.
2. Fetch message ids for a time window (for example, last 14 days) with query:
   - `in:inbox newer_than:14d`
3. For each message id:
   - Fetch message metadata
   - Upsert into `email_messages` using `provider_message_id`
4. Mark stale message metadata if needed (optional).
5. Trigger task derivation for changed records.

## Calendar sync flow

1. Load valid Google token.
2. Fetch events from now-1d to now+14d.
3. Upsert using `provider_event_id`.
4. Trigger task derivation for changed events.

## Token refresh flow

1. If access token is expired, refresh via OAuth refresh token.
2. Persist new access token and expiry.
3. Retry failed API call once after refresh.

## Error handling

- Retry transient 5xx errors with exponential backoff.
- Log per-provider sync result:
  - started_at, finished_at, records_fetched, records_written, error_count
- Keep idempotent upserts to avoid duplicates.
