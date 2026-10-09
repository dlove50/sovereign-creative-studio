## 1. Who you are and the rules

You are an AI assistant (Claude Code, Codex, the DeepSeek harness or similar) running on David's **Lenovo Legion laptop**. David copied **Sovereign Creative Studio**
from their main PC to this laptop using this kit. Your job: **install it, make it run, verify it, and report plainly.** Do the work with tool calls; do not
announce steps you will not perform. If something is unfinished or untested, say so.

Rules that apply no matter what:
- Use **they/them** for David unless told otherwise.
- **Windows 11 only.** Do not set up Linux or WSL versions.
- **Ask before downloading anything large** that the scripts do not already download (model files over about 500 MB, new apps). The setup script's own downloads
  (Python packages, PyTorch, npm packages, the 80 MB Demucs file, winget tools with `-InstallPrereqs`) are expected.
- **Never push this project to GitHub or any cloud.** Never print, log or paste the contents of `.env`, `secrets\`, API keys or `session_secret`.
- Make small changes. Back up a file before editing it. Do not delete the kit or the original data.
- Do not create accounts or log in to websites for David.
- Only the Windows launchers in this kit are supported. The code files use LF line endings; keep them.

## 2. What Sovereign Creative Studio is

A local-first creative studio: a FastAPI backend (`backend/`, port **8002**, SQLite database `backend/sovereign.db`) and a Next.js 14 web app (`frontend/`, port **3000**,
production build). Local AI runs through ComfyUI (images, video, avatars, songs), Ollama (text) and Piper (voice). Key features:

- **Music Lab** (`/music-lab`): songs with **YuE2** (local, free), covers, library, visual stage, **Dub Plate** studio (cuts, FX, spoken or sung voice special,
  vocal/instrumental "version" side with Demucs).
- **Director** (`/director`): 12 video templates (short film, music video, real estate, product ads, ad remake, social content, UGC ads, micro drama, brand film,
  explainer, film trailer, promo video) that plan, film, narrate, score and mix a finished video. **Needs the main ComfyUI and video models, see section 10.**
- Avatars, voices, brand kits, image studio, movies, slides, podcasts, transcription, and more (see `docs\` and `README.md` in the code folder).
- Local accounts with credits. Without a login the app acts as the local owner (David). A `401 /api/auth/me` in the browser console is normal when not signed in.

## 3. The hardware reality (read this before promising anything)

| | Original PC | This laptop (Lenovo Legion) |
|---|---|---|
| GPU | RTX 5070 Ti, **16 GB** graphics memory | RTX 4070 Laptop, **8 GB** graphics memory |
| RAM | large | 32 GB |
| CPU | desktop | Intel Core i9 14th gen |

What this means (expectations, not guarantees; **verify with the readiness check and a real song**):
- **Music Lab, covers, dub plates, voice, pages, Jarvis tools:** expected to work. YuE2 (int8) peaked at about 5.9 GB on the original PC.
- **Lyric writer**: runs on whatever Ollama model is installed (the script picks one). `gemma4:e4b` (9.6 GB) spills into RAM on 8 GB; a 3 to 4 billion parameter model is faster. The lyric writer asks Ollama for strict JSON, so very small or old models may write poor lyrics; prefer `gemma4:e4b` or `qwen3:4b` (`ollama pull qwen3:4b`).
- **Director / images / avatars:** the video models (MiniMax H3, LTX 22B, Wan 14B) need about 16 GB. On 8 GB they may be extremely slow or fail. They are **not installed by default** here.
- Laptop thermals: long generations throttle. Keep it plugged in, set Windows power mode to Best performance, close games and browsers with video.

## 4. What is already on the laptop, and what is in the kit

David says the laptop **already has Ollama (with a llama model), YuE2 (the music model, with a ComfyUI that runs it) and the DeepSeek harness**. So the kit carries only Sovereign itself,
not those. **First job: find them** (do not reinstall or move them):
- Ollama: `ollama list` (models) and `where ollama`.
- ComfyUI with YuE2: look for a folder containing `main.py`, `comfy_extras\nodes_yue2.py` and `models\checkpoints\yue2_3b_int8_convrot.safetensors` (try `Documents\ComfyUI`, `C:\ComfyUI`, ComfyUI Desktop under `AppData\Local\Programs`, `ComfyUI_windows_portable`).
  Also find the `python.exe` that runs it (often `ComfyUI\.venv\Scripts\python.exe`). `setup-laptop.ps1` searches common places automatically; if it does not find it, pass `-ComfyDir` and `-ComfyPython`.
- If that ComfyUI is older than 0.37 (no `nodes_yue2.py`) songs cannot work with it. The kit has ComfyUI 0.37 code in `comfyui\ComfyUI`; the script builds a separate copy from it in that case.
- The DeepSeek harness: see section 13 for plugging Sovereign's music tools into it.

```
Sovereign-Transfer  START_HERE.md                this file
  MANIFEST.json                size + SHA256 of every file (verify-transfer.ps1 checks it)
  code.tar                     the whole project (no venv, node_modules or build folders) plus its git history in .git
  data.tar                     data\sovereign.db (accounts, credits, projects), data\config\.env and .env.local (settings),
                               data\backend-storage (music library, avatars, images, Piper voices, uploads; no old backups,
                               and NO generated videos: videos, avatar_videos, captioned, director were left out on purpose)
  secrets\                     session secret and integration keys (keep private)
  comfyui.tar                  ComfyUI v0.37 code, a fallback if the laptop has no ComfyUI that can run YuE2 (no big models)
  models\MODEL_INVENTORY.md    every large model on the original PC and which ones are NOT in the kit
  (models\music\ and ollama\ appear only if the kit was built with -IncludeMusicModels / -IncludeOllama)
  extras\agent-music-tools\    server.py (music/video tool server for Jarvis and the DeepSeek harness) and the harness patch file
  locks\                       exact package lists from the original PC and versions.json
  tools\                       setup-laptop.ps1, verify-transfer.ps1, check-readiness.ps1, export-to-drive.ps1
