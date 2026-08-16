# M3 READY NOW (phases 01-05) — rerun review

Date: 2026-08-16
Branch: `feat/agents`
Reviewer: code-reviewer (independent re-verification, not changelog trust)

## Scope

New untracked files (diffed against empty):
`worldstate/state.py`, `worldstate/llm_slice.py`,
`agents/vocabulary.py|messages.py|coordinator.py|resource.py|allocator.py|planner.py|monitor.py`,
`prompts/planner.py`, `graph/edges.py|explain.py|grounding.py`, `tests/agents/*` (13 modules).
Source LOC ~1,120; test LOC ~620.

Modified plan docs: `plan.md`, `phase-03/04/05` — reviewed; the edits record the C8
(UUIDv4) and `triggering_evidence_version` decisions and one added phase-03 requirement
clarifying `AllocationCandidate.window` semantics. These are decision records, not
goalpost moves, with the caveat noted in L8.

## Gate results

| Gate | Result |
|---|---|
| `ruff check worldstate agents graph prompts tests/agents` | All checks passed |
| `ruff format --check` (same paths) | 36 files already formatted |
| `pytest -q tests/agents -m agents` | 42 passed |
| Marker coverage | every test module sets `pytestmark = pytest.mark.agents`; `-m agents` selects all 42 collected tests (no silent deselect) |
| Forbidden runtime imports (grep, all M3 source) | none found (`store|trust|tools|schedule|verify|api|asyncpg|fastapi|openai|anthropic|litellm|paho`) |

`make check-agents` could not be run via `make` in this environment because the
project venv has no `pytest`; both target commands were run directly with
`/usr/bin/python`, which has the deps. Result is equivalent.

## Prior-fix re-verification (independent)

All ten claimed fixes are present and behaviorally confirmed:

- Deep-freeze of mutable leaves — `FarmStateSnapshot.__post_init__` freezes; `bytearray`
  leaf raises `TypeError` (verified).
- Constructor auto-freeze — external dict mutated after construction does not reach the
  snapshot (verified).
- Allowlist wildcard subtree — `telemetry.latest` yields `{}`, `telemetry.latest.*` yields
  the subtree (verified).
- Planner exception narrowing — `except (ConnectionError, GroundingError, TimeoutError)`.
- Evidence ref/metric validation — `r_<UUIDv4>#metric` with a cross-check that the ref
  suffix equals `claim.metric` and `evidence.metric` (verified; see M1 for residual gap).
- Version fail-closed — `allocate()` raises `StateVersionMismatch` when resource/trust
  versions are absent or mismatched (verified).
- Idempotency watermark — `_highest_version_by_slot` rejects `<=` versions and survives
  `_seen` trim (verified).
- Edge direction — `supports`/`derived_from` cannot terminate on an `r_` node (verified).
- Route conflict — accept + blocking reject raises `RoutingError` (verified).
- Resource clock fail-closed — missing `now` / stale / future `ledger_as_of` all return
  `REQUEST_MORE_EVIDENCE` (verified).

Candidate tank budget was **not** fully closed — see H1.

## Critical Issues

None. No trust-boundary escape, snapshot escape, scenario leak, or credential path was
reproducible. `scenario` is rejected as a section name and recursively at any depth before
projection; prompt facts are key-allowlisted and scalar-only; no error message carries
values or PII.

## High Priority

### H1 — Allocator does not enforce cumulative tank-reserve headroom (correctness, over-allocation)

`agents/allocator.py` checks `TANK_BELOW_RESERVE` and `TANK_RESERVE_LIMIT` per candidate,
but the only running budgets decremented across the loop are `remaining_drawdown` and
`remaining_minutes` (caller-supplied). Tank headroom is never accumulated.

Reproduced: two candidates, each `tank_level_pct=60`, `safe_reserve_pct=20`,
`drawdown_pct=30`, with `available_drawdown_pct=100`:

```
selected: [('a', '30'), ('b', '30')] total drawdown: 60   tank headroom: 40
```

