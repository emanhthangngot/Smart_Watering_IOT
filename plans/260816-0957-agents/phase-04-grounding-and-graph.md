---
phase: 4
title: "Grounding and Evidence Graph core"
status: pending
priority: P1
effort: "4h"
dependencies: [1, 3]
---

# Phase 04: Grounding and Evidence Graph Core

## Context Links

- [Plan overview](./plan.md)
- [Master design §11.1 and §11.4](../reports/plan.md)
- [Planner](./phase-03-planner.md)

## Overview

Build grounding, edge validation, and backward BFS as pure data operations now. Database persistence, Action/Verify emitters, age-at-decision lookup, and `/explain` routing remain coordination work.

## Requirements

- Functional: `assert_grounded()` rejects every requested ref absent from the supplied available-ref set; it proves membership only, never semantic truth.
- Functional: accepted evidence format is metric-qualified `r_<UUIDv4>#metric`; C8 selected the collision-safe identity, while C0 must still freeze the shared serializer before adapters.
- Functional: numeric/status claims are accepted only when a typed decision-time evidence view proves metric, value/status, unit, state version, trust/freshness, and cited ref agree; unsupported semantic claims fall back to deterministic wording.
- Functional: narration gets at most 2 grounding retries; the third path is deterministic allocation/reasons with no narration.
- Functional: relations are exactly `supports`, `derived_from`, `produced`, `verified_by`, `invalidates`.
- Functional: BFS traverses backward through `supports` and `derived_from`, terminates on cycles, and returns stable ordering.
- Non-functional: edges are consequences, never evidence authority; no dangling reading target is accepted at the persistence gate or created later by retention.

## Architecture

```text
available evidence-ref set + proposed refs
  → assert_grounded
  → typed semantic claim validation
  → accepted narration or UngroundedClaim

Edge values supplied by caller
  → validate relation/node IDs
  → in-memory graph
  → backward BFS
  → [after C1/C4] persisted edges and /explain DTO
```

M3 emits Planner, Diagnosis, and Monitor edges. M4 emits Action and Verify edges through the same validated M3 API after C4. Monitor is M3, correcting the current phase's stale “last two are M4” claim.

## Readiness Split

### READY NOW

- Grounding set check and explicit `UngroundedClaim`.
- Typed, caller-supplied decision-time evidence view plus pure numeric/status claim validation; no repository lookup in the core.
- Two-attempt narration wrapper with deterministic fallback.
- Edge relation/value validation.
- In-memory adjacency and cycle-safe BFS.
- Tests for fabricated refs, retry count, cycles, stable ordering, and relation direction.

### COORDINATION

- C0: authoritative ref syntax and Plan evidence field serialization.
- C1: edge repository, reading existence check, state-version/trust-snapshot lookup, and retention that preserves/materializes every referenced evidence node for the audit lifetime.
- C2: version-bound trust/freshness values used by the semantic validator.
- C4: M4 Action/Verify emitters and `/explain/{decisionId}` router.
- C8: globally unambiguous evidence IDs and collision behavior; the selected UUIDv4 format is enforced by the pure parser, while owner-side storage/serializer tests remain required.
- INV-4 DB/integration test is appended only when real storage exists.

## File Inventory

| Action | Absolute path | Responsibility | Coordination |
|---|---|---|---|
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/graph/grounding.py` | membership check, typed claim validation, error, retry policy | C0/C2/C8 for strict adapters |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/graph/edges.py` | relation/edge values and in-memory graph | C1 for persistence |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/graph/explain.py` | backward BFS and explain projection | C1/C4 for age/API |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_grounding.py` | grounding/retry tests | none for set semantics |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_graph_edges.py` | relation/edge validation | none |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_explain.py` | BFS/cycle/order tests | none |
| Append later | `/home/pearspringmind/Hackathon/vamos_su2026/tests/invariants/test_inv_04.py` | real-reading/no-dangling invariant | C1/C4; append-only |

## Function and Interface Checklist

