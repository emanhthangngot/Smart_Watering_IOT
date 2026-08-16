---
phase: 6
title: "Grounded reporting — deferred"
status: pending
priority: P3
effort: "0h until approved"
dependencies: [4, 5]
---

# Phase 06: Grounded Reporting — Deferred

## Context Links

- [Plan overview](./plan.md)
- [Master design §7.1 and cut order §13.3](../reports/plan.md)
- [Grounding and graph](./phase-04-grounding-and-graph.md)

## Decision

`DEFERRED — DO NOT START.` Reporting has no named API or UI consumer in the current M4/M5 plans and is not required for N1-N4 or INV-4. Creating report types, prompts, or tests now would spend the independent-work window on an unconsumed P1 surface while P0 closed-loop contracts remain open.

This phase is a coordination note, not an implementation work package. It creates no source or test files.

## Conditions to Reopen

All conditions are mandatory:

- Phases 01-05 P0 behavior and their offline tests are green.
- C0-C5 integration gates are executable, including evidence identity, durable readers, version-bound trust, tool/recovery safety, and provider security.
- Dev/M4/M5 names the consuming API endpoint and/or UI journey, its owner, DTO, permissions, and acceptance test.
- Product confirms Reporting is worth more than the remaining closed-loop, scenario, and demo-hardening work.
- A data-retention path guarantees all cited evidence remains resolvable for the report's audit lifetime.

## Proposed Scope After Reopen

- Assemble trace, immutable plan history, challenges, and Action/Outcome verification from read-only owner-provided projections.
- Produce a deterministic structured trace summary first.
- Optionally narrate only structured grounded facts through C5; no tool, schedule, state, or SQL writes.
- Validate both citation membership and the semantic agreement of numeric/status claims with typed decision-time evidence.
- Preserve `PASS`, `FAIL`, and `INCONCLUSIVE` as distinct outcomes.
- Return an explicit unavailable/invalid result when the provider or grounding check fails; never fabricate prose or sensor values.

## Deferred File Inventory

| Action now | Proposed path after reopen | Gate |
|---|---|---|
| Do not create | `/home/pearspringmind/Hackathon/vamos_su2026/agents/reporting.py` | named consumer + C1/C4 readers |
| Do not create | `/home/pearspringmind/Hackathon/vamos_su2026/prompts/reporting.py` | C5 provider/egress contract |
| Do not create | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_reporting.py` | approved report contract and consumer |

## Reopen Validation Matrix

| Case | Required result |
|---|---|
| Valid grounded trace | structured summary succeeds |
| Action PASS/outcome FAIL | both states remain distinct |
| INCONCLUSIVE verification | remains INCONCLUSIVE |
| Known citation, wrong number/status | report rejected semantically |
| Unknown citation | report rejected structurally |
| Evidence expired from raw storage | retained audit projection still resolves |
| Provider absent/timeout | deterministic summary or explicit unavailable result |
| Unauthorized consumer | API rejects before report assembly |

Every test module created after reopening must set `pytestmark = pytest.mark.agents`.

## Success Criteria for This Plan

- [ ] No Reporting source, prompt, endpoint, UI, or test file is created during the independent-first implementation.
- [ ] Deferral does not block phases 01-05, N1-N4, or INV-4.
- [ ] Reopening requires a named consumer and explicit owner acceptance, not schedule availability alone.

## Risks and Rollback

- Citation presence alone does not prove a claim matches evidence; a reopened phase must reuse phase-04 typed semantic validation.
- Reporting is attractive demo scope but currently has no consumer. It is the first cut when schedule pressure threatens P0.
- No rollback is needed while deferred because this phase changes no code or runtime contract.
