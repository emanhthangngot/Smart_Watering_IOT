---
phase: 3
title: "Plan and approval"
status: pending
priority: P1
effort: "3h"
dependencies: [1]
---

# Phase 3: Plan and approval

## Overview

Plan card + request input + approval flow bound to revision hash (§11.2,
§7.4).

## Requirements

- Functional: plan card shows version, status, assumptions, evidence
  chips, objections, expected outcomes, water budget. Request box calls
  `POST /farm/request`. Approve/reject calls `POST /approvals/{revisionId}/approve|reject`
  with the operator token, bound to the exact `revisionHash` shown.
- Non-functional: if the plan changes underneath a stale approval attempt,
  the UI surfaces the mismatch rather than silently resubmitting.

## Architecture

Consumes `POST /farm/request`, `GET /farm/plan/{revisionId}`,
`POST /approvals/*` (M4).

## Related Code Files

- Create: `frontend/app/plans/`, `frontend/app/request/`,
  plan-card component, approval-flow component

## Implementation Steps

1. Request input box → `POST /farm/request`, shows returned `traceId`/`planLineageId`.
2. Plan card: full field set from §11.2, evidence chips link to `/explain`.
3. Approval action: requires operator token entry, sends `revisionHash`,
   surfaces `EXPIRED`/hash-mismatch responses clearly.

## Success Criteria

- [ ] Plan card displays all fields listed in §11.2, not a subset.
- [ ] Approving a stale revision (hash mismatch) shows an explicit error, not a silent no-op.
- [ ] Request box is a real entry point in the UI — chu trình bắt đầu bằng "nhận yêu cầu" (§11.2).

## Risk Assessment

Low — API-shaped consumer; main risk is quietly dropping the revision-hash
binding for convenience, which would defeat §7.4's audit guarantee.
