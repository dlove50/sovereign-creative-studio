import { expect, test } from "@playwright/test";

import {
  MOTION_STORAGE_KEY,
  parseMotionPreference,
  resolveMotionEnabled,
  type MotionPreference,
} from "../src/lib/motion-preference";

test.describe("motion preference contract", () => {
  test("defaults missing and invalid stored values to system", () => {
    expect(parseMotionPreference(null)).toBe("system");
    expect(parseMotionPreference("")).toBe("system");
    expect(parseMotionPreference("enabled")).toBe("system");
    expect(parseMotionPreference("ON")).toBe("system");
  });

  test("accepts all three selectable states", () => {
    const states: MotionPreference[] = ["system", "on", "off"];

    for (const state of states) {
      expect(parseMotionPreference(state)).toBe(state);
    }
  });

  test("resolves system, forced-on, and forced-off correctly", () => {
    expect(resolveMotionEnabled("system", false)).toBe(true);
    expect(resolveMotionEnabled("system", true)).toBe(false);
    expect(resolveMotionEnabled("on", true)).toBe(true);
    expect(resolveMotionEnabled("off", false)).toBe(false);
  });

  test("uses a stable browser storage key and persists every state", async ({ page }) => {
    await page.route("https://motion.sovereign.test/", (route) =>
      route.fulfill({ contentType: "text/html", body: "<!doctype html><title>Motion preference</title>" }),
    );
    await page.goto("https://motion.sovereign.test/");

    for (const state of ["system", "on", "off"] satisfies MotionPreference[]) {
      await page.evaluate(
        ({ key, value }) => localStorage.setItem(key, value),
        { key: MOTION_STORAGE_KEY, value: state },
      );
      const stored = await page.evaluate((key) => localStorage.getItem(key), MOTION_STORAGE_KEY);
      expect(parseMotionPreference(stored)).toBe(state);
    }
  });
});

test.describe("motion runtime", () => {
  test.beforeEach(async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
  });

  test("forced-on motion runs even when the operating system requests reduced motion", async ({ page }) => {
    await page.addInitScript(
      ({ key }) => localStorage.setItem(key, "on"),
      { key: MOTION_STORAGE_KEY },
    );
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 15_000 });

    await expect(page.locator("html")).toHaveAttribute("data-motion", "on", { timeout: 5_000 });
    await expect(page.locator("html")).toHaveClass(/lenis/);
    await expect(page.locator(".page-enter")).toHaveCSS("animation-name", "page-in");
  });

  test("forced-off motion remains still and updates without a reload", async ({ page }) => {
    await page.addInitScript(
      ({ key }) => localStorage.setItem(key, "on"),
      { key: MOTION_STORAGE_KEY },
    );
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 15_000 });
    await expect(page.locator("html")).toHaveAttribute("data-motion", "on", { timeout: 5_000 });

    await page.evaluate(({ key }) => {
      localStorage.setItem(key, "off");
      window.dispatchEvent(new StorageEvent("storage", { key, newValue: "off" }));
    }, { key: MOTION_STORAGE_KEY });

    await expect(page.locator("html")).toHaveAttribute("data-motion", "off", { timeout: 5_000 });
    await expect(page.locator("html")).not.toHaveClass(/lenis/);
    await expect(page.locator(".page-enter")).toHaveCSS("animation-name", "none");
  });
});
