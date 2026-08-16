const now = "2026-08-16T10:05:04Z";
let taskState = [
  { id: "TASK-018", title: "Kiểm tra pump và valve", deviceCode: "PUMP_01", reason: "Flow thực tế thấp hơn assumption A1.", instructions: "Kiểm tra van, lọc và đường ống trước khi resume plan.", priority: "CRITICAL", status: "unread", evidenceRefs: ["r-pump-17"], createdAt: now },
  { id: "TASK-021", title: "Xác minh soil probe", deviceCode: "SOIL_01", reason: "Soil evidence vượt TTL của scope tưới.", instructions: "Đối chiếu cảm biến với phép đo tay tại Area A.", priority: "HIGH", status: "acknowledged", evidenceRefs: ["r-soil-44"], createdAt: now },
];

const state = {
  farmStateVersion: 42, updatedAt: now, partialMode: true,
  devices: [
    { deviceCode: "SOIL_01", freshness: "STALE", connectivity: "CONNECTED", ageSeconds: 18, eventTime: "2026-08-16T10:04:46Z", dcs: 0.38, tier: "INVESTIGATE", reasons: ["Reading vượt TTL 15 giây", "Cần xác minh soil probe"], metrics: { moisture: { value: 31.8, unit: "%" }, temperature: { value: 29.4, unit: "°C" } } },
    { deviceCode: "WEATHER_01", freshness: "FRESH", connectivity: "CONNECTED", ageSeconds: 3, eventTime: "2026-08-16T10:05:01Z", dcs: 0.94, tier: "PROPOSE", reasons: ["Telemetry ổn định"], metrics: { temperature: { value: 31.2, unit: "°C" }, humidity: { value: 64, unit: "%" } } },
    { deviceCode: "PUMP_01", freshness: "FRESH", connectivity: "CONNECTED", ageSeconds: 2, eventTime: "2026-08-16T10:05:02Z", dcs: 0.91, tier: "PROPOSE", reasons: ["Flow evidence hiện hữu"], metrics: { flow_rate: { value: 13.9, unit: "L/min" }, power: { value: 646, unit: "W" } } },
    { deviceCode: "TANK_01", freshness: "FRESH", connectivity: "CONNECTED", ageSeconds: 4, eventTime: "2026-08-16T10:05:00Z", dcs: 0.92, tier: "PROPOSE", reasons: ["Mức nước trên reserve"], metrics: { level: { value: 59.8, unit: "%" } } },
    { deviceCode: "SUN_01", freshness: "FRESH", connectivity: "CONNECTED", ageSeconds: 5, eventTime: "2026-08-16T10:04:59Z", dcs: 0.96, tier: "AUTO", reasons: ["Sensor ổn định"], metrics: { lux: { value: 52700, unit: "lx" } } },
    { deviceCode: "PH_01", freshness: "FRESH", connectivity: "CONNECTED", ageSeconds: 4, eventTime: "2026-08-16T10:05:00Z", dcs: 0.89, tier: "PROPOSE", reasons: ["pH là advisory"], metrics: { ph: { value: 6.7, unit: "pH" } } },
  ],
  activePlan: { planLineageId: "PLAN-001", planRevisionId: "PLAN-001-V2" }, traceId: "TRACE-001",
  crossSensor: { anomalies: ["SOIL_01 stale: định lượng tưới đang bị giới hạn."] },
};

