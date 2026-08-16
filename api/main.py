"""FastAPI app entrypoint. Owner: dev (this file), routers: M4 feat/tools-runner-api.

Design reference: plans/reports/plan.md §11.3.

Auto-discovers every module under api/routers/*.py that exposes an
`APIRouter` named `router`, and includes it. This exists so adding an
endpoint never requires editing a shared registration list — see
plans/260816-0957-farmops-delivery/phase-01-skeleton-and-config.md
("api/routers/ auto-discovery").
"""

from __future__ import annotations

import importlib
import pkgutil

from fastapi import FastAPI

import api.routers as routers_pkg

app = FastAPI(title="FarmOps AI")

for _, module_name, _ in pkgutil.iter_modules(routers_pkg.__path__):
    module = importlib.import_module(f"api.routers.{module_name}")
    router = getattr(module, "router", None)
    if router is not None:
        app.include_router(router)


@app.get("/health")
def health() -> dict:
    """§11.3 — batch period, late_ratio, skew, uptime, outbox depth. Stub."""
    return {"status": "stub"}
