# Sovereign Creative Studio 2.0 — handoff (Claude Code → Codex), 2026-10-22

Written by the Claude Code session that started the upgrade. Everything below is committed on branch
`feat/sovereign-2.0-performance-engine` (12 commits on top of `amd-sync`; `git log amd-sync..HEAD`).
Read the commit messages: each one explains the why. The full session transcript is exported next to this
file (see "Transcript" at the end).

## Where things are

| What | Where |
| --- | --- |
| Repo (live copy, Linux AiServerR9700) | `/mnt/storage/Projects/sovereign-creative-studio` |
| Data (DB, media) | `/mnt/storage/Projects/sovereign-data` |
| Pre-upgrade backup (DB, media, .env, git bundle) | `/mnt/storage/Projects/sovereign-backups/2026-10-21-pre-2.0` |
| Launcher | `~/ai/launchers/sovereign.sh` (frontend :3100, backend :8012). Backend does not auto-reload. |
| Frontend build | build into `.next-staging` (`NEXT_DIST_DIR=.next-staging BACKEND_ORIGIN=http://127.0.0.1:8012 npm run build`), stop Sovereign, swap `.next` → `.next-prev`, `.next-staging` → `.next`, relaunch |
| ComfyUI | `~/ai/ComfyUI` on :8188. Models: `/mnt/storage/AI-Models/comfyui` |
| GPU Python for Demucs + enhance models | `~/ai/venvs/sovereign-stems` (reuses ComfyUI's ROCm torch via a `.pth` file) |
| MCP server venv | `~/ai/venvs/sovereign-mcp` (`mcp` 2.3, `httpx`, `pillow`) |

## What was built (all tested; see tests/)

1. **Multi-Performer Director** — `backend/app/services/performance_engine.py`, `routers/performances.py`,
   page `/performance` ("Duet" in the rail). N performers; each owns their vocal stem, a timeline of
   SINGING / SPEAKING / BACKGROUND_VOCAL / LISTENING / MOVING / IDLE regions, stage position, motion seed.
   Gated per-performer lip-sync audio (silence outside their parts), modes A–E, auto camera, director sheet.
2. **Duet renderer** — `services/performance_render.py`: one two-speaker Wan 2.1 + InfiniteTalk pass, chunked,
   reframed per camera shot, muxed with the master song, then Real-ESRGAN x2.
3. **Universal AI Enhance** — `services/enhance.py`, `enhance_worker.py`, `routers/enhance.py`, page `/enhance`.
   FFmpeg ops + Demucs + Real-ESRGAN / GFPGAN / RIFE. Non-destructive, presets, compare.
4. **Liquid-glass UI** — `frontend/src/app/globals.css` (tokens + glass rules + CSS ambient "world"), `layout.tsx`.
5. **MCP server** — `tools/sovereign_mcp/server.py` + README; 16 `sovereign_*` tools; registered in DeepSeek Harness
   (`~/.dsh/profiles/web/cordis.patch.yml`, id `mcp-sovereign`).
6. **Image Templates** — `services/image_templates.py`, `routers/image_templates.py`, page `/image-templates`.
   48 templates matching davinci.ai's image templates (inputs/choices in `docs/IMAGE_TEMPLATES_REFERENCE.md`),
   running on local Qwen Image Edit / Flux / Enhance. Watermark Remover deliberately excluded.
7. **Demo tooling** — `tools/demo/build_duet_stems.py`, `tools/demo/run_duet_demo.py` (drives the duet through MCP).
8. **ComfyUI node** — `tools/comfyui_nodes/sovereign_infinitetalk_parallel.py` (copied into `~/ai/ComfyUI/custom_nodes/`).
   REQUIRED for two-performer renders: ComfyUI's stock two-speaker node lays speaker 2's audio AFTER speaker 1's,
   so speaker 2's lips followed the wrong audio. Verified fixed on the handoff test (performance `18dba136de1b`).

## Config added to `backend/.env` (not in git)

`MUSIC_COMFYUI_URL=http://127.0.0.1:8188`, `MUSIC_COMFYUI_DIR`, `MUSIC_COMFYUI_PYTHON`,
`MUSIC_STEMS_PYTHON=~/ai/venvs/sovereign-stems/bin/python`, `PERFORMANCE_WIDTH=640`, `PERFORMANCE_HEIGHT=368`,
`PERFORMANCE_AUDIO_SCALE=1.4`. Another session set `GENERATOR_BACKEND=comfyui` and others (backup `.env.bak-20261021-wave2`).

## Hard-won facts (read before rendering)

- 30 GB RAM machine. ComfyUI under `~/ai/start-comfyui.sh` is capped at 24 GB and uses `--cache-none`: Wan 14B +
  InfiniteTalk multi then swap for 15+ min per part. Use caching on and a 28 GB cap — the launcher used was
  `/tmp/claude-1000/comfy-render.sh` (copy of start-comfyui.sh with `MemoryMax=28G`, no `--cache-none`,
  `--fp8_e4m3fn-text-enc`). `--highvram` runs out of VRAM. 832x480 forces partial offload; 640x368 fits.
- Measured: ~3.5–4 min per 81-frame part; 6 s clip ≈ 8.5 min incl. upscale; the 75 s song = 26 parts ≈ 75–90 min.
- Another Claude session ("AI PC setup and Deepseek Harness configuration") also uses ComfyUI — coordinate before restarting it.

## What is left

1. **Full five-mode demo render** — performance `2b117783cdff` ("Two Lights On One Stage (five-mode demo)") is fully
   set up (Ben's regions fixed by hand: verse 2 / harmony / backing / response). Start: `POST /api/performances/2b117783cdff/render`
   (or the Render button on `/performance`). It was cancelled at part 1/26 by David to free the GPU.
2. **QA the result** against the brief's list (wrong-mouth movement, drift, identity, seams, flicker…): crop each face
   across the handoffs at 14.6, 27.6, 41.6, 50.4, 55.3/57.7 s, as done for the handoff test.
3. **Two order-dependent backend tests** fail only in the full suite: `test_productions::test_production_crud_workspace_and_export`,
   `test_project_workspace::test_project_workspace_returns_project_media_and_counts` (pass alone and together with all new
   tests). Four other failures pre-date the upgrade (OCR "48:21", slides OCR, video_agent ollama-down, openai image edit).
4. **Ship**: rebuild frontend (render panel copy still says 832x480-era text; consider showing SD/HD), restart, final report.
5. Known limitations to state honestly: the demo song (YuE2) has one voice — Singer B's harmony is a pitch-shifted copy;
   camera moves are digital crops of one master shot; >2 performers render is not built (reported, not faked);
   reverb removal has no model.

## Transcript

`/mnt/storage/Projects/sovereign-data/handoff/claude-session-2026-10-21.zip` (14 MB; also in ~/Downloads) — exported from the Claude desktop session "Sovereign Creative Studio upgrade".
