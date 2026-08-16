"""Real sim ingest -> normalize -> Postgres -> trust pipeline.

Ticks a `sim.world.WorldState` every ``cadence_s`` seconds, publishes a batch
in the exact shape ``sim.publisher.build_batch`` produces, writes it through
``store.ingest.ingest_raw_batch`` (same call as ``store/smoke_test.py`` and
the real MQTT client), and computes real DCS/tier trust verdicts over the
readings that were actually ingested. This is the ``ACTUATION_TARGET=sim``
closed loop described in ``sim/publisher.py``'s module docstring: the pump
command this process sets is fed back into the next published batch.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from config import Config
from graph.edges import EdgeRelation, EvidenceEdge, EvidenceGraph
from ingest.cadence import CadenceTracker, ttl_seconds
from ingest.clock import ClockTracker
from ingest.normalize import NormalizeCounters, NormalizeResult
from ingest.presence import PresenceTracker
from registry.specs import DEVICES, SCOPES, metrics_for_device, required_specs
from sim.faults import FaultFlags
from sim.publisher import build_batch
from sim.world import WorldState as SimWorldState
from store.ingest import ingest_raw_batch
from store.outbox_drain import outbox_depth
from trust.reasons import explain as trust_explain
from trust.score import DCS_POLICY_VERSION, ScoreSnapshot, score_scope
from trust.states import assign_state
from trust.tier import Tier, TierState, evaluate_tier

logger = logging.getLogger(__name__)

WINDOW_LEN = 20

_FRESHNESS_RANK = {
    "FRESH": 0,
    "STALE": 1,
    "SUSPECT": 2,
    "OFFLINE": 3,
    "MISSING": 4,
}


@dataclass
class _MetricState:
    value: float
    event_time: str
    received_at: float
    source_status: str
    reading_id: str


class FarmPipeline:
    """Owns the sim world, the ingest counters, and the derived trust state.

    Thread-safe: `tick()` runs on the asyncio loop, readers (FastAPI request
    handlers, which FastAPI dispatches to a worker thread for sync routes)
    call the snapshot methods below from any thread.
    """

    def __init__(self, config: Config, *, cadence_s: float = 5.0) -> None:
        self.config = config
        self.cadence_s = cadence_s
        self.world = SimWorldState()
        self.faults = FaultFlags()
        self.clock = ClockTracker()
        self.cadence = CadenceTracker()
        self.presence = PresenceTracker()
        self.counters = NormalizeCounters()
        self.graph = EvidenceGraph()

        self._lock = threading.RLock()
        self._latest: dict[tuple[str, str], _MetricState] = {}
        self._windows: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=WINDOW_LEN))
        self._reading_rows: dict[str, dict[str, Any]] = {}
        self._state_version = 0
        self._updated_at: datetime | None = None
        self._pump_on = False
        self._pump_active_since: float | None = None
        self._pump_last_active_at: float | None = None
        self._device_scores: dict[str, tuple[ScoreSnapshot, TierState]] = {}
        self._scope_scores: dict[str, tuple[ScoreSnapshot, TierState]] = {}
        self._device_last_rules: dict[str, tuple[str, ...]] = {}
        # set by wiring: Callable[[str, ScoreSnapshot, Tier, tuple[str, ...]], None]
        self.on_trust_finding: Any = None

    # -- actuation --------------------------------------------------------

    def set_pump(self, on: bool) -> None:
        with self._lock:
            self._pump_on = on
            now = time.time()
            if on:
                self._pump_active_since = now
            else:
                self._pump_last_active_at = now

    def pump_is_on(self) -> bool:
        with self._lock:
            return self._pump_on

    def pump_was_activated(self) -> bool:
        """True once ``set_pump(True)`` has been called at least once."""
        with self._lock:
            return self._pump_active_since is not None

    # -- ingest loop --------------------------------------------------------

    async def tick(self) -> NormalizeResult:
        with self._lock:
            self.world.tick(
                self.cadence_s,
                self._pump_on,
                pump_no_effect=self.faults.pump_no_effect,
                tank_leak=self.faults.tank_leak,
            )
            epoch = int(time.time())
            batch = build_batch(self.world, self.faults, self.config, epoch)

        result, self.counters, written = await ingest_raw_batch(
            batch, self.config, self.clock, self.cadence, self.presence, self.counters
        )
        if not written:
            logger.warning("pipeline tick: batch diverted to local outbox (network failure)")
        self._apply_readings(result)
        self._recompute_trust()
        self._raise_findings()
        return result

    def _apply_readings(self, result: NormalizeResult) -> None:
        if result.dropped or result.filtered or not result.readings:
            return
        with self._lock:
            now = time.time()
            for reading in result.readings:
                key = (reading.device_code, reading.metric)
                self._latest[key] = _MetricState(
                    value=reading.value,
                    event_time=reading.event_time,
                    received_at=now,
                    source_status=reading.source_status,
                    reading_id=reading.reading_id,
                )
                self._windows[f"{reading.device_code}.{reading.metric}"].append(reading.value)
                row = self._reading_rows.setdefault(
                    reading.reading_id, {"device": reading.device_code, "metrics": {}}
                )
                row["metrics"][reading.metric] = {
                    "value": reading.value,
                    "unit": reading.unit,
                    "eventTime": reading.event_time,
                    "sourceStatus": reading.source_status,
                }
            self._state_version += 1
            self._updated_at = datetime.now(UTC)

    def _recompute_trust(self) -> None:
        with self._lock:
            bundle: dict[str, dict[str, Any]] = {}
            ages: dict[str, float] = {}
            ttls: dict[str, float] = {}
            now = time.time()
            for (device, metric), state in self._latest.items():
                key = f"{device}.{metric}"
                bundle[key] = {"value": state.value, "source_status": state.source_status}
                spec = next(
                    (s for s in metrics_for_device(device) if s.metric == metric), None
                )
                ttl_batches = spec.ttl_batches if spec is not None else 3
                ages[key] = max(0.0, now - state.received_at)
                ttls[key] = ttl_seconds(ttl_batches, self.cadence.observed_period_s)
            windows = {key: list(values) for key, values in self._windows.items()}

            for scope in SCOPES:
                previous_tier = self._scope_scores.get(scope, (None, None))[1]
                snapshot = score_scope(
                    bundle,
                    windows,
                    scope,
                    ages=ages,
                    ttls=ttls,
                    source_state_version=self._state_version,
                )
                tier_state = evaluate_tier(snapshot.dcs, previous_tier)
                self._scope_scores[scope] = (snapshot, tier_state)

            for device in DEVICES:
                keys = [
                    (device, spec.metric)
                    for spec in metrics_for_device(device)
                    if (device, spec.metric) in self._latest
                ]
                if not keys:
                    continue
                specs = {(d, m): {"weight": 1, "required": True} for d, m in keys}
                previous_tier = self._device_scores.get(device, (None, None))[1]
                snapshot = score_scope(
                    bundle,
                    windows,
                    device,
                    specs=specs,
                    ages=ages,
                    ttls=ttls,
                    source_state_version=self._state_version,
                )
                tier_state = evaluate_tier(snapshot.dcs, previous_tier)
                self._device_scores[device] = (snapshot, tier_state)

    def _raise_findings(self) -> None:
        callback = self.on_trust_finding
        if callback is None:
            return
        with self._lock:
            items = list(self._device_scores.items())
        for device, (snapshot, tier_state) in items:
            rules = snapshot.rules_fired
            if not rules or rules == self._device_last_rules.get(device):
                self._device_last_rules[device] = rules
                continue
            self._device_last_rules[device] = rules
            if rules:
                try:
                    callback(device, snapshot, tier_state.tier, rules)
                except Exception:  # a finding callback must never break ingest
                    logger.exception("pipeline: trust finding callback failed for %s", device)

    # -- read-side snapshots --------------------------------------------------------

    def state_version(self) -> int:
        with self._lock:
            return self._state_version

    def latest_value(self, device: str, metric: str) -> float | None:
        with self._lock:
            state = self._latest.get((device, metric))
            return state.value if state is not None else None

    def latest_evidence_ref(self, device: str, metric: str) -> str | None:
        with self._lock:
            state = self._latest.get((device, metric))
            return f"{state.reading_id}#{metric}" if state is not None else None

    def metric_window(self, device: str, metric: str) -> list[float]:
        with self._lock:
            return list(self._windows.get(f"{device}.{metric}", ()))

    def reading_row(self, reading_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._reading_rows.get(reading_id)
            return {"device": row["device"], "metrics": dict(row["metrics"])} if row else None

    def scope_snapshot(self, scope: str) -> tuple[ScoreSnapshot, TierState] | None:
        with self._lock:
            return self._scope_scores.get(scope)

    def health_snapshot(self) -> dict[str, Any]:
        with self._lock:
            batches_seen = self.counters.batches_seen
            late_ratio = (
                self.counters.late_batches / batches_seen if batches_seen else 0.0
            )
            missing = [
                device
                for device in DEVICES
                if self.presence.is_missing(device) or self.presence.is_offline(device)
            ]
            reasons: list[str] = []
            if batches_seen == 0:
                reasons.append("no batches ingested yet")
            if self.clock.skew_warning():
                reasons.append("clock skew exceeds warning threshold")
            return {
                "status": "ok" if batches_seen > 0 else "degraded",
                "batchPeriodSeconds": round(self.cadence.observed_period_s, 3),
                "lateRatio": round(late_ratio, 4),
                "clockSkewSeconds": round(self.clock.skew_correction(), 4),
                "outboxDepth": outbox_depth(),
                "missingDevices": missing,
                "reasons": reasons,
            }

    def devices_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            now = time.time()
            out: list[dict[str, Any]] = []
            for device in DEVICES:
                metrics: list[dict[str, Any]] = []
                ages: list[float] = []
                for spec in metrics_for_device(device):
                    state = self._latest.get((device, spec.metric))
                    if state is None:
                        continue
                    age = max(0.0, now - state.received_at)
                    ttl = ttl_seconds(spec.ttl_batches, self.cadence.observed_period_s)
                    reading_state = assign_state(
                        {"source_status": state.source_status},
                        present=not self.presence.is_missing(device),
                        absent_batches=self.presence.absence_streak(device),
                        offline_batches=self.presence.offline_batches,
                        age=age,
                        ttl=ttl,
                    )
                    ages.append(age)
                    metrics.append(
                        {
                            "metric": spec.metric,
                            "value": state.value,
                            "unit": spec.unit,
                            "eventTime": state.event_time,
                            "ageSeconds": round(age, 2),
                            "freshness": reading_state.value,
                        }
                    )
                snapshot, tier_state = self._device_scores.get(device, (None, None))
                if self.presence.is_missing(device):
                    freshness = "MISSING"
                elif self.presence.is_offline(device):
                    freshness = "OFFLINE"
                elif metrics:
                    freshness = max(metrics, key=lambda m: _FRESHNESS_RANK[m["freshness"]])[
                        "freshness"
                    ]
                else:
                    freshness = "MISSING"
                out.append(
                    {
                        "deviceCode": device,
                        "freshness": freshness,
                        "connectivity": "OFFLINE" if self.presence.is_offline(device) else "ONLINE",
                        "eventTime": metrics[-1]["eventTime"] if metrics else None,
                        "ageSeconds": max(ages) if ages else None,
                        "dcs": round(snapshot.dcs, 3) if snapshot is not None else None,
                        "tier": (
                            tier_state.tier.value
                            if tier_state is not None and tier_state.tier is not None
                            else "UNKNOWN"
                        ),
                        "reasons": (
                            [trust_explain(snapshot, tier_state.tier)]
                            if snapshot is not None and tier_state is not None
                            else []
                        ),
                        "metrics": metrics,
                        "aggregation": "BACKEND",
                    }
                )
            return out

    def evidence_health(self) -> dict[str, Any]:
        required = sorted({spec.device_code for spec in required_specs("irrigation_plan")})
        devices = {d["deviceCode"]: d for d in self.devices_snapshot()}
        missing = [d for d in required if devices.get(d, {}).get("freshness") != "FRESH"]
        return {
            "state": "PARTIAL" if missing else "COMPLETE",
            "source": "COORDINATOR",
            "reasons": (
                [f"required device {d} is not FRESH" for d in missing]
                if missing
                else ["all required devices are FRESH"]
            ),
            "requiredDeviceCodes": required,
        }

    def scope_verdicts(self) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._scope_scores.items())
        return [
            {
                "scope": scope,
                "dcs": round(snapshot.dcs, 3),
                "tier": tier_state.tier.value if tier_state.tier is not None else "UNKNOWN",
                "reasons": list(snapshot.rules_fired),
                "policyVersion": str(DCS_POLICY_VERSION),
            }
            for scope, (snapshot, tier_state) in items
        ]

    def farm_state_snapshot(self) -> dict[str, Any]:
        with self._lock:
            updated_at = self._updated_at
            version = self._state_version
        return {
            "farmStateVersion": version,
            "updatedAt": updated_at.isoformat() if updated_at is not None else None,
            "devices": self.devices_snapshot(),
            "evidenceHealth": self.evidence_health(),
        }


__all__ = ["EdgeRelation", "EvidenceEdge", "EvidenceGraph", "FarmPipeline", "Tier"]
