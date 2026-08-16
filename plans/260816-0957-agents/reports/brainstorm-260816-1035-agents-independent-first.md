---
title: "Agents independent-first design"
status: approved
branch: feat/agents
created: 2026-08-16
---

# Agents Independent-First Design

## Summary

Build M3-owned pure domain behavior before cross-branch contracts exist. Delay persistence, trust, tools, API, and runtime wiring until their owners publish stable interfaces. Do not duplicate or locally redefine shared contracts to appear unblocked.

## Problem Statement

`feat/agents` owns World State, deterministic agents, Planner orchestration, grounding, Evidence Graph, monitoring/replan, and Reporting. Current plan treats M3 as one block behind M1/M2/M4, while several useful kernels require only Python stdlib and M3-owned types.

Cross-branch gaps:

- `contracts.py` is unfrozen and has no `PlanRevision`.
- M1 plans `store/db.py` as a pool, not a repository contract.
- M2 has filenames but no typed verdict/physics/divergence results.
- M4 has no stable callable tool port; M4-before-M3 merge order conflicts with routers importing M3.
- LLM provider/model is not selected.

## Exact Requirements

- Expected artifact: update `plans/260816-0957-agents/plan.md` and its six phase files; no implementation.
- Acceptance: every task classified `READY NOW` or `COORDINATION`; every coordination item names owner, required contract, unblock evidence, and validation command.
- Scope boundary: M3-owned paths only. No plan step authorizes edits to `contracts.py`, `store/`, `trust/`, `tools/`, `schedule/`, `verify/`, or `api/`.
- Non-negotiable: deterministic allocator remains primary; only Planner phrasing and Reporting may use LLM; no `scenario` in runtime; no side effect outside M4 tool layer.
- Touchpoints: M1 shared contracts/storage, M2 trust outputs, M4 tool/API/recovery, M5 serialized operator views, dev merge/integration gates.

## Approaches Evaluated

### Full wait for upstream branches

Pros: no temporary seams. Cons: wastes parallel capacity; hides M3 design problems until late integration; unnecessary.

### Duplicate shared contracts inside M3

Pros: immediate coding. Cons: contract drift, mapping debt, ownership violation in spirit, likely rewrite after G0. Rejected.

### Independent pure kernel plus explicit ports

Pros: useful work now; unit-testable; adapters remain thin; respects ownership; makes coordination requirements executable. Cons: requires discipline to keep ports narrow and avoid speculative abstractions. Selected.

## Recommended Design

Two lanes:

1. `READY NOW`: M3-owned enums/value objects, versioned in-memory World State, whitelist LLM slice, deterministic Coordinator routing, allocation primitives, membership plus typed semantic grounding validation, graph traversal, pure monitor guard, and unit tests.
2. `COORDINATION`: shared Plan contract, storage repositories, trust adapters, tool gateway, API serialization/wiring, recovery hook, LLM provider, and end-to-end scenarios.

Grounded Reporting is deferred entirely until phases 01-05 are green and a named API/UI consumer is approved.

Ports exist only at demonstrated boundaries. Domain code accepts injected callables/protocols; it never imports `store/db.py` connection details or FastAPI. Shared domain objects remain owned by `contracts.py`; M3 must not create a competing `PlanRevision`.

## Clean-Code Controls

- YAGNI: no agent framework, event bus, generic plugin system, DI container, or second persistence layer.
- KISS: pure functions and frozen dataclasses where state mutation is not required; explicit state transitions where it is.
- DRY: one evidence-ref parser, one lifecycle transition table, one allocator constraint evaluator, one LLM-slice whitelist.
- Exact boundaries: domain modules do not import `api`, `tools`, `schedule`, `verify`, or asyncpg.
- Tests-first for monotonic versioning, immutable revisions, grounding rejection, retry cap, idempotent invalidation, and one-open-replan invariant.

## Risks

- Over-abstracting ports before upstream APIs exist. Mitigation: add a port only for a call already required by master scenarios N1-N4.
- Pure kernel diverges from frozen shared records. Mitigation: keep shared-object construction in later adapters; kernel outputs M3-owned intermediate results only.
- M3/M4 circular merge. Mitigation: M4 exposes callable adapters; final wiring occurs on `dev` after both modules exist, not by cross-editing ownership paths.
- Reporting distracts from P0. Mitigation: phase 06 creates no code until closed-loop gates and a named consumer are approved.
- Advisory resource checks can race concurrent reservations. Mitigation: final authorization requires M4 to atomically verify and reserve `active + requested <= available`.
- In-memory replan locks can orphan after a crash. Mitigation: C1/C4 require a durable job, pending-effect record, claim/lease recovery, and a multi-worker startup barrier.

## Success Metrics

- Independent unit suite runs without Supabase, MQTT, FastAPI, M2, M4, or LLM credentials.
- No ready-now module imports a downstream-owned package.
- Coordination ledger has no unnamed owner or unverifiable unblock condition.
- Integration phase maps N1-N4 and INV-4 to concrete tests.
- `make check-agents` and `make ownership` are the branch gates.

## Next Steps

1. Rewrite the existing M3 plan around independent and coordination lanes.
2. Add exact file inventories, function/interface checklists, test matrices, dependencies, and rollback notes to each phase.
3. Fact-check paths/contracts against branch plans.
4. Red-team dependency and scope claims.
5. Validate unresolved contract decisions before implementation crosses a coordination gate.

## Unresolved Questions

- Who adds and freezes `PlanRevision` and missing `Challenge` fields at G0: M1 or dev integrator?
- What exact repository functions will M1 expose for plans, snapshots, edges, and invalidations?
- What exact typed outputs will M2 expose for verdict, physics evidence, and divergence?
- What exact M4 callable surface will cover inspection creation, schedule defer/cancel, graph events, and recovery monitor attachment?
- Which LLM provider/model implements Planner phrasing and, only if phase 06 reopens, Reporting?
- Should evidence identity retain the current six-hex suffix with collision handling, or migrate to a globally unique ID before C0 freezes refs?
- Is `farmStateVersion` the authority for `triggering_evidence_version`, or does dev require another monotonic evidence epoch?
