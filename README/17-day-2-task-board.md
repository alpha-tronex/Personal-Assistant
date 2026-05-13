# Day 2 Task Board

Focus: Gmail ingestion, normalization, and dedupe.

## Priority legend

- P0: Must complete today
- P1: Should complete today
- P2: Nice to have

## Time budget (target)

- Total: 5 to 7 focused hours
- Buffer: 45 minutes for API/debug handling

## Board

## 1) OAuth token usage for Gmail

- [ ] **P0** Read stored Google credentials from `oauth_tokens` (20 min)
- [ ] **P0** Implement access-token refresh helper (35 min)
- [ ] **P1** Add one-retry-on-401 wrapper for Gmail calls (20 min)

Done when:
- Gmail API calls succeed with refreshed token when access token is expired.

## 2) Gmail sync endpoint and service

- [ ] **P0** Implement `POST /api/v1/sync/gmail` request validation (20 min)
- [ ] **P0** Add Gmail list call for last 14 days (`in:inbox newer_than:14d`) (35 min)
- [ ] **P0** Add Gmail message metadata fetch loop (45 min)
- [ ] **P1** Return queued/running status contract-compatible response (20 min)

Done when:
- Sync endpoint can fetch message IDs and metadata for current user.

## 3) Message normalization and persistence

- [ ] **P0** Map payload into `email_messages` fields (40 min)
- [ ] **P0** Upsert by `provider_message_id` (45 min)
- [ ] **P0** Persist labels, unread flag, subject, snippet, timestamps (35 min)
- [ ] **P1** Track `provider_thread_id` for conversation grouping (20 min)

Done when:
- Re-running sync does not create duplicates and updates changed rows.

## 4) Sync observability

- [ ] **P1** Add basic per-sync metrics (`fetched`, `written`, `failed`) (25 min)
- [ ] **P1** Add structured logs for start/end and failure counts (20 min)
- [ ] **P2** Add `GET /api/v1/sync/jobs/:job_id` placeholder response (25 min)

Done when:
- You can quickly inspect what happened during each sync run.

## End-of-day demo checklist

- [ ] Trigger Gmail sync from endpoint
- [ ] Show inserted rows in `email_messages`
- [ ] Re-run sync to prove idempotent upsert
- [ ] Simulate expired token and verify refresh path

## Day 2 success criteria

- Gmail sync works end to end with dedupe.
- Token refresh does not break sync.
- Metrics/logging provide basic confidence for Day 3.
