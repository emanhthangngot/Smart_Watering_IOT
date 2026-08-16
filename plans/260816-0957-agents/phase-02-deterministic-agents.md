---
phase: 2
title: "Deterministic agent core"
status: pending
priority: P1
effort: "5h"
dependencies: [1]
---

# Phase 02: Deterministic Agent Core

## Context Links

- [Plan overview](./plan.md)
- [Master design §§7.1-7.2, §8](../reports/plan.md)
- [World State core](./phase-01-world-state.md)

## Overview

Build the M3-owned message vocabulary, Coordinator routing, and pure resource-policy kernel now. Field Evidence and Diagnosis adapters wait for frozen M1/M2 types; no local copy of their contracts is allowed.

## Requirements

- Functional: vocabulary is exactly `PROPOSE | ACCEPT | REJECT | REQUEST_MORE_EVIDENCE | REVISE | ESCALATE_TO_HUMAN`.
- Functional: Coordinator routes from an internal `RouteSignal` projection plus World State version; it never creates evidence, thresholds, allocations, or side effects.
- Functional: Resource returns a blocking objection when `active_reserved_drawdown_pct + requested_drawdown_pct` exceeds `max(0, level_pct - safe_reserve_pct)` or when scheduling facts show a conflict.
- Functional: every route/resource decision names the source World State version; a trust verdict with a different or absent `source_state_version` is not usable.
- Non-functional: plain callables and small value objects; no base `Agent` hierarchy, reflection registry, framework graph, LLM, or direct import of M4 tools.

## Architecture

`RouteSignal` is a minimal, ephemeral projection used only by the Coordinator route table. It must not repeat the reason/evidence/revision fields owned by the shared `Challenge`. Shared `Reading`, `PlanRevision`, `Challenge`, trust, and tool results remain external contracts.

```text
M3 RouteSignal(s) + state version
  → Coordinator route table
  → RouteDecision

ResourceInput (numbers already supplied by adapters)
  → deterministic budget/conflict checks
  → ResourceAssessment
```

## Readiness Split

### READY NOW

- Six-verb enum.
- M3-only `RouteSignal`, `RouteDecision`, `ResourceInput`, and `ResourceAssessment` records.
- Explicit Coordinator route table and invalid-transition errors.
- Pure daily drawdown/conflict checks.
- Semantic boundary tests: no LLM, no tools/schedule imports, no invented thresholds.

### COORDINATION

- C0/M1+dev: frozen `Reading`, `Challenge`, `PlanRevision` and serializer.
- C2/M2: typed trust verdict, required-metric action blocks, physics evidence, and exact `source_state_version` binding.
- C3/M4: atomic daily active-drawdown reservation. The pure M3 check is advisory; final acceptance occurs only when M4 reserves the same amount in one transaction. M3 never writes ledger rows.
- Field Evidence adapter starts after C0. Diagnosis adapter starts after C2.

## File Inventory