- [ ] `split_evidence_ref(ref: str) -> tuple[str, str]` exists once; no duplicate parsers.
- [ ] `assert_grounded(requested: Collection[str], available: Collection[str]) -> None` reports all missing refs deterministically.
- [ ] `DecisionEvidenceView` contains ref, metric, typed value/status, unit, source state version, trust/freshness, and decision-time observation; it is an internal read projection, not a replacement shared contract.
- [ ] `validate_sensor_claim(claim, evidence) -> None` compares typed numeric/status content and rejects version/ref/metric/unit/value mismatches.
- [ ] `run_grounded_narration(narrate, validate, fallback, *, max_retries=2)` never performs a third narration call.
- [ ] `EdgeRelation` contains exactly five relations.
- [ ] `EvidenceEdge` contains source, destination, relation, and trace ID.
- [ ] `EvidenceGraph.add(edge)` validates and deduplicates exact duplicate edges.
- [ ] `trace_to_readings(graph, decision_id) -> tuple[...]` is cycle-safe and stable.
- [ ] After C1, repository write verifies referenced reading/decision/action exists before commit and retention cannot delete a node still referenced by a decision edge.

## Implementation Steps

1. Write grounding tests using supplied sets; implement missing-ref collection and deterministic error output while documenting that membership is not semantic validation.
2. Write typed numeric/status claim tests for wrong metric, value, unit, trust/freshness, and state version; implement the smallest pure validator.
3. Write the retry-cap test first; implement one wrapper shared by Planner phrasing, not another generic retry library.
4. Write edge validation/dedup tests; implement the five-value relation enum and edge record.
5. Write BFS tests for direct support, derived chains, branching, duplicates, cycles, and missing start node.
6. Implement stable traversal with explicit visited set and deterministic neighbor order.
7. Set `pytestmark = pytest.mark.agents` in every new M3 test module.
8. After C0/C8, lock `readingId#metric` syntax and add shared-record plus collision mapping tests.
9. After C1/C2/C4, add repository/API adapters, retention tests, and INV-4; never move FastAPI code into `graph/`.

## Test Scenario Matrix

| Case | Input | Expected |
|---|---|---|
| Valid refs | all refs available | accepted |
| Fabricated ref | one ref absent | `UngroundedClaim` lists missing ref |
| Multiple fabricated | unordered missing refs | stable ordered error |
| Known ref, wrong value | citation exists but claim differs | rejected by semantic validator |
| Stale/untrusted evidence | ref exists but decision-time eligibility fails | rejected; deterministic fallback |
| State version mismatch | evidence V12, decision V13 | rejected |
| Two bad narrations | both ungrounded | exactly 2 calls, then fallback |
| Direct support | reading → decision | reading returned |
| Derived chain | reading → diagnosis → plan | reading returned once |
| Cycle | decision A ↔ B | terminates, no duplicates |
| Invalid relation | unknown string | rejected |
| Dangling reading | DB edge target absent | rejected after C1 |
| Evidence retention | referenced reading ages past raw-data TTL | audit node/immutable projection remains resolvable after C1 |
| ID collision | two readings resolve to same short ID after C8 | storage/ref contract fails safely; never aliases evidence |
| Age semantics | old decision snapshot | decision-time age, not current age after C1 |

## Success Criteria

- [x] `pytest -q tests/agents/test_grounding.py tests/agents/test_graph_edges.py tests/agents/test_explain.py -m agents` passes offline.
- [x] Narration call count is never greater than 2 for one plan attempt.
- [x] Citation membership alone cannot pass a mismatched numeric/status claim.
- [x] BFS output is deterministic and cycle-safe.
- [x] Every test module created by this phase is selected by `pytest -m agents`.
- [ ] After C1/C4, `pytest -q tests/invariants/test_inv_04.py -m invariants` passes against real persisted data. (blocked on C1/C4)
- [x] `/explain` stays M4-owned while traversal semantics stay M3-owned.

## Risk Assessment

- Master docs conflict: bare IDs in §6 example vs metric-qualified refs in §11.4. Treat `readingId#metric` as proposed authority, but require C0 to correct/freeze it before strict parser code.
- Current six-hex reading IDs can collide. C8 must choose and freeze collision-safe identity before strict production parsing.
- Master prose says four join points while its table has five. Plan uses the five table rows; dev must correct prose.
- In-memory graph proves algorithms only, not INV-4 persistence or post-retention explainability. Do not mark the phase fully integrated until C1/C4 tests pass.

## Rollback

Pure graph commits are independent from repository and router wiring. Revert only the adapter if M1/M4 surfaces change.
