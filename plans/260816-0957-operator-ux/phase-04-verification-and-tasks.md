---
phase: 4
title: "Verification and tasks"
status: pending
priority: P1
effort: "3h"
dependencies: [1]
---

# Phase 4: Verification and tasks

## Overview

Action vs Outcome verification rendered separately with 3 states each;
inspection tasks; notification center (§11.2, §7.5).

## Requirements

- Functional: `PASS|FAIL|INCONCLUSIVE` shown distinctly per layer — never
  merged into one status. Notification center: HIGH/CRITICAL banners,
  badge, `unread → acknowledged → resolved` lifecycle via
  `GET /tasks`, `POST /tasks/{id}/acknowledge|resolve`.
- Non-functional: no dependency on an external notification service — all
  self-contained in this app.

## Architecture

Consumes `GET /farm/plan/{revisionId}` (verification records embedded or
linked), `GET /tasks` (M4).

## Related Code Files

- Create: `frontend/app/tasks/`, notification-center component,
  verification-badge component (3-state, reused across Action/Outcome)

## Implementation Steps

1. Verification badge component: renders `PASS`/`FAIL`/`INCONCLUSIVE`
   distinctly (color + label, not color alone).
2. Use it twice per action — once for Action Verification, once for
   Outcome Verification — never collapsed into a single indicator.
3. Notification center: HIGH/CRITICAL banner, badge count, lifecycle
   actions wired to the tasks API.

## Success Criteria

- [ ] A plan with Action=PASS, Outcome=FAIL renders both distinctly on the same view.
- [ ] `INCONCLUSIVE` never renders visually identical to `PASS`.
- [ ] Task lifecycle (unread→acknowledged→resolved) is fully operable from the UI without a page reload per step (or with an acceptable reload — decide once, be consistent).

## Risk Assessment

Low — the risk is collapsing the two verification layers into one badge
for visual simplicity, which directly undermines §10.1's design intent.
