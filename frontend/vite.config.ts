import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const apiRoutes = [
  "/farm",
  "/health",
  "/trust",
  "/explain",
  "/timeline",
  "/approvals",
  "/tasks",
];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: Object.fromEntries(
      apiRoutes.map((route) => [route, "http://127.0.0.1:8000"]),
    ),
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
