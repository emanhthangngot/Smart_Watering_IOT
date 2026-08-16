---
phase: 3
title: "Normalize and outbox"
status: pending
priority: P1
effort: "3h"
dependencies: [1, 2]
---

# Phase 3: Normalize and outbox

## Overview

§3.2 normalize pipeline: batch validation, team/environment filter, per
(device, metric) Reading construction, presence tracking, `epoch` authority
+ skew correction (§3.4), watermark/`late` flag, EWMA batch cadence (§3.5).

## Requirements

- Functional: unknown metric → skip + counter, never crash. Non-finite
  value → skip + audit. Missing both `epoch` and `timestamp` → drop batch,
  count, never guess. `|epoch − parse(timestamp)| > 2s` → audit
  `time_field_mismatch`, still use `epoch`.
- Non-functional: `skew_correction` = median of last 100
  `(received_at − event_time)`; `age < 0` after correction clamps to 0,
  counts `clock_anomaly`.

## Architecture

Device absent from `devices[]` ≥ `offline_batches` (default 3) → OFFLINE.
`ttl(metric) = clamp(ttl_batches × observed_batch_period, 15s, 1800s)`,
bootstrapped at `observed_batch_period = 10s` before 5 batches observed.

## Related Code Files

- Create: `ingest/normalize.py`, `ingest/presence.py`, `ingest/clock.py`
  (skew + watermark), `ingest/cadence.py` (EWMA)

## Implementation Steps

1. `ingest/normalize.py`: batch validate → team/env filter → per-device
   per-metric Reading construction using `registry/specs.py`.
2. `ingest/presence.py`: track consecutive absences per device, emit
   OFFLINE at threshold.
3. `ingest/clock.py`: epoch authority, skew EWMA, watermark, `late` flag.
4. `ingest/cadence.py`: EWMA batch period, bootstrap value.
5. Feed normalized Readings into `store/ingest.py` (phase 2).

## Success Criteria

- [ ] Batch with unknown metric → `unknown_metric` counter increments, no exception.
- [ ] Batch with non-finite value → skipped + audit row, no exception.
- [ ] Batch missing both `epoch` and `timestamp` → dropped, counted.
- [ ] Device absent 3 consecutive batches → presence tracker reports OFFLINE.
- [ ] `test_inv_10.py`: every threshold constant checked against §3.1 NORMAL baselines.

## Risk Assessment

Cadence unknown before competition — EWMA bootstrap already covers this
(§3.5); revisit `ttl` floor if real cadence differs wildly from 10s.
