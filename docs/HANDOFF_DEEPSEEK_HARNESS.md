# Handoff for the DeepSeek harness (written 2026-10-07 by Claude Code)

Read this first if you are taking over this work. Be useful, not chatty: **do the work with tool calls instead of announcing it**.
David (the user) wants things *finished, verified and reported plainly*. When something is not tested, say so.

## 0. House rules (from David and his CLAUDE.md)

- Surgical changes. Match existing style. Back up any existing file before editing it (backups for this work live in
  `C:\Users\David\Documents\Codex\sovereign-backups\music-lab-2026-10-06\`).
- **Never download anything without asking David first** (name, source, size). Never create accounts or log in to websites for him.
- **Do not copy other companies' logos, photos or branding.** Build the *features*; make original art (local image models).
- Windows 11 only. Do not touch Linux setups. Do not push anything to GitHub. Do not commit personal info.
- Tool habits on this machine: shell heredocs with quotes/backticks break often. **Write files with the file-write tool, then run them.**
  PowerShell for process control, bash only for simple things. Files in the Sovereign backend use **LF** line endings.
- Pronouns: use they/them for David unless told otherwise.

## 1. Environment map

| Thing | Where |
|---|---|
| Sovereign Creative Studio repo | `C:\Users\David\Documents\Codex\sovereign-creative-studio` (backend FastAPI `backend/app`, frontend Next.js 14 `frontend/src`) |
| Backend / frontend / main ComfyUI | `http://127.0.0.1:8002` / `http://localhost:3000` / `http://127.0.0.1:8001` |
| YuE2 music engine (separate ComfyUI) | `http://127.0.0.1:8199` (Sovereign can auto-start it) |
| Demucs vocal splitter | isolated venv `C:\Users\David\Documents\Codex\sovereign-stems\venv` (borrows ComfyUI's torch via a .pth file) |
| Jarvis (Claude Code agent) | `C:\Users\David\my-agent`; music tools in `tools/music/server.py` (MCP server "Jarvis music"); `.mcp.json` entry `sovereign-music` (David must approve it once by running `claude` there) |
| DeepSeek harness | `C:\Users\David\Documents\Codex\deepseek-harness` (web UI on `http://127.0.0.1:3080`), launcher `launch-deepseek-harness.ps1` |
| Music files | `backend\storage\music\<id>.mp3` + `<id>.json` (+ `.viz.json`, `.dub.json`, `.dubstate.json`, `.stems\`) |

**Restart Sovereign after backend or frontend changes** (production build, nothing hot-reloads). PowerShell:

```powershell
$env:NEXT_DIST_DIR='.next-cinematic-fixed'; $env:BACKEND_ORIGIN='http://127.0.0.1:8002'
foreach($port in 3000,8002){ $p=(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).OwningProcess; if($p){ taskkill /PID $p /T /F | Out-Null } }
Set-Location 'C:\Users\David\Documents\Codex\sovereign-creative-studio\frontend'; npm.cmd run build
Set-Location 'C:\Users\David\Documents\Codex\sovereign-creative-studio'
& 'backend\.venv\Scripts\python.exe' 'tools\local_launcher.py' start
```

Only restart when no music/video job is running (check `GET /api/music/now-playing`, `/api/videos`). The backend has a local-owner login
fallback, so API calls need no token locally. Never let `next lint` create an ESLint config. Type-check with `npx tsc --noEmit -p .` in `frontend`.

Tests (all must stay green): `backend\.venv\Scripts\python.exe -m pytest tests/test_music.py tests/test_music_playback.py tests/test_dubplate.py -q` from `backend` (97 pass with test_director.py and test_cinematic_planner.py as of this handoff).

## 2. What is DONE and working (verified)

**Music Lab** (`/music-lab`, sidebar "Music", Home banner, Apps library tile). Tabs: Create, Library, Stage, Dub Plate, Engine.
- Songs by YuE2 (local, free; ElevenLabs is only the optional paid engine). Create from an idea (local `gemma4:e4b` writes lyrics) or custom lyrics.
- **Length slider 1 to 5 minutes in 0.5 steps, default 3:30** (210 s). Backend `MAX_SECONDS=300`. A 5:00 request produced 4:30 (engine ends early on very long songs); that is expected and the UI says so.
- Play / pause / stop / seek / skip on both outputs (browser or speakers). Speaker pause/seek/resume are backend features (`music_playback.py`, `/api/music/pause|resume|seek`).
- Visualizer (spectrum/halo/waves) from real audio data.
- **Covers**: `POST /api/music/cover {song_id, style}` (SheetSage melody extraction to YuE2 "melody" mode). Backend + Jarvis tool only; **no UI button yet** (good small task: add "Make a cover" to the Library rows).
- **Dub Plate tab** (`dub-studio.tsx`, `dub-fx-panel.tsx`, `dub-press-panel.tsx`, `dub-waveform.tsx`, backend `services/dubplate.py`, `routers/music_dub.py`):
  waveform + beat grid + BPM, 8 hot cues, loops, tempo fader (key locked), EQ/filter/pitch/echo/reverb/drop-outs, cut, voice special
  (spoken via Piper **or sung by YuE2** with isolated vocal fitted to tempo/key), audition, and press **vocal side / version (instrumental) side / both**.
- Vocal/instrumental splitting with Demucs (`services/stems.py`, `stems_worker.py`, cached in `<id>.stems`).
- Starter library: 14 genre songs, plus earlier songs and a cover (19 songs total at handoff).

**Jarvis**: tools `create_song`, `create_song_from_idea`, `cover_song`, `press_dubplate`, `split_song`, `analyze_song`, play/pause/resume/seek/stop, list, status.
**DeepSeek harness**: the same tool server is registered through `.local\sovereign-music\sovereign-music.patch.yml` (and `--patch` in the launcher),
plus `.local\intent-guard` (re-prompts when a turn ends with only "Let me check..."). Neither was exercised through a live model turn.

UI polish done this session: credits gem icon (`components/gem-icon.tsx`, in top bar and the rail Credits item), rail "Music" item (`lib/navigation.ts` `RAIL_NAV`).

## 3. DONE: Director (OpenArt-style templates), finished 2026-10-07

David asked for the OpenArt "Direct Your Video" features inside Sovereign: Short Film, Music Video, Real Estate, Product Ads, Ad Remake, Social Content, UGC Ads,
Micro Drama, Brand Film, Explainer, Film Trailer, Promo video. Built and verified (OpenArt's inner screens need a login, so only the public template list was used;
**no OpenArt logos or photos were copied**, tile art is original, made locally with z-image by `tools/generate_director_tiles.py`).

- Backend: `services/director_templates.py` (12 templates, brief fields, planner structure, soundtrack styles), `services/director.py` (job runner; JSON state in `backend/storage/director/`,
  no DB migration), `routers/director.py` (`/api/director/*`). One film at a time. Pipeline: plan (fast planner `gemma4:e4b` about 30 s, or "best" = `VIDEO_AGENT_MODEL` several minutes;
  shot lengths rescaled to fit) then per shot: keyframe picture (z-image) then MiniMax H3 image-to-video for vertical, text-to-video for widescreen (falls back to LTX), then join
  (`concat_clips`, normalises size/fps/audio), local-voice narration per shot, Music Lab instrumental soundtrack, ducked mix (`mix_audio`), final MP4 in `storage/videos/director-<id>.mp4`.
  Narration or soundtrack failures never lose the film (a note is recorded). Cancelled/failed/deleted Micro Drama episodes are removed from their series.
- Micro Drama series: episode 2+ re-prompts the planner with the character/location bible and earlier synopses (prompt-level consistency; faces may still vary). Verified: episode 2's plan reused the same characters and followed the direction text.
- `services/cinematic_planner.py` `write_plan(prompt, seconds, model=None, exact=True)` got two optional args (defaults keep old behaviour; its 17 tests pass).
- Frontend: `/director` (grid of formats + your videos), `/director/new?template=...` (brief form, length slider, voice-over/soundtrack toggles, planner speed, cost range),
  `/director/watch?id=...` (stage timeline, shots grid, result player + download, next episode). Home has a "Direct your video" carousel; rail item "Director"; Apps library tile.
- Jarvis/harness tools: `list_video_templates`, `make_video`, `video_status`, `next_episode` in `my-agent/tools/music/server.py`.
- Verified live: a 10 s Social Content video (5 shots, narration + music, 480x832, about 3 minutes after a 6-minute slow planner run) and a 45 s Micro Drama episode
  (8 shots at about 75 s each, 47 s output with soundtrack). Costs: 20 credits per shot (about 100 to 160 credits for those). Those two test videos were deleted by mistake
  during cleanup; their raw clips remain in `storage/videos` but the assembled films are gone. Re-make them from the UI if wanted.
- Tests: `tests/test_director.py` (23). Whole music+director suite: run the command in section 1 plus `tests/test_director.py tests/test_cinematic_planner.py` (97+ pass).

Ideas not done: per-shot "redo this shot" and editing the plan before filming; real character identity lock (needs reference-image conditioning); uploading a reference ad for Ad Remake
(only a text description is used); a browser click-through of the new screens (they were checked via HTTP, page text and DOM only).

## 3b. Laptop transfer kit (built 2026-10-07)

David is moving Sovereign to a Lenovo Legion (RTX 4070 laptop GPU, **8 GB** graphics memory, 32 GB RAM). Everything for that lives in `tools/transfer/` and `docs/LAPTOP_TRANSFER_HANDOFF.md`:
- `export-to-drive.ps1` builds `G:\Sovereign-Transfer` (code, DB snapshot, settings, storage without backups, music engine + YuE2/SheetSage models, Ollama gemma4:e4b + qwen3:4b, lock files,
  `MANIFEST.json` with SHA256, `START_HERE.md`). `-DryRun` shows sizes. Optional `-IncludeVideoModels`, `-IncludeBackups`, `-SkipOllama`.
- `setup-laptop.ps1` (run on the laptop) verifies, installs tools (`-InstallPrereqs`), copies, rewrites paths in `backend\.env`, builds the venvs, the front end, Demucs, imports Ollama models, writes launchers, runs tests, runs `check-readiness.ps1`.
- Repo changes made for portability: `tools/local_launcher.py` reads `SOVEREIGN_COMFY_*` environment variables (defaults unchanged); `backend/requirements.txt` gained `piper-tts` and `numpy`.
- The handoff text that the laptop's AI reads is `docs/LAPTOP_TRANSFER_HANDOFF.md` (the export prepends a header and saves it as `START_HERE.md`).

## 4. Other open items

- Jarvis `sovereign-music` MCP server still needs David's one-time approval (`claude` in `C:\Users\David\my-agent`). Check whether the voice Jarvis (`fullstack-agent\start.bat voice`) loads `.mcp.json`.
- "GPT-Astra": David mentioned linking music tools to it. Unknown to me. Ask David where it lives and whether it can load MCP servers.
- Optional: "Make a cover" button in the Library; engine tab note about Demucs; Sovereign changes are **not committed** to git (David has not asked).
- YuE2 licence: tell David to check terms before commercial use of generated songs. Instrumental-only mode is experimental.
- The YuE2 ComfyUI on 8199 is left running; Sovereign can start/stop it itself.

## 5. How to report back

Short, plain, honest: what works (verified how), what is untested, what David must do, any limits (for example "5:00 came out 4:30"). No lyrics read aloud, no hype.