The plan drains 60% from a tank with 40% of usable headroom, i.e. 20% below safe reserve.
Phase-03 requires "tank-reserve … constraints" and matrix row *Low tank → no
over-allocation*. Today the invariant holds only if the caller happens to pass
`available_drawdown_pct == level_pct - safe_reserve_pct`, which nothing in the code, the
types, or the tests requires — and if that is the intended contract, the per-candidate
tank fields are redundant.

Fix: track `remaining_tank_headroom` from the first candidate's tank facts (or reject
candidates whose tank facts disagree) and decrement it alongside `remaining_drawdown`;
emit `TANK_RESERVE_LIMIT` when exhausted. Add the two-candidate cumulative case to
`tests/agents/test_allocator.py`.

### H2 — Monitor dedupe state is not bounded (memory growth; violates phase-05 non-functional)

`agents/monitor.py`: `_trim()` bounds only `_seen`. `cleanup()` prunes `_seen` and
`_last_by_slot`. `_highest_version_by_slot` is never pruned or capped by either path.

Reproduced with `max_entries=5`, 1,000 distinct assumption slots, closing every replan and
calling `cleanup()` each iteration:

```
seen: 2   watermarks: 1000   last_by_slot: 2   open: 0
```

Phase-05 requires "bounded memory for local dedupe state" and a cleanup that removes
expired dedupe state without dropping open-replan locks. One entry per
`(plan_revision_id, assumption_id)` ever seen is unbounded in a long-lived monitor process
across plan revisions.

Compounding: `tests/agents/test_monitor.py::test_cleanup_is_bounded_and_does_not_remove_open_slot`
asserts only `remembered_events == 0` (a `_seen` counter). It executes the cleanup path
without proving the boundedness claim in its own name — a phantom assertion.

Fix: prune `_highest_version_by_slot` for slots that are neither open nor present in
`_last_by_slot` after cleanup, or cap it with the same LRU policy; assert total retained
state (all four containers) in the test.

### H3 — The import-boundary test does not detect `from X import Y` (broken guard on a plan acceptance criterion)

`tests/agents/test_agent_boundaries.py` collects `alias.name` for both `ast.Import` and
`ast.ImportFrom`. For `ImportFrom`, `alias.name` is the *imported symbol*, not the module
(`node.module` holds the module). Reproduced:

```python
src = "from trust.verdicts import Verdict\nimport tools.runner\n"
# test sees: {'tools', 'Verdict'}  -> catches only 'tools'
```

So `from trust.verdicts import Verdict` or `from store.db import pool` inside
`coordinator.py`/`resource.py` passes the guard.

Second gap: the guard covers only `agents/coordinator.py` and `agents/resource.py`. The
plan acceptance criterion is "**Ready-now modules** do not import `store`, `trust`,
`tools`, `schedule`, `verify`, `api`, FastAPI, asyncpg, or an LLM SDK", and phase-05
success criteria separately require it for `agents/monitor.py`. `worldstate/*`,
`graph/*`, `prompts/planner.py`, `agents/planner.py`, `agents/monitor.py`,
`agents/allocator.py` are unguarded. (Grep confirms the tree is currently clean — the
defect is that the automated gate would not catch a regression.)

Fix: use `node.module` for `ImportFrom`, iterate every `.py` under
`worldstate|agents|graph|prompts`, and include `asyncpg`, `fastapi`, and the LLM SDK names
in the forbidden set. Resolve paths from `Path(__file__).parents[2]` rather than a
CWD-relative literal.

## Medium Priority

### M1 — Evidence-ref metric suffix accepts arbitrary payload

`graph/grounding.py::_UUID_REF` ends with `#[^#]+`. Reproduced accepted refs:

```
r_<uuid>#level\nIGNORE PRIOR INSTRUCTIONS
r_<uuid># (single space)
r_<uuid>#{"a":1}
```

The parsed metric flows into `validate_sensor_claim` comparisons and into
`build_planner_prompt` (JSON-escaped, so no prompt break today, but this is the parser
that phase-04 designates as the single authority for ref syntax before the C0 freeze).
Constrain to `[A-Za-z0-9_]{1,64}` (or the C0 metric charset) and add a rejection test.

### M2 — Resource kernel raises a raw `TypeError` on mixed tz-awareness

