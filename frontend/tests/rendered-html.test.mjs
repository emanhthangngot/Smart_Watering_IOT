import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the farm operations cockpit", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<html lang="vi">/i);
  assert.match(html, /<title>AquaOps Copilot · Farm Operations<\/title>/i);
  assert.match(html, /MQTT trực tuyến/);
  assert.match(html, /Xác minh phiên tưới Khu A/);
  assert.match(html, /Phê duyệt tạo phiếu/);

  for (const device of ["SOIL_01", "WEATHER_01", "PUMP_01", "PH_01", "TANK_01", "SUN_01"]) {
    assert.match(html, new RegExp(device));
  }
  for (const agent of ["Coordinator", "Field IoT", "Diagnosis", "Resource", "Action"]) {
    assert.match(html, new RegExp(agent));
  }
});

test("keeps evidence, partial mode and API verification explicit", async () => {
  const [dashboard, styles, mockData] = await Promise.all([
    readFile(new URL("../app/operations-dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../app/mock-data.ts", import.meta.url), "utf8"),
  ]);

  assert.match(dashboard, /partialMode/);
  assert.match(dashboard, /loại khỏi quyết định/);
  assert.match(dashboard, /TASK-024 đã được tạo và xác minh/);
  assert.match(dashboard, /Read-back VERIFIED/);
  assert.match(dashboard, /aria-live="polite"/);
  assert.match(styles, /prefers-reduced-motion/);
  assert.match(styles, /min-height:44px/);
  assert.match(styles, /@media \(max-width:700px\)/);
  assert.match(mockData, /flow_rate|L\/phút|Lưu lượng/);
});
