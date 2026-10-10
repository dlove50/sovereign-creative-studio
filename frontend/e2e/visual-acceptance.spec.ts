import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

import { MOTION_STORAGE_KEY } from "../src/lib/motion-preference";

const viewports = [
  { name: "mobile", width: 375, height: 812 },
  { name: "tablet-portrait", width: 768, height: 1024 },
  { name: "tablet-landscape", width: 1024, height: 768 },
  { name: "desktop", width: 1440, height: 1000 },
] as const;

const screenshotDirectory = path.resolve(process.cwd(), "test-results", "acceptance-screenshots");

async function mockStudio(page: Page) {
  await page.addInitScript(
    ({ key }) => localStorage.setItem(key, "off"),
    { key: MOTION_STORAGE_KEY },
  );
  await page.route("**/api/**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: "[]",
  }));
  await page.route("**/api/auth/me", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ name: "Studio Owner", role: "owner_admin", credits: 120 }),
  }));
}

async function assertPageContract(page: Page, heading: string | RegExp) {
  await expect(page.locator("html")).toHaveAttribute("data-motion", /on|off/, { timeout: 5_000 });
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible({ timeout: 5_000 });
  expect(await page.getByRole("heading", { level: 1 }).count()).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    await page.evaluate(() => document.documentElement.clientWidth),
  );

  const firstInteractive = page.locator("main a:visible, main button:visible, main input:visible, main textarea:visible").first();
  if (await firstInteractive.count()) {
    await firstInteractive.focus();
    await expect(firstInteractive).toBeFocused();
    const box = await firstInteractive.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x + box!.width).toBeLessThanOrEqual(await page.evaluate(() => window.innerWidth));
    expect(box!.y + Math.min(box!.height, 1)).toBeGreaterThanOrEqual(0);
  }
}

test.describe("responsive and visual acceptance", () => {
  test.beforeAll(async () => {
    await mkdir(screenshotDirectory, { recursive: true });
  });

  for (const viewport of viewports) {
    test(`${viewport.name} preserves home, library, and workflow layout`, async ({ browser }) => {
      const page = await browser.newPage({ viewport });
      const consoleErrors: string[] = [];
      page.on("console", (message) => {
        if (message.type() === "error") consoleErrors.push(message.text());
      });
      await mockStudio(page);

      const surfaces = [
        { path: "/", heading: /^Welcome(?: back)?/, name: "home" },
        { path: "/projects", heading: "Projects", name: "library" },
        { path: "/video-agent", heading: "What do you want to create?", name: "workflow" },
      ] as const;

      for (const surface of surfaces) {
        await page.goto(surface.path, { waitUntil: "domcontentloaded", timeout: 15_000 });
        await assertPageContract(page, surface.heading);
        await page.screenshot({
          path: path.join(screenshotDirectory, `${surface.name}-${viewport.name}.png`),
          fullPage: true,
        });
      }

      expect(consoleErrors.filter((message) => !message.includes("favicon"))).toEqual([]);
      await page.close();
    });
  }

  test("desktop shell remains stable with the account menu open", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await mockStudio(page);
    await page.goto("/projects", { waitUntil: "domcontentloaded", timeout: 15_000 });
    await expect(page.getByLabel("Credits")).toContainText("120", { timeout: 5_000 });
    const account = page.getByRole("button", { name: "Account menu" });
    await account.focus();
    await account.press("Enter");
    await expect(page.getByRole("radiogroup", { name: "Motion" })).toBeVisible({ timeout: 5_000 });
    await page.screenshot({ path: path.join(screenshotDirectory, "shell-desktop.png"), fullPage: true });
  });
});
