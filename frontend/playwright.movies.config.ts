import { defineConfig } from "@playwright/test";

// All API requests are intercepted by fixtures; no production database or GPU is used.
// Run `npm run build` first, then `npx playwright test -c playwright.movies.config.ts`.
export default defineConfig({
  testDir: "./e2e",
  testMatch: "movie-editor.spec.ts",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  workers: 1,
  use: { headless: true, screenshot: "only-on-failure" },
  webServer: {
    command: "npm run start -- --hostname 127.0.0.1 --port 3011",
    url: "http://127.0.0.1:3011/projects",
    reuseExistingServer: false,
  },
});
