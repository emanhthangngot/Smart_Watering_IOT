---
phase: 1
title: "World State core"
status: pending
priority: P1
effort: "3h"
dependencies: []
---

# Phase 01: World State Core

## Context Links

- [Plan overview](./plan.md)
- [Master design §4.1](../reports/plan.md)
- [Independent-first decision](./reports/brainstorm-260816-1035-agents-independent-first.md)

## Overview

`READY NOW`. Build an in-memory, versioned World State and an allowlist-based LLM slice. Persistence is a later adapter; it must not leak asyncpg or M1 schema details into the domain core.

## Requirements

- Functional: initial version `0`; every accepted update creates a new snapshot with version `previous + 1`; historical snapshots never change.
- Functional: downstream decisions can stamp the exact `created_from_state_version` they consumed.
- Functional: the LLM slice contains only explicitly allowed fields and recursively rejects `scenario`.
- Non-functional: stdlib only; deterministic; no database, network, global mutable singleton, or wall-clock lookup hidden inside domain logic.

## Architecture

`WorldState` owns snapshot history and takes the timestamp as input. `build_llm_slice()` is a pure boundary function. Persistence later implements C1 around public snapshot operations; it does not replace their semantics.

```text
State update + explicit timestamp
  → validate top-level section
  → copy-on-write snapshot
  → version + 1
  → optional allowlisted LLM slice
```

## Readiness Split

### READY NOW

- Snapshot model and in-memory history.
- Monotonic update operation.
- Version lookup and current snapshot lookup.
- Recursive allowlist projection and forbidden-key assertion.
- Unit and property-style tests using fixed timestamps.

### COORDINATION

- C1/M1: repository for loading/appending snapshots with optimistic version conflict detection; the current M1 plan exposes a pool but no operational snapshot repository.
- C0/M1+dev: mapping from frozen shared decisions to `created_from_state_version`.
- C2/M2: any trust/physics projection accepted into a snapshot must name the same `source_state_version`; stale or unversioned verdicts are rejected rather than silently attached.
- C4/M4: serialization for `GET /farm/state`.

Do not import `store.db` before C1. Do not write a SQL repository under `worldstate/`.

## File Inventory

| Action | Absolute path | Responsibility | Coordination |
|---|---|---|---|
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/worldstate/state.py` | `FarmStateSnapshot`, `WorldState`, copy-on-write update/history | none for core |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/worldstate/llm_slice.py` | allowlist projection, forbidden-key check | C5 only when provider wired |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_world_state.py` | version/history/immutability tests | none |
| Create | `/home/pearspringmind/Hackathon/vamos_su2026/tests/agents/test_llm_slice.py` | allowlist and nested `scenario` tests | none |

Do not create the previously proposed `worldstate/version.py`; versioning is one invariant owned by `WorldState`, so splitting it adds indirection without a second responsibility.

## Function and Interface Checklist

- [ ] `FarmStateSnapshot`: frozen/slots record with state version, update time, and the §4.1 top-level sections.
- [ ] `WorldState.current() -> FarmStateSnapshot`.
- [ ] `WorldState.at(version: int) -> FarmStateSnapshot` with explicit not-found error.
- [ ] `WorldState.apply(section: str, value: object, *, at: datetime) -> FarmStateSnapshot`.
- [ ] `build_llm_slice(snapshot, allowed_paths) -> Mapping[str, object]`.
- [ ] `assert_no_forbidden_keys(value, forbidden={"scenario"}) -> None`.
- [ ] No function reads `datetime.now()` internally; caller supplies time for replay.

## Implementation Steps

1. Write failing tests for version 0, two sequential updates, historical immutability, and deterministic replay with fixed timestamps.
2. Implement the smallest snapshot/history model that passes those tests.
3. Write failing tests for top-level and deeply nested `scenario`, unknown fields, and immutable output.
4. Implement recursive allowlist projection; reject forbidden keys before any provider call.
5. Add an import-boundary test proving this phase does not import external-owner/runtime packages.
6. Set `pytestmark = pytest.mark.agents` in every new M3 test module so `make check-agents` cannot silently deselect it.
7. After C1/C2, add conflict and trust-version mapping tests without changing the pure snapshot semantics.
8. Run the phase regression gate.

## Test Scenario Matrix

| Case | Input | Expected |
|---|---|---|
| Initial state | no updates | version 0, empty allowed sections |
| Sequential update | two accepted patches | versions 1 then 2 |
| Historical read | mutate later section | version 1 unchanged |
| Invalid section | unknown top-level key | explicit domain error, no new version |
| Forbidden top-level | `scenario` | rejected |
| Forbidden nested | nested `scenario` | rejected |
| Extra field | not in allowlist | omitted, not passed through |
| Replay | same updates/timestamps | structurally identical snapshots |
| Stale trust projection | verdict version != snapshot version after C2 | rejected; no new snapshot |
| Concurrent append | two writes from same expected version after C1 | one succeeds, one explicit conflict |

## Success Criteria

- [ ] `pytest -q tests/agents/test_world_state.py tests/agents/test_llm_slice.py -m agents` passes.
- [ ] Two accepted updates always increment exactly once.
- [ ] No caller can mutate an earlier snapshot through a shared nested reference.
- [ ] No output from `build_llm_slice()` contains `scenario` at any depth.
- [ ] Every test module created by this phase is selected by `pytest -m agents`.
- [ ] After C1/C2, stale trust projections and competing snapshot appends fail closed.
- [ ] `rg -n "import (asyncpg|store|trust|tools|api)" worldstate tests/agents/test_world_state.py tests/agents/test_llm_slice.py` returns no prohibited import.

## Risk Assessment

- Deep immutability can become an unnecessary generic framework. Use only the concrete §4.1 sections and copy-on-write containers needed by tests.
- In-memory history is not production persistence. Mark it as the domain implementation, not a silent persistence substitute; C1 remains mandatory.

## Rollback

This phase creates only M3-owned files. Revert the phase commit if the frozen contract forces a different snapshot boundary; do not patch around it with dual models.
