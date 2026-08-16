"""Manual end-to-end proof: drives one full farm request -> approval ->
execution -> verification cycle purely through HTTP calls to a live
`uvicorn api.main:app` instance.

Usage:
    OPERATOR_TOKEN=dev-local-token ACTUATION_TARGET=sim \\
        .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 &
    OPERATOR_TOKEN=dev-local-token python -m api.e2e_smoke

Assumes the server is already running (this script never starts or stops
it) with Postgres reachable per `store/db.py` and `ACTUATION_TARGET=sim` so
the schedule runner actually drives the sim actuator, mirroring
`store/smoke_test.py`'s "exit 0 on real success" contract: prints PASS/FAIL
per step and exits non-zero on the first hard failure.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("FARMOPS_API_URL", "http://127.0.0.1:8000")
OPERATOR_TOKEN = os.environ.get("OPERATOR_TOKEN", "dev-local-token")
POLL_INTERVAL_S = 3.0
POLL_TIMEOUT_S = 180.0


class SmokeFailure(RuntimeError):
    pass


def _request(method: str, path: str, body: dict | None = None, *, auth: bool = False) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["X-Operator-Token"] = OPERATOR_TOKEN
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SmokeFailure(f"{method} {path} -> HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise SmokeFailure(f"{method} {path} -> connection failed: {error.reason}") from error


def _poll_plan(revision_id: str, terminal_statuses: set[str]) -> dict:
    deadline = time.monotonic() + POLL_TIMEOUT_S
    last: dict = {}
    while time.monotonic() < deadline:
        last = _request("GET", f"/farm/plan/{revision_id}")
        if last.get("status") in terminal_statuses:
            return last
        time.sleep(POLL_INTERVAL_S)
    raise SmokeFailure(
        f"plan {revision_id} did not reach {terminal_statuses} within "
        f"{POLL_TIMEOUT_S:.0f}s (last status={last.get('status')!r})"
    )


def _step(label: str, fn) -> object:
    try:
        result = fn()
    except SmokeFailure as error:
        print(f"FAIL — {label}: {error}", file=sys.stderr)
        raise
    print(f"PASS — {label}")
    return result


def run() -> int:
    try:
        _step(
            "health reports a real batch period (data plane is live)",
            lambda: _assert_health(),
        )

        request_result = _step(
            "POST /farm/request creates a real plan revision",
            lambda: _request(
                "POST",
                "/farm/request",
                {"intent": "irrigate", "scope": "irrigation_plan", "text": "e2e smoke: irrigate"},
                auth=True,
            ),
        )
        trace_id = request_result["traceId"]
        plan_revision_id = f"{request_result['planLineageId']}-V1"

        plan = _step(
            f"GET /farm/plan/{plan_revision_id} returns PROPOSED with actions",
            lambda: _assert_plan_proposed(plan_revision_id),
        )

        _step(
            f"POST /approvals/{plan_revision_id}/approve executes the plan",
            lambda: _request(
                "POST",
                f"/approvals/{plan_revision_id}/approve",
                {"revisionHash": plan["revisionHash"]},
                auth=True,
            ),
        )

        settled = _step(
            "schedule runner drives the plan to a terminal status with real verifications",
            lambda: _poll_plan(plan_revision_id, {"DONE", "NEEDS_REPLAN"}),
        )
        _assert_has_verifications(settled)

        _step(
            f"GET /timeline/{trace_id} shows the full PROPOSED->APPROVED->EXECUTING sequence",
            lambda: _assert_timeline(trace_id),
        )

        decision_id = plan.get("decisionId")
        if decision_id:
            _step(
                f"GET /explain/{decision_id} returns real evidence nodes",
                lambda: _assert_explain(decision_id),
            )

        _step("GET /tasks returns the inspection task list", lambda: _request("GET", "/tasks"))

        print(f"\ne2e_smoke: OK — plan {plan_revision_id} reached {settled['status']}")
        return 0
    except SmokeFailure as error:
        print(f"\ne2e_smoke: FAIL — {error}", file=sys.stderr)
        return 1


def _assert_health() -> dict:
    health = _request("GET", "/health")
    if health.get("batchPeriodSeconds") is None:
        raise SmokeFailure(f"/health has no real batchPeriodSeconds: {health}")
    return health


def _assert_plan_proposed(plan_revision_id: str) -> dict:
    plan = _request("GET", f"/farm/plan/{plan_revision_id}")
    if plan.get("status") != "PROPOSED":
        raise SmokeFailure(f"expected PROPOSED, got {plan.get('status')}: {plan}")
    if not plan.get("actions"):
        raise SmokeFailure(f"plan has no actions: {plan}")
    if not plan.get("revisionHash"):
        raise SmokeFailure(f"plan has no revisionHash: {plan}")
    return plan


def _assert_has_verifications(plan: dict) -> None:
    verifications = plan.get("verifications") or []
    if not verifications:
        raise SmokeFailure(f"plan {plan.get('planRevisionId')} has no verifications: {plan}")
    layers = {v.get("layer") for v in verifications}
    if "ACTION" not in layers:
        raise SmokeFailure(f"no ACTION-layer verification recorded: {verifications}")


def _assert_timeline(trace_id: str) -> list[dict]:
    timeline = _request("GET", f"/timeline/{trace_id}")
    types = [event.get("type") for event in timeline]
    required = ["FARM_REQUESTED", "PLAN_PROPOSED"]
    missing = [t for t in required if t not in types]
    if missing:
        raise SmokeFailure(f"timeline missing {missing}; got {types}")
    return timeline


def _assert_explain(decision_id: str) -> dict:
    explanation = _request("GET", f"/explain/{decision_id}")
    nodes = explanation.get("nodes") or []
    if not nodes:
        raise SmokeFailure(f"explanation for {decision_id} has no evidence nodes: {explanation}")
    return explanation


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
