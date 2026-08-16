import {
  normalizeExplain,
  normalizeFarmRequest,
  normalizeFarmState,
  normalizeHealth,
  normalizePlan,
  normalizeTasks,
  normalizeTimeline,
  normalizeTrust,
} from "./normalize";
import type {
  ApprovalRequest,
  FarmRequest,
  FarmRequestResult,
  FarmState,
  HealthStatus,
  InspectionTask,
  PlanDetail,
  TimelineEvent,
  TrustVerdict,
  EvidenceNode,
} from "./types";
import { assertTaskTransition, type TaskAction } from "../domain/taskLifecycle";
import { demoResponse } from "./demo";

interface RequestOptions extends RequestInit {
  operatorToken?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

function errorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    for (const key of ["detail", "message", "error"]) {
      if (typeof record[key] === "string") return record[key];
    }
  }
  return fallback;
}

export function isRevisionConflict(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  if ([409, 412].includes(error.status)) return true;
  if (error.status !== 422) return false;
  const details = JSON.stringify(error.details ?? "");
  return /revision|hash|stale|expired/i.test(`${error.message} ${details}`);
}

export class FarmOpsApi {
  private readonly baseUrl: string;
  private readonly operatorToken: string;

  constructor(operatorToken = "", baseUrl = import.meta.env.VITE_API_BASE_URL ?? "") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.operatorToken = operatorToken.trim();
  }

  private get demoMode(): boolean {
    return typeof window !== "undefined" && new URLSearchParams(window.location.search).get("demo") === "1";
  }

  private async request(path: string, options: RequestOptions = {}): Promise<unknown> {
    if (this.demoMode) return demoResponse(path, options);
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    if (options.body) headers.set("Content-Type", "application/json");
    const token = options.operatorToken ?? this.operatorToken;
    if (token) headers.set("X-Operator-Token", token);

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, { ...options, headers });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError("Không thể kết nối FarmOps API.", 0, error);
    }

    const contentType = response.headers.get("content-type") ?? "";
    const payload = response.status === 204
      ? null
      : contentType.includes("application/json")
        ? await response.json()
        : await response.text();
    if (!response.ok) {
      throw new ApiError(
        errorMessage(payload, `FarmOps API trả về lỗi ${response.status}.`),
        response.status,
        payload,
      );
    }
    return payload;
  }

  async getFarmState(signal?: AbortSignal): Promise<FarmState> {
    return normalizeFarmState(await this.request("/farm/state", { signal }));
  }

  async getHealth(signal?: AbortSignal): Promise<HealthStatus> {
    return normalizeHealth(await this.request("/health", { signal }));
  }

  async getTrust(signal?: AbortSignal): Promise<TrustVerdict[]> {
    return normalizeTrust(await this.request("/trust/current", { signal }));
  }

  async getTasks(signal?: AbortSignal): Promise<InspectionTask[]> {
    return normalizeTasks(await this.request("/tasks", { signal }));
  }

  async requestPlan(request: FarmRequest, signal?: AbortSignal): Promise<FarmRequestResult> {
    return normalizeFarmRequest(await this.request("/farm/request", {
      method: "POST",
      body: JSON.stringify(request),
      signal,
    }));
  }

  async getPlan(revisionId: string, signal?: AbortSignal): Promise<PlanDetail> {
    return normalizePlan(await this.request(`/farm/plan/${encodeURIComponent(revisionId)}`, { signal }));
  }

  async decidePlan(
    revisionId: string,
    decision: "approve" | "reject",
    request: ApprovalRequest,
    signal?: AbortSignal,
  ): Promise<void> {
    await this.request(`/approvals/${encodeURIComponent(revisionId)}/${decision}`, {
      method: "POST",
      body: JSON.stringify(request),
      signal,
    });
  }

  async updateTask(task: InspectionTask, action: TaskAction, signal?: AbortSignal): Promise<void> {
    assertTaskTransition(task, action);
    await this.request(`/tasks/${encodeURIComponent(task.id)}/${action}`, { method: "POST", signal });
  }

  async getTimeline(traceId: string, signal?: AbortSignal): Promise<TimelineEvent[]> {
    return normalizeTimeline(await this.request(`/timeline/${encodeURIComponent(traceId)}`, { signal }));
  }

  async explain(decisionId: string, signal?: AbortSignal): Promise<EvidenceNode[]> {
    return normalizeExplain(await this.request(`/explain/${encodeURIComponent(decisionId)}`, { signal }));
  }
}
