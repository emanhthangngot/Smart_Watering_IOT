---
phase: 6
title: "Reporting"
status: pending
priority: P2
effort: "2h"
dependencies: [4]
---

# Phase 6: Reporting

## Overview

LLM-based operational report from trace/plan history/verification — read
only, no side effects (§7.1).

## Requirements

- Functional: given a trace slice and plan history, produce a readable
  operator report explaining what happened and why.
- Non-functional: never calls a tool, never mutates World State.

## Architecture

Reads via `graph/explain.py` (phase 04) for grounded citations in its
narrative — does not re-derive evidence itself.

## Related Code Files

- Create: `agents/reporting.py`, `prompts/reporting.py`

## Implementation Steps

1. `agents/reporting.py`: assemble trace + plan history + verification
   records, call LLM to phrase a report.
2. `prompts/reporting.py`: prompt template requiring citation of real
   `readingId`s pulled from `graph/explain.py`, not invented.

## Success Criteria

- [ ] Reporting module contains no import from `tools/`, `schedule/`, or `store/` write paths.
- [ ] Generated report cites at least one real `readingId` per claim about sensor state.

## Risk Assessment

Low — read-only by construction; main risk is the LLM inventing numbers in
prose, mitigated by requiring citations resolved through `graph/explain.py`.
