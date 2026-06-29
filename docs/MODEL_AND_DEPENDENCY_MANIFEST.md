# Sovereign Creative Studio — Model and Dependency Manifest

This document lists every large file and external dependency that is NOT stored in
the GitHub repository. After cloning, install these manually to restore the full
Quick Chain MVP on a new machine.

---

## What Is and Is Not in the Repository

| Category              | In GitHub? | Why                                  |
|-----------------------|-----------|--------------------------------------|
| Source code           | ✓ Yes     | Small text files                     |
| ComfyUI workflows     | ✓ Yes     | Small JSON files                     |
| backend .env.example  | ✓ Yes     | Safe placeholder values only         |
| Piper model files     | ✗ No      | 60 MB each — too large for git       |
| Whisper model files   | ✗ No      | 138 MB — exceeds GitHub 100 MB limit |
| ComfyUI model files   | ✗ No      | 2 GB – 14 GB per model               |
| backend/.env          | ✗ No      | Contains machine-specific paths      |
| Generated outputs     | ✗ No      | User content                         |
| Python .venv          | ✗ No      | Rebuild with pip install             |
| node_modules          | ✗ No      | Rebuild with npm install             |
| .next build           | ✗ No      | Rebuild with local_launcher clean    |

---

## 1. Python Backend

### Version
Python 3.11+ recommended.

### Install
```bat
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

---

## 2. Node.js Frontend

### Version
Node.js 20 LTS recommended.

### Install
```bat
cd frontend
npm install
```

---

## 3. FFmpeg

**Required for:** audio merge (adding voice to video), transcription pre-processing.

**Install:**
- Download from https://ffmpeg.org/download.html
- Or use winget: `winget install Gyan.FFmpeg`
- Set the path in `backend/.env`:
  ```
  FFMPEG_PATH=C:\path\to\ffmpeg.exe
  ```

**Current path on David's machine:**
```
C:\Users\David\AppData\Local\Microsoft\WinGet\Packages\
  Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\
  ffmpeg-8.1.1-full_build\bin\ffmpeg.exe
