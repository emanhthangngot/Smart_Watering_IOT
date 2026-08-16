import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const farmState = {
  farmStateVersion: 42,
  updatedAt: "2026-08-16T10:05:04Z",
  devices: [
    {
      deviceCode: "SOIL_01",
      freshness: "STALE",
      connectivity: "CONNECTED",
      ageSeconds: 18,
      eventTime: "2026-08-16T10:04:46Z",
      dcs: 0.38,
      tier: "INVESTIGATE",
      reasons: ["Reading vượt TTL 15 giây", "Cần kiểm tra cảm biến đất"],
      metrics: { moisture: { value: 31.8, unit: "%" }, temperature: { value: 29.4, unit: "°C" } },
    },
    {
      deviceCode: "PUMP_01",
      freshness: "FRESH",
      connectivity: "CONNECTED",
      ageSeconds: 2,
      eventTime: "2026-08-16T10:05:02Z",
      dcs: 0.91,
      tier: "PROPOSE",
      reasons: ["Freshness và flow evidence đầy đủ"],
      metrics: { flow_rate: { value: 13.9, unit: "L/min" }, power: { value: 646, unit: "W" } },
    },
  ],
  activePlan: { planLineageId: "PLAN-001", planRevisionId: "PLAN-001-V2" },
  traceId: "TRACE-001",
  partialMode: true,
  crossSensor: { anomalies: ["SOIL_01 stale, định lượng tưới đang bị giới hạn"] },
};

const planDetail = {
  plan: {
    planLineageId: "PLAN-001",
    planRevisionId: "PLAN-001-V2",
    revisionOfPlanRevisionId: "PLAN-001-V1",
    revisionHash: "sha256:exact-v2-hash",
    version: 2,
    status: "PROPOSED",
    goal: { type: "IRRIGATION", area: "A" },
    createdFromStateVersion: 42,
    evidenceRefs: ["r-soil-1", "r-pump-1"],
    constraints: ["tankReserve >= 20%", "no pump overlap"],
    waterBudget: { plannedDrawdownPct: 6.5, plannedPumpMinutes: 18 },
    confidence: { dcs: 0.8, tier: "PROPOSE", dcsPolicyVersion: 3 },
    requiresApproval: true,
    decisionId: "DECISION-PLAN-V2",
  },
  assumptions: [
    {
      assumptionId: "A1",
      predicate: "PUMP_01.flow_rate >= 8 L/min",
      status: "VALID",
      evidenceRefs: ["r-pump-1"],
      observationWindow: "2 sliding windows",
    },
    {
      assumptionId: "A3",
      predicate: "SOIL_01 remains FRESH",
      status: "INVALIDATED",
      evidenceRefs: ["r-soil-1"],
      invalidatedReason: "SOIL_01 vượt TTL",
    },
  ],
  challenges: [
    {
      challengeId: "CH-1",
      agent: "Diagnosis",
      blocking: false,
      status: "REQUEST_MORE_EVIDENCE",
      reason: "Soil evidence stale, chỉ cho phép partial mode.",
    },
  ],
  actions: [
    { actionId: "IRR-104", type: "IRRIGATION_SCHEDULE", status: "PENDING", parameters: { minutes: 18 } },
  ],
  expectedOutcomes: [
    { metric: "flow_rate", predicate: "flow_rate >= threshold", threshold: 8, tolerance: 0.5, observationWindow: "2 windows" },
  ],
  verifications: [
    { id: "AV-1", layer: "ACTION", expected: "IRR-104", observed: "IRR-104", result: "PASS", evidenceRefs: ["tool-1"] },
    { id: "OV-1", layer: "OUTCOME", expected: "flow >= 8", observed: null, result: "INCONCLUSIVE", evidenceRefs: [] },
  ],
};

const initialTasks = [
  {
    id: "TASK-018",
    title: "Kiểm tra pump và valve",
    deviceCode: "PUMP_01",
    reason: "Flow giảm dưới ngưỡng assumption A1",
    instructions: "Kiểm tra van, lọc và đường ống trước khi resume plan.",
    priority: "CRITICAL",
    status: "unread",
    evidenceRefs: ["r-pump-fault"],
    createdAt: "2026-08-16T10:05:10Z",
  },
];

