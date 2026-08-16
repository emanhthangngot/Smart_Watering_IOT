import type {
  ActivePlanRef, Assumption, Challenge, ContractWarning, DeviceSnapshot, EvidenceNode,
  ExpectedOutcome, FarmRequestResult, FarmState, FreshnessStatus, HealthStatus,
  InspectionTask, MetricReading, PlanAction, PlanDetail, TaskPriority, TaskStatus,
  TimelineEvent, TrustTier, TrustVerdict, Verification, VerificationLayer, VerificationResult,
} from "./types";

type UnknownRecord = Record<string, unknown>;

export function asRecord(value: unknown): UnknownRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : {};
}

function has(record: UnknownRecord, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key) && record[key] !== null && record[key] !== undefined;
}
function first(record: UnknownRecord, ...keys: string[]): unknown {
  return keys.find((key) => has(record, key)) ? record[keys.find((key) => has(record, key))!] : undefined;
}
function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : typeof value === "number" || typeof value === "boolean" ? String(value) : fallback;
}
function number(value: unknown): number | undefined {
  const parsed = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : undefined;
}
function boolean(value: unknown): boolean {
  return value === true || value === "true" || value === 1;
}
function list(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  return Object.entries(asRecord(value)).map(([key, item]) => Object.keys(asRecord(item)).length ? { _key: key, ...asRecord(item) } : item);
}
function texts(value: unknown): string[] {
  return list(value).map((item) => typeof item === "string" ? item : text(first(asRecord(item), "reason", "message", "label", "code"))).filter(Boolean);
}
function unwrap(value: unknown): UnknownRecord {
  const root = asRecord(value); const data = asRecord(root.data); return Object.keys(data).length ? data : root;
}
function warning(warnings: ContractWarning[], path: string, code: ContractWarning["code"], message: string): void {
  warnings.push({ path, code, message });
}
function requiredText(record: UnknownRecord, warnings: ContractWarning[], path: string, ...keys: string[]): string {
  const value = text(first(record, ...keys));
  if (!value) warning(warnings, path, "MISSING_REQUIRED", `Thiếu trường contract bắt buộc: ${path}.`);
  return value;
}

function normalizeFreshness(value: unknown, warnings?: ContractWarning[], path = "freshness"): FreshnessStatus {
  const raw = text(value).toUpperCase();
  if (["FRESH", "STALE", "OFFLINE", "MISSING", "SUSPECT"].includes(raw)) return raw as FreshnessStatus;
  if (warnings) warning(warnings, path, raw ? "INVALID_ENUM" : "MISSING_REQUIRED", raw ? `Freshness '${raw}' không thuộc contract; hiển thị UNKNOWN.` : `Thiếu freshness cho ${path}.`);
  return "UNKNOWN";
}
function normalizeTier(value: unknown, warnings?: ContractWarning[], path = "tier"): TrustTier {
  const raw = text(value).toUpperCase();
  if (["AUTO", "PROPOSE", "INVESTIGATE"].includes(raw)) return raw as TrustTier;
  if (raw && warnings) warning(warnings, path, "INVALID_ENUM", `Autonomy tier '${raw}' không thuộc contract; hiển thị UNKNOWN.`);
  return "UNKNOWN";
}
function normalizeMetrics(record: UnknownRecord): MetricReading[] {
  const raw = first(record, "metrics", "values", "readings");
  const fromRecord = (metric: UnknownRecord, name: string, value: unknown): MetricReading => ({
    name, value: first(metric, "value", "observed") ?? value,
    unit: text(first(metric, "unit")) || undefined,
    eventTime: text(first(metric, "eventTime", "event_time", "timestamp")) || undefined,
    ageSeconds: number(first(metric, "ageSeconds", "age_s", "freshnessAgeSeconds")),
    freshness: has(metric, "freshness") ? normalizeFreshness(metric.freshness) : undefined,
  });
  if (Array.isArray(raw)) return raw.map((item, index) => {
    const metric = asRecord(item); return fromRecord(metric, text(first(metric, "metric", "name", "_key"), `metric-${index + 1}`), item);
  });
  return Object.entries(asRecord(raw)).map(([name, value]) => fromRecord(asRecord(value), name, value));
}
function normalizeDirectDevice(value: unknown, key?: string, aggregation: DeviceSnapshot["aggregation"] = "BACKEND"): DeviceSnapshot {
  const record = asRecord(value); const trust = asRecord(first(record, "trust", "confidence")); const contractWarnings: ContractWarning[] = [];
  if (value !== null && (typeof value !== "object" || Array.isArray(value))) warning(contractWarnings, "device", "TYPE_MISMATCH", "Device snapshot không phải object.");
  const deviceCode = requiredText(record, contractWarnings, "deviceCode", "deviceCode", "device_code", "id", "_key") || key || "UNKNOWN";
  return {
    deviceCode,
    freshness: normalizeFreshness(first(record, "freshness", "freshnessStatus", "freshness_status", "status"), contractWarnings, `${deviceCode}.freshness`),
    connectivity: text(first(record, "connectivity", "connection", "sourceStatus", "source_status"), "UNKNOWN").toUpperCase(),
    eventTime: text(first(record, "eventTime", "event_time", "timestamp")) || undefined,
    ageSeconds: number(first(record, "ageSeconds", "age_s", "freshnessAgeSeconds")),
    dcs: number(first(record, "dcs", "score") ?? first(trust, "dcs", "score")),
    tier: normalizeTier(first(record, "tier") ?? first(trust, "tier"), contractWarnings, `${deviceCode}.tier`),
    reasons: texts(first(record, "reasons", "reason", "trustReasons", "trust_reasons")),
    metrics: normalizeMetrics(record), aggregation, contractWarnings,
  };
}

