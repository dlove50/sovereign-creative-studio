import { expect, test } from "@playwright/test";

test.describe("shared UI contract", () => {
  test("controls expose professional sizing, focus, disabled, and surface styling", async ({ page }) => {
    await page.route("**/api/**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "{}" }),
    );
    await page.goto("/chain", { waitUntil: "domcontentloaded", timeout: 15_000 });

    const textarea = page.getByLabel("What should the image look like?");
    const submit = page.getByRole("button", { name: "Generate Image" });
    await expect(textarea).toBeVisible({ timeout: 5_000 });

    for (const control of [textarea, submit]) {
      const box = await control.boundingBox();
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    }

    await textarea.focus();
    await expect(textarea).toBeFocused();
    expect(await textarea.evaluate((node) => getComputedStyle(node).boxShadow)).not.toBe("none");
    expect(await textarea.evaluate((node) => parseFloat(getComputedStyle(node).borderRadius))).toBeGreaterThanOrEqual(10);

    await expect(submit).toBeDisabled();
    expect(await submit.evaluate((node) => Number(getComputedStyle(node).opacity))).toBeLessThan(1);

    const tokens = await page.locator("html").evaluate((node) => {
      const styles = getComputedStyle(node);
      return ["--surface-subdued", "--surface-raised", "--shadow-card", "--content-wide", "--motion-fast"]
        .map((name) => styles.getPropertyValue(name).trim());
    });
    expect(tokens.every(Boolean)).toBe(true);

    await page.unroute("**/api/**");
    await page.route("**/api/**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
    );
    await page.goto("/assets-library", { waitUntil: "domcontentloaded", timeout: 15_000 });
    const input = page.getByPlaceholder("Search prompt, filename, project, type");
    await expect(input).toBeVisible({ timeout: 5_000 });
    await expect(input).toHaveAttribute("data-ui", "input");
    expect((await input.boundingBox())?.height ?? 0).toBeGreaterThan(43.9);
  });

  test("load failures use assertive error semantics instead of an empty state", async ({ page }) => {
    await page.route("**/api/**", (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Studio unavailable" }) }),
    );
    await page.goto("/gallery", { waitUntil: "domcontentloaded", timeout: 15_000 });

    const alert = page.getByRole("alert").filter({ hasText: "Couldn't load your gallery" });
    await expect(alert).toBeVisible({ timeout: 5_000 });
    await expect(alert).toContainText("Couldn't load your gallery");
    await expect(alert.getByRole("button", { name: "Try again" })).toHaveCSS("min-height", "44px");

    await page.goto("/assets-library", { waitUntil: "domcontentloaded", timeout: 15_000 });
    const card = page.locator('[data-ui="card"]');
    await expect(card).toBeVisible({ timeout: 5_000 });
    expect(await card.evaluate((node) => parseFloat(getComputedStyle(node).borderRadius))).toBeGreaterThanOrEqual(10);
    expect(await card.evaluate((node) => getComputedStyle(node).boxShadow)).not.toBe("none");
  });
});
