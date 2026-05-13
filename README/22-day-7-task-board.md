# Day 7 Task Board

Focus: Basic dashboard UX and end-to-end verification.

## Priority legend

- P0: Must complete today
- P1: Should complete today
- P2: Nice to have

## Time budget (target)

- Total: 6 to 8 focused hours
- Buffer: 60 minutes for integration polishing

## Board

## 1) Dashboard summary API

- [ ] **P0** Implement `GET /api/v1/dashboard/summary` response assembly (35 min)
- [ ] **P0** Include today focus, customer, finance, calendar, and last sync sections (35 min)
- [ ] **P1** Ensure response shape matches `09-api-contracts.md` (20 min)

Done when:
- Frontend can render one consolidated payload with minimal extra calls.

## 2) Minimal frontend view (or API-first fallback)

- [ ] **P0** Build simple page with 4 panels: Develop, Customers, Finance, Calendar (70 min)
- [ ] **P0** Show top tasks with score and due info (30 min)
- [ ] **P1** Add loading/empty/error states for each panel (30 min)

Done when:
- Dashboard is usable for morning triage.

## 3) Task actions integration

- [ ] **P0** Wire mark-done action to `PATCH /api/v1/tasks/:task_id` (30 min)
- [ ] **P0** Wire snooze action with date picker to same endpoint (35 min)
- [ ] **P1** Add link-out to source context (email/event) where available (20 min)

Done when:
- You can manage tasks directly from dashboard without manual DB edits.

## 4) End-to-end reliability pass

- [ ] **P1** Run full flow: sync -> recompute -> briefing -> dashboard (35 min)
- [ ] **P1** Test one failure path per stage and verify error response consistency (30 min)
- [ ] **P2** Record known gaps in `07-decision-log.md` for Week 2 hardening (20 min)

Done when:
- Daily workflow works from data ingestion to execution interface.

## End-of-day demo checklist

- [ ] Show dashboard summary payload in API
- [ ] Show dashboard page rendering all 4 panels
- [ ] Mark one task done and one snoozed from UI
- [ ] Confirm morning briefing reflects updated task state

## Day 7 success criteria

- MVP is operational for personal daily use.
- You can trust morning output enough to run your day.
- Week 2 can focus on reliability and polish, not core build.
