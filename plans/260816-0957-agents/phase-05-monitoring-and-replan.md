---
phase: 5
title: "Monitoring, invalidation, and replan"
status: pending
priority: P1
effort: "5h"
dependencies: [2, 3, 4]
---

# Phase 05: Monitoring, Invalidation, and Replan

## Context Links

- [Plan overview](./plan.md)
- [Master design §6.1, §9.5, §10.2, §10.4](../reports/plan.md)
- [Planner](./phase-03-planner.md)
- [Grounding and graph](./phase-04-grounding-and-graph.md)

## Overview

Build the pure invalidation guard now: touched-assumption selection, explicit-time debounce, idempotency key handling, and one-open-replan state. Concrete A1-A6 predicates, durable atomicity, tool effects, revision persistence, and restart recovery wait for C0-C4.

## Requirements

- Functional: evaluate only assumptions touched by changed evidence/metrics.
- Functional: idempotency identity is `(plan_revision_id, assumption_id, triggering_evidence_version)`; C0/dev must define what the evidence version represents before persistence.
- Functional: repeated evidence inside one observation window produces one invalidation/suspension.
- Functional: at most one open replan per `(plan_revision_id, assumption_id)`.
- Functional: replan creates V(n+1) and never mutates Vn after C0/C1.
- Functional: durable replan jobs have explicit `PENDING | RUNNING | COMPLETED | FAILED` state plus claim/lease recovery; a worker crash cannot leave an unobservable in-memory lock.
- Functional: A6 invalidation requests schedule defer/cancel with a reason through M4; M3 never changes a schedule row.
- Functional: narrow expected-vs-actual divergence is a P0 predicate and consumes C2 evidence bound to the evaluated source state version.
- Non-functional: explicit clock input, bounded memory for local dedupe state, no LLM per MQTT batch.

## Architecture

```text
changed evidence projection
  → select touched assumptions
  → injected deterministic predicate evaluator
  → InvalidationDecision
  → idempotency/debounce/open-replan guard
  → [after C1] atomic durable invalidation + replan job + pending effect
  → claimed effect/replan worker
  → [after gates] Coordinator + M4 effects
```

Effects consume accepted durable pending-effect records. This is a narrow transactional outbox for M3/M4 commands, not a generic event bus. The invalidation, open-replan uniqueness, and pending effect are committed together so duplicate batches or crashes cannot lose or double-call M4.

## Readiness Split

### READY NOW

- `InvalidationKey`, `InvalidationDecision`, and monitor-state records.
- Touched-assumption index over explicit dependency keys.
- Explicit-time debounce.
- In-memory duplicate suppression and one-open-replan transition.
- 1 Hz stress test and bounded-state cleanup policy.

### COORDINATION

- C0: frozen `Assumption`, `PlanRevision`, lifecycle states, evidence-version meaning.
- C1: atomic durable invalidation/open-replan uniqueness, revision persistence, replan job claims/leases, and pending-effect outbox in one transaction.
- C2: A1-A6 trust/divergence inputs and required-metric status bound to source state version; the narrow expected-vs-actual predicate is P0.
- C3: inspection creation, schedule defer/cancel, idempotent receipts.
- C4: startup recovery reattaches monitor before runner/API accept work; runner claim vs suspension/cancel is one atomic eligibility decision; multi-worker startup uses one leader or atomic claim barrier.

## File Inventory

| Action | Absolute path | Responsibility | Coordination |
|---|---|---|---|
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/agents/monitor.py` | selection, decision, debounce/idempotency guard | C0/C2 for actual predicates |
| Create later | `/home/pearspringmind/Hackathon/vamos_su2026/agents/replan.py` | immutable V(n+1) construction and lineage | C0/C1 |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_monitor.py` | selection/debounce/idempotency tests | none for core |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_monitor_stress.py` | repeated 1 Hz events and memory bound | none for core |
| Create later | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_replan.py` | immutable lineage/open-replan integration | C0/C1 |
| Create later | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_monitor_effects.py` | A6 inspection/schedule effects | C2/C3/C4 |
| Create later | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_replan_recovery.py` | crash/lease/multi-worker recovery and claim race | C1/C4 |

## Function and Interface Checklist

