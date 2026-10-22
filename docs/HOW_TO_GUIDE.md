# Sovereign Creative Studio — How-To Guide (Windows & Linux)

A plain-language walkthrough for getting the studio running, using it day to day,
and fixing the common things that go wrong. This is the friendly companion to the
more detailed [Operator guide](OPERATOR_GUIDE.md),
[Model & dependency manifest](MODEL_AND_DEPENDENCY_MANIFEST.md), and
[Recovery & maintenance](RECOVERY_AND_MAINTENANCE.md) guides.

> **Platform note.** Sovereign Creative Studio is built and supported on
> **Windows 11**. The one-click launcher (`Start-Sovereign-Creative-Studio.bat`)
> and the desktop shortcut are Windows-only. The Linux section below is an
> **unofficial, manual** way to run the same code on Linux — it works, but you
> start each service yourself and adjust paths. Nothing here changes the app's
> Windows-first design.

---

## 1. What this program is

Sovereign Creative Studio is a **private, fully local AI production workspace**.
Everything runs on your own machine — no cloud account required for the core
features. In one app you can:

- generate and edit **images** (ComfyUI);
- turn images into **video** (LTX / Wan);
- write **copy and summaries** (Ollama / Qwen);
- transcribe video to text (**Whisper**);
- generate **voice narration** (Piper) and **talking avatars** (Wan InfiniteTalk);
- organize everything in **Assets, Projects, Collections, and Brand Kits**.

It runs as three cooperating services:

| Service  | What it does                        | Address                  |
| -------- | ----------------------------------- | ------------------------ |
| Frontend | The web app you click around in     | `http://localhost:3000`  |
| Backend  | The API, database, and job engine   | `http://127.0.0.1:8000`  |
| ComfyUI  | The image/video generation engine   | `http://127.0.0.1:8001`  |

You always **open the app at `http://localhost:3000`**. The other two run in the
background.

---

## 2. Everyday use on Windows

### Start it

Use **any one** of these — they all do the same thing:

- **Double-click the desktop shortcut** *Sovereign Creative Studio* (the crown
  icon). ← easiest
- Or double-click **`Start-Sovereign-Creative-Studio.bat`** in the project folder
  (`C:\Users\David\Documents\Codex\sovereign-creative-studio`).

A console window opens and starts ComfyUI, the backend, and the frontend, then
opens your browser. **First start of the day takes a minute or two** while the
services warm up.

When it's ready, the app is at:

```text
http://localhost:3000
```

### Stop it

Double-click **`Stop-Sovereign-Creative-Studio.bat`**. This shuts all three
services down cleanly. Closing the browser tab alone does **not** stop them.

### If a start goes wrong or a port is stuck

Open PowerShell in the project folder and run:

```powershell
python tools\local_launcher.py clean
```

`clean` clears stuck ports, rebuilds the frontend, and starts fresh. To confirm
everything came up correctly:

```powershell
python tools\local_launcher.py smoke
```

---

## 3. First-time setup on Windows (new machine)

Skip this if the studio already runs on this PC. Full detail lives in the
[Model & dependency manifest](MODEL_AND_DEPENDENCY_MANIFEST.md); this is the short
version.

1. **Install prerequisites**
   - Python **3.11+**
   - Node.js **20 LTS**
   - **FFmpeg** — `winget install Gyan.FFmpeg`
   - **Ollama** (for summaries) — https://ollama.com/download, then
     `ollama pull qwen3:4b`
   - **ComfyUI** (image/video engine) plus its model files

2. **Build the backend**
   ```bat
   cd backend
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```

3. **Build the frontend**
   ```bat
   cd frontend
   npm install
   ```

4. **Create the config file**
   Copy `backend\.env.example` to `backend\.env` and fill in the machine-specific
   values (FFmpeg path, ComfyUI URL, model names). See the manifest for the full
   template.

5. **Point the launcher at your ComfyUI install**
   If ComfyUI lives somewhere new, update the paths near the top of
   `tools\local_launcher.py` (`COMFY_DIR`, `COMFY_PY`, model/user/output dirs).