`agents/resource.py`: `resource.now - resource.ledger_as_of` with one naive and one aware
datetime raises `TypeError: can't subtract offset-naive and offset-aware datetimes`
(reproduced). This escapes the kernel as an untyped exception rather than
`REQUEST_MORE_EVIDENCE` or `ResourceInputError`, so the caller's boundary handling sees an
unmodelled failure. Phase-02 requires timezone identity to be explicit and the kernel to
treat unknown facts as more-evidence. Guard `tzinfo` agreement explicitly.

### M3 — `farm_day` and `timezone` are presence-checked but never used

`ResourceInput.farm_day` / `.timezone` are validated for non-emptiness and then never read.
The phase-02 matrix row *Day boundary — reservations straddle configured farm-day timezone
→ totals belong to the explicit correct day; no host-timezone inference* has no
implementation and no test. Either the day-scoped totals are entirely the caller's
responsibility (then the fields are decorative and give false assurance in review), or the
kernel must bucket `ledger_as_of` into `farm_day` under `timezone`. Decide and document;
do not leave a presence check standing in for the requirement.

### M4 — `WorldState.apply` re-copies the entire state per update, and history is unbounded

`apply()` calls `_thaw()` over **all** sections, `deepcopy()` on the new value, `_freeze()`
on the whole result, and then `__post_init__` calls `_freeze()` on it a second time — three
full traversals of the entire world state for a one-key update. Sections not being updated
are already immutable and can be carried by reference.

Measured: with a 5,000-row `telemetry` section, 20 unrelated one-key `resources` updates
took **0.557 s** (≈28 ms each), and 22 full deep copies are retained in `_history` forever.
At the design's 1 Hz MQTT batch cadence this is a live CPU and memory problem, not a
theoretical one.

Fix: `values = dict(self.current().sections)`; freeze only the incoming value; drop the
duplicate `_freeze` at the call site. Separately, bound `_history` (ring buffer or explicit
retention) and note it in phase-01 alongside the C1 persistence gate. Minor related item:
`current()` does `max(self._history)` — O(n) per call, called twice per `apply`; track the
head version.

### M5 — `_freeze` rejects `datetime` and `Decimal` leaves

`FarmStateSnapshot(..., {"telemetry": {"observed_at": datetime(...)}})` raises
`TypeError: unsupported mutable snapshot leaf: datetime` (reproduced). Both types are
immutable and both are pervasive in this domain (`Reading.event_time`, evidence
observation times, `Decimal` money/percent values). Fail-closed is the right default, but
the allowlist is too narrow and will surface as a wall at the M1 adapter gate. Add
`datetime`, `date`, `Decimal`, and `Enum` to the accepted leaf types.

### M6 — Test gaps against the phase matrices (7 of 10 allocator branches unexercised)

Reason codes never asserted anywhere in `tests/agents`:
`MISSING_ALLOWED_WINDOW`, `MISSING_TANK_FACT`, `TANK_RESERVE_LIMIT`, `INVALID_REQUEST`,
`WINDOW_TOO_SHORT`, `PUMP_OVERLAP`, `PUMP_MINUTE_LIMIT`.

`PUMP_OVERLAP` is the notable one: `test_no_overlap_allowed_window_and_reserve_constraints_are_explicit`
names overlap but its candidates sit at `window(5)`/`window(6)` while the existing
allocation is at `window(3)` — the overlap branch never executes, and the two other
candidates are rejected earlier by `OUTSIDE_ALLOWED_WINDOW`/`TANK_BELOW_RESERVE`. The test
name overstates what it proves. (I confirmed by direct execution that the overlap logic
itself is correct, both against `existing_allocations` and against already-selected slices,
so this is a coverage defect, not a behavior defect.)

Also missing against the phase matrices:
- Phase-04 *Stale/untrusted evidence*: `trust_eligible=False` / `freshness_eligible=False`
  rejection in `validate_sensor_claim` is never tested.
- Phase-04 *Multiple fabricated refs → stable ordered error*: only a single missing ref is
  tested.
- Phase-03 implementation step 4 explicitly requires adversarial injection text in the
  prompt-boundary test; `test_prompt_serializes_grounded_text_as_data` uses benign values
  only.