const timeline = {
  events: [
    { id: "EV-1", timestamp: "2026-08-16T10:00:00Z", actor: "Planner", type: "PROPOSED", title: "Planner đề xuất PLAN-001-V1", decisionId: "DECISION-1", evidenceRefs: ["r-soil-1"] },
    { id: "EV-2", timestamp: "2026-08-16T10:01:00Z", actor: "Resource", type: "CHALLENGED", title: "Resource yêu cầu giảm thời lượng", detail: "Tank reserve không đủ cho V1." },
    { id: "EV-3", timestamp: "2026-08-16T10:02:00Z", actor: "Planner", type: "REVISED", title: "Planner tạo PLAN-001-V2" },
  ],
};

async function fulfillJson(route: Route, json: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(json) });
}

async function mockApi(page: Page, options: { approvalConflict?: boolean } = {}) {
  let tasks = structuredClone(initialTasks);
  await page.addInitScript(() => window.sessionStorage.setItem("farmops-operator-token", "e2e-token"));
  await page.route("**/farm/state", (route) => fulfillJson(route, farmState));
  await page.route("**/health", (route) => fulfillJson(route, {
    status: "healthy",
    batchPeriodSeconds: 5,
    lateRatio: 0.012,
    clockSkewSeconds: 0.8,
    uptimeSeconds: 7420,
    outboxDepth: 0,
    dbWriteLatencyMs: 42,
    missingDevices: ["PH_01"],
  }));
  await page.route("**/trust/current", (route) => fulfillJson(route, { verdicts: [
    { scope: "SOIL_01", dcs: 0.38, tier: "INVESTIGATE", reasons: ["Freshness hard cap đang áp dụng"] },
    { scope: "PUMP_01", dcs: 0.91, tier: "PROPOSE", reasons: ["Reading đầy đủ và nhất quán"] },
  ] }));
  await page.route("**/farm/plan/*", (route) => fulfillJson(route, planDetail));
  await page.route("**/farm/request", async (route) => {
    expect(route.request().headers()["x-operator-token"]).toBe("e2e-token");
    await fulfillJson(route, { traceId: "TRACE-NEW", planLineageId: "PLAN-NEW" });
  });
  await page.route("**/approvals/*/approve", async (route) => {
    if (options.approvalConflict) {
      await fulfillJson(route, { detail: "revision hash mismatch" }, 409);
      return;
    }
    expect(route.request().headers()["x-operator-token"]).toBe("e2e-token");
    expect((await route.request().postDataJSON()).revisionHash).toBe("sha256:exact-v2-hash");
    await route.fulfill({ status: 204 });
  });
  await page.route("**/approvals/*/reject", (route) => route.fulfill({ status: 204 }));
  await page.route("**/tasks", (route) => fulfillJson(route, { tasks }));
  await page.route("**/tasks/*/acknowledge", async (route) => {
    tasks = tasks.map((task) => ({ ...task, status: task.id === "TASK-018" ? "acknowledged" : task.status }));
    await route.fulfill({ status: 204 });
  });
  await page.route("**/tasks/*/resolve", async (route) => {
    tasks = tasks.map((task) => ({ ...task, status: task.id === "TASK-018" ? "resolved" : task.status }));
    await route.fulfill({ status: 204 });
  });
  await page.route("**/timeline/*", (route) => fulfillJson(route, timeline));
  await page.route("**/explain/*", (route) => fulfillJson(route, { nodes: [
    { id: "r-soil-1", type: "READING", label: "SOIL_01 moisture", value: 31.8, unit: "%", relation: "supports", eventTime: "2026-08-16T10:04:46Z", age_s: 12, sourceStatus: "STALE" },
  ] }));
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("overview only marks its own navigation item active", async ({ page }) => {
  await page.goto("/");
  const sidebarNav = page.locator(".sidebar__nav");
  await expect(sidebarNav.locator('a[href="/"]')).toHaveAttribute("aria-current", "page");
  await expect(sidebarNav.locator('a[href="/#devices"]')).not.toHaveAttribute("aria-current", "page");
  await expect(sidebarNav.locator('a[href="/#monitoring"]')).not.toHaveAttribute("aria-current", "page");
});

test("operator starts a traceable planning workflow", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Tổng quan trang trại" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tình trạng hiện tại" })).toBeVisible();
  await page.getByRole("button", { name: /PUMP_01/i }).first().click();
  await expect(page.getByRole("img", { name: "Đường nước có evidence flow" })).toBeVisible();
  await expect(page.getByText("SOIL_01", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Reading vượt TTL 15 giây")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sức khỏe pipeline" })).toBeVisible();

  await page.getByLabel("Nội dung yêu cầu").fill("Lập kế hoạch tưới Khu A trong ca chiều.");
  await page.getByRole("button", { name: /Gửi yêu cầu cho Coordinator/i }).click();
  await expect(page.getByText("Workflow đã bắt đầu")).toBeVisible();
  await expect(page.getByText("PLAN-NEW")).toBeVisible();
});

