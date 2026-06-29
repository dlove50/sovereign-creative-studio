# Sovereign Creative Studio — Local Startup and Recovery

**Quick Chain MVP — Phase 2.4**

---

## 1. How to Start the App

Open a terminal in the project root and run:

```bat
python tools/local_launcher.py start
```

This starts:
1. **ComfyUI** on port 8001 (image and video generation)
2. **Backend (FastAPI)** on port 8002
3. **Frontend (Next.js production)** on port 3000

Open the app in your browser: **http://localhost:3000**

### Skip ComfyUI (backend + frontend only)

```bat
python tools/local_launcher.py start --skip-comfy
```

Use this if ComfyUI is already running or you are only using transcription/copy features.

### Start and open browser automatically

```bat
python tools/local_launcher.py start --open-browser
```

---

## 2. How to Stop the App

```bat
python tools/local_launcher.py stop
```

This kills the processes listening on ports 3000, 8001, and 8002.

---

## 3. Ports Used

| Service    | Port  | URL                           |
|------------|-------|-------------------------------|
| Frontend   | 3000  | http://localhost:3000         |
| ComfyUI    | 8001  | http://127.0.0.1:8001         |
| Backend    | 8002  | http://127.0.0.1:8002         |
| Ollama     | 11434 | http://127.0.0.1:11434        |

The frontend proxies all `/api/*` requests to the backend on port 8002.

**Important:** The frontend proxy target (8002) is baked into the production build at
compile time. Always use `python tools/local_launcher.py clean` to rebuild — never
run `npx next build` directly, as it will bake port 8000 and cause 500 errors.

---

## 4. What to Do if Krea 2 is Not Ready

The Quick Chain uses **Krea 2 Turbo FP8** for image generation.

**Symptom:** The image model dropdown shows "Setup required" next to Krea 2.

**Fix:**
1. Make sure the Krea 2 model file `krea2_turbo_fp8.safetensors` is present in your
   ComfyUI checkpoints directory.
2. Make sure ComfyUI is running on port 8001.
3. Restart ComfyUI if you recently added the model file.

See `docs/MODEL_AND_DEPENDENCY_MANIFEST.md` for exact file names and locations.

---

## 5. What to Do if Video Generation Fails

**Symptom:** The video step gets stuck or returns an error.

**Fix:**
1. Make sure ComfyUI is running: http://127.0.0.1:8001
2. Make sure the LTX video model is installed in ComfyUI models:
   `ltx-2.3-22b-dev-fp8.safetensors`
3. Check the ComfyUI logs for GPU memory errors.
4. If out of VRAM, close other GPU-intensive programs and retry.

---

## 6. What to Do if Voice Preview Fails

**Symptom:** Clicking "Preview Voice" shows an error or the audio player does not appear.

**Fix:**
1. Make sure Piper voice model files are in `backend/storage/models/piper/`.
   Expected files: `en_US-lessac-low.onnx`, `en_US-lessac-medium.onnx`,
   `en_US-amy-medium.onnx`, `en_GB-alan-medium.onnx` (plus `.onnx.json` for each).
2. Make sure FFmpeg is installed and the path is set in `backend/.env`:
   ```
   FFMPEG_PATH=C:\path\to\ffmpeg.exe
   ```
3. Run the smoke test to check readiness:
   ```bat
   python tools/local_launcher.py smoke
   ```

---

## 7. What to Do if Summary Fails (Ollama Down)

**Symptom:** Clicking "Create a Summary" shows an amber error: *"Summary engine is not running."*

**Fix:**
1. Start Ollama in a terminal:
   ```bat
   ollama serve
   ```
2. The app will show the error message and let you continue without a summary.
   Your transcript is saved regardless — only the AI summary requires Ollama.
3. After starting Ollama, try "Create a Summary" again.

**Note:** Ollama is optional. Image generation, video, voice, transcription, and
downloads all work without Ollama. Only the summary step requires it.

---

## 8. What to Do if the Frontend Proxy Points to Port 8000 Instead of 8002

**Symptom:** The frontend returns HTTP 500 errors for API calls (especially on `/api/generations/presets`).

**Cause:** The production frontend build bakes the backend URL at compile time.
If `npx next build` is run without `BACKEND_ORIGIN`, it defaults to port 8000.

