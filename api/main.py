"""FastAPI app entrypoint. Owner: dev (this file), routers: M4 feat/tools-runner-api.

Design reference: plans/reports/plan.md §11.3.

Auto-discovers every module under api/routers/*.py that exposes an
`APIRouter` named `router`, and includes it. This exists so adding an
endpoint never requires editing a shared registration list — see
plans/260816-0957-farmops-delivery/phase-01-skeleton-and-config.md
("api/routers/ auto-discovery").
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import pkgutil
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import api.routers as routers_pkg
from api.bootstrap import build_schedule_runner
from api.runtime import runtime
from api.service import service
from api.workflow import build_workflow
from config import Config
from ingest.worker import LiveIngestionWorker
from store.db import close_pool, get_pool
from store.migrations import apply_live_ingestion_migration
from store.read_model import PostgresFarmStateRepository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    del app_instance
    config = Config.from_env()
    read_model = PostgresFarmStateRepository(config.team_code)
    worker = LiveIngestionWorker(config) if config.mqtt_enabled else None
    service.configure_data_plane(
        read_model,
        mqtt_enabled=config.mqtt_enabled,
        ingestion_status=worker.status if worker is not None else None,
    )
    runtime.configure_data_plane(worker)
    runtime.configure_schedule_runner(build_schedule_runner(config, service))
    service.configure_workflow(build_workflow(service, read_model, asyncio.get_running_loop()))
    try:
        pool = await get_pool()
        await apply_live_ingestion_migration(pool)
    except Exception as error:
        # DB/MQTT availability must not prevent the read API from starting.
        # The worker retries its whole lifecycle and applies the migration
        # before consuming once PostgreSQL becomes reachable.
        logger.warning("live data plane starts degraded: %s", type(error).__name__)
    await runtime.start()
    try:
        yield
    finally:
        await runtime.stop()
        runtime.configure_data_plane(None)
        runtime.configure_schedule_runner(None)
        service.workflow = None
        service.configure_data_plane(None, mqtt_enabled=False)
        await close_pool()


app = FastAPI(title="FarmOps AI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(Config.from_env().cors_origins),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Operator-Token"],
)

for finder, module_name, is_package in pkgutil.iter_modules(routers_pkg.__path__):
    del finder, is_package
    module = importlib.import_module(f"api.routers.{module_name}")
    router = getattr(module, "router", None)
    if router is not None:
        app.include_router(router)
