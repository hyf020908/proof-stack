import { defineConfig, devices } from "@playwright/test";

const systemChrome = process.env.PROOFSTACK_E2E_SYSTEM_CHROME === "true";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], channel: systemChrome ? "chrome" : undefined },
    },
  ],
  webServer: {
    command: "pnpm build && pnpm preview",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