const freshnessScore: Record<FreshnessStatus, number> = { FRESH: 0, UNKNOWN: 1, STALE: 2, SUSPECT: 3, OFFLINE: 4, MISSING: 5 };
const tierScore: Record<TrustTier, number> = { UNKNOWN: 0, AUTO: 1, PROPOSE: 2, INVESTIGATE: 3 };
function worst<T>(values: T[], score: (value: T) => number): T | undefined {
  return values.reduce<T | undefined>((current, value) => current === undefined || score(value) > score(current) ? value : current, undefined);
}
function oldestDate(values: Array<string | undefined>): string | undefined {
  const dated: string[] = [];
  for (const value of values) if (value && !Number.isNaN(new Date(value).getTime())) dated.push(value);
  return dated.sort((a, b) => new Date(a).getTime() - new Date(b).getTime())[0];
}
function worstConnection(values: string[]): string {
  const score = (value: string) => ["OFFLINE", "DISCONNECTED", "DOWN"].includes(value.toUpperCase()) ? 3 : ["UNKNOWN", ""].includes(value.toUpperCase()) ? 2 : ["DEGRADED", "CONNECTING"].includes(value.toUpperCase()) ? 1 : 0;
  return worst(values, score) ?? "UNKNOWN";
}
function aggregateDeviceReadings(deviceCode: string, snapshots: DeviceSnapshot[]): DeviceSnapshot {
  const freshness = worst(snapshots.map((item) => item.freshness), (item) => freshnessScore[item]) ?? "UNKNOWN";
  const metrics = snapshots.flatMap((item) => item.metrics);
  const ages = snapshots.map((item) => item.ageSeconds).filter((item): item is number => item !== undefined);
  const scores = snapshots.map((item) => item.dcs).filter((item): item is number => item !== undefined);
  return {
    deviceCode, freshness, connectivity: worstConnection(snapshots.map((item) => item.connectivity)),
    eventTime: oldestDate(snapshots.map((item) => item.eventTime)), ageSeconds: ages.length ? Math.max(...ages) : undefined,
    dcs: scores.length ? Math.min(...scores) : undefined,
    tier: worst(snapshots.map((item) => item.tier ?? "UNKNOWN"), (item) => tierScore[item]),
    reasons: [`Frontend tổng hợp bảo thủ từ ${Math.max(metrics.length, snapshots.length)} metric reading; freshness xấu nhất là ${freshness}.`, ...snapshots.flatMap((item) => item.reasons)].filter((item, index, values) => values.indexOf(item) === index),
    metrics, aggregation: "FRONTEND_CONSERVATIVE_FALLBACK", contractWarnings: snapshots.flatMap((item) => item.contractWarnings ?? []),
  };
}
function devicesFromLatest(telemetry: UnknownRecord): DeviceSnapshot[] {
  const grouped = new Map<string, DeviceSnapshot[]>();
  for (const item of list(first(telemetry, "latest", "readings"))) {
    const reading = asRecord(item); const deviceCode = text(first(reading, "deviceCode", "device_code", "device", "_key"));
    if (!deviceCode) continue;
    const snapshot = normalizeDirectDevice(reading, deviceCode, "FRONTEND_CONSERVATIVE_FALLBACK"); const metricName = text(first(reading, "metric", "name"));
    if (metricName) snapshot.metrics = [{ name: metricName, value: first(reading, "value", "observed"), unit: text(first(reading, "unit")) || undefined, eventTime: snapshot.eventTime, ageSeconds: snapshot.ageSeconds, freshness: snapshot.freshness }];
    grouped.set(deviceCode, [...(grouped.get(deviceCode) ?? []), snapshot]);
  }
  return [...grouped.entries()].map(([deviceCode, snapshots]) => aggregateDeviceReadings(deviceCode, snapshots));
}
function getRequiredDeviceCodes(root: UnknownRecord): string[] {
  const coordinator = asRecord(first(root, "coordinator", "evidenceHealth", "evidence_health"));
  return texts(first(coordinator, "requiredDeviceCodes", "required_device_codes", "requiredEvidenceDevices", "required_evidence_devices") ?? first(root, "requiredDeviceCodes", "required_device_codes", "requiredEvidenceDevices", "required_evidence_devices"));
}
function assessEvidenceHealth(root: UnknownRecord, devices: DeviceSnapshot[]): FarmState["evidenceHealth"] {
  const coordinator = asRecord(first(root, "coordinator", "evidenceHealth", "evidence_health")); const requiredDeviceCodes: string[] = getRequiredDeviceCodes(root);
  const explicit = first(coordinator, "partialMode", "partial_mode", "isPartial", "is_partial") ?? first(root, "partialMode", "partial_mode");
  const state = text(first(coordinator, "state", "status", "evidenceState", "evidence_state")).toUpperCase();
  if ([true, false, "true", "false", 0, 1].includes(explicit as boolean | string | number)) return { state: boolean(explicit) ? "PARTIAL" : "COMPLETE", source: "COORDINATOR", reasons: texts(first(coordinator, "reasons", "reason")), requiredDeviceCodes };
  if (["COMPLETE", "FULL", "PARTIAL", "UNKNOWN"].includes(state)) return { state: state === "FULL" ? "COMPLETE" : state as "COMPLETE" | "PARTIAL" | "UNKNOWN", source: "COORDINATOR", reasons: texts(first(coordinator, "reasons", "reason")), requiredDeviceCodes };
  if (requiredDeviceCodes.length) {
    const missing = requiredDeviceCodes.filter((code) => devices.find((item) => item.deviceCode.toUpperCase() === code.toUpperCase())?.freshness !== "FRESH");
    return { state: missing.length ? "PARTIAL" : "COMPLETE", source: "CONSERVATIVE_FALLBACK", reasons: [missing.length ? `Evidence bắt buộc chưa đủ: ${missing.join(", ")}.` : "Các thiết bị coordinator đánh dấu bắt buộc đều FRESH."], requiredDeviceCodes };
  }
  return { state: "UNKNOWN", source: "CONSERVATIVE_FALLBACK", reasons: ["Coordinator chưa khai báo evidence bắt buộc; không suy ra partial mode từ sensor tùy chọn."], requiredDeviceCodes: [] };
}