**Fix:**
```bat
python tools/local_launcher.py clean
```

This stops the frontend, deletes `.next`, rebuilds with `BACKEND_ORIGIN=http://127.0.0.1:8002`,
and restarts. Takes about 3–4 minutes.

---

## 9. How to Run the Smoke Test

```bat
python tools/local_launcher.py smoke
```

Checks:
- Backend health
- Frontend health
- Proxy target (should be port 8002)
- Krea 2 preset readiness
- Audio merge (Piper + FFmpeg) readiness
- Ollama availability
- Six MVP routes: /create, /videos, /video-to-text, /assets-library, /chain, /status

---

## 10. How to Run the Full Playwright Test

Make sure Ollama is running and warm (needed for the Summarize step):

```bat
ollama run qwen3:4b "hi"
```

Then run:

```bat
python tools/local_launcher.py smoke --full
```

Or run Playwright directly:

```bat
cd frontend
npx playwright test e2e/quick-chain.spec.ts --reporter=line
```

The full test exercises the complete Quick Chain flow:
Krea 2 image → video → upscale → voice select → voice preview → add voice →
transcribe → summarize → download all.

Expected: **2/2 tests pass** (full flow + regression).

---

## 11. Where Backups Are Stored

Backups are ZIP archives stored in the parent directory:

```
C:\Users\David\Documents\Codex\sovereign_*.zip
```

They are created with Python's `zipfile` module and exclude:
- `.next/` (rebuild with clean)
- `node_modules/` (run `npm install`)
- `backend/.venv/` (run `pip install -r requirements.txt`)
- `backend/storage/` (model files and generated outputs)

---

## 12. Current Stable Backup

```
sovereign_quick_chain_mvp_complete_YYYYMMDD_HHMMSS.zip
```

(Created at the end of Phase 2.4.)

Previous stable backup:
```
sovereign_phase_2_3_ui_polished_20260629_145455.zip
```

---

## 13. How to Clone from GitHub onto a New Computer

```bat
git clone https://github.com/YOUR_USERNAME/sovereign-creative-studio.git
cd sovereign-creative-studio
```

Then follow the install steps in `docs/MODEL_AND_DEPENDENCY_MANIFEST.md` to
install the large model files that are not stored in the repository.

---

## 14. What Still Needs to Be Installed Manually on the New AI Computer

After cloning, the following must be installed separately:

### ComfyUI
- Install ComfyUI and configure it to run on port 8001.
- Update the paths in `tools/local_launcher.py` (COMFY_DIR, COMFY_PY, etc.) to
  match the new machine's directory layout.

### Krea 2 Model Files
- `krea2_turbo_fp8.safetensors` — in ComfyUI checkpoints directory
- `krea2_ae.safetensors` — in ComfyUI VAE directory
- Exact paths are described in `docs/MODEL_AND_DEPENDENCY_MANIFEST.md`

### Other Image Models (optional)
- `flux1-dev-fp8.safetensors`, `flux2-klein-4b.safetensors`, etc.

### LTX Video Model
- `ltx-2.3-22b-dev-fp8.safetensors` — in ComfyUI models/video_models/

### Video Upscale Model
- Check `docs/MODEL_AND_DEPENDENCY_MANIFEST.md` for the upscale model file

### Piper Voice Models
- Place all 4 `.onnx` and `.onnx.json` files in `backend/storage/models/piper/`
- Download from: https://huggingface.co/rhasspy/piper-voices

### Whisper Model (auto-downloads on first use)
- Stored in `backend/storage/models/whisper/`
- Downloads automatically when you first use transcription

### FFmpeg
- Install FFmpeg (https://ffmpeg.org/) and add the `ffmpeg.exe` path to `backend/.env`

### Ollama + qwen3:4b
- Install Ollama (https://ollama.com/)
- Pull the model: `ollama pull qwen3:4b`

### Python Backend Dependencies
```bat
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### Node.js Frontend Dependencies
```bat
cd frontend
npm install
```

### Environment Files
- Copy `backend/.env.example` to `backend/.env` and fill in machine-specific paths
- Copy `frontend/.env.local.example` to `frontend/.env.local` (if needed)

### First Run
```bat
python tools/local_launcher.py clean
```

This builds the production frontend with the correct backend port (8002) baked in.