const plan = {
  plan: { planLineageId: "PLAN-001", planRevisionId: "PLAN-001-V2", revisionOfPlanRevisionId: "PLAN-001-V1", revisionHash: "sha256:demo-v2-hash", version: 2, status: "PROPOSED", goal: { type: "IRRIGATION", area: "A" }, createdFromStateVersion: 42, evidenceRefs: ["r-soil-44", "r-pump-17", "r-tank-09"], constraints: ["tankReserve >= 20%", "no pump overlap"], waterBudget: { plannedDrawdownPct: 6.5, plannedPumpMinutes: 18 }, confidence: { dcs: 0.8, tier: "PROPOSE", dcsPolicyVersion: 3 }, requiresApproval: true, decisionId: "DECISION-PLAN-V2", approvalExpiresAt: "2026-08-16T10:30:00Z" },
  assumptions: [{ assumptionId: "A1", predicate: "PUMP_01.flow_rate >= 8 L/min", status: "VALID", evidenceRefs: ["r-pump-17"], observationWindow: "2 sliding windows", affectedActionIds: ["IRR-104"] }, { assumptionId: "A3", predicate: "SOIL_01 remains FRESH", status: "INVALIDATED", evidenceRefs: ["r-soil-44"], observationWindow: "15 seconds", affectedActionIds: ["IRR-104"], invalidatedReason: "SOIL_01 vượt TTL", invalidatedEvidence: "r-soil-44" }],
  challenges: [{ challengeId: "CH-1", targetPlanRevisionId: "PLAN-001-V2", agent: "Diagnosis", blocking: false, status: "REQUEST_MORE_EVIDENCE", reason: "Soil evidence stale; only partial irrigation proposal is allowed.", evidenceRefs: ["r-soil-44"], requestedEvidence: "Manual soil inspection" }],
  actions: [{ actionId: "IRR-104", type: "IRRIGATION_SCHEDULE", status: "PENDING", parameters: { minutes: 18, area: "A" } }],
  expectedOutcomes: [{ metric: "flow_rate", predicate: "flow_rate >= threshold", threshold: 8, tolerance: 0.5, observationWindow: "2 windows", evidenceSource: "PUMP_01.flow_rate", affectedAssumptionId: "A1" }],
  verifications: [{ id: "AV-1", layer: "ACTION", expected: "IRR-104", observed: "IRR-104", result: "PASS", window: "read-back", evidenceRefs: ["tool-1"] }, { id: "OV-1", layer: "OUTCOME", expected: "flow >= 8", observed: null, result: "INCONCLUSIVE", window: "2 windows", evidenceRefs: ["r-pump-17"] }],
};

export async function demoResponse(path: string, options: RequestInit): Promise<unknown> {
  if (path === "/farm/state") return state;
  if (path === "/health") return { status: "HEALTHY", batchPeriodSeconds: 5, lateRatio: 0.012, clockSkewSeconds: 0.8, uptimeSeconds: 7420, outboxDepth: 0, dbWriteLatencyMs: 42, missingDevices: [], reasons: ["Demo data is local only."] };
  if (path === "/trust/current") return { verdicts: state.devices.map((device) => ({ scope: device.deviceCode, dcs: device.dcs, tier: device.tier, reasons: device.reasons, policyVersion: "3" })) };
  if (path === "/tasks") return { tasks: taskState };
  if (path.startsWith("/farm/plan/")) return plan;
  if (path.startsWith("/timeline/")) return { events: [{ id: "EV-1", timestamp: now, actor: "Planner", type: "PROPOSED", title: "Planner tạo PLAN-001-V2", detail: "Dùng evidence pump, tank và soil mới nhất.", decisionId: "DECISION-PLAN-V2", evidenceRefs: ["r-pump-17", "r-tank-09"] }, { id: "EV-2", timestamp: now, actor: "Diagnosis", type: "CHALLENGED", title: "Soil evidence stale", detail: "Yêu cầu kiểm tra thực địa trước khi định lượng tưới.", evidenceRefs: ["r-soil-44"] }] };
  if (path.startsWith("/explain/")) return { nodes: [{ id: "r-pump-17", type: "READING", label: "PUMP_01 flow rate", value: 13.9, unit: "L/min", relation: "supports", eventTime: now, ageAtDecisionSeconds: 2, sourceStatus: "FRESH" }, { id: "r-tank-09", type: "READING", label: "TANK_01 level", value: 59.8, unit: "%", relation: "supports", eventTime: now, ageAtDecisionSeconds: 4, sourceStatus: "FRESH" }, { id: "r-soil-44", type: "READING", label: "SOIL_01 moisture", value: 31.8, unit: "%", relation: "limits", eventTime: now, ageAtDecisionSeconds: 18, sourceStatus: "STALE" }] };
  if (path === "/farm/request") return { traceId: "TRACE-DEMO-NEW", planLineageId: "PLAN-DEMO-NEW" };
  const taskMatch = path.match(/^\/tasks\/([^/]+)\/(acknowledge|resolve)$/);
  if (taskMatch && options.method === "POST") { taskState = taskState.map((task) => task.id === decodeURIComponent(taskMatch[1]) ? { ...task, status: taskMatch[2] === "acknowledge" ? "acknowledged" : "resolved" } : task); return null; }
  if (path.startsWith("/approvals/")) return null;
  throw new Error(`Không có demo fixture cho ${path}`);
}
