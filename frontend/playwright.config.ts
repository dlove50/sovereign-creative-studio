import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 600_000,       // 10 min total per test (image + video + upscale)
  expect: { timeout: 240_000 }, // 4 min per assertion (GPU generation time)
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
