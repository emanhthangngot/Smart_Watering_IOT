---
title: "M3 Agents and orchestration"
description: "Build the M3 pure agent kernel first, then integrate through explicit cross-branch gates."
status: pending
priority: P1
effort: 22h
issue: null
branch: feat/agents
owner: M3
tags: [feature, backend, agents, critical]
blockedBy: [260816-0957-data-plane, 260816-0957-trust-engine, 260816-0957-tools-runner-api]
blocks: []
created: 2026-08-16
---

# M3 — Agents & Orchestration

## Overview

Implement in two lanes. `READY NOW` builds pure M3 behavior without Supabase, MQTT, FastAPI, M2, M4, or an LLM credential. `COORDINATION` starts only after the named owner publishes an executable contract. Plan completion is blocked by M1/M2/M4; the pure kernels in phases 01-05 are not.

Design authority: [`plans/reports/plan.md`](../reports/plan.md) §§4.1, 6, 7, 10.2, 11.1. Decision report: [`Agents independent-first design`](./reports/brainstorm-260816-1035-agents-independent-first.md).

## Branch Context Audit

Audited on 2026-08-16 using each local branch tip; feature branches are plan/skeleton branches based on `dev`, so coordination claims below are not inferred from hypothetical implementation.

| Branch | Audited tip | Relevant contract/ownership result |
|---|---|---|
| `dev` | `c74ede2` | Owns integration order and frozen cross-branch gates; current delivery order needs C7 repair. |
| `feat/data-plane` (M1) | `4fb2070` | Owns shared contracts/storage; `PlanRevision` and operational repository surfaces required by C0/C1 are not planned. |
| `feat/trust-engine` (M2) | `64f47ed` | Owns trust/physics/divergence; typed outputs and source-state binding required by C2 are not frozen. |
| `feat/agents` (M3) | `b873303` | Owns the pure kernels and adapters in this plan; must not edit M1/M2/M4/M5-owned paths. |
| `feat/tools-runner-api` (M4) | `02c8c9b` | Owns tools, runner, API, ledger, recovery; atomic reservation/claim/effect and composition gates are C3/C4. |
| `feat/operator-ux` (M5) | `4a66724` | Consumes serialized API state/explain data; owns no M3 runtime surface and currently names no Reporting consumer. |

## Workspace Rules

- Own: `worldstate/`, `agents/`, `graph/`, `prompts/`, `tests/agents/`.
- Append-only: this plan, `tests/invariants/test_inv_04.py`, `docs/agents.md`, `requirements/agents.txt`.
- Read-only: `contracts.py`, `registry/`, `store/`, `trust/`, `tools/`, `schedule/`, `verify/`, `api/`, `frontend/`.
- No new top-level directory, agent framework, event bus, DI container, duplicate shared contract, or direct side effect.
- Before PR: `make check-agents && make ownership && git rebase origin/dev`.
- Retry/output rules: [`phase-03-retry-and-output-control.md`](../260816-0957-farmops-delivery/phase-03-retry-and-output-control.md).

## Clean and Exact Code Gates

- Apply YAGNI, then KISS, then DRY. Add a file/abstraction only when the phase inventory gives it one concrete responsibility.
- Do not add placeholder behavior, fake production data, permissive fallbacks, duplicate contracts, generic agent/event frameworks, or TODO-backed acceptance.
- Keep pure kernels synchronous and side-effect free; inject time, policies, state versions, and external projections explicitly.
- Use frozen/immutable value objects, named domain errors, stable ordering/tie-breaks, and one canonical serializer/hash after C0.
- Numeric boundaries, units, freshness windows, timezone, and rounding must be explicit and tested at equality/just-over limits; do not rely on implicit binary-float equality across contracts.
- Catch only expected boundary failures. Provider, storage, trust, and tool errors fail closed and preserve the deterministic result/audit trail.
- New tests prove behavior, carry the `agents` marker, and use real owner contracts at integration gates; test doubles stay inside tests.

## Execution Strategy

