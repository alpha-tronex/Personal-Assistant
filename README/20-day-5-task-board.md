# Day 5 Task Board

Focus: Priority scoring and Today list quality.

## Priority legend

- P0: Must complete today
- P1: Should complete today
- P2: Nice to have

## Time budget (target)

- Total: 5 to 6 focused hours
- Buffer: 45 minutes for tuning score outcomes

## Board

## 1) Scoring engine

- [ ] **P0** Implement base scoring formula from `04-prioritization-rules.md` (45 min)
- [ ] **P0** Add overdue/due-today boosts (20 min)
- [ ] **P0** Add VIP and finance-near-due boosts (25 min)
- [ ] **P1** Add promo/newsletter penalties (20 min)

Done when:
- Every task gets a deterministic `priority_score`.

## 2) Urgency bucketing and ordering

- [ ] **P0** Map tasks to `Today`, `ThisWeek`, `Later` based on score and due date (25 min)
- [ ] **P0** Sort by urgency then score descending (20 min)
- [ ] **P1** Resolve ties with recency and due_at proximity (15 min)

Done when:
- Ranking order is consistent and understandable.

## 3) Output constraints

- [ ] **P0** Enforce max 10 tasks in Today list (15 min)
- [ ] **P0** Enforce composition goals (top dev, top customer, finance due soon) (30 min)
- [ ] **P1** Add fallback logic if one category has insufficient items (20 min)

Done when:
- Today list is concise and balanced for execution.

## 4) Validation and tuning pass

- [ ] **P1** Test scoring on 20-30 recent tasks and inspect ranking quality (35 min)
- [ ] **P1** Adjust 3-5 rule weights based on obvious misses (30 min)
- [ ] **P2** Add score breakdown field for debug visibility (20 min)

Done when:
- Ranking feels actionable with minimal obvious mis-prioritizations.

## End-of-day demo checklist

- [ ] Show sample ranked tasks with score values
- [ ] Show Today list cap at 10 items
- [ ] Show category composition constraints in output
- [ ] Demonstrate one rule tweak and improved ranking

## Day 5 success criteria

- Prioritization engine is working and understandable.
- Today output is concise and practical.
- Ready to generate morning briefings on Day 6.