| Action | Absolute path | Responsibility | Coordination |
|---|---|---|---|
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/agents/vocabulary.py` | six interaction verbs | none |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/agents/messages.py` | M3-only conversation/resource value objects | none |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/agents/coordinator.py` | deterministic route table | phase 01 only |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/agents/resource.py` | pure budget/conflict policy | M4 ledger adapter later |
| Create later | `/home/pearspringmind/Hackathon/vamos_su2026/agents/field_evidence.py` | map frozen Reading/bundle to M3 facts | C0 |
| Create later | `/home/pearspringmind/Hackathon/vamos_su2026/agents/diagnosis.py` | map M2 evidence to objections | C2 |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_coordinator.py` | route/transition tests | none |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_resource.py` | budget/conflict tests | none |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_agent_boundaries.py` | import/permission/vocabulary checks | none |

## Function and Interface Checklist

- [ ] `InteractionVerb(str, Enum)` contains exactly six values.
- [ ] `RouteSignal` includes only signal ID, source participant, interaction verb, blocking flag, and source state version; shared reason/evidence/revision data stays in C0 records.
- [ ] `RouteDecision` includes next participant/event, source state version, and accepted signal IDs.
- [ ] `route(signals, state_version) -> RouteDecision` rejects mixed state versions and uses a visible decision table.
- [ ] `ResourceInput` includes level, safe reserve, active reserved drawdown, requested drawdown, farm-day/timezone identity, schedule conflicts, `ledger_as_of`, and source state version.
- [ ] `evaluate_resource(input) -> ResourceAssessment` uses only supplied values and marks stale/unknown facts as more-evidence, not acceptance.
- [ ] `available_drawdown_pct = max(0, level_pct - safe_reserve_pct)` computed once.
- [ ] Advisory pass requires `active_reserved_drawdown_pct + requested_drawdown_pct <= available_drawdown_pct`; C3 repeats and reserves this atomically.
- [ ] Tie/error behavior is deterministic and covered by tests.

## Implementation Steps

1. Write vocabulary and projection validation tests; then implement the enum/value objects without cloning `Challenge`.
2. Write a table-driven Coordinator test for accept, revise, more-evidence, reject, and human escalation paths.
3. Implement only the transitions exercised by §7.2; reject ambiguous/conflicting response sets explicitly.
4. Write Resource tests for exact-budget, active-plus-requested over-budget, negative availability, existing schedule conflict, stale ledger, and unknown inputs.
5. Implement pure Resource policy with injected policy values; do not hard-code `safe_reserve_pct` or query a ledger.
6. Add AST/import checks proving Coordinator/Resource cannot call side-effect modules.
7. Set `pytestmark = pytest.mark.agents` in every new M3 test module.
8. After C0/C2/C3, add thin adapters, state-version matching tests, and an M4 atomic-reservation concurrency test without changing core semantics.

## Test Scenario Matrix

| Case | Input | Expected |
|---|---|---|
| All accept | Diagnosis/Resource `ACCEPT` | route toward proposal/approval |
| Blocking objection | one blocking `REJECT` | `REVISE`; no action |
| Evidence gap | `REQUEST_MORE_EVIDENCE` | Field Evidence/inspection route |
| Conflicting responses | accept + unresolved blocking reject | explicit invalid state |
| Budget exact | active + requested == available | advisory assessment accepts; C3 must reserve atomically |
| Active reservation | available 40, active 25, request 25 | blocking objection; required total is 50 |
| Budget exceeded | active + requested > available | blocking objection |
| Tank below reserve | available <= 0 | blocking objection |
| Schedule conflict | occupied pump/window | blocking objection |
| Missing value | required resource fact absent | request more evidence; never guess |
| Stale ledger | `ledger_as_of` outside accepted freshness | request more evidence |
| Day boundary | reservations straddle configured farm-day timezone | totals belong to the explicit correct day; no host-timezone inference |
| Stale trust | trust version != source state version after C2 | reject input; no route/action |
| Concurrent reservation | two requests pass advisory check after C3 | M4 atomically accepts only capacity-safe reservation(s) |

## Success Criteria

- [ ] `pytest -q tests/agents/test_coordinator.py tests/agents/test_resource.py tests/agents/test_agent_boundaries.py -m agents` passes.
- [ ] No Coordinator branch contains a numeric farm threshold.
- [ ] Diagnosis/Resource/Coordinator source contains no import from `tools`, `schedule`, `verify`, or `api`.
- [ ] Resource equality boundary is documented and tested; no floating comparison ambiguity remains.
- [ ] Every test module created by this phase is selected by `pytest -m agents`.
- [ ] Later C0/C2/C3 adapters have one mapping test each before use.

## Risk Assessment

- M3-only messages can accidentally become a second public contract. Keep `RouteSignal` intentionally lossy/internal and map frozen shared records only in adapters.
- The pure Resource result cannot reserve capacity. Treat it as advisory until C3 proves the atomic reservation; never authorize a tool from the advisory result alone.
- A generic agent superclass would add ceremony without behavior. Do not introduce one unless two concrete agents need shared executable logic, not just similar names.

## Rollback

Adapters are separate commits from the core. If an upstream type changes, revert/remap the adapter; preserve the independently tested route/resource semantics.