export function normalizeFarmState(value: unknown): FarmState {
  const root = unwrap(value); const telemetry = asRecord(root.telemetry); const directDevices = first(root, "devices") ?? first(telemetry, "devices");
  let devices = list(directDevices).map((item) => normalizeDirectDevice(item)); if (!devices.length) devices = devicesFromLatest(telemetry);
  const connectivity = asRecord(first(telemetry, "connectivity"));
  devices = devices.map((device) => {
    const connection = asRecord(connectivity[device.deviceCode]); const rawConnection = connectivity[device.deviceCode];
    return { ...device, connectivity: text(first(connection, "status", "connectivity"), text(rawConnection, device.connectivity)).toUpperCase(), freshness: has(connection, "freshness") ? normalizeFreshness(connection.freshness, device.contractWarnings, `${device.deviceCode}.connectivity.freshness`) : device.freshness, ageSeconds: number(first(connection, "ageSeconds", "age_s")) ?? device.ageSeconds, reasons: [...new Set([...device.reasons, ...texts(first(connection, "reasons", "reason"))])] };
  });
  const active = asRecord(first(root, "activePlan", "active_plan")); const planRevisionId = text(first(active, "planRevisionId", "plan_revision_id"));
  const activePlan: ActivePlanRef | undefined = planRevisionId ? { planRevisionId, planLineageId: text(first(active, "planLineageId", "plan_lineage_id")) } : undefined;
  const assessment = assessEvidenceHealth(root, devices); const crossSensor = asRecord(first(root, "crossSensor", "cross_sensor"));
  return { farmStateVersion: number(first(root, "farmStateVersion", "farm_state_version")), updatedAt: text(first(root, "updatedAt", "updated_at")) || undefined, devices, activePlan, traceId: text(first(root, "traceId", "trace_id", "activeTraceId", "active_trace_id")) || undefined, anomalies: texts(first(crossSensor, "anomalies")), partialMode: assessment.state === "PARTIAL", evidenceHealth: assessment, contractWarnings: [{ path: "contracts.py", code: "UNFROZEN_CONTRACT", message: "Shared contract đang ở phiên bản 0.0.0-unfrozen; trường thiếu hoặc lạ được hiển thị như uncertainty." }] };
}

