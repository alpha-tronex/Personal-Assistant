# Day 4 Task Board

Focus: Derive actionable tasks from emails and calendar events.

## Priority legend

- P0: Must complete today
- P1: Should complete today
- P2: Nice to have

## Time budget (target)

- Total: 5 to 7 focused hours
- Buffer: 45 minutes for classification tuning

## Board

## 1) Derivation pipeline skeleton

- [ ] **P0** Implement task derivation service entrypoint (30 min)
- [ ] **P0** Add `POST /api/v1/tasks/recompute` with scope handling (25 min)
- [ ] **P1** Support `changed_only` vs `all_recent` modes (25 min)

Done when:
- Recompute endpoint triggers derivation for target records.

## 2) Email-to-task mapping

- [ ] **P0** Add rule matcher for category/action/urgency from email text (45 min)
- [ ] **P0** Create task title/details generation rules (35 min)
- [ ] **P1** Skip obvious non-actionable promo/newsletter messages (25 min)

Done when:
- Actionable emails produce meaningful tasks and noise is reduced.

## 3) Calendar-to-task mapping

- [ ] **P0** Derive prep/review tasks for key meeting patterns (35 min)
- [ ] **P0** Set due times relative to event starts (for example, 2h before) (25 min)
- [ ] **P1** Avoid duplicate prep tasks for unchanged events (25 min)

Done when:
- Relevant meetings create useful prep tasks without duplication.

## 4) Task persistence behavior

- [ ] **P0** Upsert tasks by stable source key (`source_type + source_id + action_type`) (35 min)
- [ ] **P0** Preserve manual statuses (`Done`, `Snoozed`) when recomputing (30 min)
- [ ] **P1** Add `updated_at` handling for changed task content (15 min)

Done when:
- Recompute updates tasks safely without clobbering user progress.

## End-of-day demo checklist

- [ ] Run recompute and inspect new tasks
- [ ] Confirm both email and calendar sources produce tasks
- [ ] Mark one task done, rerun recompute, verify status preserved
- [ ] Validate non-actionable emails are mostly filtered out

## Day 4 success criteria

- Task derivation is functional and stable.
- Output is directionally useful for daily work.
- Ready for scoring and ranking on Day 5.
