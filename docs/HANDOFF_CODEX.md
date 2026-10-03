# Handoff: HeyGen-style rebuild of Sovereign Creative Studio (Claude → Codex)

Last updated: 2026-10-02 · Branch `master` · Backend baseline `fbc1107`

## Resume checkpoint — stage 5b completed, 2026-10-02

Stage 5b is implemented. Continue from the local commit titled
`feat: finish scene-by-scene movie editor`; do not recreate this work.

Completed:
- `/movies/new` creates one draft and redirects to `/movies/[id]`.
- Desktop Create and mobile navigation now open the movie editor.
- Projects includes searchable/filterable movie cards, draft badges, and editor links.
- Editor supports title/orientation, scene selection/add/delete, avatar looks, voices,
  scripts, Improve delivery, autosave, Generate, polling, playback, and download.
- Saves are serialized and Generate waits for the latest save. Failed saves can be retried.
- Delayed Improve delivery responses preserve newer edits and target the original scene.
- Rendering locks editing; mobile layout fits a 390px viewport.

Validation from this session:
- Backend: **498 passed** with an isolated temporary database (66.67 seconds).
- Frontend: `npx tsc --noEmit` passed; production build passed.
- Browser: **5 Playwright tests passed**, covering create/edit/reload/Projects,
  overlapping saves and rendering, delayed Improve delivery, failed-save retry,
  and desktop/mobile layout. API responses are mocked; no test movies are created
  in the production database. Screenshots were visually inspected.
- Re-run browser tests after `npm run build` with
  `npx playwright test -c playwright.movies.config.ts` from `frontend/`.
- Mechanical UI detector returned no findings. Existing charcoal/cyan styling was
  preserved; no new visual system or design-token changes were introduced.
- Running frontend rebuilt and restarted through the launcher. The old backend was
  restarted after confirming an empty ComfyUI queue; migration 0025 -> 0026 applied.
  The live frontend's `/api/movies` proxy returned HTTP 200 and Projects loaded.

Remaining validation limitation: a real GPU movie render and real Qwen delivery
improvement were not performed in this session. The browser tests simulate those
responses; they do not establish voice/lip-sync quality or real render completion.
A real multi-scene render is the next integration check before calling the entire
movie pipeline end-to-end verified. Future app features below remain unimplemented.

## Goal

The owner wants Sovereign to work and look like HeyGen (the AI avatar video app): same
layout, flow and feature set, but **local-first** on this Windows PC and with
Sovereign's own name, images and wording. Do **not** copy HeyGen's logo, name, photos
or exact copy text. Layout, structure and flow are fine to mirror.

## Ground rules (from the owner — follow them)

- **Never push to GitHub. Commit locally only.** Never commit personal info.
- **Windows 11 is the target.** No Linux changes unless the owner says
  "Let's fix the Linux system". (A Linux box with a Radeon R9700 32 GB and ComfyUI exists;
  offloading renders to it is a future task, not started.)
- Local-first: no cloud services by default.
- Ritual per change: implement → `backend/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`
  (from `backend/`) → `npx tsc --noEmit` (from `frontend/`) → rebuild → verify in a browser → commit.
- Ask before large downloads, deleting user data, or anything irreversible.

## Run it

```
python tools/local_launcher.py start     # ComfyUI :8001, backend :8002, frontend :3000
python tools/local_launcher.py stop
python tools/local_launcher.py clean     # rebuilds the frontend; does NOT restart the backend
```
After backend changes: `stop` then `start` (migrations run on startup).
Also needed: **Ollama** (`C:\Users\David\AppData\Local\Programs\Ollama\ollama app.exe`) for
scripts, and **VibeVoice Studio** on :8010 (desktop shortcut) for cloned voices.

## Earlier completed stages (prior agent's verification record)

| Stage | What | Key files |
|---|---|---|
| Voice | VibeVoice cloned voices (`vibevoice:<name>`); Whisper check re-renders bad takes (match < 0.75); GPU hand-off ComfyUI ↔ VibeVoice | `backend/app/services/voice.py` |
| Looks engine | Qwen Image Edit 2509 workflow fixed (official Plus template) | `backend/workflows/image_edit_qwen_2509.json` |
| Long videos | Chained InfiniteTalk chunks (81 frames, 9 overlap) + FFmpeg join; lightx2v LoRA; presets `portrait_480p` / `landscape_480p` | `backend/app/services/avatar_comfyui.py`, `avatar_presets.py` |
| 1 Shell + Home | Icon rail + Create fly-out, charcoal/cyan tokens, Welcome with live 4-step setup, App library | `frontend/src/components/shell/app-rail.tsx`, `home/welcome-view.tsx`, `apps/apps-library-view.tsx` |
| 2 Avatars | Gallery, avatar page, Edit look window, Look studio (15 templates, Look Packs, custom packs); looks grouped (`group_id`, migration 0025) | `frontend/src/components/avatars/*`, `frontend/src/lib/look-templates.ts`, `look-queue.ts` |
| 3 Video agent | Prompt → Qwen script (`qwen3.8:27b`, `VIDEO_AGENT_MODEL`) → voice → avatar; review or auto-pilot | `backend/app/services/video_agent.py`, `frontend/src/components/video-agent/video-agent-view.tsx` |
| 4 Projects | Search/sort/filter, folders (= projects), video grid, player, Move to trash (recoverable) | `frontend/src/components/projects/projects-library-view.tsx` |
| 5a Movies backend | `movies` table (0026), `/api/movies` CRUD, `/render`, `/improve-delivery`, worker renders scenes then joins | `backend/app/services/movies.py`, `backend/app/routers/movies.py` |

