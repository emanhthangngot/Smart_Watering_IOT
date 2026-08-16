---
phase: 2
title: "Farm State and health panel"
status: pending
priority: P1
effort: "3h"
dependencies: [1]
---

# Phase 2: Farm State and health panel

## Overview

Farm State screen + health panel (§11.2): observed batch period,
`late_ratio`, clock skew, absent devices, outbox depth — all from
`GET /health` and `GET /farm/state` (M4).

## Requirements

- Functional: freshness/connectivity and DCS/tier shown with a **reason in
  words**, not color alone.
- Non-functional: works at 390px width.

## Architecture

Consumes `GET /farm/state` and `GET /health` (M4, read-only dependency).

## Related Code Files

- Create: `frontend/app/farm-state/`, `frontend/app/health/` (or app-router
  equivalents), shared device/freshness display components

## Implementation Steps

1. Farm State page: per-device freshness chip + textual reason (e.g. "SOIL_01: stale, 840s old, ttl 300s").
2. Health panel: batch period, `late_ratio`, skew, absent devices, outbox depth.
3. Poll `GET /farm/state` / `GET /health` on an interval (WebSocket/poll 5s per §11.4 P0 decision — no Supabase Realtime in P0).

## Success Criteria

- [ ] Every freshness/tier indicator has adjacent text explaining why, not color alone.
- [ ] Screen renders without horizontal scroll at 390px.

## Risk Assessment

Low — straightforward consumer of an already-defined API contract.
