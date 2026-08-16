---
date: 2026-08-16
session: "M3 agents independent-first planning"
---

# Journal: 2026-08-16 — M3 Agents Plan-Only Session

## Context

Reworked the M3 Agents and Orchestration plan without implementing code. This journal records the session history; the plan, owner contracts, and future accepted decisions remain authoritative.

## What Happened

1. Audited `dev` (`c74ede2`) and five feature tips: `feat/data-plane` (`4fb2070`), `feat/trust-engine` (`64f47ed`), `feat/agents` (`b873303`), `feat/tools-runner-api` (`02c8c9b`), and `feat/operator-ux` (`4a66724`). The feature branches were still plan/skeleton branches, so no missing contract was treated as implemented.
2. Selected the independent-first design: build M3-owned, synchronous pure kernels with injected boundaries; wait for owner-published persistence, trust, tool, API, recovery, and provider contracts. Local substitutes for shared contracts were rejected.
3. Split phases 01–05 into `READY NOW` and `COORDINATION`, ordered as World State → deterministic agents → Planner → grounding/graph → monitoring/replan.
4. Red-teamed the plan: 15 unique Critical/High findings, 14 incorporated, with the evidence-ID choice retained as a user decision.
5. Deferred phase 06 Reporting. It has no named M4 API or M5 UI consumer and creates no code until P0 behavior, integration gates, retention, and consumer acceptance are ready.

## Coordination Gates Recorded

| Gate | Historical coordination requirement |
|---|---|
| C0 | M1/dev freeze `PlanRevision`, complete shared records/enums, serializer, and revision hash. |
| C1 | M1 provide operational repositories, atomic revision/assumption/edge writes, durable replan/effects, and evidence retention. |
| C2 | M2 publish typed trust/physics/divergence outputs bound to source-state versions; treat narrow divergence as P0. |
| C3 | M4 expose typed tool operations and atomic active-drawdown reservation with idempotent control. |
| C4 | M4/dev compose routing, graph, recovery, claim-vs-cancel atomicity, pending effects, and multi-worker recovery. |
| C5 | Dev/M3 select one fail-closed provider/model with egress, redaction, timeout, output, secret, and auth controls. |
| C6 | Dev assign an ownership-safe location for N1–N4 scenario tests. |
| C7 | Dev repair merge order to M4 core → M3 core → dev-owned composition. |
| C8 | M1/dev/user freeze globally unambiguous evidence identity and collision behavior. |

## Reflection

The independent-first boundary preserves useful offline work while making integration dependencies testable. The main remaining risk is treating green generic commands as evidence before the named owner tests and composed-tree checks exist.

## Decisions Made

| Decision | Rationale | Impact |
|---|---|---|
| Implement pure M3 kernels first | They need no upstream runtime services or credentials. | Phases 01–05 can begin in order without crossing ownership boundaries. |
| Keep adapters behind executable gates | Upstream contracts are not frozen. | No duplicate `PlanRevision`, repositories, trust records, or tool surfaces. |
| Defer Reporting | No approved consumer; P0 closed-loop work is more valuable. | Phase 06 remains a coordination note with zero implementation effort. |

## Validation Status

- Plan consistency sweep completed across `plan.md`, phases 01–06, and the approved brainstorm report: zero stale internal contradictions reported.
- Branch-qualified ownership and dependency audit recorded for `dev` plus all five feature branches.
- Plan and every phase remain `pending`; no source implementation was performed.
- No implementation tests, lint, typecheck, build, ownership gate, or invariant suite was run in this plan-only session. Named commands remain future unblock evidence, not current validation.
- AgentWiki publishing was skipped because external publication was out of scope and unavailable.

## Next Steps

- Start only phases 01–05 `READY NOW`; keep every adapter/effect task pending until its C0–C8 evidence exists.
- Have owner plans close C0–C7, then validate with their named tests before composed `dev` gates.
- Reopen Reporting only after its mandatory consumer, retention, security, and P0 conditions are accepted.

## Unresolved Questions

- C8: retain `r_` plus six hex with collision handling, or migrate to a globally unique evidence ID before freezing the contract?
- What is the authority for `triggering_evidence_version`: `farmStateVersion`, a batch epoch, or another monotonic version?
