---
phase: 1
title: "World State"
status: pending
priority: P1
effort: "3h"
dependencies: []
---

# Phase 1: World State

## Overview

Monotonic Farm World State store (§4.1): `farmStateVersion`,
`createdFromStateVersion` stamped on every decision, and a policy-filtered
slice for anything sent to the LLM.

## Requirements

- Functional: `farmStateVersion` increments on every update, never
  decreases. Every decision record stores `createdFromStateVersion` so
  replay reconstructs exactly what the system saw at decision time.
- Non-functional: LLM only ever receives a filtered slice — never the raw
  full state, never `scenario`.

## Architecture

Structured state, typed decision records — natural language is explanation
only, never a data source (§4.1). Persisted via `store/db.py` (M1,
read-only dependency here).

## Related Code Files

- Create: `worldstate/state.py`, `worldstate/version.py`,
  `worldstate/llm_slice.py` (policy filter)

## Implementation Steps

1. `worldstate/state.py`: the state shape from §4.1's JSON skeleton.
2. `worldstate/version.py`: monotonic version counter + update helper.
3. `worldstate/llm_slice.py`: whitelist-based filter, explicitly drops
   `scenario` and anything not policy-approved.

## Success Criteria

- [ ] Two consecutive updates always produce strictly increasing `farmStateVersion`.
- [ ] `worldstate/llm_slice.py` output never contains the key `scenario`.
- [ ] Every decision object created downstream carries a `createdFromStateVersion` matching the state at creation time.

## Risk Assessment

If the LLM slice filter is ever bypassed, `scenario` could leak into the
reasoning path — this is INV-9's other half (M1 owns the grep test; this
module is what the grep test protects).