```
The big folders are packed as `.tar` files because USB sticks write many small files very slowly. `setup-laptop.ps1` unpacks them (Windows' built-in `tar.exe`).

## 5. Install (one command)

1. Plug in the laptop. Make sure the NVIDIA driver is installed (`nvidia-smi` works; driver 580 or newer is best for CUDA 13, older drivers use a different PyTorch build automatically).
2. Open **Windows PowerShell** (not admin needed) and run, using the kit's drive letter:

```powershell
powershell -ExecutionPolicy Bypass -File G:\Sovereign-Transfer\tools\setup-laptop.ps1 -InstallPrereqs
```

Flags: `-InstallRoot C:\Sovereign` (default), `-ComfyDir <folder> -ComfyPython <python.exe>` (use the ComfyUI that already has YuE2), `-LyricsModel <ollama model>`, `-SkipVerify`, `-SkipFrontendBuild`, `-SkipTests`, `-TorchCuda cu128`, `-DryRun`.
Run it once with `-DryRun` first: it prints what it found (Python, Node, ffmpeg, Ollama and its models, and any ComfyUI with YuE2) and changes nothing.
It writes a log to `C:\Sovereign\setup.log`. It is safe to run again; finished work is reused and an existing database is backed up first.
Expect 10 to 30 minutes (the kit is about 4 GB; the stick may be slow; then package downloads). Building a new music engine adds a multi-GB PyTorch download.

If the script stops, read the last error, fix it, and run it again. If `winget` tools were just installed, **open a new terminal** so PATH updates, then re-run.

## 6. What the script does (and the manual equivalent)

1. **Verify** every file against `MANIFEST.json`.
2. **Tools**: Python 3.12+ (3.13 preferred), Node LTS (original used 24), Git, ffmpeg (`winget install -e --id ...`). Ollama is not installed by the script; it is already here.
3. **Copy**: code to `C:\Sovereign\sovereign-creative-studio`, database/settings/storage into `backend\`, secrets into `backend\storage\secrets`. The kit's ComfyUI is copied to `C:\Sovereign\ComfyUI` only when no usable existing ComfyUI is found; model files are copied only if the kit has them and the target lacks YuE2.
4. **Settings**: rewrites a marked block at the end of `backend\.env` with this PC's paths (`FFMPEG_PATH`, `MUSIC_COMFYUI_DIR`, `MUSIC_COMFYUI_PYTHON`, `MUSIC_STEMS_PYTHON`) and picks the lyric/story model from the Ollama models installed here (`gemma4:e4b` if present, else `qwen3:4b`, else a llama model); it writes it as `MUSIC_LYRICS_MODEL`, `VIDEO_AGENT_MODEL` and `DIRECTOR_FAST_PLANNER_MODEL`.
5. **Backend venv**: `py -3.13 -m venv backend\.venv`, then `pip install -r locks\backend-freeze.txt` (falls back to `requirements.txt`).
6. **Front end**: `npm ci` then `npm run build` with `NEXT_DIST_DIR=.next-cinematic-fixed` and `BACKEND_ORIGIN=http://127.0.0.1:8002` (the backend address is baked into the build; if you change it, rebuild).
7. **Music engine Python**: with an existing ComfyUI it only checks that its torch sees the GPU. Otherwise it builds `ComfyUI\.venv` with `torch==2.10.0 torchaudio==2.10.0` from `https://download.pytorch.org/whl/cu130` (or `cu128` / `cu126` by driver), then `locks\comfyui-freeze-without-torch.txt`.
8. **Vocal splitter**: `stems\venv` with a `.pth` file pointing at the music engine python's `site-packages` (so it shares torch), then `pip install demucs`, then downloads the small `htdemucs` weights once.
9. **Launchers**: `Start-Sovereign.bat`, `Stop-Sovereign.bat`, `Check-Readiness.bat` in `C:\Sovereign`, plus a desktop shortcut.
10. **Tests** (backend) and the **readiness report**.