export function normalizeTrust(value: unknown): TrustVerdict[] {
  const root = unwrap(value); const source = first(root, "verdicts", "scopes", "byScope", "by_scope") ?? root;
  return list(source).map((item, index) => { const record = asRecord(item); return { scope: text(first(record, "scope", "name", "_key"), `scope-${index + 1}`), dcs: number(first(record, "dcs", "score")), tier: normalizeTier(first(record, "tier", "autonomyTier", "autonomy_tier")), reasons: texts(first(record, "reasons", "reason", "rules")), policyVersion: text(first(record, "policyVersion", "policy_version", "dcsPolicyVersion", "dcs_policy_version")) || undefined }; });
}
export function normalizeHealth(value: unknown): HealthStatus {
  const root = unwrap(value); const batch = asRecord(first(root, "batchHealth", "batch_health"));
  return { status: text(first(root, "status"), "UNKNOWN").toUpperCase(), batchPeriodSeconds: number(first(root, "batchPeriodSeconds", "batch_period_seconds", "batchPeriod", "batch_period") ?? first(batch, "periodSeconds", "period_s")), lateRatio: number(first(root, "lateRatio", "late_ratio") ?? first(batch, "lateRatio", "late_ratio")), clockSkewSeconds: number(first(root, "clockSkewSeconds", "clock_skew_seconds", "skewSeconds", "skew_s")), uptimeSeconds: number(first(root, "uptimeSeconds", "uptime_seconds", "uptime")), outboxDepth: number(first(root, "outboxDepth", "outbox_depth")), dbWriteLatencyMs: number(first(root, "dbWriteLatencyMs", "db_write_latency_ms", "writeLatencyMs", "write_latency_ms")), missingDevices: texts(first(root, "missingDevices", "missing_devices")), reasons: texts(first(root, "reasons", "warnings")) };
}

