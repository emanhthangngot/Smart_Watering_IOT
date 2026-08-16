import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, FarmOpsApi, isRevisionConflict } from "./client";

describe("FarmOpsApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends operator token and exact revision hash to approval endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    const api = new FarmOpsApi("secret-operator-token", "https://farmops.test");
    await api.decidePlan("PLAN-001-V2", "approve", { revisionHash: "hash-v2", comment: "Đã kiểm tra" });

    const [url, options] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("https://farmops.test/approvals/PLAN-001-V2/approve");
    const headers = new Headers(options?.headers);
    expect(headers.get("X-Operator-Token")).toBe("secret-operator-token");
    expect(JSON.parse(String(options?.body))).toEqual({ revisionHash: "hash-v2", comment: "Đã kiểm tra" });
  });

  it("only treats an explicit revision-related 422 as a revision conflict", () => {
    expect(isRevisionConflict(new ApiError("validation failed", 422, { detail: "comment is too long" }))).toBe(false);
    expect(isRevisionConflict(new ApiError("validation failed", 422, { detail: "revision hash is stale" }))).toBe(true);
  });

  it("rejects an illegal unread-to-resolved task transition before requesting the API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const api = new FarmOpsApi("", "https://farmops.test");
    await expect(api.updateTask({ id: "TASK-1", status: "unread", title: "", reason: "", priority: "HIGH", evidenceRefs: [] }, "resolve")).rejects.toThrow("Không thể resolve");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("serves local demo fixtures only when the demo query flag is enabled", async () => {
    window.history.pushState({}, "", "/?demo=1");
    const api = new FarmOpsApi();
    await expect(api.getFarmState()).resolves.toMatchObject({ farmStateVersion: 42, activePlan: { planRevisionId: "PLAN-001-V2" } });
    window.history.pushState({}, "", "/");
  });
});
