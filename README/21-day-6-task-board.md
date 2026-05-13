# Day 6 Task Board

Focus: Daily briefing generation and scheduled delivery.

## Priority legend

- P0: Must complete today
- P1: Should complete today
- P2: Nice to have

## Time budget (target)

- Total: 5 to 6 focused hours
- Buffer: 45 minutes for scheduler and formatting issues

## Board

## 1) Briefing generation core

- [ ] **P0** Implement briefing assembler from ranked tasks and events (45 min)
- [ ] **P0** Render markdown sections per template (30 min)
- [ ] **P0** Persist into `daily_briefings` by `user_id + briefing_date` (25 min)

Done when:
- A valid briefing document can be generated on demand.

## 2) Briefing API routes

- [ ] **P0** Implement `GET /api/v1/briefing/today` (25 min)
- [ ] **P0** Implement `POST /api/v1/briefing/generate` (25 min)
- [ ] **P1** Implement `POST /api/v1/briefing/send` (30 min)

Done when:
- Briefings can be generated, fetched, and sent through API.

## 3) Delivery and scheduling

- [ ] **P0** Add scheduler trigger at 07:00 local timezone (35 min)
- [ ] **P1** Add internal endpoint `/api/v1/internal/jobs/daily-briefing` with token guard (25 min)
- [ ] **P1** Add minimal email delivery adapter (stub acceptable for today) (30 min)

Done when:
- Scheduled trigger can run and produce/send briefing without manual intervention.

## 4) Reliability checks

- [ ] **P1** Ensure generation is idempotent for same date (20 min)
- [ ] **P1** Add logs for generated_at and sent_at outcomes (20 min)
- [ ] **P2** Add fallback behavior when no tasks found (15 min)

Done when:
- Daily run is predictable and debuggable.

## End-of-day demo checklist

- [ ] Generate briefing via API and inspect markdown
- [ ] Fetch today briefing successfully
- [ ] Trigger send endpoint and confirm status response
- [ ] Simulate scheduler call to internal endpoint

## Day 6 success criteria

- Daily briefing pipeline works end to end.
- Scheduling path exists for morning automation.
- Ready for dashboard integration on Day 7.
