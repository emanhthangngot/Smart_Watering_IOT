---
phase: 1
title: "Freshness and states"
status: pending
priority: P1
effort: "2h"
dependencies: []
---

# Phase 1: Freshness and states

## Overview

Reading state machine (§3.3) and the freshness curve derived from
`ttl_batches × observed_batch_period` (§3.5).

## Requirements

- Functional: states FRESH / STALE / SUSPECT / OFFLINE / MISSING per the
  §3.3 table. `freshness(age, ttl)`: 1.0 if `age ≤ ttl`; linear decay to 0
  between `ttl` and `3·ttl`; 0.0 beyond.
- Non-functional: pure function, no I/O, no exceptions on missing data.

## Architecture

Consumes `Reading` + presence info from `feat/data-plane`'s `ingest/`
output (via `registry/specs.py` for `ttl_batches`) — read-only dependency,
no cross-edit.

## Related Code Files

- Create: `trust/states.py` (state assignment), `trust/freshness.py`
  (freshness curve)

## Implementation Steps

1. `trust/states.py`: given a Reading + presence + `status` field, assign
   FRESH/STALE/SUSPECT/OFFLINE/MISSING per §3.3.
2. `trust/freshness.py`: implement the piecewise freshness formula exactly
   as in §3.5.

## Success Criteria

- [ ] `status != "ok"` → SUSPECT, excluded from completeness (C).
- [ ] Device absent ≥ `offline_batches` (3) → OFFLINE.
- [ ] `freshness(age=ttl, ttl) == 1.0`, `freshness(age=2*ttl, ttl) == 0.5`, `freshness(age=3*ttl, ttl) == 0.0`.

## Risk Assessment

None significant — this is a direct formula transcription; risk is
transcription error, mitigated by exact-value unit tests above.
