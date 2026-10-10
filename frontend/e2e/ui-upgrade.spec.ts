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

  });

  test("shared inputs retain the same sizing and styling on library screens", async ({ page }) => {
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

test.describe("application shell", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
    );
    await page.route("**/api/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ name: "Studio Owner", role: "owner_admin", credits: 120 }),
      }),
    );
  });

  test("desktop rail and account menu are keyboard-safe and expose all motion modes", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/projects", { waitUntil: "domcontentloaded", timeout: 15_000 });
    await expect(page.locator("html")).toHaveAttribute("data-motion", /on|off/, { timeout: 5_000 });

    const mainNav = page.getByRole("navigation", { name: "Main" });
    await expect(mainNav.getByRole("link", { name: "Projects" })).toHaveAttribute("aria-current", "page");

    const create = page.getByRole("button", { name: "Create" });
    await create.focus();
    await expect(create).toBeFocused();
    await create.press("Enter");
    await expect(create).toHaveAttribute("aria-expanded", "true", { timeout: 5_000 });
    await expect(page.getByRole("navigation", { name: "Create" })).toBeVisible({ timeout: 5_000 });
    await page.keyboard.press("Escape");
    await expect(page.getByRole("navigation", { name: "Create" })).toBeHidden({ timeout: 5_000 });

    const account = page.getByRole("button", { name: "Account menu" });
    expect((await account.boundingBox())?.height ?? 0).toBeGreaterThan(43.9);
    await account.click();
    const motion = page.getByRole("radiogroup", { name: "Motion" });
    await expect(motion).toBeVisible({ timeout: 5_000 });

    await motion.getByRole("radio", { name: "Always on" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-motion", "on");
    await motion.getByRole("radio", { name: "Off", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-motion", "off");
    await motion.getByRole("radio", { name: "Follow system" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-motion", "off");

    await page.keyboard.press("Escape");
    await expect(motion).toBeHidden({ timeout: 5_000 });
    await expect(account).toBeFocused();

    await account.click();
    await page.locator("main").click({ position: { x: 10, y: 10 } });
    await expect(motion).toBeHidden({ timeout: 5_000 });
  });

  test("mobile navigation has 44px targets, traps focus, and closes with Escape", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/projects", { waitUntil: "domcontentloaded", timeout: 15_000 });
    await expect(page.locator("html")).toHaveAttribute("data-motion", /on|off/, { timeout: 5_000 });

    const trigger = page.getByRole("button", { name: "Open navigation" });
    expect((await trigger.boundingBox())?.height ?? 0).toBeGreaterThan(43.9);
    await trigger.click();

    const dialog = page.getByRole("dialog", { name: "Studio navigation" });
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    const projects = dialog.getByRole("link", { name: "My Projects", exact: true });
    await expect(projects).toHaveAttribute("aria-current", "page");
    await expect(projects).toHaveCSS("min-height", "44px");

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden({ timeout: 5_000 });
    await expect(trigger).toBeFocused();
  });
});

test.describe("home experience", () => {
  const readiness = {
    ffmpeg: true,
    piper: true,
    ready: true,
    detail: "ready",
    piper_detail: "ready",
    default_voice: null,
    voices: [],
  };

  async function routeHome(page: import("@playwright/test").Page, state: {
    name?: string;
    avatars?: unknown[];
    voices?: unknown[];
    jobs?: unknown[];
    failAvatars?: boolean;
    delaySetup?: boolean;
  } = {}) {
    const respond = async (route: import("@playwright/test").Route, body: unknown, fail = false) => {
      if (state.delaySetup) await new Promise((resolve) => setTimeout(resolve, 2_500));
      await route.fulfill({
        status: fail ? 503 : 200,
        contentType: "application/json",
        body: JSON.stringify(fail ? { detail: "Avatar service unavailable" } : body),
      });
    };
    await page.route("**/api/auth/me", (route) => respond(route, { name: state.name ?? "Studio Owner", role: "owner_admin", credits: 120 }));
    await page.route("**/api/avatars", (route) => respond(route, state.avatars ?? [], state.failAvatars));
    await page.route("**/api/audio-merge/readiness", (route) => respond(route, { ...readiness, voices: state.voices ?? [] }));
    await page.route("**/api/avatar-jobs", (route) => respond(route, state.jobs ?? []));
    await page.route("**/api/director/templates", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        credits_per_clip: 20,
        templates: [{ id: "promo-video", label: "Promo video", tagline: "Launch with clarity", image: "/missing-template.jpg", badge: "Popular" }],
      }),
    }));
  }

  test("shows an honest loading state before setup data resolves", async ({ page }) => {
    await routeHome(page, { delaySetup: true });
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 15_000 });
    await expect(page.getByRole("status", { name: "Loading setup" })).toBeVisible({ timeout: 1_000 });
  });

  test("shows a partial failure instead of false zero progress", async ({ page }) => {
    await routeHome(page, { failAvatars: true });
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 15_000 });
    const alert = page.getByRole("alert").filter({ hasText: "Couldn't load your setup progress" });
    await expect(alert).toBeVisible({ timeout: 5_000 });
    await expect(page.getByRole("progressbar", { name: "Setup progress" })).toHaveCount(0);
  });

  test("zero progress and long names preserve hierarchy, one primary action, and mobile width", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await routeHome(page, { name: "AveryExtraordinarilyLongUnbrokenStudioOwnerName" });
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 15_000 });

    await expect(page.getByRole("progressbar", { name: "Setup progress" })).toHaveAttribute("aria-valuenow", "0");
    await expect(page.locator('[data-primary-action="true"]')).toHaveCount(1);
    await expect(page.locator('[data-primary-action="true"]')).toHaveAttribute("href", "/avatars/new");
    await page.locator('[data-primary-action="true"]').focus();
    await expect(page.locator('[data-primary-action="true"]')).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  });

  test("completed setup presents one professional next action", async ({ page }) => {
    await routeHome(page, {
      avatars: [
        { id: "a1", group_id: null, default_voice_id: "vibevoice:owner", name: "Owner" },
        { id: "a2", group_id: "looks", name: "Studio look" },
      ],
      voices: [{ id: "vibevoice:owner", label: "Owner (VibeVoice clone)", language: "en", quality: "clone", is_default: true, ready: true }],
      jobs: [{ id: "j1", status: "completed", created_at: "2026-10-10T10:00:00Z" }],
    });
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 15_000 });

    await expect(page.getByRole("progressbar", { name: "Setup progress" })).toHaveAttribute("aria-valuenow", "100");
    await expect(page.getByText("Setup complete", { exact: true })).toBeVisible();
    await expect(page.locator('[data-primary-action="true"]')).toHaveCount(1);
    await expect(page.locator('[data-primary-action="true"]')).toHaveAttribute("href", "/video-agent");
  });
});

