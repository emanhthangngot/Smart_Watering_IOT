"""Bounded live MQTT → normalize → PostgreSQL runtime worker."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from config import Config
from ingest.cadence import CadenceTracker
from ingest.clock import ClockTracker
from ingest.mqtt_client import MqttClient
from ingest.normalize import NormalizeCounters
from ingest.presence import PresenceTracker
from store.ingest import ingest_raw_batch
from store.migrations import apply_live_ingestion_migration
from store.outbox_drain import drain_forever, outbox_depth

logger = logging.getLogger(__name__)


class LiveIngestionWorker:
    """Runs MQTT and DB writes without allowing unbounded memory growth."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=config.mqtt_queue_max)
        self._clock = ClockTracker()
        self._cadence = CadenceTracker()
        self._presence = PresenceTracker()
        self._counters = NormalizeCounters()
        self._lock = threading.RLock()
        self._mqtt_state = "STARTING"
        self._received = 0
        self._persisted = 0
        self._outboxed = 0
        self._dropped_overload = 0
        self._last_message_at: str | None = None
        self._last_persisted_at: str | None = None

    async def run_forever(self) -> None:
        """Run until cancelled; RuntimeCoordinator restarts on hard failure."""
        await apply_live_ingestion_migration()
        loop = asyncio.get_running_loop()

        def on_batch(batch: dict) -> None:
            loop.call_soon_threadsafe(self._offer, batch)

        def on_status(status: str) -> None:
            loop.call_soon_threadsafe(self._set_mqtt_state, status)

        client = MqttClient(self.config, on_batch=on_batch, on_status=on_status)
        try:
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(self._consume(), name="farmops-mqtt-consumer")
                tasks.create_task(
                    asyncio.to_thread(client.run_forever), name="farmops-mqtt-transport"
                )
                tasks.create_task(drain_forever(), name="farmops-outbox-drain")
        finally:
            self._set_mqtt_state("STOPPED")
            client.stop()

    def _offer(self, batch: dict[str, Any]) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                pass
            with self._lock:
                self._dropped_overload += 1
        self._queue.put_nowait(batch)
        with self._lock:
            self._received += 1
            self._last_message_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    async def _consume(self) -> None:
        while True:
            batch = await self._queue.get()
            try:
                result, self._counters, written = await ingest_raw_batch(
                    batch,
                    self.config,
                    self._clock,
                    self._cadence,
                    self._presence,
                    self._counters,
                )
                if result.dropped or result.filtered or not result.readings:
                    continue
                with self._lock:
                    if written:
                        self._persisted += 1
                        self._last_persisted_at = (
                            datetime.now(UTC).isoformat().replace("+00:00", "Z")
                        )
                    else:
                        self._outboxed += 1
            except Exception:
                # Keep consuming newer snapshots. The write path already
                # outboxes database-class failures; this protects against an
                # unexpected malformed message escaping validation.
                logger.exception("live ingestion: unexpected batch failure")
            finally:
                self._queue.task_done()

    def _set_mqtt_state(self, state: str) -> None:
        with self._lock:
            self._mqtt_state = state

    def status(self) -> dict[str, Any]:
        with self._lock:
            counters = {
                "batchesSeen": self._counters.batches_seen,
                "droppedBatches": self._counters.dropped_batches,
                "filteredBatches": self._counters.filtered_batches,
                "unknownMetrics": self._counters.unknown_metric,
                "nonFiniteValues": self._counters.non_finite,
            }
            return {
                "enabled": True,
                "mqttState": self._mqtt_state,
                "queueDepth": self._queue.qsize(),
                "queueCapacity": self._queue.maxsize,
                "receivedBatches": self._received,
                "persistedBatches": self._persisted,
                "outboxedBatches": self._outboxed,
                "droppedOverload": self._dropped_overload,
                "outboxDepth": outbox_depth(),
                "lastMessageAt": self._last_message_at,
                "lastPersistedAt": self._last_persisted_at,
                "normalize": counters,
            }
