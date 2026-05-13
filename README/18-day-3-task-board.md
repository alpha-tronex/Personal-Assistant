# Day 3 Task Board

Focus: Calendar ingestion and event normalization.

## Priority legend

- P0: Must complete today
- P1: Should complete today
- P2: Nice to have

## Time budget (target)

- Total: 5 to 7 focused hours
- Buffer: 45 minutes for calendar edge cases

## Board

## 1) Calendar sync endpoint and range handling

- [ ] **P0** Implement `POST /api/v1/sync/calendar` request schema (20 min)
- [ ] **P0** Default range to now-1d through now+14d (20 min)
- [ ] **P1** Validate custom `range_start` and `range_end` input (20 min)

Done when:
- Endpoint accepts valid ranges and rejects invalid dates.

## 2) Google Calendar API integration

- [ ] **P0** Implement events list call for selected window (35 min)
- [ ] **P0** Include timezone-aware parsing for start/end (40 min)
- [ ] **P1** Handle all-day events correctly (25 min)

Done when:
- Calendar events are fetched consistently for the target window.

## 3) Event normalization and upsert

- [ ] **P0** Map payload into `calendar_events` schema (40 min)
- [ ] **P0** Upsert by `provider_event_id` (40 min)
- [ ] **P0** Persist attendees/location/description/title (30 min)
- [ ] **P1** Preserve source calendar identifier (`calendar_id`) (15 min)

Done when:
- Repeated sync updates existing events rather than duplicating.

## 4) Sync quality checks

- [ ] **P1** Add logs for fetched/written/failed counts (20 min)
- [ ] **P1** Confirm event updates are reflected on next sync run (20 min)
- [ ] **P2** Add basic filters for canceled/deleted events handling (25 min)

Done when:
- You can trust calendar data freshness for downstream task derivation.

## End-of-day demo checklist

- [ ] Trigger calendar sync endpoint
- [ ] Show persisted `calendar_events` rows
- [ ] Update one event in Google Calendar and re-sync
- [ ] Verify the event update appears locally

## Day 3 success criteria

- Calendar sync works end to end with upserts.
- Event timestamps and all-day behavior are correct.
- Data is ready for task derivation on Day 4.
