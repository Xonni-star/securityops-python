import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  workers: 1,
  reporter: "list",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command:
        "python3 -c \"import runpy; runpy.run_path('tests/e2e_server.py', run_name='__main__')\"",
      cwd: "../backend",
      url: "http://127.0.0.1:8001/health/live",
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        POSTGRES_PASSWORD: "e2e-only-not-for-production",
        SESSION_COOKIE_SECURE: "false",
        RATE_LIMIT_STORAGE_URI: "memory://",
      },
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 4173 --strictPort",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        E2E_API_PROXY_TARGET: "http://127.0.0.1:8001",
      },
    },
  ],
});
