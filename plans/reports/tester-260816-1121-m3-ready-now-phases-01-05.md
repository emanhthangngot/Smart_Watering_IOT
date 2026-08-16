---
type: tester
date: 2026-08-16
scope: M3 READY NOW phases 01-05
status: done_with_concerns
---

# Tester Report: M3 READY NOW Phases 01-05

## Summary

Requested executable gates pass except `make check-agents`, which cannot start because `ruff` is not installed. The 34 marked tests pass on Python 3.11.15 and Python 3.14.6, but independent probes expose acceptance gaps. Verdict: implementation not ready for M3 READY NOW acceptance until planner grounding and fail-closed input boundaries are corrected.

## Test Results Overview

| Gate | Result | Evidence |
|---|---|---|
| `pytest -q tests/agents -m agents` | PASS | 34 passed in 0.08s, Python 3.11.15 |
| `python3.14 -m pytest -q tests/agents -m agents` | PASS | 34 passed in 0.09s, Python 3.14.6 |
| `python -m compileall -q worldstate agents graph prompts tests/agents` | PASS | exit 0 |
| Python 3.14 compileall | PASS | exit 0 |
| `git diff --check` | PASS | no output |
| Supplemental target whitespace scan | PASS | no trailing whitespace or missing final newline |
| `make check-agents` | BLOCKED | exits 2 before tests: `ruff: No such file or directory` |

Coverage not collected; no project coverage gate requested.

## Acceptance Matrix

| Acceptance | Result | Notes |
|---|---|---|
| Immutable, monotonic World State | PASS | Frozen snapshots, deep JSON-shaped freezing, historical versions, explicit timestamps |
| Allowlist-only LLM slice | FAIL | Heterogeneous nested-list projection can emit the internal `_NO_MATCH` sentinel |
| Exact six interaction verbs | PASS | Exact value set verified |
| Active reservation arithmetic | PASS | Equality accepted; active + requested over available rejected |
| Deterministic allocator and provider fallback | PARTIAL | Stable ordering/fallback pass; missing tank/window facts are accepted instead of failing closed |
| Semantic grounding and maximum two narration calls | FAIL | Validator/retry helper exists but Planner never invokes it; unsupported numeric prose accepted on first call |
| Five graph relations and stable cycle-safe backward BFS | PASS | Exact relation set, deduplication, stable sorted result, cycle termination |
| Debounce and one open replan | PASS | Duplicate suppression, close/reopen, stress and bounded cleanup tests pass |
| Forbidden imports | PASS | Full AST scan found none in `worldstate/`, `agents/`, `graph/`, or `prompts/` |
| Scenario leakage in `agents/` and `graph/` | PASS | No textual hits |
| Every agent test module marked | PASS | All 13 `tests/agents/test_*.py` modules set `pytestmark = pytest.mark.agents` |

## Findings

### High — Planner bypasses semantic grounding and retry policy

`agents/planner.py:39-45` accepts any `NarrativeFields.summary` and catches all exceptions; it never calls `assert_grounded`, `validate_sensor_claim`, or `run_grounded_narration`. Read-only probe accepted `Tank is 999% full` with no grounded facts after one narrator call. `tests/agents/test_planner_fallback.py:32-35` currently codifies acceptance of unsupported numeric prose. This fails the phase-04 requirement that numeric/status claims be semantically grounded and bad narration receive at most two calls before deterministic fallback.

### High — Planner prompt does not enforce its allowlist boundary

`prompts/planner.py:27-30` serializes arbitrary caller mappings. Probe confirmed both `scenario` and a credential-shaped field cross into the prompt. Phase 03 requires structured allowlisted facts and excludes scenario/credentials. The phase-01 slice is not enforced by the Planner API.

### High — Allocator accepts missing required facts

`agents/allocator.py:101-102` treats no allowed windows as unrestricted. Lines 118-121 skip tank/reserve validation when either fact is absent. Probe using the existing planner request shape returned one accepted slice and no reasons despite missing tank, reserve, and allowed-window facts. This conflicts with the approved missing-fact fail-closed matrix.

### Medium — Resource freshness can be bypassed with no clock

`agents/resource.py:52-62` checks ledger age only when `now` is supplied. Probe supplied a 2020 ledger timestamp and `now=None`; assessment accepted with `needs_more_evidence=False`. Unknown freshness should request more evidence.

### Medium — Nested LLM projection leaks an internal sentinel

`worldstate/llm_slice.py:64-66` retains `_NO_MATCH` entries when only some list elements contain an allowed nested path. Probe of `telemetry.latest.value` over `[{'value': 1}, {'other': 2}]` returned a tuple containing a raw `object` sentinel. Output is not a clean allowlist projection.

### Medium — Evidence-ref syntax frozen before coordination gate

`graph/grounding.py:28-35` enforces strict `r_<uuidv4>#<metric>` syntax. Phase 04 assigns strict syntax freezing to C0/C8 coordination and says READY NOW should not lock the parser yet. Membership and semantic checks are otherwise correct.

## Recommendations

1. Integrate the grounding validator and two-call wrapper into Planner; reject unsupported numeric/status prose and preserve deterministic fallback.
2. Enforce allowlisted grounded-fact input at the prompt boundary, including recursive forbidden-key rejection.
3. Fail closed on missing allocator tank/reserve/window facts, or narrow the approved contract explicitly before changing tests.
4. Require an explicit evaluation clock for ledger freshness.
5. Drop unmatched list entries cleanly during nested LLM projection.
6. Defer strict evidence-ref syntax until C0/C8, or update the approved readiness split with owner evidence.
7. Install `ruff` in the development environment, then rerun `make check-agents`; do not change the Makefile.

## Unresolved Questions

- None. The approved phase files already define the expected fail-closed behavior.

## Status

Status: DONE_WITH_CONCERNS

Summary: Required tests and compile/whitespace gates pass; acceptance fails on grounded narration and multiple input-boundary gaps.

Concerns/Blockers: `ruff` unavailable; Planner grounding not integrated; prompt, allocator, resource freshness, and nested projection boundaries are not fail-closed.
