import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.CLIENTOPS_E2E_BASE_URL ?? "http://127.0.0.1:8080";

export default defineConfig({
  testDir: ".",
  outputDir: "../test-results",
  reporter: [
    ["line"],
    ["html", { outputFolder: "../playwright-report", open: "never" }],
  ],
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  forbidOnly: true,
  retries: 0,
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ignoreHTTPSErrors: baseURL.startsWith("https://"),
  },
  projects: [
    {
      name: "chromium-390",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
      },
    },
    {
      name: "chromium-768",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 768, height: 1024 },
      },
    },
    {
      name: "chromium-1024",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1024, height: 768 },
      },
    },
    {
      name: "chromium-1440",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: "firefox-1440",
      use: {
        ...devices["Desktop Firefox"],
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: "webkit-390",
      use: {
        ...devices["Desktop Safari"],
        viewport: { width: 390, height: 844 },
      },
    },
  ],
});
