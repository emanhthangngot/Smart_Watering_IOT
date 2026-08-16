# FarmOps API

The FastAPI application is exposed as `api.main:app`. It reads operator
credentials from the environment and never accepts an audit actor from a
request body.

## Authentication

Set `OPERATOR_TOKEN` and optionally `OPERATOR_ACTOR`. Every write request must
send:

```http
X-Operator-Token: <OPERATOR_TOKEN>
```

The audit log stores the configured actor and a one-way token identifier, not
the raw token. Missing or invalid credentials return `401`.

`POST /farm/request` always creates a trace. Before M3 is connected the trace
is explicitly marked `BLOCKED_DEPENDENCY`; after `FarmWorkflowPort` is
configured it moves through `QUEUING → ACCEPTED`. An uncertain queue result
returns `503` and remains inspectable through its trace rather than being
silently retried.

## Endpoints

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `POST` | `/farm/request` | Record an operator request | required |
| `GET` | `/farm/state` | Return the currently available farm state | — |
| `GET` | `/farm/plan/{revision_id}` | Look up a plan revision | — |
| `GET` | `/trust/current` | Return trust-engine availability/current result | — |
| `GET` | `/explain/{decision_id}` | Explain a recorded decision | — |
| `GET` | `/timeline/{trace_id}` | Return audit events for a trace | — |
| `POST` | `/approvals/{revision_id}/approve` | Approve the exact current revision hash | required |
| `POST` | `/approvals/{revision_id}/reject` | Reject the exact current revision hash | required |
| `GET` | `/tasks` | List operator tasks | — |
| `POST` | `/tasks/{task_id}/acknowledge` | Acknowledge a task | required |
| `POST` | `/tasks/{task_id}/resolve` | Resolve a task | required |
| `POST` | `/sim/{path}` | Simulator-only write boundary | required |
| `GET` | `/health` | Dependency-aware health status | — |

`/sim/*` returns `404` unless `ACTUATION_TARGET=sim`, and returns `503` when no
causal simulator adapter has been connected. The public API only accepts the
administrative fault-control operations `inject-fault`, `clear-fault`, and
`reset`; pump start/stop is exclusively owned by the permission-gated schedule
runner. Every simulator request requires a stable `commandId`:

```json
{
  "commandId": "demo-fault-001",
  "params": {"fault": "pump_no_effect"}
}
```

Repeating the exact command returns `DUPLICATE_REPLAY`. Reusing the same ID for
a different operation/payload returns `400`, and an uncertain adapter outcome
returns `503` then `409` on blind retry. No configured value can select a
real-hardware adapter.

## Runtime lifecycle

The FastAPI lifespan runs recovery before background work, then starts the
schedule runner, continuous approval/proposal expiry, and hourly retention when
their adapters are configured. `/health.runtime` exposes `RUNNING`, `READY`, or
explicit `BLOCKED_M1` states; missing dependencies are never presented as
healthy.

## Dependency state

Until M1 (data plane/storage) and M2 (trust engine) are merged, read endpoints
return explicit `PARTIAL` or `UNAVAILABLE` dependency states instead of
fabricated telemetry or trust results. The M4 service is intentionally behind
ports so those adapters can be connected without changing the HTTP contract.
