import { test, expect, type Page } from "@playwright/test";

const base = "http://127.0.0.1:3011";
async function studio(page: Page) {
  let movie = { id: "fixture-movie", title: "Studio draft", orientation: "portrait", scenes: [{ id: "scene-1", avatar_id: "look-1", tts_voice_id: null, script: "Hello from the studio.", status: "draft" }], status: "draft", credits_estimate: 20, output_video_path: null as string | null, error_message: null, created_at: "2026-10-02T12:00:00Z", updated_at: "2026-10-02T12:00:00Z" };
  const state = { creates: 0, renders: 0, saves: [] as string[], delaySave: 0, failSave: false, improveRelease: null as (() => void) | null, complete: false };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    let body: unknown = [];
    if (path === "/api/auth/me") body = { name: "Creator", role: "owner_admin", credits: 1000 };
    else if (path === "/api/avatars") body = [{ id: "look-1", name: "Studio look", avatar_type: "photo_avatar", source_file_path: "/fixture-look.svg", thumbnail_path: "/fixture-look.svg" }];
    else if (path.includes("readiness")) body = { voices: [{ id: "voice-1", label: "Studio voice" }] };
    else if (path === "/api/movies/improve-delivery") {
      await new Promise<void>((resolve) => { state.improveRelease = resolve; });
      body = { title: "Improved", script: "Improved delivery." };
    } else if (path === "/api/movies") {
      if (method === "POST") { state.creates++; body = movie; } else body = [movie];
    } else if (path.endsWith("/render")) {
      state.renders++; movie = { ...movie, status: "rendering" }; body = movie;
    } else if (path === "/api/movies/fixture-movie") {
      if (method === "PUT") {
        if (state.failSave) { await route.fulfill({ status: 503, json: { detail: "Save unavailable" } }); return; }
        const data = route.request().postDataJSON();
        state.saves.push(data.scenes[0]?.script || "");
        if (state.delaySave) await new Promise((r) => setTimeout(r, state.delaySave));
        movie = { ...movie, ...data, status: "draft" };
      } else if (state.complete && movie.status === "rendering") movie = { ...movie, status: "completed", output_video_path: "/fixture.mp4", scenes: movie.scenes.map((s) => ({ ...s, status: "completed" })) };
      body = movie;
    }
    await route.fulfill({ json: body });
  });
  await page.route("**/fixture-look.svg", (route) => route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="500"><rect width="300" height="500" fill="#263b42"/><text x="40" y="250" fill="white">Test avatar preview</text></svg>' }));
  return state;
}

test("create once, edit scenes, persist and open draft from Projects", async ({ page }) => {
  const state = await studio(page);
  await page.goto(`${base}/movies/new`);
  await expect(page.getByLabel("Video title")).toHaveValue("Studio draft");
  expect(state.creates).toBe(1);
  await page.getByLabel("Video title").fill("Two scenes");
  await page.getByRole("button", { name: "Add scene" }).click();
  await page.getByLabel("Script", { exact: true }).fill("The second scene.");
  await page.getByRole("combobox", { name: "Voice", exact: true }).selectOption("voice-1");
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Video title")).toHaveValue("Two scenes");
  await page.getByRole("button", { name: /Scene 2/ }).click();
  await expect(page.getByLabel("Script", { exact: true })).toHaveValue("The second scene.");
  await page.getByLabel("Delete scene").click();
  // Deleting a scene now asks first (and autosave makes it permanent): cancelling keeps it, confirming removes it.
  await page.getByRole("alertdialog").getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("button", { name: /Scene 2/ })).toHaveCount(1);
  await page.getByLabel("Delete scene").click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("button", { name: /Scene 2/ })).toHaveCount(0);
  await page.getByLabel("Back to projects").click();
  await expect(page.getByText("Draft", { exact: true })).toBeVisible();
  // The project card also has a "Delete Two scenes" button, so name the one that opens the draft.
  await page.getByRole("button", { name: /^Continue editing/ }).click();
  await expect(page.getByLabel("Video title")).toHaveValue("Two scenes");
});

test("serialize delayed saves and flush newest edits before one render", async ({ page }) => {
  const state = await studio(page); state.delaySave = 1400;
  await page.goto(`${base}/movies/fixture-movie`);
  const script = page.getByLabel("Script", { exact: true });
  await script.fill("Older draft.");
  await expect.poll(() => state.saves.length).toBe(1);
  await script.fill("Latest draft.");
  await page.getByRole("button", { name: /Generate ·/ }).click();
  await expect(page.getByRole("button", { name: "Generating…", exact: true })).toBeDisabled();
  await expect.poll(() => state.renders).toBe(1);
  expect(state.saves).toEqual(["Older draft.", "Latest draft."]);
  state.complete = true;
  await expect(page.getByRole("link", { name: "Download video" })).toBeVisible({ timeout: 10000 });
  await expect(script).toHaveValue("Latest draft.");
});

test("keep edits made while Improve delivery is pending", async ({ page }) => {
  const state = await studio(page);
  await page.goto(`${base}/movies/fixture-movie`);
  await page.getByRole("button", { name: "Improve delivery", exact: true }).click();
  await expect.poll(() => Boolean(state.improveRelease)).toBe(true);
  await page.getByLabel("Script", { exact: true }).fill("Keep my newer words.");
  state.improveRelease!();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Your edits were kept");
  await expect(page.getByLabel("Script", { exact: true })).toHaveValue("Keep my newer words.");
});

test("failed save prevents rendering and supports retry", async ({ page }) => {
  const state = await studio(page); state.failSave = true;
  await page.goto(`${base}/movies/fixture-movie`);
  await page.getByLabel("Script", { exact: true }).fill("Unsaved words.");
  await page.getByRole("button", { name: /Generate ·/ }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Save unavailable");
  expect(state.renders).toBe(0);
  state.failSave = false;
  await page.getByRole("button", { name: "Save again" }).click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
});

test("desktop and mobile editor fit the viewport", async ({ page }, testInfo) => {
  await studio(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`${base}/movies/fixture-movie`);
  await expect(page.getByLabel("Script", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("Script", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("mobile.png"), fullPage: true });
});