test("plan preserves approval hash and verification honesty", async ({ page }) => {
  await page.goto("/plans/PLAN-001-V2");
  await expect(page.getByRole("heading", { name: "PLAN-001-V2" })).toBeVisible();
  await expect(page.getByText("sha256:exact-v2-hash")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Action Verification" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Outcome Verification" })).toBeVisible();
  await expect(page.getByText("INCONCLUSIVE")).toBeVisible();

  await page.getByRole("button", { name: /Phê duyệt revision/i }).click();
  await expect(page.getByText("Đã phê duyệt đúng revision hiện tại.")).toBeVisible();
});

test("stale approval is visible and cannot look successful", async ({ page }) => {
  await page.unrouteAll({ behavior: "wait" });
  await mockApi(page, { approvalConflict: true });
  await page.goto("/plans/PLAN-001-V2");
  await page.getByRole("button", { name: /Phê duyệt revision/i }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Revision hash không còn khớp" })).toBeVisible();
  await expect(page.getByText("Đã phê duyệt đúng revision hiện tại.")).toHaveCount(0);
});

test("inspection notification follows unread to acknowledged to resolved", async ({ page }) => {
  await page.goto("/inspection-tasks");
  await expect(page.getByText("TASK-018")).toBeVisible();
  await page.getByRole("button", { name: "Xác nhận đã đọc" }).click();
  await expect(page.getByText("ACKNOWLEDGED").first()).toBeVisible();
  await page.getByRole("button", { name: "Đánh dấu đã xử lý" }).click();
  await expect(page.getByText("Nhiệm vụ đã đóng")).toBeVisible();
});

test("decision replay explains evidence age at decision time", async ({ page }) => {
  await page.goto("/trace/TRACE-001");
  await expect(page.getByRole("heading", { name: "Decision replay" })).toBeVisible();
  await expect(page.getByText("Planner đề xuất PLAN-001-V1")).toBeVisible();
  await page.getByRole("button", { name: "Vì sao?" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByText("12 giây")).toBeVisible();
  await expect(page.getByText("Tuổi tại lúc quyết định")).toBeVisible();
});

test("theme and operator credential controls remain explicit", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Chuyển sang giao diện tối" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const darkResults = await new AxeBuilder({ page }).analyze();
  expect(darkResults.violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? ""))).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-dark-overview.png`), fullPage: true });
  await page.getByRole("button", { name: "Cấu hình operator token" }).click();
  const dialog = page.getByRole("dialog", { name: "Kết nối quyền vận hành" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Operator token")).toHaveAttribute("type", "password");
  await expect(dialog).toContainText("sessionStorage");
});

test("critical screens have no serious accessibility violations or horizontal overflow", async ({ page }, testInfo) => {
  for (const path of ["/", "/plans/PLAN-001-V2", "/inspection-tasks", "/trace/TRACE-001"]) {
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `${path} horizontal overflow`).toBeLessThanOrEqual(1);
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? "")), `${path} axe violations`).toEqual([]);
  }
  await page.goto("/");
  const screenshotName = testInfo.project.name === "mobile-390" ? "mobile-overview.png" : "desktop-overview.png";
  await page.screenshot({ path: testInfo.outputPath(screenshotName), fullPage: true });
});