| Phase | Objective | Ready-now scope | Coordination gate |
|---|---|---|---|
| 01 | [World State](./phase-01-world-state.md) | In-memory immutable snapshots, monotonic version, LLM slice | M1 repository only for persistence |
| 02 | [Deterministic agents](./phase-02-deterministic-agents.md) | Vocabulary, messages, Coordinator, Resource policy | G0 Reading; G2 trust types; M4 atomic reservation |
| 03 | [Planner](./phase-03-planner.md) | Deterministic allocator, prompt boundary | G0 PlanRevision; LLM provider |
| 04 | [Grounding and graph](./phase-04-grounding-and-graph.md) | Membership + typed semantic checks, retry cap, in-memory graph/BFS | G1 edge repository/retention; M4 edge emitters/API |
| 05 | [Monitoring and replan](./phase-05-monitoring-and-replan.md) | Idempotency/debounce/open-replan guard | G0/G2/M4 repository + tool gateway + recovery |
| 06 | [Reporting](./phase-06-reporting.md) | Deferred; no code before consumer approval | LLM provider plus API/UI consumer |

Independent implementation order: phase 01 → phase 02 → phase 03 → phase 04 → phase 05. Phase 06 is not queued. Within a phase, complete only `READY NOW`; any task labeled `COORDINATION` remains pending until its ledger evidence exists.

**READY NOW status (2026-08-16):** Phases 01-05 `READY NOW` scope is implemented and gate-verified: `pytest -q tests/agents -m agents` — 51 passed; `ruff check`/`ruff format --check` clean; `python -m compileall` clean; `git diff --check` clean; `make ownership` OK; independent tester and code-reviewer rerun both closed (all blocking findings fixed and reverified: allocator tank-headroom over-allocation, monitor watermark unbounded growth, import-boundary test blind spot, resource naive/aware datetime crash, evidence-ref metric charset). Each phase's per-item `READY NOW` success criteria are checked off in its phase file; items gated on C0-C8 remain unchecked by design. Plan-level `status: pending` is unchanged — overall completion still blocks on M1/M2/M4 per `blockedBy`.

## Coordination Ledger

| ID | Owner | Required output | Current status | Unblock evidence |
|---|---|---|---|---|
| C0 | M1 + dev | Frozen `PlanRevision`, complete `Challenge`, lifecycle enums, canonical snake_case↔camelCase serializer, versioned revision-hash algorithm covering actions/evidence/outcomes | **Missing from M1 G0 plan** | named round-trip + tamper test; `CONTRACT_VERSION == "1.0.0"` only afterward |
| C1 | M1 | Snapshot/plan/edge/invalidation repositories; atomic revision+assumption+edge unit; durable replan/effect state; referenced-evidence retention | **Missing from M1 storage plan** | callable integration tests against real schema, including post-retention INV-4 |
| C2 | M2 | Typed verdict/physics/divergence with `source_state_version`, evaluation ID/time, evidence IDs, and required-metric action blocks; narrow divergence predicate is P0 | **Types/version binding missing; divergence mislabeled P2** | G2 plus import/shape/version-match tests |
| C3 | M4 | Typed tool gateway; atomic active drawdown reservation; idempotent inspection/schedule control | **Callable surface and reservation missing** | `active_reserved + requested <= available` concurrency test; INV-1/2/3/6/8 |
| C4 | M4 + dev | M3 router/graph/recovery wiring; atomic runner-claim vs suspension; durable pending effects; single/claimed recovery barrier | **Conflicts with current M4-before-M3 merge order** | claim-vs-cancel race, crash recovery, multi-worker startup, `/farm/request`, `/explain` tests |
| C5 | dev + M3 | One provider/model; fail-closed config; data-egress allowlist; redacted logging; timeout/output limits; secret rotation/constant-time auth rules | **Provider/security contract absent** | offline failure test plus opt-in provider/egress smoke test; no credential committed |
| C6 | dev integrator | Ownership/location for N1-N4 scenario tests | **Owner/path absent** | scenario path accepted by ownership gate |
| C7 | dev integrator | Partial merge order: M4 core → M3 core → dev-owned M4/M3 composition | **Current order deadlocks C4** | revised delivery merge table and integration commands |
| C8 | M1 + dev + user | Globally unambiguous evidence ID format: `r_` + full UUIDv4, backed by a DB unique constraint | **Decision recorded; owner contract still required** | DB uniqueness/collision test and frozen evidence-ref contract |

No M3 task may satisfy C0-C8 by editing another owner's file or creating a local substitute.

### Coordination Validation Commands

Run these only after the owning branch adds the named gate tests; a green command without those tests is not unblock evidence.