function normalizeAssumption(item: unknown, index: number): Assumption {
  const record = asRecord(item); const contractWarnings: ContractWarning[] = [];
  return { assumptionId: requiredText(record, contractWarnings, `assumptions[${index}].assumptionId`, "assumptionId", "assumption_id", "id") || `assumption-${index + 1}`, predicate: requiredText(record, contractWarnings, `assumptions[${index}].predicate`, "predicate", "description", "label"), status: text(first(record, "status"), "UNKNOWN").toUpperCase(), evidenceRefs: texts(first(record, "evidenceRefs", "evidence_refs")), observationWindow: text(first(record, "observationWindow", "observation_window")) || undefined, affectedActionIds: texts(first(record, "affectedActionIds", "affected_action_ids")), invalidatedAt: text(first(record, "invalidatedAt", "invalidated_at")) || undefined, invalidatedReason: text(first(record, "invalidatedReason", "invalidated_reason")) || undefined, invalidatedEvidence: text(first(record, "invalidatedEvidence", "invalidated_evidence")) || undefined, contractWarnings };
}
function normalizeChallenge(item: unknown, index: number): Challenge {
  const record = asRecord(item); const contractWarnings: ContractWarning[] = [];
  return { challengeId: requiredText(record, contractWarnings, `challenges[${index}].challengeId`, "challengeId", "challenge_id", "id") || `challenge-${index + 1}`, targetPlanRevisionId: requiredText(record, contractWarnings, `challenges[${index}].targetPlanRevisionId`, "targetPlanRevisionId", "target_plan_revision_id") || undefined, agent: requiredText(record, contractWarnings, `challenges[${index}].agent`, "agent", "actor"), blocking: boolean(first(record, "blocking")), status: text(first(record, "status", "decision"), "OPEN").toUpperCase(), reason: requiredText(record, contractWarnings, `challenges[${index}].reason`, "reason", "message"), evidenceRefs: texts(first(record, "evidenceRefs", "evidence_refs")), requestedEvidence: text(first(record, "requestedEvidence", "requested_evidence")) || undefined, revision: text(first(record, "revision", "requestedRevision", "requested_revision")) || undefined, contractWarnings };
}
function normalizeExpectedOutcome(item: unknown, index: number): ExpectedOutcome {
  const record = asRecord(item); const contractWarnings: ContractWarning[] = [];
  const outcome: ExpectedOutcome = { metric: requiredText(record, contractWarnings, `expectedOutcomes[${index}].metric`, "metric", "name"), predicate: requiredText(record, contractWarnings, `expectedOutcomes[${index}].predicate`, "predicate", "description"), threshold: number(first(record, "threshold")), tolerance: number(first(record, "tolerance")), observationWindow: text(first(record, "observationWindow", "observation_window", "window")) || undefined, evidenceSource: text(first(record, "evidenceSource", "evidence_source")) || undefined, affectedAssumptionId: text(first(record, "affectedAssumptionId", "affected_assumption_id")) || undefined, contractWarnings };
  if (outcome.threshold === undefined) warning(contractWarnings, `expectedOutcomes[${index}].threshold`, "MISSING_REQUIRED", "Thiếu threshold bắt buộc."); if (outcome.tolerance === undefined) warning(contractWarnings, `expectedOutcomes[${index}].tolerance`, "MISSING_REQUIRED", "Thiếu tolerance bắt buộc."); if (!outcome.observationWindow) warning(contractWarnings, `expectedOutcomes[${index}].observationWindow`, "MISSING_REQUIRED", "Thiếu observationWindow bắt buộc."); if (!outcome.evidenceSource) warning(contractWarnings, `expectedOutcomes[${index}].evidenceSource`, "MISSING_REQUIRED", "Thiếu evidenceSource bắt buộc."); if (!outcome.affectedAssumptionId) warning(contractWarnings, `expectedOutcomes[${index}].affectedAssumptionId`, "MISSING_REQUIRED", "Thiếu affectedAssumptionId bắt buộc."); return outcome;
}
function normalizeVerification(item: unknown, index: number): Verification {
  const record = asRecord(item); const contractWarnings: ContractWarning[] = []; const layer = text(first(record, "layer")).toUpperCase(); const result = text(first(record, "result", "status"), "INCONCLUSIVE").toUpperCase(); const window = text(first(record, "window", "observationWindow", "observation_window")) || undefined;
  if (layer !== "ACTION" && layer !== "OUTCOME") warning(contractWarnings, `verifications[${index}].layer`, "INVALID_ENUM", "Verification layer không thuộc ACTION|OUTCOME; hiển thị OUTCOME."); if (!["PASS", "FAIL", "INCONCLUSIVE"].includes(result)) warning(contractWarnings, `verifications[${index}].result`, "INVALID_ENUM", "Verification result không thuộc contract; hiển thị INCONCLUSIVE."); if (!has(record, "expected")) warning(contractWarnings, `verifications[${index}].expected`, "MISSING_REQUIRED", "Thiếu expected bắt buộc."); if (!has(record, "observed") && !has(record, "actual")) warning(contractWarnings, `verifications[${index}].observed`, "MISSING_REQUIRED", "Thiếu observed bắt buộc."); if (!window) warning(contractWarnings, `verifications[${index}].window`, "MISSING_REQUIRED", "Thiếu window bắt buộc.");
  return { id: text(first(record, "verificationId", "verification_id", "id"), `verification-${index + 1}`), layer: (layer === "ACTION" ? "ACTION" : "OUTCOME") as VerificationLayer, expected: first(record, "expected"), observed: first(record, "observed", "actual"), result: (["PASS", "FAIL", "INCONCLUSIVE"].includes(result) ? result : "INCONCLUSIVE") as VerificationResult, window, evidenceRefs: texts(first(record, "evidenceRefs", "evidence_refs")), contractWarnings };
}
function normalizeAction(item: unknown, index: number): PlanAction {
  const record = asRecord(item); return { actionId: text(first(record, "actionId", "action_id", "id"), `action-${index + 1}`), type: text(first(record, "type", "actionType", "action_type"), "ACTION"), status: text(first(record, "status")) || undefined, parameters: asRecord(first(record, "parameters", "params")) };
}
export function normalizePlan(value: unknown): PlanDetail {
  const root = unwrap(value); const nested = asRecord(root.plan); const plan = Object.keys(nested).length ? nested : root; const confidence = asRecord(first(plan, "confidence")); const contractWarnings: ContractWarning[] = [];
  if (!has(plan, "requiresApproval") && !has(plan, "requires_approval")) warning(contractWarnings, "requiresApproval", "MISSING_REQUIRED", "Thiếu requiresApproval; approval bị khóa an toàn.");
  return { planLineageId: requiredText(plan, contractWarnings, "planLineageId", "planLineageId", "plan_lineage_id"), planRevisionId: requiredText(plan, contractWarnings, "planRevisionId", "planRevisionId", "plan_revision_id", "revisionId", "revision_id"), revisionOfPlanRevisionId: text(first(plan, "revisionOfPlanRevisionId", "revision_of_plan_revision_id")) || undefined, revisionHash: requiredText(plan, contractWarnings, "revisionHash", "revisionHash", "revision_hash"), version: number(first(plan, "version")), status: text(first(plan, "status"), "UNKNOWN").toUpperCase(), goal: asRecord(first(plan, "goal")), createdFromStateVersion: number(first(plan, "createdFromStateVersion", "created_from_state_version")), evidenceRefs: texts(first(plan, "evidenceRefs", "evidence_refs")), constraints: texts(first(plan, "constraints")), assumptions: list(first(root, "assumptions") ?? first(plan, "assumptions")).map(normalizeAssumption), actions: list(first(root, "actions") ?? first(plan, "actions")).map(normalizeAction), expectedOutcomes: list(first(root, "expectedOutcomes", "expected_outcomes") ?? first(plan, "expectedOutcomes", "expected_outcomes")).map(normalizeExpectedOutcome), waterBudget: asRecord(first(plan, "waterBudget", "water_budget")), confidence: { dcs: number(first(confidence, "dcs", "score")), tier: normalizeTier(first(confidence, "tier"), contractWarnings, "confidence.tier"), policyVersion: text(first(confidence, "dcsPolicyVersion", "dcs_policy_version", "policyVersion", "policy_version")) || undefined }, requiresApproval: boolean(first(plan, "requiresApproval", "requires_approval")), challenges: list(first(root, "challenges") ?? first(plan, "challenges")).map(normalizeChallenge), verifications: list(first(root, "verifications") ?? first(plan, "verifications")).map(normalizeVerification), decisionId: text(first(plan, "decisionId", "decision_id")) || undefined, approvalExpiresAt: text(first(root, "approvalExpiresAt", "approval_expires_at", "expiresAt", "expires_at") ?? first(plan, "approvalExpiresAt", "approval_expires_at", "expiresAt", "expires_at")) || undefined, contractWarnings };
}