6. **Add the models** — Piper voices, Whisper (auto-downloads on first use), and
   the ComfyUI checkpoints/VAE/video models listed in the manifest.

7. **Launch and test**
   ```bat
   python tools\local_launcher.py clean
   ```
   Open `http://localhost:3000` and run one **Quick Chain** to confirm.

---

## 4. Running on Linux (unofficial / manual)

> The `.bat` launcher and `tools/local_launcher.py` assume Windows paths
> (`.venv\Scripts\python.exe`, `npm.cmd`, `taskkill`), so they cannot run here.
> Use **`tools/start-sovereign-linux.sh {start|stop|status}`**, or start the
> three services by hand as below. GPU image/video generation needs either an
> **NVIDIA GPU with current drivers + CUDA** or an **AMD GPU with ROCm**
> (see `docs/AMD_ROCM_LINUX_GPU_SETUP.md` for the Radeon AI PRO R9700 machine);
> CPU-only will run the app but generation will be very slow or unavailable.

### 4.1 Install prerequisites

Example for Debian/Ubuntu (adapt for your distro):

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip ffmpeg git curl
# Node.js 20 LTS (via nodesource)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
# Ollama (optional — only needed for AI summaries)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:4b
```

You also need **ComfyUI** installed separately (its own repo + Python venv +
model files) and, for GPU work, the matching driver stack for your card:
**NVIDIA driver + CUDA**, or **ROCm** on AMD. Note that
`backend/workflows/comfyui_extra_model_paths.yaml` is a Windows reference copy
(`base_path: C:/Users/David/...`); nothing in the backend reads it, but if you
pass an extra-model-paths file to ComfyUI you need one with Linux paths.

### 4.2 Get the project and build it

```bash
# copy or clone the project to your home directory, e.g. ~/sovereign-creative-studio
cd ~/sovereign-creative-studio

# Backend
cd backend
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
cd ..

# Frontend
cd frontend
npm install
cd ..
```

### 4.3 Configure

```bash
cp backend/.env.example backend/.env
```

Then edit `backend/.env` and use **Linux-style paths**, for example:

```ini
COMFYUI_BASE_URL=http://127.0.0.1:8001
FFMPEG_PATH=/usr/bin/ffmpeg
VOICE_ENABLED=true
VOICE_BACKEND=piper
VOICE_MODEL_NAME=en_US-lessac-low
VOICE_MODEL_PATH=storage/models/piper/en_US-lessac-low.onnx
COPY_BACKEND=local-qwen
OLLAMA_QWEN_MODEL=qwen3:4b
TRANSCRIPTION_BACKEND=local_whisper
TRANSCRIPTION_MODEL_NAME=base
TRANSCRIPTION_DEVICE=cpu
TRANSCRIPTION_COMPUTE_TYPE=int8
```

Place the Piper voice files under `backend/storage/models/piper/` (Whisper
auto-downloads on first transcription).

### 4.4 Start the three services

Open **three terminals** (or use the script below).

**Terminal 1 — ComfyUI** (adjust to your ComfyUI install path):

```bash
cd ~/ComfyUI
python main.py --port 8001
```

**Terminal 2 — Backend:**

```bash
cd ~/sovereign-creative-studio/backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 3 — Frontend:**

```bash
cd ~/sovereign-creative-studio/frontend
npm run dev
```

Then open **`http://localhost:3000`**.

### 4.5 Optional: a one-command Linux start script

Save this as `start-all.sh` in the project root, then
`chmod +x start-all.sh` and run `./start-all.sh`. Edit `COMFY_DIR` to match your
ComfyUI install.

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
COMFY_DIR="$HOME/ComfyUI"   # <-- change to your ComfyUI path

# ComfyUI on :8001
( cd "$COMFY_DIR" && python main.py --port 8001 ) &
sleep 12

# Backend on :8000
( cd "$ROOT/backend" && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 ) &
sleep 6

# Frontend on :3000
( cd "$ROOT/frontend" && npm run dev ) &

echo "Sovereign Creative Studio starting -> http://localhost:3000"
wait
```

Press **Ctrl+C** in that terminal to stop everything.

---

## 5. How to actually use it (both platforms)

Once the app is open at `http://localhost:3000`:

### The recommended path: **Quick Chain**

The Home page leads with **Quick Chain**, which walks you from an idea to finished
files in order:

1. **Prompt → Image** — type what you want; it generates an image.
2. **Image → Video** — animates the image.
3. **Upscale** *(optional)* — sharpens/enlarges the video.
4. **Add Voice** *(optional)* — Piper narration.
5. **Transcribe + Summary** *(optional)* — Whisper text + Qwen summary.
6. **Download** — save the finished outputs.

You can stop at any step — you don't have to run the whole chain.

### Or use a single studio directly

- **Image Studio** — text-to-image and reference-image editing.
- **Video Generator** — text/image/video-to-video, extend, upscale.
- **Avatars & Voices** — reusable avatars + Piper voices + talking-avatar jobs.
- **Transcribe Video** — Whisper transcription and Qwen summaries.
- **Assets** / **My Projects** — organize and re-find finished work.

On a small screen, use the **menu button (top-left)** to reach the sidebar
destinations.

### Accounts and credits (quick version)

- **owner/admin** manages users, credits, providers, jobs, storage, backups, and
  models.
- **family user** gets the creator experience and sees their own work.
- **Credits are only charged after a job succeeds.** Failed, cancelled,
  setup-required, and out-of-memory jobs cost **zero**. (Full rate table is in the
  [Operator guide](OPERATOR_GUIDE.md).)

---

## 6. Where your data lives

| What                | Location                              |
| ------------------- | ------------------------------------- |
| Database            | `backend/sovereign.db`                |
| Generated media     | `backend/storage/`                    |
| Backups             | `backend/storage/backups/`            |
| Workflow templates  | `backend/workflows/`                  |
| Server-side secrets | `backend/storage/secrets/`            |
| ComfyUI models      | Windows: `C:\Users\David\ComfyUI-Shared\models` (Linux: your ComfyUI models dir) |

**Backups** are created from inside the app (owner/admin). They snapshot the
database, app storage, and workflows — but **not** secrets or the large external
ComfyUI models, so keep your models directory backed up separately. Read
[Recovery & maintenance](RECOVERY_AND_MAINTENANCE.md) **before** restoring or
deleting anything.

---

## 7. Troubleshooting

| Symptom | Try this |
| --- | --- |
| Browser shows "can't connect" at `:3000` | Give it a minute on first start. Then confirm the launcher window is still open / services are running. |
| Start failed or a port is stuck (Windows) | `python tools\local_launcher.py clean`, then `... smoke` to verify. |
| A service won't bind its port (Linux) | Make sure nothing else uses 3000/8000/8001: `ss -tlnp \| grep -E ':(3000\|8000\|8001)'` and stop the conflicting process. |
| Image/video generation errors or "setup required" | Open **Status** — a model or ComfyUI path is missing. Check the [manifest](MODEL_AND_DEPENDENCY_MANIFEST.md). |
| Summaries fail but everything else works | Ollama isn't running / `qwen3:4b` not pulled. Start Ollama and `ollama pull qwen3:4b`. |
| "Add Voice" fails | Piper voice files missing from `backend/storage/models/piper/`. |
| Adding voice to video fails | `FFMPEG_PATH` in `backend/.env` is wrong or FFmpeg isn't installed. |
| Jobs stuck / stale | Open **Job Monitor** (admin) and review; see [Recovery & maintenance](RECOVERY_AND_MAINTENANCE.md). |

For service-by-service Windows startup diagnostics, see
[LOCAL_STARTUP_AND_RECOVERY.md](LOCAL_STARTUP_AND_RECOVERY.md).

---

## 8. Good habits

- Create a **backup** before changing models, workflows, or provider settings.
- **Download** anything important out of app storage if it must live elsewhere.
- **Stop the studio cleanly** when you're done (Windows: the Stop `.bat`; Linux:
  Ctrl+C in the terminal running the services).
- Keep this build **local**. It's tuned for trusted use on your own machine — do
  not expose it to the internet without a dedicated security-hardening pass.