Tests: **498 passed, 0 failed** at `fbc1107`, rerun successfully during stage 5b.

## Stage 5b — implemented frontend contract

Route `/movies/[id]` (+ `/movies/new` that POSTs and redirects). Point the Create
fly-out "Scene by scene" (`frontend/src/lib/navigation.ts`, `CREATE_NAV`) at `/movies/new`,
and show movies in Projects with a **Draft** badge (`status === "draft"`).

API contract (already built and tested):
- `POST /api/movies` `{title?, orientation?: "portrait"|"landscape", scenes?: Scene[]}` → Movie
- `GET /api/movies`, `GET/PUT/DELETE /api/movies/{id}` (PUT 409 while rendering)
- `POST /api/movies/{id}/render` → 400 (no script / missing look), 402 (credits), 409 (already rendering)
- `POST /api/movies/improve-delivery` `{script}` → `{title, script, ...}` (~75 s, local Qwen)
- Movie: `{id, title, orientation, scenes, status: draft|rendering|completed|failed, output_video_path, error_message, credits_estimate}`
- Scene: `{id, avatar_id, tts_voice_id, script, status: draft|voice|video|completed|failed, error?}`

Editor layout (mirrors HeyGen AI Studio): top bar with title input, Portrait/Landscape
toggle, Generate button (shows credits estimate). Left: numbered scene list + "Add
scene". Centre: selected scene's look in the chosen aspect frame. Right: look picker
(photo avatars incl. looks), voice picker (`api.getAudioMergeReadiness().voices`), script
textarea with word count / seconds (2.5 words/s) and **Improve delivery**. Autosave via
PUT (debounced). While rendering, poll `GET` every 4 s and show per-scene status; on
completion show the player + download. Reuse styles from the existing views.

## After that: "Coming next" apps (listed in the App library)

Speech cleanup (Whisper word timestamps → cut pauses/fillers with FFmpeg), Auto clips,
Video podcast (InfiniteTalk `two_speakers` mode), Translate (Whisper → Qwen → voice →
re-lip-sync; VibeVoice is mainly English/Chinese), Slides to video (OCR studio exists),
Batch videos, Interactive video. Optional: MiniMax H3 (open-weights video+audio, ComfyUI
native; licence excludes US/EU/UK/KR, not Canada) for cinematic B-roll.

## Gotchas that cost time

- **One 16 GB GPU is shared.** VibeVoice must unload after use (`/api/models/unload`
  needs `torch._C._cuda_clearCublasWorkspaces()`); ComfyUI is freed via `POST /free`;
  Ollama calls use `keep_alive: 0`.
- **ComfyUI history lists loader previews** (`type: "input"`) before real outputs.
  `_find_video` must only take `type: "output"` (this bug once repeated chunk 0).
- **Lip-sync check that works:** a "pop once per second" audio test, measuring mouth
  peaks vs sound peaks per chunk. Muted-window checks were too coarse.
- **Next.js proxy** times out at 30 s by default; `next.config.mjs` sets `proxyTimeout` to 30 min.
- **Tests must never touch the real DB.** `tests/conftest.py` sets `DATABASE_URL`/`STORAGE_DIR`
  to a temp dir and pins env values that the real `.env` overrides. Keep it that way.
- **Local family mode:** unauthenticated requests act as the owner by design.
- Each new Alembic migration needs the head assertion in `tests/test_migrations.py` bumped.
- `local_launcher.py clean` does not restart the backend.

## Open questions for the owner

- Clean-up of test data written to the real DB on Aug 6 and Sep 27 (fake avatars, voices,
  jobs, test users): remove only the Sep 27 rows, also the Aug 6 test users, or leave it.
- Whether to start the R9700 render-offload work ("Let's fix the Linux system").

---

# Update — latest status (Claude Code, 2026-10-02 late evening)