| Gates | Owner command |
|---|---|
| C0-C1 | `make check-data-plane` plus the named round-trip/hash/repository/retention tests |
| C2 | `make check-trust` plus source-state mismatch and narrow-divergence tests |
| C3-C4 | `make check-tools` plus reservation, claim-vs-cancel, effect-recovery, and multi-worker tests |
| C5 | `make check-agents` plus the opt-in provider/egress smoke test in an approved environment |
| C6 | `make invariants` plus the dev-owned N1-N4 scenario suite |
| C7 | `make check && make ownership` on the composed `dev` tree |
| C8 | `make check-data-plane && make invariants` with the collision/uniqueness case enabled |

## Acceptance Criteria

- Independent suite runs with no external service: `pytest -q tests/agents -m agents`.
- Every M3 test module sets the `agents` marker so `make check-agents` cannot silently deselect it.
- Ready-now modules do not import `store`, `trust`, `tools`, `schedule`, `verify`, `api`, FastAPI, asyncpg, or an LLM SDK.
- Allocator returns a deterministic draft before any optional phrasing call.
- Unknown evidence refs are rejected; numeric/status claims are structurally checked against the referenced decision-time evidence; at most 2 phrasing retries, then deterministic reasons.
- Snapshots and plan revisions are immutable; all decisions carry the source state version.
- Duplicate evidence produces one invalidation and at most one open replan per assumption.
- After C0-C8: INV-4 and automated N1-N4 integration paths pass.
- Final composed gate: `make check && make ownership && make invariants` on rebased `dev`.

## Scope Boundary

P0: phases 01-05 closed-loop behavior. Phase 06 Reporting is deferred until an API/UI consumer is approved. Ghost Farm, generic agent framework, RAG, multi-provider routing, and real-hardware actuation are out of scope.

## Red Team Review

### Session — 2026-08-16

**Findings:** 15 unique (14 applied, 1 user decision pending). **Severity:** 6 Critical, 9 High. Evidence came from this plan, current skeleton, and branch-qualified M1/M2/M4 plans.

| Finding | Disposition | Applied to |
|---|---|---|
| G0 omits PlanRevision/hash contract | Accept | C0, phases 03/05 |
| C1 repository deliverable has no owner plan | Accept | C1, phases 01/04/05 |
| Resource ignores active reservation | Accept | C3, phase 02 |
| Runner claim races suspension/cancel | Accept | C4, phase 05 |
| Replan lock/effect lost across crash | Accept | C1/C4, phase 05 |
| Multi-worker startup has no recovery barrier | Accept | C4, phase 05 |
| Trust verdict not bound to state version | Accept | C2, phases 02/03/04 |
| Retention can dangle evidence edges | Accept | C1, phase 04 |
| P0 divergence mislabeled P2 | Accept | C2, phase 05 |
| M3/M4 merge cycle | Accept | C7 |
| Grounding checks membership, not semantic truth | Accept | phases 04/06 |
| API/auth and provider security gaps | Accept as coordination | C4/C5 |
| Internal AgentResponse duplicates Challenge | Accept | phase 02 narrowed to RouteSignal |
| Reporting has no consumer | Accept | phase 06 deferred |
| Six-hex evidence ID collision risk | Resolved: use `r_` + full UUIDv4 plus DB uniqueness | C8 |

## Unresolved Questions

- C0-C7 are evidenced cross-owner gaps; coordination must update the owner plans before final integration.
- C8 decision recorded: use `r_` + full UUIDv4 plus a DB unique constraint; M1/dev must still freeze and test the shared contract.
- `triggering_evidence_version` decision recorded: use the monotonic `farmStateVersion`; M1/dev must still expose it in the durable contract.

## Whole-Plan Consistency Sweep

- Files reread: `plan.md`, phases 01-06, brainstorm report, master design, and the branch-qualified M1/M2/M4/M5 plans used during scouting.
- Decision deltas reconciled: independent-first boundary, internal message narrowing, active reservation arithmetic, state-version binding, semantic grounding, durable replan/effects, retention, merge order, security gates, and Reporting deferral.
- Red-team findings: 15 unique; all decisions recorded; owner-side contract gates remain open.
- Stale internal contradictions: 0. Open external decisions: none; C0-C8 owner evidence remains required.
- Implementation recommendation: start only phases 01-05 `READY NOW`; do not start coordination adapters or phase 06 until their named gates close.
