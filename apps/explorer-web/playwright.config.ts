import { defineConfig, devices } from "@playwright/test";

const PORT = process.env.EXPLORER_DEV_PORT ?? "5173";
const HOST = process.env.EXPLORER_DEV_HOST ?? "127.0.0.1";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.EXPLORER_BASE_URL ?? `http://${HOST}:${PORT}`,
    trace: "on-first-retry",
    viewport: { width: 1280, height: 720 },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
