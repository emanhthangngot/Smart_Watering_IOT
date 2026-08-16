"""Application lifecycle orchestration for recovery and deterministic jobs."""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from api.service import service

Job = Callable[[], Any | Awaitable[Any]]


class ForeverRunner(Protocol):
    async def run_forever(self) -> None: ...


class RuntimeCoordinator:
    def __init__(
        self,
        *,
        startup_recovery: Job | None = None,
        schedule_runner: ForeverRunner | None = None,
        data_plane_runner: ForeverRunner | None = None,
        retention_job: Job | None = None,
        expiry_job: Job | None = None,
        retention_interval_seconds: float = 3600,
        expiry_interval_seconds: float = 5,
    ) -> None:
        if retention_interval_seconds <= 0 or expiry_interval_seconds <= 0:
            raise ValueError("runtime intervals must be positive")
        self.startup_recovery = startup_recovery
        self.schedule_runner = schedule_runner
        self.data_plane_runner = data_plane_runner
        self.retention_job = retention_job
        self.expiry_job = expiry_job
        self.retention_interval_seconds = retention_interval_seconds
        self.expiry_interval_seconds = expiry_interval_seconds
        self._lock = threading.RLock()
        self._tasks: list[asyncio.Task[None]] = []
        self._started = False
        self._errors: list[str] = []

    def configure(
        self,
        *,
        startup_recovery: Job,
        schedule_runner: ForeverRunner,
        retention_job: Job,
    ) -> None:
        """Wire M1-backed components before application startup."""

        with self._lock:
            if self._started:
                raise RuntimeError("runtime cannot be reconfigured while running")
            self.startup_recovery = startup_recovery
            self.schedule_runner = schedule_runner
            self.retention_job = retention_job

    def configure_data_plane(self, runner: ForeverRunner | None) -> None:
        """Install or disable the live MQTT worker while the app is stopped."""
        with self._lock:
            if self._started:
                raise RuntimeError("runtime cannot be reconfigured while running")
            self.data_plane_runner = runner

    def configure_schedule_runner(self, runner: ForeverRunner | None) -> None:
        """Install or disable the schedule runner while the app is stopped.

        Separate from `configure()` (which still requires startup_recovery
        and retention_job together) because those two have no durable
        adapter yet — see api/bootstrap.py for why. The schedule runner can
        be wired on its own.
        """
        with self._lock:
            if self._started:
                raise RuntimeError("runtime cannot be reconfigured while running")
            self.schedule_runner = runner

    async def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        try:
            if self.startup_recovery is not None:
                await _invoke(self.startup_recovery)
            if self.expiry_job is not None:
                await _invoke(self.expiry_job)
        except Exception:
            with self._lock:
                self._started = False
            raise

        if self.schedule_runner is not None:
            self._tasks.append(
                asyncio.create_task(
                    self._guarded_forever("scheduleRunner", self.schedule_runner.run_forever),
                    name="farmops-schedule-runner",
                )
            )
        if self.data_plane_runner is not None:
            self._tasks.append(
                asyncio.create_task(
                    self._guarded_forever("dataPlane", self.data_plane_runner.run_forever),
                    name="farmops-live-data-plane",
                )
            )
        if self.retention_job is not None:
            self._tasks.append(
                asyncio.create_task(
                    self._periodic(
                        "retention",
                        self.retention_job,
                        self.retention_interval_seconds,
                    ),
                    name="farmops-retention",
                )
            )
        if self.expiry_job is not None:
            self._tasks.append(
                asyncio.create_task(
                    self._periodic("expiry", self.expiry_job, self.expiry_interval_seconds),
                    name="farmops-expiry",
                )
            )

    async def stop(self) -> None:
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        with self._lock:
            self._started = False

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "started": self._started,
                "recovery": "READY" if self.startup_recovery is not None else "BLOCKED_M1",
                "scheduleRunner": (
                    "RUNNING"
                    if self._started and self.schedule_runner is not None
                    else "BLOCKED_M1"
                    if self.schedule_runner is None
                    else "STOPPED"
                ),
                "dataPlane": (
                    "RUNNING"
                    if self._started and self.data_plane_runner is not None
                    else "DISABLED"
                    if self.data_plane_runner is None
                    else "STOPPED"
                ),
                "retention": "READY" if self.retention_job is not None else "BLOCKED_M1",
                "expiry": "RUNNING" if self._started and self.expiry_job is not None else "STOPPED",
                "errors": list(self._errors[-10:]),
            }

    async def _periodic(self, name: str, job: Job, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await _invoke(job)
            except Exception as error:
                self._record_error(name, error)

    async def _guarded_forever(self, name: str, job: Callable[[], Awaitable[None]]) -> None:
        while True:
            try:
                await job()
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._record_error(name, error)
                await asyncio.sleep(1)

    def _record_error(self, name: str, error: Exception) -> None:
        with self._lock:
            self._errors.append(f"{name}:{type(error).__name__}")


async def _invoke(job: Job) -> Any:
    if inspect.iscoroutinefunction(job):
        return await job()
    result = await asyncio.to_thread(job)
    return await result if inspect.isawaitable(result) else result


runtime = RuntimeCoordinator(expiry_job=service.expire_stale_plans)
