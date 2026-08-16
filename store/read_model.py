"""PostgreSQL read model for realtime and last-known farm telemetry."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from statistics import median
from typing import Any

from ingest.cadence import BOOTSTRAP_PERIOD_S, freshness, ttl_seconds
from registry.specs import DEVICES, SPECS, metrics_for_device
from store.db import get_pool

OFFLINE_BATCHES = 3


def _as_iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def _device_codes(value: Any) -> set[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return set()
    return {str(item) for item in value} if isinstance(value, list) else set()


def _observed_period(batches: list[dict[str, Any]]) -> float:
    event_times = sorted(
        row["event_time"].timestamp()
        for row in batches
        if isinstance(row.get("event_time"), datetime)
    )
    deltas = [
        right - left
        for left, right in zip(event_times, event_times[1:], strict=False)
        if right > left
    ]
    return float(median(deltas)) if deltas else BOOTSTRAP_PERIOD_S


class PostgresFarmStateRepository:
    """Builds one UI-ready projection without inventing missing readings."""

    def __init__(self, team_code: str) -> None:
        self.team_code = team_code

    async def snapshot(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        pool = await get_pool()
        async with pool.acquire() as connection:
            reading_rows = await connection.fetch(
                """
                select distinct on (device, metric)
                  id, device, metric, value, epoch, event_time, received_at,
                  source_status, late, scenario
                from readings_all
                where team_code = $1
                order by device, metric, event_time desc, received_at desc
                """,
                self.team_code,
            )
            batch_rows = await connection.fetch(
                """
                select batch_id, epoch, event_time, source_received_at, stored_at,
                       scenario, device_codes, reading_count
                from ingest_batches
                where team_code = $1
                order by source_received_at desc
                limit 20
                """,
                self.team_code,
            )
            plans = await connection.fetch(
                """
                select plan_revision_id, plan_lineage_id, version, status,
                       created_from_state_version, created_at
                from plan_revisions
                order by created_at desc
                limit 20
                """
            )
            tasks = await connection.fetch(
                """
                select task_id, reason, evidence_refs, status, assigned_to,
                       created_at, resolved_at
                from inspection_tasks
                order by created_at desc
                limit 50
                """
            )

        readings = {(row["device"], row["metric"]): dict(row) for row in reading_rows}
        batches = [dict(row) for row in batch_rows]
        period = _observed_period(batches)
        latest_batch = batches[0] if batches else None
        batch_age = (
            max(0.0, (now - latest_batch["source_received_at"]).total_seconds())
            if latest_batch
            else None
        )
        feed_stale_after = max(15.0, period * 3)
        feed_state = (
            "NO_DATA"
            if latest_batch is None
            else "LIVE"
            if batch_age is not None and batch_age <= feed_stale_after
            else "STALE"
        )

        recent_presence = [_device_codes(row.get("device_codes")) for row in batches]
        devices: list[dict[str, Any]] = []
        state_rank = {"FRESH": 0, "STALE": 1, "OFFLINE": 2, "MISSING": 3}
        for device_code in DEVICES:
            offline = len(recent_presence) >= OFFLINE_BATCHES and all(
                device_code not in codes for codes in recent_presence[:OFFLINE_BATCHES]
            )
            metrics: dict[str, dict[str, Any]] = {}
            for spec in metrics_for_device(device_code):
                row = readings.get((device_code, spec.metric))
                if row is None:
                    metrics[spec.metric] = {
                        "value": None,
                        "unit": spec.unit,
                        "eventTime": None,
                        "receivedAt": None,
                        "ageSeconds": None,
                        "ttlSeconds": round(ttl_seconds(spec.ttl_batches, period), 3),
                        "freshness": 0.0,
                        "state": "MISSING",
                        "sourceStatus": None,
                        "readingId": None,
                    }
                    continue
                age = max(0.0, (now - row["event_time"]).total_seconds())
                ttl = ttl_seconds(spec.ttl_batches, period)
                metric_state = "OFFLINE" if offline else "FRESH" if age <= ttl else "STALE"
                metrics[spec.metric] = {
                    "value": float(row["value"]),
                    "unit": spec.unit,
                    "eventTime": _as_iso(row["event_time"]),
                    "receivedAt": _as_iso(row["received_at"]),
                    "ageSeconds": round(age, 3),
                    "ttlSeconds": round(ttl, 3),
                    "freshness": round(freshness(age, ttl), 4),
                    "state": metric_state,
                    "sourceStatus": row["source_status"],
                    "readingId": row["id"],
                    "late": bool(row["late"]),
                }
            device_state = max(
                (metric["state"] for metric in metrics.values()),
                key=state_rank.__getitem__,
                default="MISSING",
            )
            devices.append({"deviceCode": device_code, "status": device_state, "metrics": metrics})

        return {
            "status": feed_state,
            "farmStateVersion": int(latest_batch["epoch"]) if latest_batch else 0,
            "dataSource": "postgresql",
            "integration": {
                "dataPlane": "AVAILABLE" if latest_batch else "NO_DATA",
            },
            "ingestion": {
                "state": feed_state,
                "lastBatchId": latest_batch["batch_id"] if latest_batch else None,
                "lastBatchAt": _as_iso(latest_batch["source_received_at"])
                if latest_batch
                else None,
                "lastEventTime": _as_iso(latest_batch["event_time"]) if latest_batch else None,
                "lastScenario": latest_batch["scenario"] if latest_batch else None,
                "batchAgeSeconds": round(batch_age, 3) if batch_age is not None else None,
                "observedPeriodSeconds": round(period, 3),
                "staleAfterSeconds": round(feed_stale_after, 3),
            },
            "devices": devices,
            "plans": [
                {
                    "planRevisionId": row["plan_revision_id"],
                    "planLineageId": row["plan_lineage_id"],
                    "version": row["version"],
                    "status": row["status"],
                    "createdFromStateVersion": row["created_from_state_version"],
                    "createdAt": _as_iso(row["created_at"]),
                }
                for row in plans
            ],
            "inspectionTasks": [
                {
                    "taskId": row["task_id"],
                    "reason": row["reason"],
                    "evidenceRefs": row["evidence_refs"],
                    "status": row["status"],
                    "assignedTo": row["assigned_to"],
                    "createdAt": _as_iso(row["created_at"]),
                    "resolvedAt": _as_iso(row["resolved_at"]),
                }
                for row in tasks
            ],
        }

    async def health(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        pool = await get_pool()
        rows = await pool.fetch(
            """
            select batch_id, epoch, event_time, source_received_at, scenario
            from ingest_batches
            where team_code = $1
            order by source_received_at desc
            limit 20
            """,
            self.team_code,
        )
        batches = [dict(row) for row in rows]
        period = _observed_period(batches)
        latest = batches[0] if batches else None
        batch_age = (
            max(0.0, (now - latest["source_received_at"]).total_seconds()) if latest else None
        )
        stale_after = max(15.0, period * 3)
        state = (
            "NO_DATA"
            if latest is None
            else "LIVE"
            if batch_age is not None and batch_age <= stale_after
            else "STALE"
        )
        return {
            "database": "AVAILABLE",
            "state": state,
            "lastBatchId": latest["batch_id"] if latest else None,
            "lastBatchAt": _as_iso(latest["source_received_at"]) if latest else None,
            "batchAgeSeconds": round(batch_age, 3) if batch_age is not None else None,
            "observedPeriodSeconds": round(period, 3),
            "staleAfterSeconds": round(stale_after, 3),
        }


def registry_metric_count() -> int:
    """Test/documentation helper: expected metric slots in every snapshot."""
    return len(SPECS)
