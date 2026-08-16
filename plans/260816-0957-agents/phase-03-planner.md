---
phase: 3
title: "Deterministic planner"
status: pending
priority: P1
effort: "5h"
dependencies: [2]
---

# Phase 03: Deterministic Planner

## Context Links

- [Plan overview](./plan.md)
- [Master design §6 and §7.1](../reports/plan.md)
- [Deterministic agent core](./phase-02-deterministic-agents.md)

## Overview

Deliver the allocator as the ready-now feature. It ranks urgency and allocates pump time under explicit constraints before any optional LLM call. Construction/persistence of the public immutable `PlanRevision` waits for C0/C1; M3 must not invent that shared record.

## Requirements

- Functional: stable urgency ordering; tank-reserve, daily drawdown, pump-minute, no-overlap, and allowed-window constraints.
- Functional: `AllocationCandidate.window` is a fixed requested execution interval; candidates with missing tank/reserve or allowed-window facts fail closed.
- Functional: equal inputs produce byte-for-byte equivalent allocation data with a documented tie-breaker.
- Functional: Planner returns a valid deterministic result when phrasing is disabled, unavailable, times out, or is rejected as ungrounded.
- Functional: allocation input/output names `source_state_version`; trust/resource projections from any other version are rejected before ranking.
- Non-functional: numbers and actions originate only from the allocator; phrasing may add narrative fields but may not change quantitative fields.
- Non-functional: no provider SDK in the pure allocator and no secrets/config owned by M3; provider wiring is fail-closed and receives only the allowed, redacted projection.

## Architecture

```text
AllocationRequest
  → validate constraints
  → stable urgency ranking
  → allocate slices
  → AllocationResult
  → [after C0] PlanContractAdapter
  → optional PlanNarrator
  → grounding gate (phase 04)
  → persisted PlanRevision [after C1]
```

`PlanNarrator` is a narrow consumer-owned protocol, not a multi-provider framework. `None` means deterministic narrative only. Provider selection belongs to C5.

## Readiness Split

### READY NOW

- Allocation input/result/failure value objects local to the allocator, all bound to one source state version.
- Stable urgency sort and constraint evaluator.
- Deterministic reasons derived from constraint decisions.
- Restricted prompt builder and `PlanNarrator` boundary.
- Failure-path test without external LLM/network.

### COORDINATION

- C0: frozen `PlanRevision`, lifecycle/status, nested record serialization, and canonical revision hash covering action parameters, evidence refs, expected outcomes, assumptions/challenges, lineage, and source state version.
- C1: immutable revision save/load and lineage uniqueness.
- C2: trust tier plus required-metric blocking facts as allocator inputs, bound to the same source state version.
- C5: one real provider/model/config and SDK dependency, fail-closed startup, timeout/output limits, data-egress allowlist, prompt/response redaction, and no untrusted free-form state passed through.
- `PlanContractAdapter` is added only after C0; never define a competing Plan dataclass in `agents/`.

## File Inventory

| Action | Absolute path | Responsibility | Coordination |
|---|---|---|---|
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/agents/allocator.py` | allocation types, ranking, constraints, deterministic reasons | none for core |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/agents/planner.py` | allocator-first orchestration and `PlanNarrator` boundary | C0/C1/C5 for full path |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/prompts/planner.py` | narrative-only prompt builder | C5 for real call |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_allocator.py` | table-driven allocation tests | none |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_planner_fallback.py` | no-provider/failure/fallback behavior | phase 04 for grounding retry |
| Create later | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_plan_lineage.py` | immutable shared revision lineage | C0/C1 |

## Function and Interface Checklist