```

---

## 4. Ollama + Summary Model

**Required for:** AI text summary after transcription.

**Install Ollama:**
https://ollama.com/download

**Pull the summary model:**
```bat
ollama pull qwen3:4b
```

**Configuration in `backend/.env`:**
```
COPY_BACKEND=local-qwen
OLLAMA_QWEN_MODEL=qwen3:4b
```

**Note:** Ollama is optional. Image, video, voice, transcription, and download all
work without it. Only the "Create a Summary" step requires Ollama.

---

## 5. Piper TTS Voice Models

**Required for:** voice narration ("Add Voice" step in Quick Chain).

**Location on new machine:** `backend/storage/models/piper/`

**Files needed (4 voices, ~60 MB each):**

| File                             | Size   | Voice                |
|----------------------------------|--------|----------------------|
| `en_US-lessac-low.onnx`          | 60 MB  | US English (default) |
| `en_US-lessac-low.onnx.json`     | <1 KB  | Config for above     |
| `en_US-lessac-medium.onnx`       | 60 MB  | US English medium    |
| `en_US-lessac-medium.onnx.json`  | <1 KB  | Config for above     |
| `en_US-amy-medium.onnx`          | 60 MB  | US English Amy       |
| `en_US-amy-medium.onnx.json`     | <1 KB  | Config for above     |
| `en_GB-alan-medium.onnx`         | 60 MB  | British English Alan |
| `en_GB-alan-medium.onnx.json`    | <1 KB  | Config for above     |

**Download from:**
https://huggingface.co/rhasspy/piper-voices/tree/main

**Configuration in `backend/.env`:**
```
VOICE_ENABLED=true
VOICE_BACKEND=piper
VOICE_MODEL_NAME=en_US-lessac-low
VOICE_MODEL_PATH=storage/models/piper/en_US-lessac-low.onnx
```

---

## 6. Whisper Transcription Model

**Required for:** video transcription ("Transcribe" step in Quick Chain).

**Location on new machine:** `backend/storage/models/whisper/`

**Auto-downloads on first use.** The backend downloads the model from Hugging Face
automatically when transcription is first requested. No manual step needed, but
the download takes a minute on first run (~140 MB).

**Model:** `Systran/faster-whisper-base` (138 MB)

**Configuration in `backend/.env`:**
```
TRANSCRIPTION_BACKEND=local_whisper
TRANSCRIPTION_MODEL_NAME=base
TRANSCRIPTION_DEVICE=cpu
TRANSCRIPTION_COMPUTE_TYPE=int8
```

---

## 7. ComfyUI

**Required for:** all image and video generation.

**Version:** ComfyUI (latest stable recommended).

**Current install location on David's machine:**
```
C:\Users\David\ComfyUI-Installs\ComfyUI\ComfyUI\
```

**Python venv for ComfyUI:**
```
C:\Users\David\Documents\ComfyUI\.venv\Scripts\python.exe
```

**After installing ComfyUI on a new machine**, update `tools/local_launcher.py`:
```python
COMFY_DIR = Path(r"C:\new-path\ComfyUI")
COMFY_PY  = Path(r"C:\new-path\.venv\Scripts\python.exe")
COMFY_MODELS = Path(r"...")
COMFY_USER   = Path(r"...")
COMFY_BASE   = Path(r"...")
COMFY_INPUT  = Path(r"...")
COMFY_OUTPUT = Path(r"...")
```

---

## 8. ComfyUI Model Files

All model files live inside the ComfyUI shared models directory.

### Image Models (checkpoints)

| Model file                          | Used for                  | Size (approx) |
|-------------------------------------|---------------------------|---------------|
| `krea2_turbo_fp8.safetensors`       | Krea 2 — **Quick Chain**  | ~8 GB         |
| `flux1-dev-fp8.safetensors`         | FLUX.1 Dev (fallback)     | ~8 GB         |
| `flux2-klein-4b.safetensors`        | FLUX.2 Klein 4B           | ~4 GB         |
| `anything-v3.0.safetensors` or similar | SDXL / Illustrious XL | ~2-7 GB       |

### VAE Files

| File                    | Used for              |
|-------------------------|-----------------------|
| `krea2_ae.safetensors`  | Krea 2 VAE            |
| `ae.safetensors`        | FLUX.1 Dev VAE        |

### Video Models

| File                                    | Used for                          | Size   |
|-----------------------------------------|-----------------------------------|--------|
| `ltx-2.3-22b-dev-fp8.safetensors`       | LTX image-to-video — **Quick Chain** | ~22 GB |

### Video Upscale Models

| File                          | Used for                    | Size   |
|-------------------------------|-----------------------------|--------|
| *(check ComfyUI model_manager)* | Video upscale in Quick Chain | ~1-2 GB |

### CLIP / Text Encoder Models

| File                         | Used with            |
|------------------------------|----------------------|
| `clip_l.safetensors`         | FLUX.1, Krea 2       |
| `t5xxl_fp8_e4m3fn.safetensors` | FLUX.1, Krea 2     |

---

## 9. Environment Configuration

Copy `backend/.env.example` to `backend/.env` and fill in:

```ini
# Ports and URLs
COMFYUI_BASE_URL=http://127.0.0.1:8001

# FFmpeg (machine-specific path)
FFMPEG_PATH=C:\path\to\your\ffmpeg.exe

# Voice (Piper TTS)
VOICE_ENABLED=true
VOICE_BACKEND=piper
VOICE_MODEL_NAME=en_US-lessac-low
VOICE_MODEL_PATH=storage/models/piper/en_US-lessac-low.onnx

# Summary (Ollama)
COPY_BACKEND=local-qwen
OLLAMA_QWEN_MODEL=qwen3:4b

# Video
VIDEO_BACKEND=comfyui
COMFYUI_VIDEO_ENGINE=ltx
COMFYUI_VIDEO_WORKFLOW_PATH=workflows/image_to_video.json
COMFYUI_VIDEO_MODEL_NAME=ltx-2.3-22b-dev-fp8.safetensors

# Transcription
TRANSCRIPTION_BACKEND=local_whisper
TRANSCRIPTION_MODEL_NAME=base
TRANSCRIPTION_DEVICE=cpu
TRANSCRIPTION_COMPUTE_TYPE=int8
```

---

## 10. Quick Restore Checklist for New AI Computer

- [ ] Clone repository from GitHub
- [ ] Install Python 3.11+
- [ ] Install Node.js 20 LTS
- [ ] Install ComfyUI, update paths in `tools/local_launcher.py`
- [ ] Install ComfyUI model files (Krea 2, LTX video, etc.)
- [ ] Copy Piper voice models to `backend/storage/models/piper/`
- [ ] Install FFmpeg, update `FFMPEG_PATH` in `backend/.env`
- [ ] Install Ollama, pull `qwen3:4b`
- [ ] Create `backend/.env` from `backend/.env.example`
- [ ] Run `pip install -r requirements.txt` in backend
- [ ] Run `npm install` in frontend
- [ ] Run `python tools/local_launcher.py clean` to build and start
- [ ] Open http://localhost:3000 and run a Quick Chain test
- [ ] Run `python tools/local_launcher.py smoke` to verify all components
