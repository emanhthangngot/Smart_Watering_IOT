---
phase: 4
title: "MQTT client"
status: pending
priority: P1
effort: "2h"
dependencies: [3]
---

# Phase 4: MQTT client

## Overview

Python WSS subscriber to `mqtt-hackathon.lexatek.vn:443`, config-driven,
feeding `ingest/normalize.py`.

## Requirements

- Functional: connects, authenticates, subscribes at QoS 0, forwards
  payloads to normalize. `environment`/`teamCode` read from `config.py`,
  never hard-coded literals in code.
- Non-functional: reconnect after drop replays without creating duplicate
  Reading rows (dedupe is at the DB layer, phase 2, so this just needs to
  not crash on reconnect).

## Architecture

`scripts/mqtt-read.mjs` is a protocol reference (raw WSS+MQTT 3.1.1
framing) — not a runtime dependency. Python implementation may use a
maintained MQTT library (e.g. `paho-mqtt` with websocket transport) instead
of hand-rolling the frame parser.

## Related Code Files

- Create: `ingest/mqtt_client.py`
- Add to `requirements/data-plane.txt`: MQTT client library

## Implementation Steps

1. Add MQTT client dependency to `requirements/data-plane.txt`.
2. `ingest/mqtt_client.py`: connect via config, subscribe, on-message →
   `ingest/normalize.py`.
3. Reconnect logic: exponential backoff, log but don't crash the process.

## Success Criteria

- [ ] Connects to broker using `.env` credentials (manual test, not committed).
- [ ] Forced disconnect/reconnect does not crash the process or duplicate DB rows.
- [ ] `environment`/`teamCode` come from `config.py`, verified by grep — no literal `"FARM"` or `"VAMOS"` in `ingest/`.

## Risk Assessment

Topic/broker host:port confirmed via `scripts/README.md`; topic pattern
`hackathon/<team-code>/test|judge/telemetry` — confirm judge topic before
freeze per §18 open question 1.