function normalizePriority(value: unknown): TaskPriority { const raw = text(value, "MEDIUM").toUpperCase(); return ["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(raw) ? raw as TaskPriority : "MEDIUM"; }
function normalizeTaskStatus(value: unknown): TaskStatus { const raw = text(value, "unread").toLowerCase(); return ["resolved", "done", "closed"].includes(raw) ? "resolved" : ["acknowledged", "ack", "in_progress"].includes(raw) ? "acknowledged" : "unread"; }
export function normalizeTasks(value: unknown): InspectionTask[] {
  const root = unwrap(value); const source = Array.isArray(value) ? value : first(root, "tasks", "items", "inspectionTasks", "inspection_tasks") ?? [];
  return list(source).map((item, index) => { const record = asRecord(item); return { id: text(first(record, "taskId", "task_id", "id"), `task-${index + 1}`), title: text(first(record, "title", "summary"), "Kiểm tra hiện trường"), deviceCode: text(first(record, "deviceCode", "device_code", "device")) || undefined, reason: text(first(record, "reason", "description"), "Cần xác minh thủ công"), instructions: text(first(record, "instructions", "content", "check")) || undefined, priority: normalizePriority(first(record, "priority", "severity")), status: normalizeTaskStatus(first(record, "status", "notificationStatus", "notification_status")), evidenceRefs: texts(first(record, "evidenceRefs", "evidence_refs", "evidence")), createdAt: text(first(record, "createdAt", "created_at")) || undefined, updatedAt: text(first(record, "updatedAt", "updated_at")) || undefined }; });
}
export function normalizeTimeline(value: unknown): TimelineEvent[] {
  const root = unwrap(value); const source = Array.isArray(value) ? value : first(root, "events", "timeline", "items") ?? [];
  return list(source).map((item, index) => { const record = asRecord(item); return { id: text(first(record, "eventId", "event_id", "id"), `event-${index + 1}`), timestamp: text(first(record, "timestamp", "createdAt", "created_at", "eventTime", "event_time")) || undefined, actor: text(first(record, "actor", "agent", "source"), "System"), type: text(first(record, "type", "eventType", "event_type"), "EVENT").toUpperCase(), title: text(first(record, "title", "summary", "message"), "Sự kiện vận hành"), detail: text(first(record, "detail", "description", "reason")) || undefined, decisionId: text(first(record, "decisionId", "decision_id")) || undefined, evidenceRefs: texts(first(record, "evidenceRefs", "evidence_refs")) }; });
}
export function normalizeExplain(value: unknown): EvidenceNode[] {
  const root = unwrap(value); const source = Array.isArray(value) ? value : first(root, "nodes", "lineage", "items", "evidence") ?? [];
  return list(source).map((item, index) => { const record = asRecord(item); return { id: text(first(record, "nodeId", "node_id", "readingId", "reading_id", "id"), `node-${index + 1}`), type: text(first(record, "type", "nodeType", "node_type"), "EVIDENCE").toUpperCase(), label: text(first(record, "label", "metric", "title", "description"), "Evidence"), relation: text(first(record, "relation", "rel")) || undefined, value: first(record, "value", "observed"), unit: text(first(record, "unit")) || undefined, eventTime: text(first(record, "eventTime", "event_time", "timestamp")) || undefined, ageAtDecisionSeconds: number(first(record, "ageAtDecisionSeconds", "age_at_decision_seconds", "age_s")), sourceStatus: text(first(record, "sourceStatus", "source_status", "status")) || undefined }; });
}
export function normalizeFarmRequest(value: unknown): FarmRequestResult { const root = unwrap(value); return { traceId: text(first(root, "traceId", "trace_id")), planLineageId: text(first(root, "planLineageId", "plan_lineage_id")) }; }
export function formatUnknown(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Chưa có dữ liệu"; if (typeof value === "boolean") return value ? "Có" : "Không"; if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2); if (typeof value === "string") return value; try { return JSON.stringify(value); } catch { return "Không thể hiển thị"; }
}