### M7 — `worldstate/llm_slice.py` imports the private `_freeze` from `worldstate.state`

Cross-module use of an underscore-private helper. Either promote it to a documented
`freeze()` in `state.py` or move the freeze helper to a shared internal module. Same
pattern to watch: `prompts/planner.py` depends on `DecisionEvidenceView`'s field set
exactly matching `_FACT_KEYS` — adding one field to the dataclass turns every
`build_planner_prompt` call into `PromptBoundaryError` at runtime, with no test pinning the
relationship.

## Low Priority

- **L1 — Dead public surface (YAGNI).** Unused anywhere in source or tests:
  `AllocationResult.quantitative_fields`, `FarmStateSnapshot.farm_state_version`,
  `FarmStateSnapshot.section()`, `InvalidAllowlistPath` (never raised in any test).
  `NarrativeFields.reasons` is worse than unused: a narrator can populate it and `plan()`
  silently discards it, keeping only `.summary`. Remove or consume.
- **L2 — Coordinator.** (a) The `len({...source_state_version...}) != 1` check is dead —
  the preceding `any(... != state_version)` already guarantees it. (b) Duplicate
  `signal_id` values are accepted and echoed (`('s1', 's1')` reproduced); the route table
  treats them as two votes. (c) A non-blocking `ESCALATE_TO_HUMAN` produces the generic
  `"conflicting route signals have no safe transition"` instead of routing to `human`
  (reproduced) — fail-closed, but the escalation intent is silently lost.
- **L3 — Allocator numeric failures are inconsistent.** A non-finite `urgency`,
  `duration_minutes`, or `drawdown_pct` raises `AllocationInputError` and aborts the whole
  allocation (`nan urgency -> AllocationInputError` reproduced), while `duration <= 0`
  yields a per-candidate `INVALID_REQUEST` reason. One candidate with bad data destroys the
  plan for all others. Pick one policy.
- **L4 — `WorldState.apply` does not check `at` monotonicity.** Version increases while
  `updated_at` may go backwards. Explicit-time injection is correct for replay, but a
  non-decreasing assertion costs nothing and protects the audit trail.
- **L5 — `graph/explain.py` BFS is O(V·E log E).** `EvidenceGraph.incoming()` calls
  `edges()`, which sorts the entire edge set on every node visit. Build an adjacency index
  once, or sort in `trace_to_readings`.
- **L6 — Allowlist wildcard.** `telemetry.*` returns the whole frozen subtree with no
  post-projection forbidden-key re-check (safe today only because
  `assert_no_forbidden_keys` runs on the full snapshot first — so the guarantee depends on
  call ordering inside `build_llm_slice`, not on the projection itself). Mid-path wildcards
  (`a.*.b`) silently match nothing. A leaf path pointing at a `set`/`frozenset` returns the
  whole collection unfiltered, unlike the Mapping/list cases.
- **L7 — `select_touched_assumptions` scans the full dependency index per batch**
  (`O(assumptions × deps)`), building a fresh `set(dependencies)` each time. At 1 Hz with a
  growing assumption set this is the wrong direction; an inverted `metric -> assumptions`
  index is `O(changed)`.
- **L8 — Plan-doc edit worth flagging.** `phase-03` gained the requirement
  "`AllocationCandidate.window` is a fixed requested execution interval" *after*
  implementation. The semantic is reasonable, but it was documented to match code rather
  than the reverse; confirm the interval semantics with the M4 scheduling owner before C3.

## Answers to the specific review questions

(a) **Acceptance criteria.** Phase 01, 02, 04 core criteria are met. Phase 03 fails the
"no over-allocation" tank criterion (H1) and the adversarial prompt-boundary step (M6).
Phase 05 fails the "bounded memory for local dedupe state" non-functional requirement (H2).
The plan-level criterion "ready-now modules do not import …" is true in fact but its
automated gate is ineffective (H3). Phase-02's day-boundary row is unimplemented (M3).

(b) **Business-logic regressions.** None — all files are new; no existing module was
touched. `contracts.py`, `config.py`, and every read-only path are unmodified.