- [ ] `InvalidationKey` is immutable/hashable and contains the three required identities.
- [ ] `select_touched_assumptions(changed_keys, dependency_index) -> tuple[...]` is pure.
- [ ] `evaluate_changes(..., *, now, evaluator) -> tuple[InvalidationDecision, ...]` takes time/evaluator explicitly.
- [ ] `InvalidationGuard.accept(decision) -> bool` applies duplicate, debounce, and open-replan checks before effects.
- [ ] `InvalidationGuard.close_replan(plan_revision_id, assumption_id)` is only the in-memory state transition; after C1 the durable slot closes in the same transaction that commits V(n+1) or a terminal failed job.
- [ ] Cleanup removes expired debounce/dedupe state without removing an open-replan lock.
- [ ] After C0/C1, `create_next_revision(previous, reason, evidence) -> PlanRevision` increments once and preserves Vn.
- [ ] After C1, repository operation atomically writes invalidation, unique open-replan job, and pending effect; claim/lease/terminal transitions are explicit and recoverable.
- [ ] After C3, tool effects are behind narrow callables and return idempotent receipts; success marks the pending effect complete in a separate retry-safe transaction.
- [ ] After C4, runner claim succeeds only if the plan/action remains eligible, no suspension/cancel is pending, and relevant assumptions are valid under the same lock/transaction.

## Implementation Steps

1. Ask dev/C0 owner to define `triggering_evidence_version` (`farmStateVersion`, batch epoch, or other). Implement persistence only after answer.
2. Write pure selection tests, then implement the dependency index/touched selection.
3. Write explicit-time debounce and duplicate tests, then implement `InvalidationGuard`.
4. Write the one-open-replan transition test including close/reopen.
5. Add a 1 Hz repeated-event test over multiple windows; assert one event per window and bounded cleanup.
6. Set `pytestmark = pytest.mark.agents` in every new M3 test module.
7. After C0/C2, implement A1-A6 adapters as a visible registry, including the P0 narrow divergence predicate and state-version checks; do not run every predicate for every batch.
8. After C1, make invalidation uniqueness, one-open-replan, replan job, and pending effect one atomic unit; local memory is only a fast path.
9. After C1, implement claimed/leased job recovery and tests for crash before work, during work, and before terminal commit.
10. After C3, dispatch inspection/A6 schedule control from claimed pending effects and store idempotent receipts.
11. After C4, test atomic runner-claim versus suspension/cancel, restart reattachment, immediate assumption reevaluation, and multi-worker startup before accepting new work.

## Test Scenario Matrix

| Case | Input | Expected |
|---|---|---|
| Unrelated metric | no dependency match | no evaluation/event |
| First invalid evidence | unseen key | one invalidation |
| Exact replay | same key | zero duplicate events |
| Repeated 1 Hz | same window | one suspension |
| New evidence version | later window | eligible new decision |
| Open replan exists | same assumption | no second replan |
| Replan closed | new invalidation | one new replan allowed |
| Narrow divergence | expected-vs-actual predicate crosses bound after C2 | P0 invalidation; no LLM batch rerun |
| Trust/state mismatch | predicate input version != plan evaluation version | reject input; no decision/effect |
| A6 fired | soil rise/pump off after C2 | guarded defer/cancel request with reason |
| Tool retry | same effect after C3 | one M4 side effect/receipt |
| Crash after invalidation commit | worker stops before M4 call | pending effect/replan job recovered once |
| Crash after M4 receipt | worker stops before local completion | idempotent retry resolves to one side effect |
| Claim vs cancel race | M4 runner claims while M3 suspends | one serializable winner; no canceled action starts |
| Orphaned RUNNING job | lease expires after worker crash | eligible for one recovery claim |
| Two-worker restart | both instances start after C4 | one recovery barrier/atomic claim path |
| Restart | executing plan after C4 | monitor attached and assumptions reevaluated before API/runner work |

## Success Criteria

- [ ] `pytest -q tests/agents/test_monitor.py tests/agents/test_monitor_stress.py -m agents` passes offline.
- [ ] Stress test demonstrates at most one suspension per debounce window and one open replan per assumption.
- [ ] Every test module created by this phase is selected by `pytest -m agents`.
- [ ] `agents/monitor.py` imports no tool, schedule, API, DB, or LLM client.
- [ ] After C0-C4, replan/effect/recovery/race tests pass, no durable job is permanently orphaned, and Vn remains unchanged.
- [ ] No MQTT batch causes an unconditional full-agent or LLM rerun.

## Risk Assessment

- Evidence-version identity is unresolved and affects durable idempotency; do not guess it.
- In-memory dedupe is insufficient across restart; final acceptance requires C1 atomic uniqueness.
- Calling M4 before the guard turns duplicates into real tasks/schedule updates; effect order is load-bearing.
- Holding an open-replan flag without a durable job/lease can deadlock the farm after a crash. The C1 transaction and recovery claim are acceptance requirements, not optional hardening.
- A process-local startup hook is not a multi-worker barrier. C4 must select a leader or atomic claiming strategy before serving runner/API traffic.

## Rollback

Pure guard and external-effect wiring are separate commits. If a coordination contract changes, revert the adapter/effect commit without removing tested storm protection.
