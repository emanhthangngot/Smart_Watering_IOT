import { describe, expect, it } from "vitest";
import { normalizeFarmState, normalizePlan, normalizeTasks } from "./normalize";

describe("API normalization", () => {
  it("accepts snake_case World State without losing freshness reasons", () => {
    const state = normalizeFarmState({
      farm_state_version: 42,
      updated_at: "2026-08-16T10:05:04Z",
      telemetry: {
        latest: [
          {
            reading_id: "r-soil-1",
            device_code: "SOIL_01",
            metric: "moisture",
            value: 31.8,
            unit: "%",
            event_time: "2026-08-16T10:05:00Z",
            source_status: "ok",
            freshness: "STALE",
            reasons: ["Reading vượt TTL 15 giây"],
          },
        ],
      },
      active_plan: { plan_lineage_id: "PLAN-001", plan_revision_id: "PLAN-001-V2" },
    });

    expect(state.farmStateVersion).toBe(42);
    expect(state.activePlan?.planRevisionId).toBe("PLAN-001-V2");
    expect(state.devices[0]).toMatchObject({
      deviceCode: "SOIL_01",
      freshness: "STALE",
      metrics: [{ name: "moisture", value: 31.8, unit: "%" }],
    });
    expect(state.devices[0]?.reasons).toContain("Reading vượt TTL 15 giây");
    expect(state.evidenceHealth.state).toBe("UNKNOWN");
  });

  it("aggregates fallback telemetry deterministically and only marks required evidence partial", () => {
    const state = normalizeFarmState({
      requiredDeviceCodes: ["SOIL_01"],
      telemetry: { latest: [
        { device_code: "SOIL_01", metric: "moisture", value: 32, unit: "%", freshness: "FRESH", event_time: "2026-08-16T10:05:00Z", age_s: 2 },
        { device_code: "SOIL_01", metric: "temperature", value: 29, unit: "C", freshness: "STALE", event_time: "2026-08-16T10:04:00Z", age_s: 62 },
      ] },
    });
    expect(state.devices[0]).toMatchObject({ freshness: "STALE", ageSeconds: 62, eventTime: "2026-08-16T10:04:00Z", aggregation: "FRONTEND_CONSERVATIVE_FALLBACK" });
    expect(state.evidenceHealth.state).toBe("PARTIAL");
  });

  it("keeps immutable plan identity, exact hash, and separate verification layers", () => {
    const plan = normalizePlan({
      plan: {
        plan_lineage_id: "PLAN-001",
        plan_revision_id: "PLAN-001-V2",
        revision_hash: "sha256:exact-revision-hash",
        version: 2,
        status: "PROPOSED",
        requires_approval: true,
      },
      verifications: [
        { id: "AV-1", layer: "ACTION", result: "PASS", expected: "IRR-104", observed: "IRR-104" },
        { id: "OV-1", layer: "OUTCOME", result: "INCONCLUSIVE", expected: "flow >= 8", observed: null },
      ],
    });

    expect(plan.planRevisionId).toBe("PLAN-001-V2");
    expect(plan.revisionHash).toBe("sha256:exact-revision-hash");
    expect(plan.verifications.map((item) => item.layer)).toEqual(["ACTION", "OUTCOME"]);
    expect(plan.verifications[1]?.result).toBe("INCONCLUSIVE");
  });

  it("normalizes notification lifecycle aliases", () => {
    const tasks = normalizeTasks({ tasks: [
      { task_id: "TASK-1", status: "open", priority: "CRITICAL" },
      { task_id: "TASK-2", status: "ack", priority: "HIGH" },
      { task_id: "TASK-3", status: "done", priority: "LOW" },
    ] });
    expect(tasks.map((task) => task.status)).toEqual(["unread", "acknowledged", "resolved"]);
  });
});
