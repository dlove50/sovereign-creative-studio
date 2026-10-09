import { test, expect as slowExpect, type Page } from "@playwright/test";

// The project config allows 4 minutes per assertion (GPU work). These tests never wait on a GPU.
const expect = slowExpect.configure({ timeout: 15_000 });

// Regression tests for the UI phase 1 fixes. They use mocked API replies (no GPU, no credits) except the
// Music Lab and Quick Chain tests, which only read from the running backend. Served by: next start -p 3011.
const base = "http://127.0.0.1:3011";

async function api(page: Page, handler: (path: string, method: string) => { status?: number; json: unknown } | null) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const reply = url.pathname === "/api/auth/me" ? { json: { name: "Creator", role: "owner_admin", credits: 1000 } } : handler(url.pathname, route.request().method());
    if (reply) await route.fulfill({ status: reply.status ?? 200, json: reply.json });
    else await route.fulfill({ json: [] });
  });
}

test("a FastAPI validation error is shown as readable text, not [object Object]", async ({ page }) => {
  await api(page, (path) =>
    path === "/api/me"
      ? { status: 422, json: { detail: [{ loc: ["body", "amount"], msg: "must be at least 1", type: "value_error" }] } }
      : null,
  );
  await page.goto(`${base}/credits`);
  const alert = page.locator("[role=alert]:not(#__next-route-announcer__)");
  await expect(alert).toContainText("Couldn't load your credits");
  await expect(alert).toContainText("amount: must be at least 1");
  await expect(alert).not.toContainText("[object Object]");
});

test("a failed credits load offers Try again and does not claim a zero balance", async ({ page }) => {
  let healthy = false;
  await api(page, (path) => {
    if (path === "/api/me") return healthy ? { json: { name: "Creator", role: "owner_admin", credits: 42 } } : { status: 500, json: { detail: "Database is busy" } };
    return null;
  });
  await page.goto(`${base}/credits`);
  await expect(page.locator("[role=alert]:not(#__next-route-announcer__)")).toContainText("Database is busy");
  await expect(page.getByText("credits available")).toHaveCount(0);
  healthy = true;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText("42")).toBeVisible();
});

test("a failed gallery load is an error, not 'No pictures or videos yet'", async ({ page }) => {
  await api(page, (path) => (path.startsWith("/api/generations") ? { status: 503, json: { detail: "Studio unavailable" } } : null));
  await page.goto(`${base}/gallery`);
  await expect(page.locator("[role=alert]:not(#__next-route-announcer__)")).toContainText("Couldn't load your gallery");
  await expect(page.getByText("No pictures or videos yet")).toHaveCount(0);
});

test("Quick Chain does not restore a step that was running when the page closed", async ({ page }) => {
  // Real (read-only) backend: the page needs its real status replies, a blanket mock crashes it.
  await page.addInitScript(() => {
    sessionStorage.setItem("scs_quick_chain", JSON.stringify({ current: "image", running: "image", runningPreview: true }));
  });
  await page.goto(`${base}/chain`);
  const prompt = page.locator("#chain-image-prompt");
  await expect(prompt).toBeEnabled(); // it is disabled while a step is "running"
  await prompt.fill("a red bicycle");
  await expect(page.getByRole("button", { name: /generate image/i })).toBeEnabled();
});

test("Director: only a real 404 says 'not found'; a server error retries instead", async ({ page }) => {
  await api(page, (path) => (path === "/api/director/projects/gone" ? { status: 404, json: { detail: "Not found" } } : path === "/api/director/projects/flaky" ? { status: 500, json: { detail: "Hiccup" } } : null));
  await page.goto(`${base}/director/watch?id=gone`);
  await expect(page.getByText("That video was not found")).toBeVisible();
  await page.goto(`${base}/director/watch?id=flaky`);
  await expect(page.getByText("Couldn't load this video")).toBeVisible();
  await expect(page.getByText("That video was not found")).toHaveCount(0);
});

test("Music Lab keeps what you typed when you switch tabs", async ({ page }) => {
  await page.goto(`${base}/music-lab`);
  await page.getByRole("tab", { name: "Describe it" }).click();
  const idea = page.getByPlaceholder(/reggae song about a sunrise/i);
  await idea.fill("A calm piano piece for studying");
  await page.getByRole("tab", { name: /^Library/ }).click();
  await expect(idea).toBeHidden();
  await page.getByRole("tab", { name: /^Create/ }).click();
  await expect(idea).toHaveValue("A calm piano piece for studying");
});
