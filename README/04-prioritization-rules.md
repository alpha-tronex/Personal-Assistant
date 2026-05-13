# Prioritization Rules

## Goal

Surface a small, high-impact set of tasks for today.

## Base scoring

Start with `score = 0`.

Additions:
- +40 due today
- +25 overdue
- +20 unread customer email older than 24h
- +15 sender in VIP list
- +15 finance keyword and due date <= 7 days
- +10 calendar meeting today requiring prep
- +10 contains `urgent`, `blocked`, `incident`, or `payment due`

Reductions:
- -25 newsletter or promotional pattern
- -15 auto-generated notifications with no action verb
- -10 tasks marked `Waiting`

## Category keyword seeds

Finance:
- invoice, receipt, payment due, subscription, renewal, bill, charged

Customer:
- follow up, proposal, contract, onboarding, issue, support, escalation

Development:
- bug, deploy, PR, merge, release, incident, regression, prod

## Urgency mapping

- Today: due <= today or score >= 50
- ThisWeek: due within 7 days or score 30..49
- Later: everything else

## Output constraints

- Max 10 tasks in Today
- Always include:
  - top 3 Development
  - top 5 Customer
  - all Finance tasks due <= 7 days