Manual start (if you need it): `C:\Sovereign\sovereign-creative-studio\backend\.venv\Scripts\python.exe C:\Sovereign\sovereign-creative-studio\tools\local_launcher.py start --skip-comfy`
(`--skip-comfy` because the main ComfyUI is not installed on this laptop; the music engine on port **8199** is started by Sovereign itself when a song is requested).

## 7. Settings, ports and paths

- Backend settings: `backend\.env` (read by `backend\app\config.py`; every setting is an environment variable). Frontend: `frontend\.env.local`.
- Ports: frontend 3000, backend 8002, music engine 8199 (started on demand), Ollama 11434, main ComfyUI 8001 (not installed here by default).
- Music settings in `config.py`: `MUSIC_COMFYUI_URL`, `MUSIC_COMFYUI_DIR`, `MUSIC_COMFYUI_PYTHON`, `MUSIC_STEMS_PYTHON`, `MUSIC_CHECKPOINT`, `MUSIC_DIR`, `MUSIC_LYRICS_MODEL`, `MUSIC_PLAYER_VOLUME`.
- Launcher paths: `tools\local_launcher.py` reads `SOVEREIGN_COMFY_DIR`, `SOVEREIGN_COMFY_PY`, `SOVEREIGN_COMFY_MODELS`, `SOVEREIGN_COMFY_BASE` (defaults are the original PC's, so set them if you start the main ComfyUI).
- Storage layout under `backend\storage`: `music\<id>.mp3 + <id>.json` (plus `.viz.json`, `.dub.json`, `.dubstate.json`, `<id>.stems\`), `director\<id>.json`, `videos\`, `avatars\`, `models\piper\` (voices), `secrets\`.
- The database migrates itself at backend start (Alembic). Do not delete `sovereign.db`.

## 8. Verify it works (do all of these and report the results)

1. `C:\Sovereign\Check-Readiness.bat` (or `tools\check-readiness.ps1`). Every required piece should say OK. Read the per-feature verdicts.
2. Backend tests, from `C:\Sovereign\sovereign-creative-studio\backend`:
   `.venv\Scripts\python.exe -m pytest tests/test_music.py tests/test_music_playback.py tests/test_dubplate.py tests/test_director.py tests/test_cinematic_planner.py -q`
   Expected: **about 98 passed**. Failures that usually mean: *ffmpeg not found* (open a new terminal / check PATH), *rubberband filter missing* (use the Gyan.FFmpeg full build), *module not found* (re-run setup step 5).
3. Start with `C:\Sovereign\Start-Sovereign.bat`. Open `http://localhost:3000`. Check `http://127.0.0.1:8002/api/music/status`.
4. **Make a 60 second song** in Music Lab (Create tab, describe it, pick 1:00 length). The first song also starts the engine (about a minute). Watch GPU memory with `nvidia-smi`; it should stay under 8 GB.
   If it fails with an out-of-memory error, see section 11.
5. In the Library, play the song. Open **Dub Plate**, choose it, set a cue, press **Audition the cut**. Choose "Both sides" and **Press**: the first vocal split takes about 20 to 60 seconds.
6. Report: what passed, what failed with the exact error text, and the measured time for a 60 second song.

## 9. Architecture map

- `backend/app/main.py` includes every router. Routers in `backend/app/routers/`; logic in `backend/app/services/`.
- **Music**: `routers/music.py` (+ `music_dub.py`), `services/music.py` (YuE2 job pipeline through ComfyUI, song store), `music_compose.py` (idea to lyrics via Ollama),
  `music_playback.py` (speaker playback with ffplay, pause/seek, visualizer data), `dubplate.py` (waveform, BPM/key, cues, render with ffmpeg), `stems.py` + `stems_worker.py` (Demucs in its own venv),
  `music_cover.py` (SheetSage melody to YuE2 cover).
- **Director**: `routers/director.py`, `services/director.py` (job runner, JSON state in `storage\director`), `director_templates.py`, `cinematic_planner.py` (story planner), clips through `routers/videos.py` / `services/video_jobs.py`.
- Frontend routes live in `frontend/src/app/<route>/page.tsx`; screens in `frontend/src/components/`. Music: `components/music/`; Director: `components/director/`; API clients: `src/lib/api/`.
- Tests: `backend/tests/` (the five files above cover the work done most recently). Docs for older features: `docs\` (`HANDOFF_CLAUDE_CODE.md`, `HANDOFF_CODEX.md`, `LOCAL_STARTUP_AND_RECOVERY.md`, `ARCHITECTURE.md`, `OPERATOR_GUIDE.md`, `HANDOFF_DEEPSEEK_HARNESS.md`).

If a file is damaged or missing, restore it from the bundled git history: `git -C C:\Sovereign\sovereign-creative-studio status` then `git checkout -- <file>` (there are uncommitted
changes by design: the Music Lab, Dub Plate, Director and transfer work is **not committed**, so only restore files you know are tracked and unchanged).

## 10. Enabling image, video and avatar features (optional, big)

The Director, Image Studio, Video Generator and talking avatars call the **main ComfyUI on port 8001** with large models. They are off on this laptop by default.
`models\MODEL_INVENTORY.md` lists the model files the original PC uses. To try them on this laptop, ask David first, because it needs tens of GB:
1. Install ComfyUI Desktop (or use `C:\Sovereign\ComfyUI` with its own `--base-directory`) and put the needed model files in its `models` folders.
2. Start it on port **8001**, then start Sovereign without `--skip-comfy`, or leave `--skip-comfy` and start ComfyUI yourself.
3. Smaller options that fit 8 GB: SDXL (`sd_xl_base_1.0.safetensors`), Wan 2.1 1.3B text-to-video, FLUX.2 Klein 4B. Set `COMFYUI_VIDEO_ENGINE=wan` in `backend\.env` only after those models are installed.
4. Expect the MiniMax H3 / LTX 22B video models to be unusable on 8 GB without heavy offloading; test one 4 second clip before promising anything.

## 11. Tuning for 8 GB graphics memory

- Close other GPU programs. Songs run one at a time (a lock inside the backend).
- If a song fails with CUDA out-of-memory: in `backend\app\services\music.py`, function `start_engine`, add `"--lowvram"` to the ComfyUI command line, restart the backend, retry.
- The lyric model is unloaded after each use (`keep_alive: 0`) and the music engine is asked to free memory first, so they do not overlap.
- Slow lyrics: `MUSIC_LYRICS_MODEL=qwen3:4b` in `backend\.env`.
- Demucs falls back to the CPU automatically if the GPU is full.
- Keep Music Lab songs at 3:30 or shorter; 5:00 requests are already trimmed by the engine.

## 12. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `setup-laptop.ps1` says a tool is missing after installing it | Open a NEW terminal so PATH refreshes, run again |
| PyTorch install fails | Use `-TorchCuda cu128` (or `cu126`); update the NVIDIA driver |
| `torch.cuda.is_available()` is False | Driver too old or CPU torch installed; reinstall torch with the right `--index-url` |
| Port 3000 or 8002 already in use | Run `Stop-Sovereign.bat`; find other users with `netstat -ano | findstr :3000` |
| Page loads but data is empty or 500 errors | Backend not running (`http://127.0.0.1:8002/api/health`); read `backend` console window |
| "Song generation failed" / engine offline | Look at `C:\Sovereign\ComfyUI` console output; check both model files exist in `ComfyUI\models`; try `--lowvram` |
| Voice special says no voice ready | Piper voice files are in `backend\storage\models\piper`; `piper-tts` must be installed in the backend venv |
| Vocal split fails | `stems\venv` missing or Demucs weights not downloaded (needs internet once); see `setup.log`. `OSError: WinError 126 ... torch_python.dll` means the splitter environment was made with a different Python than the music engine: delete `C:\Sovereign\stems\venv` and re-run setup |
| Old videos show broken thumbnails or empty players | The kit leaves the generated video files out on purpose but keeps their records in the database. They are harmless; delete them in the app, or remove the stale records (only if David asks): `backend\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('sovereign.db'); c.execute('delete from video_generations'); c.commit()"` (run in `backend`, with the backend stopped) |
| Front end shows old/blank pages after changes | Rebuild: `set NEXT_DIST_DIR=.next-cinematic-fixed` and `npm run build` in `frontend`, restart |

## 13. Not in the kit

Jarvis (`C:\Users\David\my-agent`), the DeepSeek harness itself, the original PC's Ollama models (`qwen3.8:27b` and others), the main ComfyUI Desktop install and its video/image models,
old `backend\storage\backups` snapshots (about 29 GB), and anything David added after the kit was created.

**Plugging Sovereign into the DeepSeek harness already on the laptop.** The kit has `extras\agent-music-tools\server.py` (an MCP tool server: make songs, covers, dub plates, videos and control playback)
and `sovereign-music.patch.yml` (how the harness loads it). Steps: copy `server.py` somewhere stable (for example `C:\Sovereign\extras\agent-music-tools\server.py`, setup copies it there);
it needs Python with the packages `requests` and `mcp` (use a venv: `python -m venv C:\Sovereign\tools-venv` then `pip install requests "mcp>=2.1"`; the original PC uses mcp 2.1.1 and requests 2.34.2);
edit the patch file so `command` is that venv's `python.exe`, `args` points at `server.py`, and `SOVEREIGN_API` is `http://127.0.0.1:8002`;
then add the patch with `--patch <file>` where the harness is started (the original PC does this in `launch-deepseek-harness.ps1`). Restart the harness when it is idle.
Sovereign must be running when a tool is called. This was **not tested on the laptop**.

**Videos.** David left the old generated videos behind but wants every video **feature** (Director, Video Generator, avatars, movies) kept. The code is all here; the features
only need the main ComfyUI and models (section 10). New videos made on the laptop will appear normally.

## 14. Security and cleanup

The drive holds the database (accounts, credits), settings and secrets in plain files. Keep it private (BitLocker To Go is advised). When the laptop works and David confirms,
suggest wiping `secrets\` and `data\` from the drive. Do not copy the kit to cloud storage.

## 15. Report back

Say: what is installed and where, the readiness verdicts, test results (counts), the first song's generation time and peak GPU memory, anything that failed with the exact error,
and what David needs to do next. Keep it short and honest.
