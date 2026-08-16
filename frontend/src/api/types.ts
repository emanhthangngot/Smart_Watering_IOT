export type AsyncStatus = "idle" | "loading" | "success" | "error";

export type FreshnessStatus = "FRESH" | "STALE" | "OFFLINE" | "MISSING" | "SUSPECT" | "UNKNOWN";
export type TrustTier = "AUTO" | "PROPOSE" | "INVESTIGATE" | "UNKNOWN";
export type VerificationResult = "PASS" | "FAIL" | "INCONCLUSIVE";
export type VerificationLayer = "ACTION" | "OUTCOME";
export type TaskPriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type TaskStatus = "unread" | "acknowledged" | "resolved";

export interface MetricReading {
  name: string;
  value: unknown;
  unit?: string;
  eventTime?: string;
  ageSeconds?: number;
  freshness?: FreshnessStatus;
}

export interface ContractWarning {
  path: string;
  code: "MISSING_REQUIRED" | "INVALID_ENUM" | "TYPE_MISMATCH" | "UNFROZEN_CONTRACT";
  message: string;
}

export interface DeviceSnapshot {
  deviceCode: string;
  freshness: FreshnessStatus;
  connectivity: string;
  eventTime?: string;
  ageSeconds?: number;
  dcs?: number;
  tier?: TrustTier;
  reasons: string[];
  metrics: MetricReading[];
  aggregation: "BACKEND" | "FRONTEND_CONSERVATIVE_FALLBACK";
  contractWarnings?: ContractWarning[];
}

export interface ActivePlanRef {
  planLineageId: string;
  planRevisionId: string;
}

export interface FarmState {
  farmStateVersion?: number;
  updatedAt?: string;
  devices: DeviceSnapshot[];
  activePlan?: ActivePlanRef;
  traceId?: string;
  anomalies: string[];
  partialMode: boolean;
  evidenceHealth: {
    state: "COMPLETE" | "PARTIAL" | "UNKNOWN";
    source: "COORDINATOR" | "CONSERVATIVE_FALLBACK";
    reasons: string[];
    requiredDeviceCodes: string[];
  };
  contractWarnings?: ContractWarning[];
}

export interface TrustVerdict {
  scope: string;
  dcs?: number;
  tier: TrustTier;
  reasons: string[];
  policyVersion?: string;
}

export interface HealthStatus {
  status: string;
  batchPeriodSeconds?: number;
  lateRatio?: number;
  clockSkewSeconds?: number;
  uptimeSeconds?: number;
  outboxDepth?: number;
  dbWriteLatencyMs?: number;
  missingDevices: string[];
  reasons: string[];
}

export interface Assumption {
  assumptionId: string;
  predicate: string;
  status: "VALID" | "INVALIDATED" | string;
  evidenceRefs: string[];
  observationWindow?: string;
  affectedActionIds: string[];
  invalidatedAt?: string;
  invalidatedReason?: string;
  invalidatedEvidence?: string;
  contractWarnings?: ContractWarning[];
}

export interface Challenge {
  challengeId: string;
  targetPlanRevisionId?: string;
  agent: string;
  blocking: boolean;
  status: string;
  reason: string;
  evidenceRefs: string[];
  requestedEvidence?: string;
  revision?: string;
  contractWarnings?: ContractWarning[];
}

export interface ExpectedOutcome {
  metric: string;
  predicate: string;
  threshold?: number;
  tolerance?: number;
  observationWindow?: string;
  evidenceSource?: string;
  affectedAssumptionId?: string;
  contractWarnings?: ContractWarning[];
}

export interface Verification {
  id: string;
  layer: VerificationLayer;
  expected: unknown;
  observed: unknown;
  result: VerificationResult;
  window?: string;
  evidenceRefs: string[];
  contractWarnings?: ContractWarning[];
}

export interface PlanAction {
  actionId: string;
  type: string;
  status?: string;
  parameters: Record<string, unknown>;
}

export interface PlanDetail {
  planLineageId: string;
  planRevisionId: string;
  revisionOfPlanRevisionId?: string;
  revisionHash: string;
  version?: number;
  status: string;
  goal: Record<string, unknown>;
  createdFromStateVersion?: number;
  evidenceRefs: string[];
  constraints: string[];
  assumptions: Assumption[];
  actions: PlanAction[];
  expectedOutcomes: ExpectedOutcome[];
  waterBudget: Record<string, unknown>;
  confidence: {
    dcs?: number;
    tier: TrustTier;
    policyVersion?: string;
  };
  requiresApproval: boolean;
  challenges: Challenge[];
  verifications: Verification[];
  decisionId?: string;
  approvalExpiresAt?: string;
  contractWarnings?: ContractWarning[];
}

export interface InspectionTask {
  id: string;
  title: string;
  deviceCode?: string;
  reason: string;
  instructions?: string;
  priority: TaskPriority;
  status: TaskStatus;
  evidenceRefs: string[];
  createdAt?: string;
  updatedAt?: string;
}

export interface TimelineEvent {
  id: string;
  timestamp?: string;
  actor: string;
  type: string;
  title: string;
  detail?: string;
  decisionId?: string;
  evidenceRefs: string[];
}

export interface EvidenceNode {
  id: string;
  type: string;
  label: string;
  relation?: string;
  value?: unknown;
  unit?: string;
  eventTime?: string;
  ageAtDecisionSeconds?: number;
  sourceStatus?: string;
}

export interface FarmRequest {
  intent: string;
  scope: string;
  text: string;
}

export interface FarmRequestResult {
  traceId: string;
  planLineageId: string;
}

export interface ApprovalRequest {
  revisionHash: string;
  comment?: string;
}