Read this section first; it supersedes the "Next" sections above. Also read
`docs/HANDOFF_CLAUDE_CODE.md` (Codex's stage 5b notes). Commit locally only, never push.

## Since the earlier handoff

| Commit | What |
|---|---|
| `5c3dd80` (Codex) | Stage 5b: movie editor at `/movies/[id]`, `/movies/new`, Projects integration, 5 mocked Playwright tests |
| `b534c4b` | **MiniMax H3 video provider** `local_h3` (see below) |
| `580c1d3` | **Speech cleanup** app: `/speech-cleanup`, `POST /api/speech-cleanup`, 7 tests |

Backend tests: **511 + 7 = 518 expected passing** (run from `backend/`).

## MiniMax H3 (owner explicitly asked to download and wire it)

- ComfyUI 0.37.0 already has native H3 nodes (`comfy_extras/nodes_minimax_h3.py`); torch is 2.10+cu130,
  so the README-recommended `int8_convrot` weights apply. Licence: MiniMax H3 Community License
  (excludes US/EU/UK/KR, Canada OK, commercial < US$20M) — owner is in Canada.
- **Download:** `tools/download_minimax_h3.sh` (resumable; re-run to continue). ~70 GB from
  `Comfy-Org/MiniMax-H3` into `C:\Users\David\ComfyUI-Shared\models\{vae,loras,text_encoders,diffusion_models,model_patches,embeddings}`.
  Log: `C:\Users\David\ComfyUI-Shared\minimax_h3_download.log` (`ALL DONE` on the last line when finished).
  Speed ≈ 5 MB/s unauthenticated (≈ 3.5–4 h). If it is not running: `bash tools/download_minimax_h3.sh`.
  Order: embeddings, audio VAE, video VAE fp16, fl2v turbo 4-step LoRA, NVFP4 Qwen3-VL text encoder,
  fl2va pruned int8 model, ControlNet union, ref2v LoRA, ref2va pruned int8 model, fl2v 8-step LoRA.
- **Code:** `backend/app/video_generators/minimax_h3.py` (`build_h3_workflow`, 24 fps, 17k+5 frame grid,
  turbo 4 steps default, `quality_preset="h3_full"` = 20 steps), settings `H3_*` in `config.py`,
  readiness `_h3_ready()` in `routers/videos.py` (lists exactly which files ComfyUI still lacks),
  provider option in `videos-view.tsx`. Cost `CREDITS_PER_H3_VIDEO=20`.
- **Not yet verified on the GPU** (files were still downloading). Once the log says `ALL DONE`:
  restart ComfyUI so it lists the new files, confirm `GET /api/videos/modes` shows `local_h3` available,
  then generate one 2-second text→video and one image→video clip from Video Generator → provider
  "MiniMax H3". Expect heavy RAM offload (21 GB model on a 16 GB GPU, 31 GB system RAM); if it OOMs,
  lower `H3_LONG_SIDE/H3_SHORT_SIDE` (832/480) or try `minimax_h3_fl2va_pruned_w6a8` (16 GB) via `H3_UNET_NAME`.
  Do not run H3 while a movie/avatar render is active (single 16 GB GPU).
- Not built yet: reference-to-video (`ref2va`, `MiniMaxH3ReferenceToVideo` node), ControlNet union
  (`MiniMaxH3FunControlNetApply`), effect embeddings in the UI, first+last-frame mode in the UI,
  H3 entry in Model Manager. The files for these are in the download list.

## Real two-scene movie validation (stage 5b follow-up) — DONE, PASSED

Movie `2957e96025ec45ada9e17057bc940f78` ("Validation movie: two scenes", user `UI Test`), created via
Create → Scene by scene. Verified with real GPU/Qwen/Piper:
- Title, portrait orientation, two scenes with different looks and voices autosaved and survived a reload.
- **Improve delivery** (real Qwen 27B) rewrote scene 1 only; scene 2 was untouched.
- **Generate** (34 credits): both scenes rendered in sequence (~300 s and ~309 s) and were joined.
  Output `/storage/avatar_videos/movie_2957e960..._c15fa9c4.mp4`: 480x832, 9.64 s video / 9.71 s audio
  (0.07 s apart), scene 1 (porch look) then scene 2 (beach-house look), mouths moving in both.
- Limits: per-scene lip-sync was not separately measured with the pop test; landscape orientation and
  3+ scenes were not rendered; a 15 s movie takes roughly 13 min of GPU time.
- ComfyUI had died at 22:26 (before this test) while another script loaded the 15.6 GB model; restarted via the launcher.

## Backend restart needed

Services were restarted after the movie validation, so the backend already runs the H3 and Speech cleanup
code (`GET /api/videos/modes` shows `local_h3` with a missing-files note until the download finishes).
After ANY later backend change: `stop` then `start --hidden` (only when no job is rendering), and `clean` for the frontend.

## Remaining App-library backlog (listed as "Coming next")

Auto clips, Video podcast (InfiniteTalk `two_speakers` mode), Translate video, Slides to video,
Interactive video. (**Batch videos is built**: `/batch`, `POST /api/movies/batch`, CSV upload, all-or-nothing credit
check; verified creating 3 drafts in the browser; "Create and render all" not run on the GPU.) Not buildable locally at HeyGen scale: LiveAvatar real-time, 175-language translation.
