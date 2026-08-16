---
phase: 2
title: "Deterministic agents"
status: pending
priority: P1
effort: "4h"
dependencies: [1]
---

# Phase 2: Deterministic agents

## Overview

Coordinator, Field Evidence, Diagnosis, Resource — none use an LLM (§7.1
table). Each has an explicit permission boundary and never has a direct
side effect.

## Requirements

- Functional: Coordinator only routes, never invents thresholds/evidence,
  never has a side effect. Field Evidence is read-only, emits evidence
  bundles with provenance. Diagnosis never plans an action or calls a
  tool. Resource never creates an irrigation action directly.
- Non-functional: interaction vocabulary limited to `PROPOSE | ACCEPT |
  REJECT | REQUEST_MORE_EVIDENCE | REVISE | ESCALATE_TO_HUMAN` (§7.2).

## Architecture

Diagnosis + Resource + Trust (M2) together form the challenge layer — no
separate "Critic" agent (§7.2). Each agent is a plain callable with a typed
input/output contract, not necessarily a class hierarchy.

## Related Code Files

- Create: `agents/coordinator.py`, `agents/field_evidence.py`,
  `agents/diagnosis.py`, `agents/resource.py`, `agents/vocabulary.py`
  (shared enum)

## Implementation Steps

1. `agents/vocabulary.py`: the 6-verb enum, shared by every agent.
2. `agents/field_evidence.py`: read Reading state from World State, build
   evidence bundles with `readingId` provenance.
3. `agents/diagnosis.py`: consume `trust/physics.py` output (M2) + evidence
   bundle, produce diagnosis proposals/objections — read-only relative to
   trust internals.
4. `agents/resource.py`: tank/pump/schedule/ledger allocation proposals,
   enforces the daily drawdown constraint (§8) as a blocking objection.
5. `agents/coordinator.py`: routes based on agent responses, no invented
   values, no side effect.

## Success Criteria

- [ ] Diagnosis module contains no call into `tools/` or `schedule/` (grep check).
- [ ] Resource's blocking objection fires when a proposed plan's `plannedDrawdownPct` sum exceeds `level − safe_reserve`.
- [ ] Coordinator's route decision references only agent responses + World State, never a hard-coded threshold.

## Risk Assessment

Boundary violations (Diagnosis calling a tool, Coordinator inventing a
number) are exactly the kind of drift `scripts/check-ownership.sh` cannot
catch (it's semantic, not a file-path issue) — cover with grep-based tests
in `tests/agents/`.
