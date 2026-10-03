# Claude Code handoff — Sovereign Creative Studio

Prepared 2026-10-02, Codex → Claude Code.

## Start here

Continue the HeyGen-style, local-first Sovereign Creative Studio rebuild.
Stage 5b is implemented and committed. The immediate next task is a real two-scene
movie integration test, fixing any issues it exposes. Do not recreate the editor.
Read repository instructions and `docs/HANDOFF_CODEX.md` for earlier project context.
Inspect Git status before making changes; preserve existing work.

## Current Git state

- Branch: `master`.
- Latest implementation commit: `5c3dd80` — `feat: finish scene-by-scene movie editor`.
- Movie backend baseline: `fbc1107`.
- Earlier handoff commit: `b84a887`.
- At handoff inspection, no tracked changes; untracked `work/` contains Codex helper
  scripts and backend logs. Do not commit those logs or treat them as product code.
- This new handoff may itself appear untracked; it was created after that inspection.
- Commit locally only. **Never push to GitHub.**

## Product and constraints

Build a Windows 11, local-first avatar/video studio with HeyGen-like organization
and flows, using Sovereign's own name, images, and copy. Preserve the existing
charcoal/cyan interface. No cloud services by default. Never commit personal info.
Do not delete real user data. Ask before large downloads or irreversible actions.
Linux/render-offload work is outside current scope unless explicitly requested.

## What Codex finished in stage 5b

- `/movies/new`: creates one draft per mounted page, then redirects to `/movies/[id]`.
  Includes creation error/retry and avoids redirecting after the user leaves.
- Editor: title, portrait/landscape, scene selection/add/delete, avatar look and voice
  selectors, script editing, word/duration estimates, and Improve delivery.
- Debounced autosave with serialized writes. Generate flushes outstanding edits and
  blocks duplicate starts. Save failures retain pending edits and offer retry.
- Improve delivery targets the original scene and preserves newer script edits.
- Render polling, per-scene status/errors, edit locking, completion player/download.
- Desktop Create menu and mobile navigation link to the editor.
- Projects lists/filter/search includes movies; draft badges and editor navigation.
- Existing visual system preserved; desktop and 390px mobile screenshots inspected.

## Files to know

- `frontend/src/components/movies/movie-editor-view.tsx`
- `frontend/src/app/movies/[id]/page.tsx`
- `frontend/src/app/movies/new/page.tsx`
- `frontend/src/components/projects/projects-library-view.tsx`
- `frontend/src/components/topbar.tsx`
- `frontend/src/lib/navigation.ts`
- `frontend/src/lib/api/admin.ts`
- `frontend/src/lib/types.ts`
- `frontend/e2e/movie-editor.spec.ts`
- `frontend/playwright.movies.config.ts`
- `backend/app/routers/movies.py`
- `backend/app/services/movies.py`
- `backend/migrations/versions/0026_add_movies.py`
- `backend/tests/test_movies.py`

## Evidence from the completed Codex session

- Backend: **498 passed**, 0 failing, in 66.67 seconds, using an explicitly isolated
  temporary database and the suite's temporary storage setup.
- `npx tsc --noEmit`: passed.
- Production build: passed, including `/movies/new` and `/movies/[id]`.
- **5 Playwright tests passed**: creation/edit/reload/Projects; serialized delayed saves
  before rendering; stale Improve delivery response; failed-save retry; responsive layout.
- Browser tests intercept API responses. They do NOT verify real GPU rendering,
  real speech generation, actual movie joining, or real Qwen delivery improvement.
- Frontend rebuilt/restarted through `python tools/local_launcher.py clean --hidden`.
- Live backend initially returned 404 for movies because it predated the backend commit.
  Restarted after confirming the ComfyUI running/pending queue was empty.
- Startup applied migration **0025 → 0026**. Live frontend proxy `/api/movies` returned
  HTTP 200; Projects loaded in the browser.
- These are recorded results, not guarantees about the runtime at your next session.

## Next task: real movie integration validation

1. Check current service health and render queues. Avoid interrupting active work.
2. Use the app's Scene by scene entry point. Create a short, clearly identified
   validation draft using available authorized looks/voices; keep unrelated user data intact.
3. Use two short scenes, preferably with different looks or voices. Verify title,
   orientation, scene changes, autosave, reload, and reopening from Projects.
4. Exercise real Improve delivery once and confirm it preserves scene targeting.
5. Generate and follow both scenes through voice/video/completed. Verify joined
   output has the correct order, distinct scenes, usable audio, lip-sync, expected
   orientation, playback, and a working download.
6. Record actual movie/output IDs, timing, results, and any limitations in local
   evidence, keeping personal details out of committed documentation.
7. Fix reproduced issues; rerun appropriate checks, update handoff, commit locally.

Do not describe the whole movie pipeline as end-to-end verified until this succeeds.
Do not remove old test/user records as part of validation; cleanup is unresolved.

## Commands and runtime

From repository root:

```powershell
python tools/local_launcher.py status
python tools/local_launcher.py start --hidden
python tools/local_launcher.py clean --hidden
```

`clean` rebuilds/restarts the frontend; it does not reload an already-running backend.
Backend changes need a safe backend restart; migrations run at startup. The launcher
also has `stop`, which stops services, so check for active jobs before using it.

Services: frontend `http://localhost:3000`; backend `http://127.0.0.1:8002`;
ComfyUI port 8001; VibeVoice Studio port 8010; Ollama for local script generation.
Use the launcher to build with the correct backend proxy target.

From `backend/`, with DATABASE_URL and STORAGE_DIR verified as test-only (never real data):

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

`tests/conftest.py` uses `setdefault`: an inherited DATABASE_URL/STORAGE_DIR can
supersede its isolation. Clear unsafe inherited values or explicitly set fresh
scratch paths before testing.

From `frontend/`:

```powershell
npx tsc --noEmit
npm run build
npx playwright test -c playwright.movies.config.ts
```

The movie Playwright configuration starts its own production server on port 3011
and refuses to reuse an existing one. It uses mocked APIs and does not need the GPU.

## Implementation cautions

- Single 16 GB GPU shared among rendering, voice, and local model work.
- Preserve existing unload/free behavior for VibeVoice, ComfyUI, and Ollama.
- Movie backend renders scenes sequentially, then joins with FFmpeg. Blank-script
  scenes are excluded from rendering; the frontend must tolerate changed scene counts.
- Updates during rendering return 409; render requests may return 400, 402, or 409.
- Preserve serial autosaves and flush-before-render behavior when modifying the UI.
- Browser closure during pending saves triggers an unload warning; internal navigation
  attempts to flush pending changes. This does not guarantee delivery after network loss.
- Existing backend video extraction must select ComfyUI outputs, not loader previews.
- Alembic head tests must be updated for any future migration.
- Full GPU and Qwen validation remains outstanding; do not infer success from fixtures.

## Backlog after movie validation

The earlier handoff lists Speech cleanup, Auto clips, Video podcast, Translate,
Slides to video, Batch videos, and Interactive video. This is an unnumbered backlog,
not an approved detailed stage plan. Speech cleanup was suggested as the next feature
but has not been implemented here. Validate scope before beginning broader work.

Historical optional-model and licensing claims in older handoffs were not verified
by Codex; check official sources before relying on them.