(c) **Public contracts.** No breaking change. `contracts.py` (`CONTRACT_VERSION
"0.0.0-unfrozen"`) is untouched, and M3 correctly declines to define a local `PlanRevision`
or `Challenge`. `DecisionEvidenceView` / `RouteSignal` are appropriately scoped as internal
projections.

(d) **Repo conventions.** Followed: `from __future__ import annotations`, frozen+slots
dataclasses, module `__all__`, named domain errors, injected clocks, `pytestmark` on every
test module, ruff-clean at line-length 100. Deviations: M7 (private cross-module import)
and L1 (unused exports).

(e) **Lint/type/build.** Clean. No suppressions, no `# type: ignore`, no `Any` widening
beyond the deliberate JSON-shaped `Any` in `worldstate`. mypy is configured in
`pyproject.toml` but not wired into any `make` target and is not installed here, so no type
run was possible.

(f) **Security/correctness.**
- Immutable snapshot escape: none found — constructor freeze, `_thaw`+`deepcopy` on write,
  `MappingProxyType` views over locally-owned dicts, `TypeError` on assignment (verified).
- Allowlist leakage: nested `scenario` rejected pre-projection at any depth (verified);
  non-allowlisted siblings dropped; residual wildcard caveats in L6.
- Fail-closed boundaries: allocator version/tank-fact/window gates, resource
  clock/staleness/missing-fact gates all return or raise rather than guess — except the
  cumulative tank gap (H1) and the untyped tz `TypeError` (M2).
- Grounding bypass: no path reaches `AllocationResult.narrative` from a narrator without
  `assert_grounded` + `validate_sensor_claim` + the numeric/status token checks; the
  2-attempt cap is enforced (`calls == 2` with `max_retries=9`, verified).
- Evidence-ref parsing: single parser, UUIDv4-strict, metric suffix cross-checked against
  both claim and evidence; residual charset looseness in M1.
- Forbidden imports: none present; guard is weak (H3).
- Scenario leakage: `scenario` is not a valid section, rejected in `WorldState.__init__`,
  `apply()`, `build_llm_slice()`, and `build_planner_prompt()`.

## Recommended actions

1. Fix H1 (cumulative tank headroom) and add the two-candidate over-allocation test —
   blocking; this is a real over-irrigation path.
2. Fix H3 (`ImportFrom` module resolution + full module sweep) — blocking; without it the
   ownership/isolation criterion is unenforced going into integration.
3. Fix H2 (bound `_highest_version_by_slot`) and strengthen the boundedness assertion.
4. Tighten the evidence-ref metric charset (M1) and the tz guard in `evaluate_resource` (M2).
5. Reduce `WorldState.apply` to a shallow section swap and bound `_history` (M4); widen the
   frozen-leaf allowlist to `datetime`/`Decimal` (M5).
6. Close the M6 test gaps: `PUMP_OVERLAP` (and rename that test to what it proves),
   trust/freshness ineligibility, multi-missing-ref ordering, adversarial prompt text.
7. Resolve M3 (`farm_day`/`timezone`): implement day bucketing or remove the fields.
8. Sweep L1 dead surface before the phase commit lands.

## Metrics

- Type coverage: annotations on 100% of public functions/dataclasses; mypy not runnable
  here (not installed, not in any make target).
- Test coverage: not measurable (`coverage` not installed). Manual branch audit: 7 of 10
  allocator constraint branches and the grounding eligibility branch are unexercised.
- Lint issues: 0. Format issues: 0. Tests: 42 passed / 0 failed / 0 deselected.

## Unresolved questions

1. Is `available_drawdown_pct` contractually required to already equal tank headroom? If
   yes, the per-candidate tank fields should be removed and the invariant asserted; if no,
   H1 must be fixed in the kernel. This needs the M4/C3 reservation owner's answer.
2. Should the LLM slice (`build_llm_slice`) feed `build_planner_prompt`? Today the two
   boundaries are independent and the slice has no production consumer; phase-03 states
   "only the phase-01 slice plus allocator output may cross the boundary".
3. Are snapshot section leaves expected to carry `datetime`/`Decimal` (M5)? This determines
   whether the current freeze allowlist is a deliberate string-only contract or an
   oversight that C0 serialization will collide with.
