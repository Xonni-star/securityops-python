import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.E2E_API_PROXY_TARGET || "http://api:8000";
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": apiTarget,
        "/health": apiTarget,
      },
    },
    test: {
      environment: "jsdom",
      include: ["src/**/*.test.{ts,tsx}"],
    },
  };
});