- [ ] `allocate(request: AllocationRequest) -> AllocationResult` is pure.
- [ ] `AllocationRequest` and `AllocationResult` carry the same `source_state_version`; mismatched trust/resource inputs produce a named failure.
- [ ] Candidate tie-break order is explicit and stable, never dependent on set/dict iteration.
- [ ] Constraint evaluation returns named objections instead of silently dropping candidates.
- [ ] `PlanNarrator.narrate(allocation, grounded_facts) -> NarrativeFields` cannot return numeric/action fields and is never an authority for acceptance.
- [ ] `build_planner_prompt(allocation, grounded_facts) -> str` accepts structured allowlisted facts, treats their strings as data, and includes no raw World State, `scenario`, credentials, or operator-auth material.
- [ ] `plan(request, *, narrator=None)`: allocator always executes first.
- [ ] After C0, `PlanContractAdapter` is the only constructor mapping allocation output to the shared plan record.

## Implementation Steps

1. Write failing tests for ranking, tie-breaks, budget exhaustion, partial allocation, no-overlap, invalid window, and missing required facts.
2. Implement allocation value objects and one constraint-evaluation path; avoid separate validators that repeat rules.
3. Add deterministic reason generation from the same accepted/rejected constraint results.
4. Write prompt-boundary tests proving narrative input contains only allocation output and structured grounded facts; include adversarial text that must remain quoted data rather than instructions.
5. Implement Planner orchestration with `narrator=None` as a real supported mode, not a test fallback.
6. Add a provider-failure test double only in tests; assert returned allocation and deterministic reasons remain valid.
7. Set `pytestmark = pytest.mark.agents` in every new M3 test module.
8. After C0/C1, add the shared-record adapter, canonical-hash tamper test, and immutable lineage test.
9. After C2, add missing/mismatched trust-state version tests.
10. After C5, add offline fail-closed/redaction tests plus one opt-in provider/egress smoke test outside the default offline unit gate.

## Test Scenario Matrix

| Case | Input | Expected |
|---|---|---|
| Stable ranking | equal urgency candidates | documented ID/area tie-break |
| Low tank | drawdown exceeds availability | blocking objection; no over-allocation |
| Partial budget | some candidates fit | valid slices plus rejected reasons |
| Overlapping window | same pump/time | no overlapping slices |
| Missing fact | unknown tank/window | explicit failure/request evidence |
| Trust version mismatch | trust V12, allocation V13 | named failure; no proposal |
| Narrator absent | valid request | deterministic allocation and reasons |
| Narrator timeout | valid request | same quantitative allocation |
| Narrator changes number | invalid narrator result | reject narrative; keep deterministic fields |
| Prompt injection text | grounded string contains instructions | serialized as data; cannot widen prompt or action |
| Plan tamper | action/evidence/outcome changed after C0 | canonical hash mismatch |
| New revision | challenge after C0/C1 | V1 unchanged; V2 links to V1 |

## Success Criteria

- [x] `pytest -q tests/agents/test_allocator.py tests/agents/test_planner_fallback.py -m agents` passes without network credentials.
- [x] `rg -n "(openai|anthropic|google|litellm|api_key)" agents/allocator.py` returns no provider coupling.
- [x] Repeated allocation of the same request returns equivalent ordered results.
- [x] Provider failure never prevents a deterministic proposal.
- [x] Every test module created by this phase is selected by `pytest -m agents`.
- [ ] After C0/C1, shared Plan round-trip and immutable lineage tests pass; before that, these tasks remain blocked and are not faked. (blocked on C0/C1)

## Risk Assessment

- Defining `PlanRevision` locally would create immediate drift; prohibited.
- A prompt that receives raw state can leak `scenario` or let the model recompute numbers. Only the phase-01 slice plus allocator output may cross the boundary.
- Grounding and prompt sanitization constrain provenance/egress; they do not make untrusted sensor text semantically safe. Keep structured fields typed and never interpolate raw content into system instructions.
- Floating-point budgeting needs one rounding policy after C0/master units are confirmed; test boundary values before integration.

## Rollback

Keep allocator, shared-contract adapter, and provider adapter in separate commits. A provider or contract change should not require reverting deterministic allocation.