test.describe("primary workflow matrix", () => {
  const routes = [
    { path: "/gallery", heading: "Gallery", action: "Try again", role: "button" as const },
    { path: "/projects", heading: "Projects", action: "Make your first video", role: "link" as const },
    { path: "/avatars", heading: "Avatars", action: "New avatar", role: "link" as const },
    { path: "/apps", heading: "App library", action: "AI video generator", role: "link" as const },
    { path: "/video-agent", heading: "What do you want to create?", action: "Submit", role: "button" as const },
    { path: "/music-lab", heading: "Music Lab", action: "Create", role: "tab" as const },
    { path: "/credits", heading: "Credits", action: "Try again", role: "button" as const },
    { path: "/admin", heading: "Admin Dashboard", action: "Try again", role: "button" as const },
    { path: "/status", heading: "Status", action: "Refresh", role: "button" as const },
  ];

  test("high-traffic routes preserve hierarchy, actions, focus, and mobile width", async ({ browser }) => {
    for (const routeCase of routes) {
      const page = await browser.newPage({ viewport: { width: 375, height: 812 } });
      await page.route("**/api/**", (route) => route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Deliberately unavailable for UI-state verification" }),
      }));
      await page.route("**/api/auth/me", (route) => route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ name: "Owner", role: "owner_admin", credits: 120 }),
      }));

      await page.goto(routeCase.path, { waitUntil: "domcontentloaded", timeout: 15_000 });
      await expect(page.locator("html")).toHaveAttribute("data-motion", /on|off/, { timeout: 5_000 });
      await expect(page.getByRole("heading", { level: 1, name: routeCase.heading })).toBeVisible({ timeout: 5_000 });
      const action = page.getByRole(routeCase.role, { name: routeCase.action }).first();
      await expect(action).toBeVisible({ timeout: 5_000 });
      const focusTarget = routeCase.path === "/video-agent" ? page.getByLabel("Describe your video") : action;
      await focusTarget.focus();
      await expect(focusTarget).toBeFocused({ timeout: 2_000 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
      await page.close();
    }
  });

  test("avatar loading and project empty states remain explicit", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.route("**/api/auth/me", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ name: "Owner", role: "owner_admin", credits: 120 }),
    }));
    await page.route("**/api/avatars", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 2_000));
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    });
    await page.goto("/avatars", { waitUntil: "domcontentloaded", timeout: 15_000 });
    await expect(page.getByRole("status", { name: "Loading" })).toBeVisible({ timeout: 1_000 });

    await page.unroute("**/api/avatars");
    await page.route("**/api/**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
    await page.route("**/api/projects", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ id: "project-long", name: "An exceptionally long documentary production folder name that must remain contained" }]),
    }));
    await page.goto("/projects", { waitUntil: "domcontentloaded", timeout: 15_000 });
    await expect(page.getByText("No videos yet", { exact: true })).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("An exceptionally long documentary production folder name that must remain contained", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  });
});
