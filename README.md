# Sovereign Creative Studio

## Sovereign Creative Studio V1 Release Candidate

Sovereign Creative Studio is in **V1 Release Candidate** status for private,
local family use. Stop adding features unless David explicitly approves a new
phase; the current goal is stable normal use, backups, and safe recovery.

Completed V1 capabilities include local ComfyUI/Flux image generation, Flux-
Kontext product scenes, local ComfyUI/LTX video generation, local Whisper
video-to-text, local Qwen copy/summaries, local Piper TTS voice generation, Wan
InfiniteTalk talking avatars, Asset Library, Campaigns, Project Workspace, Brand
Kits, Creative Briefs, Production Studio, Film Studio, Storyboard Studio,
exports, family users, credits/ledger, Job Monitor, Storage Cleanup, backups,
Model Manager, Workflow Manager, Status, and optional provider shells.

Default local-first stack:

| Area | V1 default |
| --- | --- |
| Base image generation | `GENERATOR_BACKEND=comfyui` |
| Product scenes | `PRODUCT_SCENE_BACKEND=comfyui`, `PRODUCT_SCENE_MODEL=flux-kontext`, `COMFYUI_PRODUCT_SCENE_MODE=segmented_composite_polished` |
| Copy/summaries | `COPY_BACKEND=local-qwen` |
| Video | `VIDEO_BACKEND=comfyui`, `COMFYUI_VIDEO_ENGINE=ltx` |
| Transcription | `TRANSCRIPTION_BACKEND=local_whisper` |
| Voice | `VOICE_BACKEND=piper` |
| Talking avatar | `AVATAR_BACKEND=comfyui_wan_infinite_talk`, `AVATAR_WAN_PRESET=tiny_test` |

Optional premium providers are **not defaults**: Seedance/C-Dance and OpenAI are
admin-enabled only from `/admin/integrations`, require server-side API keys, and
remain off unless David configures them.

V1 credit costs:

| Feature | Credits charged on success |
| --- | ---: |
| Local LTX video | 10 |
| Optional Seedance/C-Dance video | 30 |
| Local Whisper transcription | 5 |
| Transcript/Qwen summary | 2 |
| Piper voice generation | 2 |
| Wan InfiniteTalk avatar video | 15 |

Failed, cancelled, setup-required, and OOM jobs charge **0 credits**.

Avatar preset guidance: keep `AVATAR_WAN_PRESET=tiny_test` as the default for
normal family use. `low_vram`, `balanced`, and `quality` are validated and
available, but `quality` remains warning-labeled because it takes longer and uses
more GPU memory. Do not escalate avatar settings further without a new approved
phase.

Startup and recovery:

- Normal startup: `Start-Sovereign-Creative-Studio.bat`.
- Production frontend recovery/port cleanup: `python tools/local_launcher.py clean`.
- Expected ports: frontend `http://localhost:3000`, backend
  `http://127.0.0.1:8000`, ComfyUI `http://127.0.0.1:8001`.

Backup and model preservation: app backups live in `backend/storage/backups/`
and include the SQLite DB, app storage, workflows, and a manifest. Backups
exclude secrets and large external ComfyUI model files. Preserve
`C:\Users\David\ComfyUI-Shared\models` separately. The Wan InfiniteTalk manifest
is `backend/storage/model_manifest_wan_infinite_talk.json`.

Security warning: do **not** expose this app publicly until owner fallback,
signup, network binding, and security settings are reviewed and hardened.

A private, local, full-capability AI creative studio for David and family. By
default it runs entirely on this machine — no cloud, no public signup, no
external billing. Optional premium providers can be enabled by David/Admin only.

## Full Local Production Mode

This is the normal, default operating mode. The studio runs the real local model
stack on this machine:

- **Product scenes:** ComfyUI · `flux-kontext` · `segmented_composite_polished`
- **Image/art generation:** Local ComfyUI / Flux by default, with optional
  OpenAI Image API as an admin-enabled premium provider
- **Copy:** local Qwen (`qwen3:4b`) via Ollama
- **Video:** ComfyUI · LTX — Image→Video, Text→Video, Video→Video, Video Upscale,
  and Video Extension are all wired and operational
- **Video billing:** Local LTX costs 10 credits per successful video job;
  optional Seedance/C-Dance costs 30 credits per successful job; failed jobs are
  not charged; an admin can add/remove credits for any family member at any time
- **Operational tools:** Admin Dashboard, Job Monitor, Credit Ledger, Backup &
  Recovery, Storage Management, Asset Library, Production Export, Workflow Manager

A built-in **mock fallback** remains available for emergencies (e.g. if ComfyUI
or Ollama is offline), but it is a fallback — not the default. `/status` shows the
current mode and the live stack.

The app is a small local monorepo: a FastAPI backend, a Next.js frontend, SQLite
for persistence, and local filesystem storage for generated assets.

## Accounts, roles & optional providers

**Normal startup:** `Start-Sovereign-Creative-Studio.bat` (ComfyUI + backend +
frontend). On the owner's machine you are the local owner/admin by default; family
members can **sign up / log in** for their own accounts and credits.

**Owner fallback safety:** `OWNER_FALLBACK_ENABLED=true` is a local/private
convenience flag. It lets no-cookie requests on David's own machine fall back to
the seeded owner/admin so the studio remains easy to use locally. Disable it
before any public exposure (`OWNER_FALLBACK_ENABLED=false`). Do **not** expose
the app publicly while owner fallback is enabled, because anonymous requests can
act as the local owner/admin in that mode.

**Accounts:** `/signup` and `/login` create real accounts (PBKDF2-hashed passwords,
HTTP-only signed session cookies — no plaintext passwords). Signup makes a
`family_user`. Configurable via `.env`: `PUBLIC_SIGNUP_ENABLED` (default true),
`DEFAULT_SIGNUP_CREDITS` (default 20), `SIGNUP_REQUIRES_ADMIN_APPROVAL` (default false).

**Roles:** `owner_admin` (full access: users, credits, jobs, backups, storage,
model/workflow manager, status, provider integrations), `family_user` (simplified
creator dashboard — their own projects/assets/jobs/credits, creation tools only,
no admin or backend settings, no provider keys, no impersonation), `guest`
(limited, no admin). A logged-in user is automatically the active user; only an
admin can impersonate via the Admin tools. Family users cannot impersonate by
changing headers — the backend ignores `X-SCS-Family-User-Id` for non-admins.

**Local stack is the default engine:** ComfyUI / Flux-Kontext (images & product
scenes), local Qwen (`qwen3:4b`) copy, and ComfyUI/LTX video. This never changes
unless an admin explicitly opts into a premium provider.

**Optional premium providers (admin only, `/admin/integrations`):**
- **Seedance / C-Dance 2.0 API** — optional premium cloud video provider for
  Text -> Video and Image -> Video in the first pass.
- **OpenAI API** — optional premium cloud image/art provider for Text -> Image
  and Image Edit in the first pass.

These are off by default and require an admin to add an API key and enable them.
External API usage may cost money. **API keys belong to David/Admin only** — they
are stored server-side in `backend/storage/secrets/` (gitignored), never returned
to or stored in the browser, never logged, masked in the UI, and **excluded from
backups**. Do not paste API keys into chat logs, screenshots, or the frontend.

Normal users only ever see the simplified creator tools; the admin manages users,
credits, providers, backups, storage, and models.

## Avatar & Voice

`/avatars` is a local-first foundation for talking avatars and voices:

- **Photo to Avatar / Video to Avatar:** upload a photo or short video you own to
  save a reusable avatar asset.
- **Custom Voices + voice greeting:** save preset voices and generate a **real
  local spoken greeting** with Piper (Phase 16B).
- **Preset greeting:** "Welcome, let's create something amazing!"

### Local voice / TTS (Phase 16B — real, offline)

Voice greetings are generated **on this machine, fully offline**, using
[Piper](https://github.com/OHF-Voice/piper1-gpl) via the `piper-tts` Python
package. Click **"Create a voice greeting"** on `/avatars` to synthesize the
greeting to a local `.wav` you can play or download; the result also appears in
the Asset Library. No cloud TTS is used or required.

**Piper setup (Windows):**

```powershell
# 1. Install the package into the backend venv (onnxruntime is already present)
backend\.venv\Scripts\python -m pip install piper-tts

# 2. Download a small voice model into the model dir (CPU-friendly, ~63 MB)
backend\.venv\Scripts\python -m piper.download_voices en_US-lessac-low --data-dir backend\storage\models\piper
```

**Voice model location:** `backend/storage/models/piper/` (e.g.
`en_US-lessac-low.onnx` + its `.onnx.json`). Point `VOICE_MODEL_PATH` at the
`.onnx` file, or leave it empty to auto-discover the first model in that folder.

**Switching backends** (in `backend/.env`):

- `VOICE_BACKEND=mock` — no audio; UI shows "Local voice setup required" (default
  if Piper isn't installed).
- `VOICE_BACKEND=piper` — real local audio when `piper-tts` + a voice model are
  present. Set `VOICE_MODEL_NAME` / `VOICE_MODEL_PATH` to your model.

**CPU/GPU & offline:** the `-low` voice runs comfortably on CPU and works with no
network connection. Larger Piper voices (`-medium`/`-high`) sound better but are
slower on CPU.

### Talking avatar (Phase 16C — local-first, Wan InfiniteTalk)

`/avatars` → **Create Talking Avatar**: pick a photo avatar + a generated voice,
and the backend builds a talking-avatar MP4 **locally** via ComfyUI's
`WanInfiniteTalkToVideo` (audio-driven Wan video). Local-first by design — no
cloud avatar service is used or default.

**Current provider state:** the ComfyUI nodes (`WanInfiniteTalkToVideo`, MediaPipe
face nodes, audio encode/load) and first-pass model weights are installed. The
Phase 16E smoke test generated a real local MP4 through `/api/avatar-jobs/talking`
using a tiny 256x256 / 41-frame / 2-step Wan InfiniteTalk workflow. Setup-required
and failed jobs still charge **0 credits**; completed real MP4 jobs charge
`CREDITS_PER_AVATAR_VIDEO`.

**Required model/workflow to enable Wan InfiniteTalk** (set in `backend/.env`):

- Workflow: `backend/workflows/avatar_wan_infinite_talk.json` (ships as a scaffold;
  validate it in the ComfyUI editor once weights are present).
- A **Wan 2.x video diffusion** model → `AVATAR_WAN_MODEL_NAME` (diffusion_models).
- The **InfiniteTalk** `model_patch` → `AVATAR_INFINITETALK_PATCH_NAME` (model_patches).
- A **wav2vec2 audio encoder** → `AVATAR_AUDIO_ENCODER_NAME` (audio_encoders).
- A **Wan umt5** text encoder (text_encoders) and a **Wan VAE** (vae).

These are large (tens of GB combined) and are **not** auto-downloaded. Phase 16E
installed the approved first-pass set into the shared ComfyUI model folders.

### Talking avatar model install plan (Phase 16D approval gate)

Do **not** download these automatically. This is the approved-source checklist used
for Phase 16E. The current local check found:

- ComfyUI reachable on `http://127.0.0.1:8001`.
- CUDA active on an RTX 5070 Ti with roughly 16 GB VRAM.
- `WanInfiniteTalkToVideo`, audio loader/encoder nodes, model patch loader, Wan
  video nodes, MediaPipe face nodes, `CreateVideo`, and `SaveVideo` present.
- Loader files installed and visible: audio encoder, Wan diffusion model,
  InfiniteTalk patch, Wan umt5 text encoder, and Wan VAE.
- Available C: drive space at inspection time: about 885 GB free.

Recommended minimal native-ComfyUI install set:

| Component | Trusted source | Exact file | Expected folder | Approx size | Loader/env |
| --- | --- | --- | --- | ---: | --- |
| Wan image-to-video diffusion | `Comfy-Org/Wan_2.1_ComfyUI_repackaged` | `wan2.1_i2v_480p_14B_fp8_scaled.safetensors` | `C:\Users\David\ComfyUI-Shared\models\diffusion_models\` | ~16.4 GB | `UNETLoader`; `AVATAR_WAN_MODEL_NAME=wan2.1_i2v_480p_14B_fp8_scaled.safetensors` |
| InfiniteTalk patch | `MeiGen-AI/InfiniteTalk` | `comfyui/infinitetalk_single.safetensors` | `C:\Users\David\ComfyUI-Shared\models\model_patches\` | ~2.53 GB | `ModelPatchLoader`; `AVATAR_INFINITETALK_PATCH_NAME=infinitetalk_single.safetensors` |
| Audio encoder | `TencentGameMate/chinese-wav2vec2-base`, revision `refs/pr/1` | `model.safetensors` | `C:\Users\David\ComfyUI-Shared\models\audio_encoders\` | ~363 MB | `AudioEncoderLoader`; recommended local name `chinese-wav2vec2-base.safetensors` |
| Wan text encoder | `Comfy-Org/Wan_2.1_ComfyUI_repackaged` | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `C:\Users\David\ComfyUI-Shared\models\text_encoders\` | ~6.74 GB | `CLIPLoader` with `type=wan` |
| Wan VAE | `Comfy-Org/Wan_2.1_ComfyUI_repackaged` | `wan_2.1_vae.safetensors` | `C:\Users\David\ComfyUI-Shared\models\vae\` | ~254 MB | `VAELoader` |

Estimated minimal download footprint is about **26.3 GB** before cache/temporary
files. Keep at least **40 GB free** on the model drive. The original upstream
Wan-AI sharded base model is much larger; use the ComfyUI repackaged single-file
FP8 model first unless there is a specific reason to validate the original shard
layout.

Installed Phase 16E files:

- `C:\Users\David\ComfyUI-Shared\models\diffusion_models\wan2.1_i2v_480p_14B_fp8_scaled.safetensors`
- `C:\Users\David\ComfyUI-Shared\models\model_patches\infinitetalk_single.safetensors`
- `C:\Users\David\ComfyUI-Shared\models\audio_encoders\chinese-wav2vec2-base.safetensors`
- `C:\Users\David\ComfyUI-Shared\models\text_encoders\umt5_xxl_fp8_e4m3fn_scaled.safetensors`
- `C:\Users\David\ComfyUI-Shared\models\vae\wan_2.1_vae.safetensors`

Phase 16E validation notes:

- ComfyUI loader visibility: passed for all five required model groups.
- `/api/avatars/readiness`: `ready: true`.
- First 512x512 / 81-frame / CFG 5 scaffold attempt failed safely with a Wan
  MultiTalk audio-attention shape mismatch and charged 0 credits.
- The working smoke scaffold uses `cfg: 1.0`, `steps: 2`, `width: 256`,
  `height: 256`, and `length: 41` to avoid CFG/audio batch mismatch and keep VRAM
  low for first-pass validation.
- Completed smoke MP4:
  `backend/storage/avatar_videos/b6f482152b2f4b9fb489be029dff5add.mp4`.

If reinstalling or replacing model files later:

1. Download only from the trusted sources above.
2. Place files in the expected ComfyUI model folders.
3. Restart ComfyUI.
4. Recheck `/api/avatars/readiness` and ComfyUI `/object_info` loader dropdowns.
5. Set `AVATAR_WAN_MODEL_NAME`, `AVATAR_INFINITETALK_PATCH_NAME`, and
   `AVATAR_AUDIO_ENCODER_NAME` to the exact loader dropdown names.
6. Validate `backend/workflows/avatar_wan_infinite_talk.json` in the ComfyUI
   editor with a tiny test before enabling family use.

Hardware expectation: this is a heavy Wan 14B path. The RTX 5070 Ti 16 GB should
be treated as **borderline but plausible** for short, low-resolution tests with
FP8 weights, offload/low-memory behavior, and small frame counts. Close other GPU
apps first. Do not expect long clips, 720p/1080p, or fast generation at this stage.

Alternative local avatar engines reviewed:

- **LivePortrait**: lighter and strong for portrait animation, but not a direct
  Piper WAV lip-sync path without an additional driving-video or audio pipeline.
- **SadTalker**: mature and lighter for audio-driven single-image talking heads,
  but older quality than Wan/InfiniteTalk.
- **MuseTalk**: strong lip-sync focused on the face/mouth region; useful fallback
  candidate if Wan is too heavy.
- **Wav2Lip**: lightweight lip-sync research tool, but upstream use is
  non-commercial/personal-research oriented and quality is not a full avatar
  generation path.
- **Hallo**: MIT-licensed audio-driven portrait animation candidate, but not yet
  wired into this app or current ComfyUI setup.

Recommendation: keep `AVATAR_BACKEND=comfyui_wan_infinite_talk` enabled for local
tiny talking-avatar tests, keep the conservative smoke workflow defaults, and only
increase resolution, frames, or steps after a manual VRAM check. Setup-required
and failed jobs must continue to charge 0 credits.

### Talking avatar quality presets (Phase 16F)

`/avatars` now exposes named Wan InfiniteTalk quality presets. Family users can
select a preset, but they cannot send arbitrary width/frame/step values. Raw
settings remain server-controlled through environment variables.

| Preset | UI label | Width/height | Frames | Steps | CFG | Status |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `tiny_test` | Fast test | 256x256 | 41 | 2 | 1.0 | Default verified smoke preset |
| `low_vram` | Better quality | 320x320 | 41 | 4 | 1.0 | Cautious next step |
| `balanced` | Balanced | 384x384 | 61 | 6 | 1.0 | Test only after Low VRAM succeeds |
| `quality` | High quality | 512x512 | 81 | 8 | 1.0 | Experimental; may OOM on 16 GB VRAM |

The earlier 512x512 / 81-frame / CFG 5 attempt failed safely with a Wan
conditioning/audio-attention shape mismatch. For now, all presets keep CFG at
`1.0`; raise quality through resolution, frames, and steps only after a direct
ComfyUI validation.

Optional server-side overrides:

```env
AVATAR_WAN_PRESET=tiny_test
AVATAR_WAN_WIDTH=
AVATAR_WAN_HEIGHT=
AVATAR_WAN_FRAMES=
AVATAR_WAN_STEPS=
AVATAR_WAN_CFG=
AVATAR_WAN_MAX_RETRIES=0
```

`AVATAR_WAN_MAX_RETRIES` stays `0` by default: if ComfyUI OOMs or rejects the
workflow, the job fails cleanly, charges 0 credits, and does not retry into more
GPU pressure.

External model manifest:
`backend/storage/model_manifest_wan_infinite_talk.json` records the currently
installed Wan/InfiniteTalk file names, paths, sizes, and timestamps. App backups
do **not** include the large external model files under
`C:\Users\David\ComfyUI-Shared\models`; back up that folder separately before
reinstalling ComfyUI or moving the studio.

**Switching:** `AVATAR_BACKEND=placeholder` (default — setup_required everywhere) →
`AVATAR_BACKEND=comfyui_wan_infinite_talk` (real generation once weights exist).

**Credits:** voice generation `CREDITS_PER_VOICE_GENERATION` (default 2), avatar
video `CREDITS_PER_AVATAR_VIDEO` (default 15). Charged **only on success** —
setup-required and failed jobs never cost credits; insufficient credits block
before generation. Avatar charges write a ledger row (`transaction_type:
generation_charge`, `related_feature: avatar_video`, `amount: -15`, note includes
the provider/model). Completed avatar videos appear in the **Asset Library** as
`avatar_video` (AI-generated), owned by the creating user (admin sees all).

**Privacy:** local TTS + local avatar generation do not contact any cloud service;
your text, audio, and video never leave the machine.

**Consent & safety:** only create avatars/voices from media you have the rights to
use; generated avatar videos are AI-generated, **not real recordings**, and must not
be presented as genuine or used to impersonate anyone. **Voice cloning is not
enabled in this phase** — only preset/local TTS voices; uploading someone's voice
sample to clone it is intentionally disabled.

**Config:** `AVATAR_ENABLED`, `AVATAR_BACKEND` (default `placeholder`),
`AVATAR_WAN_WORKFLOW_PATH`, `AVATAR_WAN_MODEL_NAME`, `AVATAR_INFINITETALK_PATCH_NAME`,
`AVATAR_AUDIO_ENCODER_NAME`, `VOICE_ENABLED`, `VOICE_BACKEND` (default `mock`, set to
`piper` in `.env`), `VOICE_MODEL_NAME`, `VOICE_MODEL_PATH`.

**Troubleshooting:**
- *"Local voice setup required" / Piper missing* — run the Piper setup above and set
  `VOICE_BACKEND=piper`.
- *Voice model missing* — download a voice into `backend/storage/models/piper/` and
  set `VOICE_MODEL_PATH` (or `VOICE_MODEL_NAME`).
- *No audio output* — confirm the `.onnx` + `.onnx.json` pair exist and the greeting
  returned `ready`; failed synthesis charges 0 and surfaces an error.
- *"Avatar animation model setup required"* — expected until the Wan/InfiniteTalk
  weights are installed; the admin readiness panel lists exactly what's missing.
- *ComfyUI not reachable* — start ComfyUI (the launcher starts it on `:8001`); the
  avatar readiness panel shows `ComfyUI reachable: false`.
- *Missing `WanInfiniteTalkToVideo` node* — install/update the Wan video node pack
  in ComfyUI.
- *Missing model files* — install the Wan diffusion model, InfiniteTalk patch,
  audio encoder, umt5 text encoder, and Wan VAE; set the matching `AVATAR_*` env vars.
- *Missing workflow* — ensure `backend/workflows/avatar_wan_infinite_talk.json` exists.
- *No face detected / no audio* — use a clear front-facing photo and a generated
  voice that has audio (create a voice greeting first).
- *Insufficient credits* — ask the admin to add credits (`/admin`).
- *Slow CPU generation* — Wan video is GPU-heavy; expect long runs on CPU.

## Image Quality Modes

The **Create** page has an **Image Quality Mode** dropdown that picks both a local
model and a subject-tuned prompt enhancer from one choice. Quality is a model *and*
a prompt-strategy problem — a better model alone will not fix a face that is tiny in
a wide scene, so the face/animal modes add framing and (planned) refinement.

Modes never hard-block: each resolves to the **best installed model** in its
preference list, and the safe local default is always available. The UI shows which
model is actually used and whether the recommended one needs setup. No cloud
provider is ever the default.

| Mode | Recommended model | Best for |
|------|-------------------|----------|
| Realistic / General | FLUX.2 Klein 4B | everyday realistic images and scenes |
| Portrait / Human Face | FLUX.2 Klein 4B (or FLUX.1-dev) | people; correct facial anatomy, symmetrical eyes, skin texture, face large in frame |
| Animal / Pet Portrait | FLUX.2 Klein 4B | pets/animals as the clear main subject (fills 35–45% of frame, realistic muzzle/eyes/fur) |
| Product Shot | FLUX / FLUX-Kontext product workflow | product hero shots, studio lighting, clean backgrounds |
| Anime / Illustration | Illustrious XL (anime SDXL) | anime/illustration; falls back to current local + anime prompt if not installed |
| Cartoon / 3D Character | FLUX.2 Klein 4B (or stylized SDXL) | family-friendly cartoon, Pixar-like 3D, children's-book style |
| Fallback (SDXL) | SDXL Base + Refiner | stable mature fallback when Flux is unavailable or too slow |

**Model readiness today:** FLUX.1-dev (FP8) and SDXL Base are **installed and ready**,
so Portrait/Animal/Realistic already render at higher quality than the old SD1.5
default. **FLUX.2 Klein 4B** (the recommended model) and **Illustrious XL** (anime)
are **not installed yet** → those modes report "Recommended model not installed —
using <fallback>" and still produce a result with the best ready model. FLUX.2-**dev**
(32B) is intentionally not offered — too heavy for 16 GB VRAM / 32 GB RAM.

**Subject-size guidance.** For the Portrait and Animal modes the UI shows: *"Small or
distant faces may distort — make the subject large in the frame."* If your prompt
reads like a wide landscape with a small subject, an extra inline warning appears.
Example dog prompt that works well:

> Photorealistic golden retriever walking toward the camera on a gravel path, dog is
> the main subject and fills 35–45% of the image, clear face visible, realistic
> canine facial anatomy, symmetrical eyes, natural muzzle proportions, detailed
> golden fur around the face, relaxed happy expression, soft summer sunlight, shallow
> depth of field, farmhouse and trees softly blurred in the background.

**Face / Subject Refine (architecture only — coming soon).** A better model still
won't fully fix crooked eyes, warped mouths, weak dog snouts, bad hands, or blurry
small faces. The planned pipeline is: generate → detect face/subject → inpaint/refine
that region → upscale. The architecture and a disabled **"Face / Subject Refine —
coming soon"** control are in place; enable with `FACE_REFINE_ENABLED=true` once the
detector + `face_subject_refine.json` workflow are installed.

**To enable the recommended models (admin, optional, large downloads):**
- **FLUX.2 Klein 4B** → put the weights in ComfyUI `diffusion_models` as
  `flux2-klein-4B.safetensors` (or set `FLUX2_KLEIN_MODEL_NAME`); validate
  `text_to_image_flux2_klein.json` in the ComfyUI editor.
- **Illustrious XL / anime SDXL** → put the checkpoint in ComfyUI `checkpoints`
  (name containing `illustrious`/`anime`); `text_to_image_illustrious.json` then runs.

**Config:** `IMAGE_QUALITY_PRESET` (default `local_fast`), `IMAGE_WORKFLOW_FLUX2_KLEIN`,
`IMAGE_WORKFLOW_FLUX1_DEV`, `IMAGE_WORKFLOW_SDXL`, `IMAGE_WORKFLOW_ILLUSTRIOUS`,
`FLUX2_KLEIN_MODEL_NAME`, `FACE_REFINE_ENABLED`, `IMAGE_WORKFLOW_FACE_REFINE`.

## Local Image Edit / Reference Image Editing

The **Create** page now supports local **Image Edit** through ComfyUI using
Qwen-Image-Edit 2509. Local ComfyUI remains the default provider; OpenAI Image
Edit is still optional and only becomes selectable when configured in Admin
Integrations.

Use **Image Edit** when you want to upload or select an existing image and
describe an instruction-based edit, for example:

- "Make the golden retriever look like a cute polished 3D cartoon character
  while preserving the dog's pose and face structure."
- "Improve the lighting and make this image look like a professional
  studio-quality portrait while preserving the subject identity and face."

The local workflow is:

`backend/workflows/image_edit_qwen_2509.json`

It uses these installed ComfyUI files:

| Component | File | Local path |
|-----------|------|------------|
| Qwen edit diffusion model | `qwen_image_edit_2509_fp8_e4m3fn.safetensors` | `C:\Users\David\Documents\ComfyUI\models\diffusion_models` |
| Qwen2.5-VL text encoder | `qwen_2.5_vl_7b_fp8_scaled.safetensors` | `C:\Users\David\Documents\ComfyUI\models\text_encoders` |
| Qwen image VAE | `qwen_image_vae.safetensors` | `C:\Users\David\Documents\ComfyUI\models\vae` |

Readiness is reported by `GET /api/generations/modes`. Local Image Edit is ready
only when ComfyUI is reachable, the workflow exists, `TextEncodeQwenImageEdit`
is present, and all three Qwen model files appear in the matching ComfyUI loader
dropdowns.

Source images must be local storage URLs such as `/storage/uploads/example.png`
or `/storage/generated/example.png`; the backend safely resolves them under
`backend/storage`, uploads the image to ComfyUI's input endpoint, injects the
uploaded filename into `LoadImage`, and saves the edited result back under
`backend/storage`.

Successful local edits charge the normal image generation cost
(`CREDITS_PER_GENERATION`, default `5`). Failed setup/validation paths, including
missing source images, do not create fake output and do not charge credits.

**Config:** `COMFYUI_IMAGE_EDIT_WORKFLOW_PATH`
(default `workflows/image_edit_qwen_2509.json`), `GENERATOR_BACKEND=comfyui`,
`COMFYUI_BASE_URL=http://127.0.0.1:8001`.

## What's Included

- Next.js dashboard shell with Projects, Create, and Gallery pages
- FastAPI backend with SQLite and local file storage
- Models for users, projects, credits, credit transactions, and generations
- Lightweight in-process generation queue with `queued`, `running`, `completed`,
  and `failed` statuses
- Product image uploads associated with projects
- Mock background-removal processing with `uploaded`, `processing`, `completed`,
  and `failed` statuses
- Product ad scene generation from uploaded assets with simple presets
- AI Copy Studio: marketing copy (descriptions, captions, ads, hooks, SEO titles)
  with selectable tone, via mock templates or a real LLM (OpenAI / Ollama)
- Campaign presets: launch a coordinated product scene + copy from one preset
- Asset collections: group multiple product uploads and launch collection-wide
  campaign bundles from one creative brief
- Production Studio: assemble storyboards, shots, generated videos, and export
  planning packages for video production
- Storyboard Studio: plan multi-scene shot sequences, continuity notes, and
  exportable storyboard shot lists
- Real ComfyUI/LTX video: turn a completed scene or prompt into MP4 clips across
  all five modes (Image→Video, Text→Video, Video→Video, Upscale, Extension);
  mock fallback and guarded Wan 2.2 readiness reporting remain available
- Exports: download scene images, copy `.txt`, videos, and campaign `.zip` bundles
- Private local Admin Dashboard for service health, workflow safety, family users,
  credits, recent jobs, and failed jobs
- One-command Windows run scripts, a `/status` page, and `/api/status` summary
- Mock generator that writes local SVG placeholder assets
- ComfyUI image generator adapter using the same backend interface
- Alembic database migrations (no DB resets on schema change)
- Credit deduction per completed generation, recorded in the ledger

Deliberately out of scope (private local app): Redis, Celery, PostgreSQL, public
authentication/signup, real payments/billing, and cloud deployment.

## Tech Stack

| Layer    | Choice                                           |
| -------- | ------------------------------------------------ |
| Frontend | Next.js 14 App Router, Tailwind CSS, shadcn/ui   |
| Backend  | FastAPI, SQLAlchemy 2.0                          |
| Storage  | SQLite and local filesystem (`backend/storage/`) |
| Engine   | Mock generator or ComfyUI image adapter          |

## Project Structure

```text
sovereign-creative-studio/
|-- start-backend.ps1        # run scripts (Windows)
|-- start-frontend.ps1
|-- start-all.ps1
|-- run-tests.ps1
|-- backend/
|   |-- .env.example
|   |-- app/
|   |   |-- main.py
|   |   |-- config.py
|   |   |-- startup.py        # startup config checks
|   |   |-- database.py
|   |   |-- models.py
|   |   |-- schemas.py
|   |   |-- deps.py
|   |   |-- seed.py
|   |   |-- generators/
|   |   |   |-- base.py
|   |   |   |-- mock.py
|   |   |   |-- comfyui.py
|   |   |   `-- __init__.py
|   |   |-- background_removal/
|   |   |   |-- base.py
|   |   |   |-- mock.py
|   |   |   |-- real.py
|   |   |   `-- __init__.py
|   |   |-- product_scene_generators/
|   |   |   |-- base.py
|   |   |   |-- mock.py
|   |   |   |-- comfyui.py
|   |   |   `-- __init__.py
|   |   |-- copy_generators/
|   |   |   |-- base.py
|   |   |   |-- mock.py
|   |   |   |-- openai.py
|   |   |   |-- ollama.py
|   |   |   |-- prompt.py
|   |   |   `-- __init__.py
|   |   |-- video_generators/
|   |   |   |-- base.py
|   |   |   |-- comfyui.py
|   |   |   |-- mock.py
|   |   |   `-- __init__.py
|   |   |-- presets.py           # static campaign presets
|   |   |-- services/
|   |   |   |-- asset_jobs.py
|   |   |   |-- product_scene_jobs.py
|   |   |   |-- copy_jobs.py
|   |   |   |-- video_jobs.py
|   |   |   |-- exports.py
|   |   |   `-- generation_jobs.py
|   |   `-- routers/
|   |-- migrations/            # Alembic: env.py + versions/0001-0004
|   |-- alembic.ini
|   |-- migrate.py             # dev: apply migrations to head
|   |-- tests/
|   |-- workflows/
|   |   |-- comfyui_extra_model_paths.yaml
|   |   |-- text_to_image.json
|   |   |-- product_scene.json
|   |   |-- product_scene_flux_kontext.json
|   |   |-- product_scene_qwen_image.json
|   |   |-- product_scene_hidream_e1.json
|   |   |-- product_scene_ipadapter.json
|   |   `-- product_scene_inpaint.json
|   `-- requirements.txt
`-- frontend/
    |-- .env.example
    `-- src/
        |-- app/
        |-- components/
        `-- lib/
```

## Quick start (Windows)

For the full local studio, including ComfyUI, double-click:

```text
Start-Sovereign-Creative-Studio.bat
```

The launcher starts ComfyUI, the backend, and the frontend in separate windows,
waits for each health endpoint to respond, then opens:

- ComfyUI: http://127.0.0.1:8001
- Status page: http://localhost:3000/status

The batch file delegates to `tools/local_launcher.py`, which normalizes the
Windows environment before launching services. This avoids a known local issue
where inherited `Path` and `PATH` variables can both exist and break PowerShell
process startup.

From the project root, one command launches both services in their own windows
(creating the venv, installing deps, and seeding `.env.local` on first run):

```powershell
powershell -ExecutionPolicy Bypass -File start-all.ps1
```

Then open http://localhost:3000 (the **Status** page confirms the backend is
connected and shows how it's configured).

Other scripts:

| Script | Does |
| ------ | ---- |
| `Start-Sovereign-Creative-Studio.bat` | One-click ComfyUI + backend + frontend launcher with health polling |
| `Stop-Sovereign-Creative-Studio.bat` | Stops listeners on ports 8001, 8000, and 3000 |
| `backend\.venv\Scripts\python.exe tools\local_launcher.py status` | Prints local service health without PowerShell env access |
| `start-backend.ps1` | Backend only â†’ http://localhost:8000 |
| `start-frontend.ps1` | Frontend only â†’ http://localhost:3000 |
| `start-all.ps1` | Both, in separate windows |
| `run-tests.ps1` | Backend tests + frontend typecheck & build |

Copy `backend/.env.example` â†’ `backend/.env` and `frontend/.env.example` â†’
`frontend/.env.local` to customize configuration (both are optional; defaults
work out of the box).

## Starting the app

### One-click local studio launcher

Use the root batch launcher for normal local work:

```text
Start-Sovereign-Creative-Studio.bat
```

It starts:

- ComfyUI on `http://127.0.0.1:8001`
- FastAPI backend on `http://127.0.0.1:8000`
- Next.js frontend on `http://localhost:3000`

The launcher polls these URLs instead of relying on fixed sleeps:

- `http://127.0.0.1:8001/system_stats`
- `http://127.0.0.1:8000/api/health`
- `http://localhost:3000`

If one service does not become ready, the launcher names the failing service and
leaves the service windows open so the error is visible.

To stop the local studio, run:

```text
Stop-Sovereign-Creative-Studio.bat
```

It targets only processes listening on the app ports: `8001`, `8000`, and
`3000`.

Advanced helper commands:

```powershell
backend\.venv\Scripts\python.exe tools\local_launcher.py status
backend\.venv\Scripts\python.exe tools\local_launcher.py start --skip-comfy
backend\.venv\Scripts\python.exe tools\local_launcher.py stop
```

Use `--skip-comfy` when ComfyUI is already running and you only need the backend
and frontend.

### Manual startup fallback

If the launcher fails, start each service manually.

ComfyUI:

```powershell
cd C:\Users\David\ComfyUI-Installs\ComfyUI\ComfyUI
C:\Users\David\Documents\ComfyUI\.venv\Scripts\python.exe -s main.py --feature-flag show_signin_button=true --base-directory C:\Users\David\Documents\ComfyUI --user-directory C:\Users\David\Documents\ComfyUI\user --database-url sqlite:///C:\Users\David\Documents\ComfyUI\user\comfyui.db --port 8001 --enable-manager --extra-model-paths-config "C:\Users\David\AppData\Roaming\Comfy Desktop\shared_model_paths.yaml" --input-directory C:\Users\David\Documents\ComfyUI\input --output-directory C:\Users\David\Documents\ComfyUI\output
```

Backend:

```powershell
cd C:\Users\David\Documents\Codex\sovereign-creative-studio\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd C:\Users\David\Documents\Codex\sovereign-creative-studio\frontend
npm.cmd run build
npm.cmd run start
```

> **WARNING — never run dev and production frontend at the same time.**
> Normal use = `Start-Sovereign-Creative-Studio.bat` (production server on
> `localhost:3000`). Dev mode (`npm run dev` / `next dev`) is for actively
> editing frontend code and **only after stopping the production launcher**.
>
> **Build-directory isolation (durable fix):** production (`next build` /
> `next start`) writes to `frontend/.next`; dev (`next dev`) writes to
> `frontend/.next-dev`. `next.config.mjs` selects the directory by `NODE_ENV`
> (override with `NEXT_DIST_DIR`), so a dev server can no longer corrupt the
> production `.next` build — even if both somehow run. The launcher still
> blocks production startup when it detects `next dev`, and `start-frontend.ps1`
> runs production by default (dev requires the explicit `-Dev` flag, which
> refuses to run while production is on 3000 and uses `.next-dev`).
> To recover/rebuild production cleanly: `python tools/local_launcher.py clean`.

### Troubleshooting ports

Expected URLs:

- Frontend: http://localhost:3000
- Backend health: http://127.0.0.1:8000/api/health
- Backend docs: http://127.0.0.1:8000/docs
- ComfyUI: http://127.0.0.1:8001
- ComfyUI health: http://127.0.0.1:8001/system_stats

If a port is already occupied, run `Stop-Sovereign-Creative-Studio.bat` first.
If that does not clear the conflict, inspect the listener:

```powershell
Get-NetTCPConnection -LocalPort 8001,8000,3000 -State Listen
```

### If ComfyUI is offline

The Status page and Model Manager both have a **Refresh** button. If they show
ComfyUI offline, confirm:

- ComfyUI is running at `http://127.0.0.1:8001`
- `backend/.env` has `COMFYUI_BASE_URL=http://127.0.0.1:8001`
- the ComfyUI launcher window did not close with a path or Python error

Start again with `Start-Sovereign-Creative-Studio.bat`, then press **Refresh** in
Status or Model Manager.

## Private Admin Dashboard

Phase 1 of the local/family studio admin layer adds a private Admin Dashboard at:

```text
http://localhost:3000/admin
```

It is intentionally local-first and lightweight. It shows service health, active
model/workflow configuration, product scene model and mode, video backend, copy
provider, ComfyUI reachability, recent jobs, failed jobs, family users, credit
balances, and recent credit transactions.

Admin endpoints:

```text
GET  /api/admin/dashboard
POST /api/admin/workflow/reset-safe-defaults
```

Family user endpoints:

```text
GET  /api/admin/family-users
POST /api/admin/family-users
PUT  /api/admin/family-users/{user_id}
POST /api/admin/family-users/{user_id}/disable
POST /api/admin/family-users/{user_id}/reactivate
```

The Family Users section on `/admin` is for this private local studio only. It
lets David/Admin create family members, choose `owner_admin`, `family_user`, or
`guest`, disable/reactivate accounts, add private notes, and view each user's
current credit balance and latest activity. This phase does not add passwords,
public signup, OAuth, payments, monthly plans, or cloud user management.

Credits and usage endpoints:

```text
GET  /api/admin/credits/transactions
POST /api/admin/credits/add
POST /api/admin/credits/remove
POST /api/admin/credits/transactions/{transaction_id}/refund
```

The Credits and Usage section on `/admin` is an internal family ledger. It shows
family balances, recent generation usage by user, recent credit transactions,
manual admin adjustments, and refund controls for eligible charged transactions.
Ledger entries include transaction type, feature, related job id, status, note,
amount, balance after, and timestamp. Failed jobs that were not charged show as
not charged in the usage list. This is not payment processing, a subscription
system, or a public top-up flow.

The safe reset action delegates to the existing Workflow Manager and restores
the important local defaults without changing generation logic:

- product scene model: `flux-kontext`
- video backend: `mock`
- ComfyUI URL remains `http://127.0.0.1:8001`
- frontend API base remains `http://127.0.0.1:8000`

This is not public SaaS administration. It is a private local/family control
surface for this machine.

## Backup and Recovery

A simple local-first backup system protects your data before real-world trials.
It is intentionally local only: no cloud, no external services, no scheduled
jobs, and no automatic destructive restore.

### What a backup includes

Each backup is a single timestamped ZIP (e.g. `scs-backup-20260620-143000.zip`)
containing, when present:

- `backend/sovereign.db` — the SQLite database (users, credits, generations, ledger)
- `backend/storage/` — generated assets, uploads, processed images, videos, etc.
- `backend/storage/workflow_config.json` — current workflow configuration
- `backend/.env` — backend environment configuration
- `frontend/.env.local` — frontend environment configuration (if present)
- `backend/workflows/` — ComfyUI workflow templates
- `README.md`
- `backup_manifest.json` — backup id, created-at, file list, app name, and a safe-config summary

Intentionally **excluded**: the `backups/` folder itself (so old backups are
never nested inside new ones), the `storage/tmp/` scratch space and `_test*`
caches, plus `.venv`, `node_modules`, `.next`, and other caches.

Creating a backup is read-only over your live data — nothing is moved or deleted.

### How to create a backup

1. Open the admin area at `/admin`.
2. Click **Backup & Recovery** (or go directly to `/admin/backups`).
3. Click **Create Backup**. The new ZIP appears in the list with its size and date.
4. Use **Download** to save a copy off this machine if you want an extra copy.

### Where backups are stored

`backend/storage/backups/` on this machine.

### Manual restore (do this with the app stopped)

Restore is manual on purpose. **Do not overwrite the live database while the
studio is running.**

1. **Stop the studio** (both backend and frontend) — e.g. run
   `Stop-Sovereign-Creative-Studio.bat`.
2. **Copy your current files somewhere safe first** (at minimum
   `backend/sovereign.db` and `backend/storage/`) so you can roll back.
3. Unzip the chosen backup ZIP to a temporary folder.
4. **Restore `backend/sovereign.db`** by copying it back over the live file.
5. **Restore the `backend/storage/` files** you need (assets, uploads, etc.).
6. **Restore `backend/storage/workflow_config.json`** if you need the saved config.
7. **Restart the studio** (e.g. `Start-Sovereign-Creative-Studio.bat`).
8. **Verify** `/status`, `/admin`, and `/workflow-manager` load and look correct.

> Warning: never restore files while the backend or frontend is running — the
> live SQLite database may be open, and overwriting it can corrupt data.

## Job Monitor, Cleanup, and Asset Trash

Local/private admin maintenance tools:

- `/admin/jobs` — Job Monitor for queued, running, completed, and failed jobs,
  plus stale-job recovery and a per-job **Dismiss** (archive) action.
- `/admin/storage` — local storage report and conservative dry-run-first cleanup.
- **Asset trash** — "Trash" actions on the Videos page and Asset Library move an
  item to `backend/storage/trash/` and hide it from normal views. It is a
  **recoverable archive, not a permanent delete**: original uploads and assets
  referenced by productions/storyboards require an extra confirmation, and items
  can be restored via the admin trash API. Nothing is permanently removed unless
  trash is explicitly emptied.

### Stale jobs and legacy records

If a crash/restart leaves jobs stuck in `queued`/`running`, the Job Monitor shows
a **Stale jobs** panel (jobs past a time threshold) with "Mark as cancelled/failed"
— this only updates status (no files deleted) and never charges uncharged jobs.
Old legacy `/create`-page video attempts (stored as failed `base_generation`,
"ComfyUI adapter currently supports image generation only") are clearly relabelled
and can be dismissed out of the monitor; real `/videos` failures are not hidden.

### Job Monitor

The Job Monitor normalizes active generation work across base image generation,
Product Scenes, Copy Studio, and Videos. It shows:

- summary counts for queued, running, completed, failed, and total jobs
- feature/type, status, user, project, prompt/title, result URL, error message,
  and timestamps
- simple filters by status and feature

The monitor is intentionally read-only. Failed jobs are kept because they are
part of the local audit trail and may be referenced by the credit ledger.

### Storage Cleanup

The Storage Cleanup page reports:

- total storage size and file count
- folder sizes
- largest non-sensitive files
- a cleanup dry-run plan
- protected paths and cleanup candidates

Always follow this order:

1. Create a backup first from `/admin/backups`.
2. Open `/admin/storage`.
3. Run **Dry-run cleanup**.
4. Review every candidate.
5. Execute only by typing the exact confirmation phrase shown by the dry run.

Cleanup protects:

- original uploads in `backend/storage/uploads/`
- live generated assets referenced by database rows
- processed assets, product scenes, videos, masks, and pose presets
- `workflow_config.json`, the database, and env files
- the newest backups

Cleanup candidates are intentionally narrow: scratch files under `storage/tmp/`,
`_test*` artifacts, regenerable export bundles, and old backups beyond the keep
count. The backend re-validates protections at execution time, so dry-run output
is not trusted blindly.

For real-world trials, run a backup, review `/admin/jobs` for recent failures,
and run a storage dry-run before handing the app to family users.

## Run Locally (manual)

Use two terminals: backend first, then frontend.

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- A demo user with 100 credits is seeded on first run.
- The SQLite DB (`backend/sovereign.db`) is created and migrated to the latest
  schema automatically on startup; generated files land in `backend/storage/`.

See [Database migrations](#database-migrations) for upgrading an existing
database.

### Frontend

```powershell
cd frontend
copy .env.local.example .env.local
npm install
npm run build
npm run start
```

Then open http://localhost:3000. Create generates images asynchronously, Upload
stores product images for projects, Product Scenes turns assets into ad-scene
concepts, and Asset Library centralizes uploaded/generated media.

For normal one-click local studio use, use `Start-Sovereign-Creative-Studio.bat`
(production frontend on `localhost:3000`). For frontend development only, stop
the production launcher first, then run `start-frontend.ps1 -Dev`. **Never run
dev and production frontend at the same time** — they share `frontend/.next` and
dev corrupts the production build. Recover with
`python tools/local_launcher.py clean`.

On macOS/Linux, use `source .venv/bin/activate` and
`cp .env.local.example .env.local`.

## ComfyUI Setup

The backend defaults to `GENERATOR_BACKEND=mock`. To use ComfyUI for image
generation:

1. Install and start ComfyUI locally.
2. Make sure the ComfyUI API is reachable at `http://127.0.0.1:8001` when using
   the local studio launcher.
3. Place the checkpoint referenced by the workflow in ComfyUI's checkpoints
   folder, or edit `backend/workflows/text_to_image.json` to use a checkpoint
   available on your machine.
4. Start the backend with these env vars:

```powershell
cd backend
$env:GENERATOR_BACKEND = "comfyui"
$env:COMFYUI_BASE_URL = "http://127.0.0.1:8001"
$env:COMFYUI_WORKFLOW_PATH = "workflows/text_to_image.json"
uvicorn app.main:app --reload --port 8000
```

The adapter loads the workflow JSON, replaces the `__PROMPT__` text in the
positive `CLIPTextEncode` node, randomizes the KSampler seed, posts the workflow
to `/prompt`, polls `/history/{prompt_id}`, downloads the first output image from
`/view`, saves it under `backend/storage/`, and returns a `/storage/<id>.png`
URL. The public generator interface is the same as the mock generator.

This workspace also includes `backend/workflows/comfyui_extra_model_paths.yaml`,
which points the local ComfyUI source checkout at models stored under
`C:/Users/David/Documents/ComfyUI`.

The included workflow is an image-only text-to-image workflow. Video generation
is intentionally not part of this phase.

## Generation Flow

`POST /api/generations` creates a row with `status="queued"` and returns
immediately. A single in-process worker thread opens its own database session,
marks the generation `running`, calls the active generator, then stores either:

- `completed` with `file_url` and a credit ledger entry
- `failed` with a useful `error` string and no credit charge

The frontend polls `GET /api/generations/{id}` every few seconds while a
generation is queued or running. `GET /api/generations` lists history for
Dashboard/Gallery.

## Product Assets

The Upload page provides the local foundation for product photography:

- choose a project
- upload a product image
- store the original under `backend/storage/uploads/`
- create a `product_assets` database row
- list uploaded assets with status badges
- run mock background removal

Asset endpoints:

| Method | Path                                | Purpose                          |
| ------ | ----------------------------------- | -------------------------------- |
| `POST` | `/api/assets/upload`                | Upload an image for a project    |
| `GET`  | `/api/assets`                       | List product assets              |
| `GET`  | `/api/assets/{id}`                  | Get one product asset            |
| `POST` | `/api/assets/{id}/remove-background`| Queue background removal         |
| `POST` | `/api/assets/{id}/mask`             | Upload a product mask (inpaint)  |

The current background-removal adapter is a mock implementation that copies the
original image to `backend/storage/processed/` and marks the asset `completed`.
The real adapter is stubbed for a later phase.

## Project Workspace

Each project has a workspace page at `/projects/{id}`. It organizes the media
and generations for one project without adding new tables or changing the
underlying generation flows.

The workspace shows:

- project name, description, created date, counts by type, and latest activity
- overview tab with recent activity and latest upload/scene/copy/video
- brand kit and creative briefs tabs (campaign planning)
- uploads and processed assets
- product scene images
- copy generations
- video generations
- campaign/bundle placeholder section for future stored campaign records
- download links using the existing export endpoints where available

Project workspace endpoint:

| Method | Path                                | Purpose                              |
| ------ | ----------------------------------- | ------------------------------------ |
| `GET`  | `/api/projects/{project_id}/workspace` | Project-level media workspace summary |

The existing Asset Library endpoint also accepts `project_id`:

```text
GET /api/library?project_id=<project id>
```

The Projects page links each project card to its workspace with an **Open
workspace** action.

## Brand Kits

Each project can store lightweight creative guidance in its Brand Kit tab on
`/projects/{id}`. Brand kits are stored directly on the `projects` table so they
stay local, simple, and tied to the project workspace.

Brand kit fields:

- brand name
- brand voice
- target audience
- primary colors
- style keywords
- negative keywords
- product positioning
- campaign notes

Brand Kit endpoints:

| Method | Path                                  | Purpose                  |
| ------ | ------------------------------------- | ------------------------ |
| `GET`  | `/api/projects/{project_id}/brand-kit` | Read project brand kit   |
| `PUT`  | `/api/projects/{project_id}/brand-kit` | Update project brand kit |

`GET /api/projects/{project_id}/workspace` also includes `brand_kit`.

When a project has brand guidance, new product-scene, copy, and campaign jobs
append a compact `Brand guidance:` block to the stored prompt/request context.
For example, voice, audience, colors, style keywords, negative keywords,
positioning, and campaign notes become reusable context for downstream
generation without changing model defaults or ComfyUI workflows.

## Creative Briefs

Creative briefs are lightweight campaign plans inside a project, so you can plan
before generating. They support the workflow:
**Project → Brand Kit → Creative Brief → Generate Assets.**

Each brief lives in the **Creative Briefs** tab on `/projects/{id}` and combines
the brand kit, the campaign goal, and the creative plan. Briefs are stored in a
`creative_briefs` table, scoped to their parent project.

Brief fields:

- title
- campaign goal
- target channels
- deliverables
- key messages
- creative direction
- reference notes
- selected asset ids (JSON list; reserved for an asset picker, empty for now)
- status (`draft`, `in_review`, `approved`, `archived`)

Brief endpoints:

| Method   | Path                                            | Purpose            |
| -------- | ----------------------------------------------- | ------------------ |
| `POST`   | `/api/projects/{project_id}/briefs`             | Create a brief     |
| `GET`    | `/api/projects/{project_id}/briefs`             | List project briefs|
| `GET`    | `/api/projects/{project_id}/briefs/{brief_id}`  | Get one brief      |
| `PUT`    | `/api/projects/{project_id}/briefs/{brief_id}`  | Update a brief     |
| `DELETE` | `/api/projects/{project_id}/briefs/{brief_id}`  | Delete a brief     |

`GET /api/projects/{project_id}/workspace` also includes `creative_briefs`.

The Creative Briefs tab provides a brief list, a simple editor (inputs +
textareas), and a copy-pasteable brief summary.

**Influence on generation:** product-scene, copy, **campaign**, and **video**
requests all accept an optional `brief_id`:

- `POST /api/product-scenes` — appends brief context to the scene prompt.
- `POST /api/copy` — appends brief context to the copy prompt.
- `POST /api/campaigns/from-preset` — appends brief context to **both** the
  generated scene prompt and the copy prompt.
- `POST /api/videos` — appends brief context to the video prompt.

When `brief_id` is provided it is validated against the selected project (a brief
from another project returns a clean `404`), and a compact `Creative brief:`
block is appended to the stored prompt **after** any brand guidance — brand-kit
behaviour is unchanged. Requests without `brief_id` are unaffected.

**UI selectors:** the Product Scenes, Copy Studio, Campaigns, and Videos pages
each have a "Creative brief (optional)" dropdown. It loads the selected project's
briefs ("No brief" + brief titles), includes the chosen `brief_id` in the
request, and clears itself when you switch to a project that doesn't contain that
brief.

## Product Scenes

The Product Scenes page is the foundation for Pippit-style product ad concepts:

- choose a project
- select an uploaded or background-removed product asset
- enter a scene prompt
- choose one simple preset: `studio`, `luxury`, `outdoor`, or `social ad`
- queue a product-scene generation job
- poll status until the mock result appears

Product scene endpoints:

| Method | Path                       | Purpose                         |
| ------ | -------------------------- | ------------------------------- |
| `POST` | `/api/product-scenes`      | Queue a product ad scene job    |
| `GET`  | `/api/product-scenes`      | List product scene history      |
| `GET`  | `/api/product-scenes/{id}` | Get one product scene job       |

There are two product-scene backends, selected by `PRODUCT_SCENE_BACKEND`:

- **mock** (default/fallback): writes an SVG concept to
  `backend/storage/product-scenes/`, using the processed asset URL when one is
  available, otherwise the original upload URL.
- **comfyui**: a real adapter. It resolves the selected product asset to a local
  file, uploads it to ComfyUI's input folder (`/upload/image`), injects the
  uploaded filename, the scene prompt, and the preset style into the active
  workflow, posts to `/prompt`, polls `/history/{prompt_id}`, downloads the first
  output image from `/view`, and saves it to
  `backend/storage/product-scenes/<id>.png`. The `ProductSceneResult` shape is
  identical to the mock's.

The comfyui backend has multiple modes. The mode can be chosen **per generation**
from the UI (the "Scene edit mode" toggle on the Product Scenes page) or set as
the default via `COMFYUI_PRODUCT_SCENE_MODE`. Each mode appends a mode-specific
prompt enhancement, and brand-kit + creative-brief context still flow through.

Core modes:

- **img2img** (default/fallback): uses `backend/workflows/product_scene.json`
  unless `PRODUCT_SCENE_MODEL` selects a newer model workflow. Works with a plain
  Stable Diffusion checkpoint and no custom nodes.
- **ipadapter**: uses `backend/workflows/product_scene_ipadapter.json` for
  stronger product-identity preservation. Needs the IPAdapter custom nodes.
- **inpaint** (strongest preservation): uses
  `backend/workflows/product_scene_inpaint.json` with a **product mask**. Provide
  a mask where **white = product**; the workflow inverts it so the background
  becomes the inpainted region.

Creative modes (Phase C9):

- **segmented_composite** — `product_scene_segmented_composite.json`. RemBG
  human-segments the subject and regenerates **only** the background via Flux
  Fill, compositing the preserved subject back in. Best for fashion/clothing and
  subject-preserving background changes. Needs RemBG nodes + the `u2net_human_seg`
  model and `flux1-fill-dev`.
- **segmented_composite_polished** (Phase C10B) —
  `product_scene_segmented_composite_polished.json`. A higher-quality composite:
  it segments the subject, refines the mask (`MaskFix+` edge-erode → `MaskSmooth+`
  → `MaskBlur+`) to cut white halos, generates a clean subject-free background,
  **color-matches** the foreground to the background lighting
  (`ImageColorMatch+` in LAB) with subtle brightness/contrast tuning, then
  composites with a soft edge. Best when `segmented_composite` shows fringing.
  Needs RemBG + the `ComfyUI_essentials` nodes (`MaskSmooth+`, `ImageColorMatch+`,
  `ImageCompositeMasked`).
- **advertising_scene** — `product_scene_advertising_scene.json`. Flux/Kontext
  with stronger ad styling and looser pose preservation (higher denoise). Best
  for ecommerce hero images, luxury ads, and social creatives.
- **fashion_editorial** — `product_scene_fashion_editorial.json`. Flux/Kontext
  with magazine/editorial styling while preserving the subject and clothing. Best
  for editorial covers and luxury campaign scenes.
- **creative_fashion_edit** — `product_scene_creative_fashion_edit.json`.
  Flux/Kontext-style image editing with higher denoise (`0.68`) and transformation
  language. This is the **Creative Edit** mode: it can change background/location,
  pose moderately, clothing color when requested, styling, lighting, framing, and
  composition. Use it for true fashion/editorial advertising rather than strict
  product preservation.

**When to use which:** `segmented_composite_polished` is the highest-quality
subject-preserving background swap (fashion/people) and should be preferred when
its nodes are installed; `segmented_composite` is the lighter fallback;
`advertising_scene` for polished product ads, `fashion_editorial` for high-end
editorial looks, `creative_fashion_edit` when you intentionally want stronger
fashion transformation, and `inpaint`/`ipadapter`/`img2img` for the previous
preservation/speed trade-offs.

**Availability & fallback:** the Workflow Manager marks `segmented_composite`
available only when its workflow exists **and** RemBG is installed;
`advertising_scene`/`fashion_editorial`/`creative_fashion_edit` need their
workflow files. Selecting an unavailable mode is rejected with a clear reason;
unknown modes fall back to img2img. The Product Scenes mode toggle disables modes
that aren't available.

Local model notes from the Creative Fashion Edit investigation: this workstation
currently exposes Flux/Kontext nodes and Flux model files (`flux1-dev.safetensors`
and `flux1-fill-dev.safetensors`). Qwen Image Edit nodes are present, but the
Qwen Image Edit / Qwen Image Edit 2509 UNET and VAE files were not listed by
ComfyUI's `UNETLoader` / `VAELoader`. The expected future files for Qwen mode are
the official Qwen Image Edit 2509 UNET (for example
`qwen_image_edit_2509_fp8_e4m3fn.safetensors`) under
`models/unet`, the matching Qwen image VAE (for example
`qwen_image_vae.safetensors`) under `models/vae`, and the matching Qwen
text/image encoder under `models/text_encoders` or `models/clip`, depending on
the ComfyUI node pack. Do not download substitutes from random sources.

**Known limitations:** segmented composites are the most resource-heavy modes and
can show **compositing halos / edge fringing** around the subject when RemBG masks
are imperfect. `segmented_composite_polished` reduces this via edge-erode + smooth
+ blur and LAB color-matching, but very fine details (hair, transparent fabric)
may still fringe. **Contact shadows:** an explicit contact-shadow pass was
evaluated and intentionally left out — the available node approaches (compositing
a darkened blob under the subject) reliably produce hard black halos rather than
realistic grounding, so the polished workflow instead relies on color-matching and
a slight brightness reduction for grounding. A dedicated, safe shadow pass is a
candidate for a future phase. The advertising/fashion modes restyle the scene and
may drift product details at higher denoise; lower the KSampler `denoise` in the
workflow for tighter preservation.

A per-request mode is sent as `mode` on `POST /api/product-scenes`; omitting it
uses the configured default. Any unrecognized mode falls back to img2img.

**Masks.** Upload a mask for an asset with `POST /api/assets/{id}/mask` (the UI
does this automatically when you attach a mask in inpaint mode). The mask is
stored under `backend/storage/masks/` and recorded on the asset's `mask_url`. If
inpaint mode is requested but the asset has no mask, the adapter falls back to
the mode named by `COMFYUI_PRODUCT_SCENE_INPAINT_FALLBACK` (`img2img` by default,
or `ipadapter`).

### Using ComfyUI for product scenes (img2img)

```powershell
cd backend
$env:PRODUCT_SCENE_BACKEND = "comfyui"
$env:COMFYUI_PRODUCT_SCENE_MODE = "img2img"
$env:COMFYUI_BASE_URL = "http://127.0.0.1:8188"
uvicorn app.main:app --reload --port 8000
```

### Using IPAdapter mode (better product preservation)

IPAdapter mode requires extra ComfyUI components. Before enabling it:

1. Install the **ComfyUI_IPAdapter_plus** custom nodes (by cubiq) into
   `ComfyUI/custom_nodes/` and restart ComfyUI.
2. Download the model files those nodes need:
   - a **CLIP-Vision** model into `ComfyUI/models/clip_vision/`
     (e.g. `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`)
   - the matching **IPAdapter** model into `ComfyUI/models/ipadapter/`
     (e.g. `ip-adapter-plus_sd15.safetensors` for an SD1.5 checkpoint)
   The bundled workflow uses `IPAdapterUnifiedLoader` with the
   `PLUS (high strength)` preset, which auto-selects these by filename.
3. Start the backend in ipadapter mode:

```powershell
cd backend
$env:PRODUCT_SCENE_BACKEND = "comfyui"
$env:COMFYUI_PRODUCT_SCENE_MODE = "ipadapter"
$env:COMFYUI_BASE_URL = "http://127.0.0.1:8188"
uvicorn app.main:app --reload --port 8000
```

Before submitting, the adapter calls ComfyUI's `/object_info` and checks that the
`IPAdapter*` nodes used by the workflow are actually registered. If they are
missing, the job fails fast with a clear error naming the missing nodes and
telling you to install `ComfyUI_IPAdapter_plus` and its models (or switch back to
`COMFYUI_PRODUCT_SCENE_MODE=img2img`).

### Pose Studio identity preservation with IPAdapter

Pose Studio currently uses SDXL + OpenPose for the pose stage and Qwen Image Edit
for refinement. This follows target poses, but if the SDXL stage starts from an
empty latent it can drift into a different person before Qwen sees the image.

The intended Phase 3 fix is to add IPAdapter conditioning to the SDXL/OpenPose
stage:

- OpenPose controls the target body pose.
- SDXL IPAdapter uses the source product/person image as the identity reference.
- Qwen Image Edit remains the final refinement/polish stage.

Local investigation on 2026-06-19 found:

- Present: `sd_xl_base_1.0.safetensors`
- Present: `control-openpose-sdxl-1.0.safetensors`
- Present: `Qwen-Image-Edit-2509-Q4_K_M.gguf`
- Present: `qwen_2.5_vl_7b_fp8_scaled.safetensors`
- Present: `qwen_image_vae.safetensors`
- Missing: `ComfyUI_IPAdapter_plus` custom nodes
- Missing: `models/ipadapter/`
- Missing/empty: `models/clip_vision/`
- ComfyUI was not reachable at `http://127.0.0.1:8001` during this check, so
  `/object_info` could not confirm registered IPAdapter nodes.

Recommended official IPAdapter install for SDXL Pose Studio:

- Custom nodes: `cubiq/ComfyUI_IPAdapter_plus` in ComfyUI `custom_nodes/`
- CLIP Vision: `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` in
  `ComfyUI/models/clip_vision/` (about 2.53 GB)
- SDXL IPAdapter subject model: `ip-adapter-plus_sdxl_vit-h.safetensors` in
  `ComfyUI/models/ipadapter/` (about 848 MB)
- Optional SDXL face-focused model:
  `ip-adapter-plus-face_sdxl_vit-h.safetensors` in
  `ComfyUI/models/ipadapter/` (about 848 MB)

On an RTX 5070 Ti 16 GB, the safest validation path is a two-stage workflow:
first SDXL + OpenPose + IPAdapter at a conservative resolution, then Qwen
refinement with a low-to-moderate denoise. Running SDXL ControlNet, IPAdapter,
and Qwen in one graph may be VRAM-tight, so keep the first standing-to-walking
test small before increasing resolution.

Current Pose Studio modes:

- **Identity Pose** (`pose_edit`): preferred path using
  `product_scene_pose_identity_preset.json` or
  `product_scene_pose_identity_reference.json`. This is
  SDXL + OpenPose + IPAdapter, followed by Qwen Image Edit refinement.
- **Stylized Pose** (`pose_stylized`): fallback path using the original
  `product_scene_pose_preset.json` or `product_scene_pose_reference.json`.
  This is SDXL + OpenPose, followed by Qwen refinement, and should be treated as
  approximate identity.

Live validation on 2026-06-19:

- Installed `ComfyUI_IPAdapter_plus` into
  `C:\Users\David\Documents\ComfyUI\custom_nodes\ComfyUI_IPAdapter_plus`
- Installed `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` into
  `C:\Users\David\Documents\ComfyUI\models\clip_vision`
- Installed `ip-adapter-plus_sdxl_vit-h.safetensors` and
  `ip-adapter-plus-face_sdxl_vit-h.safetensors` into
  `C:\Users\David\Documents\ComfyUI\models\ipadapter`
- Confirmed ComfyUI `/object_info` lists `IPAdapterUnifiedLoader`,
  `IPAdapterAdvanced`, `CLIPVisionLoader`,
  `control-openpose-sdxl-1.0.safetensors`, and
  `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`
- Generated a live Identity Pose output through the backend adapter:
  `backend/storage/product-scenes/identity_pose_smoke.png`

Result: identity/clothing preservation is substantially better than the
SDXL/OpenPose-only fallback. The bundled `walking` preset still produces a
conservative fashion stance rather than an obviously walking stride, so future
tuning should focus on stronger pose presets or reference-pose images.

### Using inpaint / mask-preserve mode (strongest preservation)

Inpaint mode uses core ComfyUI nodes (`VAEEncodeForInpaint`, `LoadImageMask`,
`InvertMask`) â€” no custom nodes â€” but **requires a product mask**.

```powershell
cd backend
$env:PRODUCT_SCENE_BACKEND = "comfyui"
$env:COMFYUI_PRODUCT_SCENE_MODE = "inpaint"
$env:COMFYUI_PRODUCT_SCENE_INPAINT_FALLBACK = "img2img"   # or "ipadapter"
$env:COMFYUI_BASE_URL = "http://127.0.0.1:8188"
uvicorn app.main:app --reload --port 8000
```

In the UI, pick **Mask preserve** and attach a mask image (white = product). The
adapter uploads both the product and the mask, verifies the inpaint nodes via
`/object_info` (failing fast with a clear error if any are missing), and keeps the
product region while regenerating the background. With no mask attached, it falls
back to `COMFYUI_PRODUCT_SCENE_INPAINT_FALLBACK`.

All three workflows use these sentinels, replaced at submit time:

- `__PRODUCT_IMAGE__` in the `LoadImage` node â†’ the uploaded product filename
- `__PRODUCT_MASK__` in the `LoadImageMask` node (inpaint only) â†’ the uploaded mask
- `__PROMPT__` in the positive `CLIPTextEncode` node â†’ the scene prompt
- `__PRESET__` in the same node â†’ the preset style descriptor
  (`studio`, `luxury`, `outdoor`, `social ad`; unknown presets fall back to
  `studio`)

The KSampler seed is randomized per run. An unset or unrecognized
`PRODUCT_SCENE_BACKEND` falls back to the mock generator, so the app keeps
working without ComfyUI. Place each workflow's checkpoint in ComfyUI's
checkpoints folder, or edit the workflow JSON to match a checkpoint you have.

### Product-scene model families

For ComfyUI product scenes, `PRODUCT_SCENE_MODEL` can select a model-specific
workflow:

| Value | Workflow | Local status |
| ----- | -------- | ------------ |
| unset | `backend/workflows/product_scene.json` | Legacy SD1.5 low-denoise img2img |
| `flux-kontext` | `backend/workflows/product_scene_flux_kontext.json` | Uses the installed Flux-family files (`flux1-dev.safetensors`, `clip_l.safetensors`, `t5xxl_fp8_e4m3fn_scaled.safetensors`, `ae.safetensors`) plus `FluxKontextImageScale` |
| `qwen-image` | `backend/workflows/product_scene_qwen_image.json` | Requires official Qwen Image Edit/Inpaint files not currently present locally |
| `hidream-e1` | `backend/workflows/product_scene_hidream_e1.json` | Requires official HiDream E1 files not currently present locally |

The adapter logs the selected workflow, model family, checkpoint/model file,
denoise strength, and conditioning strength before submit. For model-specific
workflows it also checks ComfyUI `/object_info` before `/prompt`; if a required
node or model file is missing, the job fails fast with a clear error instead of
silently falling back to a generic SD workflow.

Current local ComfyUI product-scene recommendation:

```powershell
$env:PRODUCT_SCENE_BACKEND = "comfyui"
$env:PRODUCT_SCENE_MODEL = "flux-kontext"
$env:COMFYUI_PRODUCT_SCENE_MODE = "img2img"
$env:COMFYUI_BASE_URL = "http://127.0.0.1:8001"
```

For best subject preservation on people/apparel, use an uploaded full-body
product image with the Flux model path first. If you have a clean product/person
mask, inpaint mode remains the strongest preservation path because it keeps the
subject region and changes the surrounding scene.

## Copy Studio

The Copy Studio page (`/copy-studio`) generates lightweight marketing copy for a
product or ad scene. Pick a project, optionally link a product asset and/or a
completed product scene, choose a copy type and tone, add an audience and a
prompt, then generate. Results stream in with `queued` / `running` / `completed` /
`failed` states and a copy-to-clipboard button.

- **Copy types:** `product_description`, `instagram_caption`, `facebook_ad`,
  `tiktok_hook`, `seo_title`.
- **Tones:** `luxury`, `friendly`, `bold`, `professional`, `playful`.

Generation runs on the same in-process worker pattern as the other features. If
an asset or scene is linked, a short product context (asset filename, scene
prompt) is woven into the copy.

The generator is configurable via `COPY_BACKEND`, all behind the same
`CopyGenerator` interface. **Switch providers from the UI** — the Workflow
Manager copy section lists every provider with live availability and persists
your choice (no restart). Copy Studio shows the active provider, model, and
status, with a warning when mock is active or a provider is unavailable.

| Provider | `COPY_BACKEND` | Available when | Env |
| -------- | -------------- | -------------- | --- |
| Mock (fallback) | `mock` | always | — |
| OpenAI | `openai` | `OPENAI_API_KEY` set | `OPENAI_COPY_MODEL` (default `gpt-4o-mini`) |
| Claude | `claude` | `ANTHROPIC_API_KEY` set | `ANTHROPIC_COPY_MODEL` (default `claude-3-5-sonnet-latest`) |
| Gemini | `gemini` | `GEMINI_API_KEY` set | `GEMINI_COPY_MODEL` (default `gemini-1.5-flash`) |
| Local Ollama | `ollama` | Ollama reachable + model pulled | `OLLAMA_BASE_URL`, `OLLAMA_COPY_MODEL` |
| Local Qwen | `local-qwen` | Ollama reachable + a Qwen model pulled | `OLLAMA_QWEN_MODEL` (default `qwen2.5`) |
| Local DeepSeek | `local-deepseek` | Ollama reachable + a DeepSeek model pulled | `OLLAMA_DEEPSEEK_MODEL` (default `deepseek-r1`) |

```powershell
# OpenAI / Claude / Gemini
$env:COPY_BACKEND = "openai"; $env:OPENAI_API_KEY = "sk-..."
$env:COPY_BACKEND = "claude"; $env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:COPY_BACKEND = "gemini"; $env:GEMINI_API_KEY = "..."
# Local Ollama presets
$env:COPY_BACKEND = "local-qwen"      # uses OLLAMA_QWEN_MODEL
$env:COPY_BACKEND = "local-deepseek"  # uses OLLAMA_DEEPSEEK_MODEL
```

**Local Ollama setup:** install Ollama, run it (defaults to
`http://127.0.0.1:11434`), and pull a model — e.g. `ollama pull qwen2.5` or
`ollama pull deepseek-r1`. The Workflow Manager probes Ollama's `/api/tags` to
confirm a matching model is present before allowing the provider.

All real providers reuse the shared safe prompt builder (copy type, tone,
audience, product asset/scene context, brand guidance, creative brief, and the
user prompt). Each fails with a clear copy-job error (not a crash) on a missing
key, offline provider, unavailable model, timeout, or empty/malformed response —
and an unknown `COPY_BACKEND` falls back to the mock generator. No API keys are
required at startup.

Copy endpoints:

| Method | Path              | Purpose                      |
| ------ | ----------------- | ---------------------------- |
| `POST` | `/api/copy`       | Queue a copy generation job  |
| `GET`  | `/api/copy`       | List copy history            |
| `GET`  | `/api/copy/{id}`  | Get one copy generation      |

## Videos

The Videos page (`/videos`) turns a **completed product scene** into a short
motion clip. Pick a scene, write a motion prompt, choose a motion preset and
duration, then generate; results stream in with `queued` / `running` /
`completed` / `failed` states and a download button.

- **Motion presets:** `slow_zoom`, `orbit`, `handheld`, `product_reveal`,
  `product_motion`.
- **Duration:** 2â€“30 seconds.

The **video foundation** supports a mock fallback and real ComfyUI/LTX adapter
paths. Normal local production mode uses `VIDEO_BACKEND=comfyui`; the mock
backend remains available for troubleshooting and writes a self-contained
animated HTML artifact under `backend/storage/videos/`. The Videos page shows
the active backend, warns if ComfyUI is offline, and previews MP4 outputs with a
native video player.

Real ComfyUI mode currently wires:

- **Image -> Video:** completed product scene or source image to MP4 via
  `backend/workflows/image_to_video.json`.
- **Text -> Video:** prompt-only MP4 generation via
  `backend/workflows/text_to_video_ltx.json`.
- **Video Upscale:** existing MP4/video output to higher-resolution MP4 via
  `backend/workflows/video_upscale_ltx.json`.
- **Video -> Video:** existing MP4/video output to conservative LTX restyle MP4
  via `backend/workflows/video_to_video_ltx.json`.
- **Video Extension:** existing MP4 continued/extended to a longer MP4 via
  `backend/workflows/video_extension_ltx.json`. The input clip's frames are
  standardized (`ImageScale` to 768x512) and anchored at frame 0 as an LTX guide
  (`LTXVAddGuide`) inside a longer `EmptyLTXVLatentVideo`; the sampler generates
  the remaining frames, then `LTXVCropGuides` + decode produce a single longer
  clip. The extension length comes from the requested duration (mapped onto LTX's
  8k+1 frame grid).

All five real video modes are now wired. The normal local production setting is
`VIDEO_BACKEND=comfyui`; the mock backend remains available as a fallback and
renders an animated placeholder for every mode when `VIDEO_BACKEND=mock`.

### ComfyUI video setup

1. Start ComfyUI with its API server available at `COMFYUI_BASE_URL`. The local
   studio launcher uses `http://127.0.0.1:8001`.
2. Verify the LTX stack in ComfyUI first: CUDA should be active, the LTXV nodes
   should be visible in `/object_info`, and the LTX checkpoint should appear in
   `CheckpointLoaderSimple` / `LTXAVTextEncoderLoader`.
3. The committed Image -> Video and Text -> Video workflows are **API-format**
   LTX 2.3 quality workflows adapted from the official ComfyUI Desktop
   `Image to Video (LTX-2.3).json` and `Text to Video (LTX-2.3).json`
   blueprints. They use `ltx-2.3-22b-dev-fp8.safetensors`,
   `gemma_3_12B_it_fp4_mixed.safetensors`, and the official
   `ltx-2.3-22b-distilled-lora-384.safetensors` companion LoRA. Override
   Image -> Video with `COMFYUI_VIDEO_WORKFLOW_PATH` or Text -> Video with
   `COMFYUI_TEXT_TO_VIDEO_WORKFLOW_PATH` only after validating the replacement
   workflow directly in ComfyUI.
   Video Upscale uses `backend/workflows/video_upscale_ltx.json`; override it
   with `COMFYUI_VIDEO_UPSCALE_WORKFLOW_PATH` if needed.
   Video -> Video uses `backend/workflows/video_to_video_ltx.json`; override it
   with `COMFYUI_VIDEO_TO_VIDEO_WORKFLOW_PATH` if needed.
   Video Extension uses `backend/workflows/video_extension_ltx.json`; override it
   with `COMFYUI_VIDEO_EXTENSION_WORKFLOW_PATH` if needed. It requires the
   `LTXVAddGuide` / `LTXVCropGuides` / `EmptyLTXVLatentVideo` / `ImageScale` nodes
   and uses the `__VIDEO_LENGTH_FRAMES__` placeholder for the extended length.
4. Keep these placeholders in the workflow so the adapter can inject runtime
   values:
   - `__SOURCE_IMAGE__` for the uploaded source image/video filename (Image ->
     Video, Video Upscale, and Video -> Video).
   - `__PROMPT__` for the motion prompt.
   - `__MOTION_PRESET__` for `slow_zoom`, `orbit`, `handheld`,
     `product_reveal`, or `product_motion`.
   - `__DURATION_SECONDS__` for the requested duration.
   - `__VIDEO_MODEL__` for `COMFYUI_VIDEO_MODEL_NAME` when your workflow needs a
     model name.
   - `__VIDEO_UPSCALE_MODEL__` for `COMFYUI_VIDEO_UPSCALE_MODEL_NAME` in the
     Video Upscale workflow.
   - `__VIDEO_WIDTH__`, `__VIDEO_HEIGHT__`, `__VIDEO_STEPS__`,
     `__VIDEO_CFG__`, `__VIDEO_TILE_SIZE__`, and `__VIDEO_TEMPORAL_SIZE__` for
     quality preset injection.
   - `__I2V_STRENGTH__` for Image -> Video source-image guide strength.
   - `__LTX_DISTILLED_LORA_STRENGTH__` for the official LTX 2.3 distilled LoRA
     strength.
   - `__VIDEO_LENGTH_FRAMES__` for the Video Extension target length in frames
     (computed from the requested duration on LTX's 8k+1 grid).
5. In `backend/.env`, keep the local LTX production config:

```powershell
VIDEO_BACKEND=comfyui
COMFYUI_BASE_URL=http://127.0.0.1:8001
COMFYUI_VIDEO_ENGINE=ltx
COMFYUI_VIDEO_WORKFLOW_PATH=workflows/image_to_video.json
COMFYUI_TEXT_TO_VIDEO_WORKFLOW_PATH=workflows/text_to_video_ltx.json
COMFYUI_VIDEO_UPSCALE_WORKFLOW_PATH=workflows/video_upscale_ltx.json
COMFYUI_VIDEO_TO_VIDEO_WORKFLOW_PATH=workflows/video_to_video_ltx.json
COMFYUI_VIDEO_MODEL_NAME=ltx-2.3-22b-dev-fp8.safetensors
COMFYUI_VIDEO_UPSCALE_MODEL_NAME=ltx-2.3-spatial-upscaler-x2-1.1.safetensors
```

Use `VIDEO_BACKEND=mock` only when ComfyUI/LTX is offline or you intentionally
want the lightweight placeholder renderer for troubleshooting.

### LTX quality presets

The Videos page includes local LTX quality modes:

| Preset | Runtime settings | Use |
| --- | --- | --- |
| Safe Preview | 256x256, 8 fps, short 8-step clip | quick compatibility/smoke tests only |
| Standard Local | 512x320, 8 fps, 12 steps | recommended Text -> Video default |
| Best Local Quality | 640x384, 8 fps, 16 steps | short clips where detail matters |
| Image-to-Video Best | 640x384, 8 fps, 16 steps, high image guide strength | best local path for dogs, people, products, and characters |

For detailed subjects, generate a strong still image first (for example with
FLUX.1 Krea) and then use **Image -> Video**. Pure Text -> Video can work, but
small animals/people in wide scenes are more likely to look soft or unstable.

Wan 2.2 is exposed as an experimental Film Studio candidate. To try it later,
keep `VIDEO_BACKEND=comfyui` and set:

```powershell
COMFYUI_VIDEO_ENGINE=wan
COMFYUI_WAN_VIDEO_WORKFLOW_PATH=workflows/image_to_video_wan.json
COMFYUI_WAN_VIDEO_MODEL_NAME=<installed Wan image-to-video UNET filename>
```

The live ComfyUI API check on June 19, 2026 found Wan video nodes such as
`WanImageToVideo`, `Wan22ImageToVideoLatent`, `WanCameraImageToVideo`,
`CreateVideo`, and `SaveVideo`, but did not find Wan UNET or Wan VAE model files
in the active loader dropdowns. The committed Wan workflow also expects
`umt5_xxl_fp8_e4m3fn_scaled.safetensors`, while the current CLIP loader exposes
the local `t5xxl_*` encoders. Model Manager will therefore report Wan as missing
until the proper Wan 2.2 I2V model, VAE, and compatible text encoder are
installed.

The committed `image_to_video.json` is a native LTXV workflow for the inspected
local ComfyUI node set, but real ComfyUI video generation still depends on the
custom nodes, model architecture support, Python runtime, and model files
installed in your local ComfyUI. Generated video/animation outputs are copied
into `backend/storage/videos/`; if ComfyUI is offline, the workflow is missing,
required video nodes/models are absent, polling times out, or the history
response contains no video/animation output, the job records a clear failure
message.

### Tiny LTX app smoke test

Use this path when validating real video mode:

1. Start the studio with `Start-Sovereign-Creative-Studio.bat`.
2. Confirm ComfyUI is reachable at `http://127.0.0.1:8001/system_stats`.
3. Confirm `VIDEO_BACKEND=comfyui` for the backend process.
4. Open `/videos`, choose **Image -> Video** with a completed product scene or
   source image, choose **Text -> Video** for a prompt-only test, or choose
   **Video -> Video** with an existing local storage MP4. Select **Test/Fast**
   and submit a short prompt.
5. Confirm the job completes, an MP4 appears in `backend/storage/videos/`, the
   Videos page previews it, and `/api/exports/video/{id}` downloads it.
6. Switch to `VIDEO_BACKEND=mock` only if you need the emergency fallback.

### Phase 18/19 local validation notes

Use the updated ComfyUI Desktop environment for current video testing, not the
old `C:\AI\comfyui-dml` environment. The inspected Desktop install is:

- ComfyUI path: `C:\Users\David\ComfyUI-Installs\ComfyUI\ComfyUI`
- Python: `C:\Users\David\Documents\ComfyUI\.venv\Scripts\python.exe`
- API base URL during external Desktop validation: `http://127.0.0.1:8000`
- App launcher API base URL: `http://127.0.0.1:8001`
- Model path config:
  `C:\Users\David\AppData\Roaming\Comfy Desktop\shared_model_paths.yaml`

Live API inspection of `http://127.0.0.1:8000/system_stats` confirmed this
Desktop runtime is GPU-backed: `torch 2.10.0+cu130`, CUDA enabled, with
`NVIDIA GeForce RTX 5070 Ti`. `/object_info` shows the LTXV nodes needed by the
Desktop templates, including `LTXVImgToVideo`, `LTXVImgToVideoInplace`,
`LTXVConditioning`, `LTXAVTextEncoderLoader`, `CreateVideo`, and `SaveVideo`.

The LTX checkpoint `ltx-2.3-22b-dev-fp8.safetensors` is visible in
`CheckpointLoaderSimple` and `LTXAVTextEncoderLoader`. The official Desktop
blueprint exists at
`C:\Users\David\ComfyUI-Installs\ComfyUI\ComfyUI\blueprints\Image to Video (LTX-2.3).json`.

The official `Image to Video (LTX-2.3)` blueprint expects
`ltx-2.3-spatial-upscaler-x2-1.1.safetensors` in `latent_upscale_models`. That
file was downloaded from the Lightricks LTX-2.3 Hugging Face source referenced
by the bundled Desktop blueprint and placed at
`C:\Users\David\ComfyUI-Shared\models\latent_upscale_models`. After restarting
ComfyUI Desktop, `/object_info/LatentUpscaleModelLoader` listed the model.

Direct external smoke testing succeeded on June 16, 2026: a tiny 256x256,
9-frame native LTXV image-to-video graph using
`ltx-2.3-22b-dev-fp8.safetensors`,
`gemma_3_12B_it_fp4_mixed.safetensors`, and the LTXV native nodes completed and
saved `C:\Users\David\ComfyUI-Installs\ComfyUI\ComfyUI\output\codex_ltx_tiny_00001_.mp4`.
The app production config now uses `VIDEO_BACKEND=comfyui`; mock remains a
fallback for troubleshooting.

App-level smoke testing later succeeded with the existing `/api/videos` flow.
`backend/workflows/image_to_video.json` now contains the tiny proven LTXV API
workflow: 256x256, 9 frames, 2 sampler steps, `LTXAVTextEncoderLoader`,
`LTXVImgToVideo`, `ModelSamplingLTXV`, `CreateVideo`, and `SaveVideo`. For the
test, ComfyUI Desktop ran on `http://127.0.0.1:8000`, FastAPI ran on port 8001
to avoid the ComfyUI port conflict, and `VIDEO_BACKEND` was temporarily set to
`comfyui`. The job completed and copied the MP4 to
`backend/storage/videos/7c2a6972374141e3b165534ba642b8c9.mp4`; the backend
served the preview URL as `video/mp4`, and the export endpoint returned the same
MP4 as a downloadable attachment. The current production config keeps
`VIDEO_BACKEND=comfyui`; switch to `VIDEO_BACKEND=mock` only when the local LTX
stack is offline or being repaired.

Current Phase C1 launcher mode runs ComfyUI on `http://127.0.0.1:8001`, backend
on `http://127.0.0.1:8000`, and frontend on `http://localhost:3000`. Use
`COMFYUI_BASE_URL=http://127.0.0.1:8001` for new app-level LTX tests.

Text -> Video expansion validation succeeded on June 21, 2026 using
`backend/workflows/text_to_video_ltx.json`, the same
`ltx-2.3-22b-dev-fp8.safetensors` checkpoint, and
`gemma_3_12B_it_fp4_mixed.safetensors` through `LTXAVTextEncoderLoader`. The
live prompt-only smoke test generated a real MP4 at
`backend/storage/videos/b8551806642143bb976b91788d5e4730.mp4`; the export
endpoint returned `200 video/mp4`, Asset Library listed the video item, and Job
Monitor reported the job as completed. Current billing charges Local LTX video
jobs 10 credits on successful completion only.

Video Upscale expansion validation also succeeded on June 21, 2026 using
`backend/workflows/video_upscale_ltx.json`. The workflow loads an existing MP4
with `LoadVideo`, extracts frames with `GetVideoComponents`, encodes through the
LTX VAE, upscales latent video with `LatentUpscaleModelLoader` +
`LTXVLatentUpsampler` using
`ltx-2.3-spatial-upscaler-x2-1.1.safetensors`, decodes with `VAEDecodeTiled`,
and saves a new MP4 through `CreateVideo`/`SaveVideo`. The app-level smoke test
used `backend/storage/videos/b8551806642143bb976b91788d5e4730.mp4` as input and
generated
`backend/storage/videos/1c725b12e04a4a9a8ccf60f3322b7d61.mp4`; the export
endpoint returned `200 video/mp4`, Asset Library listed the upscaled video, and
Job Monitor reported it as completed. Current billing charges Local LTX video
jobs 10 credits on successful completion only.

Video -> Video expansion validation succeeded on June 20, 2026 using
`backend/workflows/video_to_video_ltx.json`. The workflow loads an existing MP4
with `LoadVideo`, extracts frames/fps/bit-depth with `GetVideoComponents`,
encodes video frames with `VAEEncodeTiled`, applies LTX prompt conditioning with
`LTXAVTextEncoderLoader`, `CLIPTextEncode`, and `LTXVConditioning`, samples a
low-denoise latent restyle through `ModelSamplingLTXV` + `KSampler`, decodes
with `VAEDecodeTiled`, and writes MP4 output through `CreateVideo`/`SaveVideo`.
The app-level smoke test used
`backend/storage/videos/b8551806642143bb976b91788d5e4730.mp4` as input and
generated `backend/storage/videos/87e160af6a634bad87080a065d4d22c0.mp4`; the
storage URL and export endpoint both returned `200 video/mp4`, Asset Library
listed the generated video, and Job Monitor reported the job as completed.
Current billing charges Local LTX video jobs 10 credits on successful completion
only.

For Image -> Video, the source image comes from a completed product scene
(`product_scene_id`) or an explicit `source_image_url`. A scene that isn't
completed yet returns `409`. Text -> Video requires no source image. Video
Upscale, Video -> Video, and Video Extension require `source_image_url` pointing
at an existing local storage video, for example `/storage/videos/example.mp4`.

Video Extension was validated live on June 21, 2026 using
`backend/storage/videos/87e160af6a634bad87080a065d4d22c0.mp4` (a short clip) as
input and generated a 768x512, 121-frame MP4 under `backend/storage/videos/`;
the storage URL and export endpoint both returned `200 video/mp4`, Asset Library
listed the extended video, and Job Monitor reported the job as completed. Video
jobs now charge 10 credits on successful Local LTX completion only.

### Optional Seedance / C-Dance 2.0 provider

Local LTX remains the default video provider. Phase 14A adds an optional
admin-enabled `seedance_api` provider for Text -> Video and Image -> Video. It is
implemented as a generic configurable Seedance-compatible REST adapter because
the available public documentation does not expose one stable, vendor-neutral
REST schema for every Seedance/C-Dance reseller. Admin can configure:

- API key: stored backend-only in `backend/storage/secrets/`, masked in the UI,
  excluded from backups, and never returned raw to the browser
- Base URL
- Model ID
- Task creation endpoint
- Polling/status endpoint, using `{task_id}` when the provider returns a task id

Configure it at `/admin/integrations`. After the key and config are saved,
enable the provider. The `/videos` page then shows a provider selector:

- **Local LTX**: default local/private provider, 10 credits per successful job
- **Seedance / C-Dance 2.0**: optional premium provider, 30 credits per
  successful job (`CREDITS_PER_SEEDANCE_VIDEO`, default `30`)

Failed Seedance jobs are not charged. If the active family user does not have
enough credits, the backend rejects the request before making an external API
call. Successful Seedance jobs store the provider task id when returned, download
the final video server-side into `backend/storage/videos/`, show in Job Monitor
with provider/mode metadata, and appear in Asset Library through the stored local
MP4.

Seedance is deliberately **not** wired for Video -> Video, Video Upscale, or
Video Extension in Phase 14A. Those modes remain Local LTX only unless a future
provider-specific workflow/API is validated.

Seedance environment defaults:

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `CREDITS_PER_SEEDANCE_VIDEO` | `30` | Credits charged after successful Seedance completion |
| `SEEDANCE_DEFAULT_BASE_URL` | empty | Default provider API base URL shown in admin config |
| `SEEDANCE_DEFAULT_MODEL_ID` | `seedance-2.0` | Default model id sent in create requests |
| `SEEDANCE_DEFAULT_CREATE_ENDPOINT` | `/v1/videos` | Default task creation endpoint |
| `SEEDANCE_DEFAULT_STATUS_ENDPOINT` | `/v1/videos/{task_id}` | Default polling endpoint |

Do not paste provider API keys into chat, screenshots, frontend code, or
localStorage. If Seedance fails, is disabled, or runs out of provider-side
credits, select **Local LTX** on `/videos`.

### Optional OpenAI Image API provider

Local ComfyUI / Flux remains the default image/art provider for `/create`.
Phase 14B adds an optional admin-enabled `openai_image_api` provider for:

- **Text -> Image**
- **Image Edit** using a local `/storage/...` image as the input/reference

OpenAI is not used for video, copy, product scenes, campaigns, or avatars in
this phase. Configure it at `/admin/integrations`; API keys are stored
backend-only in `backend/storage/secrets/`, masked in the UI, excluded from
backups, and never returned raw to the browser.

The implementation uses the official OpenAI Images API endpoints:

- `POST /images/generations` for Text -> Image
- `POST /images/edits` for Image Edit

Default admin config:

- Base URL: `https://api.openai.com/v1`
- Image model: `gpt-image-2`
- Size: `1024x1024`
- Quality: `low`
- Output format: PNG

OpenAI image pricing is represented inside the local family credit ledger, not
as real payment processing:

- Local image generation: `CREDITS_PER_GENERATION` (default `5`)
- OpenAI Text -> Image: `CREDITS_PER_OPENAI_IMAGE` (default `15`)
- OpenAI Image Edit: `CREDITS_PER_OPENAI_IMAGE_EDIT` (default `15`)

Credits are charged only after successful completion. Failed OpenAI jobs are not
charged. If the active family user does not have enough credits, the backend
rejects the request before making an OpenAI API call. Successful OpenAI outputs
are saved locally under `backend/storage/generated/`, then shown in Asset
Library as generated image items. If OpenAI is disabled, unconfigured, or
provider-side credits/rate limits fail, choose **Local ComfyUI / Flux** on
`/create`.

Do not paste OpenAI API keys into chat, screenshots, frontend code, or
localStorage.

Video endpoints:

| Method | Path                | Purpose                       |
| ------ | ------------------- | ----------------------------- |
| `POST` | `/api/videos`       | Queue an image-to-video or text-to-video job |
| `GET`  | `/api/videos`       | List video history            |
| `GET`  | `/api/videos/{id}`  | Get one video generation      |

## Video to Text

The Video to Text page (`/video-to-text`) is the local transcription workspace.
It accepts either an uploaded video file or an existing local `/storage/videos/...`
MP4 and creates a transcription job with `queued`, `running`, `completed`, and
`failed` states.

Normal local production mode is:

```env
TRANSCRIPTION_BACKEND=local_whisper
TRANSCRIPTION_MODEL_NAME=base
TRANSCRIPTION_DEVICE=cpu
TRANSCRIPTION_COMPUTE_TYPE=int8
```

The mock backend remains available for fallback/testing:

```env
TRANSCRIPTION_BACKEND=mock
```

The real adapter uses `faster-whisper` locally. No cloud transcription provider
is required. On Windows, install ffmpeg and the Python dependency with:

```powershell
winget install --id Gyan.FFmpeg --source winget --scope user
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If a fresh shell cannot find ffmpeg on PATH yet, set `FFMPEG_PATH` in
`backend/.env` to the installed `ffmpeg.exe`, for example the WinGet
`Gyan.FFmpeg` package path. The status page shows the selected transcription
backend, model, device, compute type, ffmpeg readiness, and faster-whisper
readiness.

If `ffmpeg` or `faster-whisper` is missing, the job fails with a clear dependency
error and does not charge credits. If a video has no speech/audio track, the job
also fails clearly without charging.

Credits:

- completed transcription job: `CREDITS_PER_TRANSCRIPTION` (default `5`)
- optional transcript summary: `CREDITS_PER_TRANSCRIPTION_SUMMARY` (default `2`)
- failed transcription jobs are not charged
- jobs are blocked before processing if the active family user has insufficient
  credits

Summary generation uses the configured local copy provider. If local Qwen/Ollama
is unavailable, the transcript still remains usable and the summary endpoint
returns a clear error.

Recommended model sizes:

- `tiny`: quickest smoke tests, lowest quality
- `base`: current local default, good balance for family/private use
- `small` / `medium`: better accuracy, slower and larger downloads

Transcription endpoints:

| Method | Path                              | Purpose |
| ------ | --------------------------------- | ------- |
| `POST` | `/api/transcriptions`             | Upload or reference a local video and queue transcription |
| `GET`  | `/api/transcriptions`             | List current user's transcription jobs |
| `GET`  | `/api/transcriptions/{id}`        | Get one transcription job |
| `POST` | `/api/transcriptions/{id}/summarize` | Generate an optional summary |
| `GET`  | `/api/transcriptions/{id}/download` | Download transcript text |

## Asset Library

The Asset Library page (`/assets-library`) is the central media manager for the
local studio. It lists uploaded product images, processed/background-removed
assets, generated product scenes, copy generations, videos, and video transcripts
in one searchable place.

The page supports:

- type filters: all, uploads, scenes, copy, transcripts, videos, campaigns
- status filters: completed only and failed only
- search by prompt, filename/title, project name, type, or status
- image previews for uploads, processed assets, and scenes
- native video preview for MP4/web video outputs
- copy preview with copy-to-clipboard
- download links using existing scene, copy, video, or direct storage URLs

Backend endpoint:

| Method | Path           | Purpose                                      |
| ------ | -------------- | -------------------------------------------- |
| `GET`  | `/api/library` | Unified derived list of library media items  |

Library item types:

| Type              | Source table/entity                  | Download behavior |
| ----------------- | ------------------------------------ | ----------------- |
| `upload`          | `product_assets.original_url`        | Direct storage URL |
| `processed_asset` | `product_assets.processed_url`       | Direct storage URL |
| `scene`           | `product_scene_generations.result_url` | `/api/exports/scene/{id}` |
| `copy`            | `copy_generations.result_text`       | `/api/exports/copy/{id}` |
| `video`           | `video_generations.result_url`       | `/api/exports/video/{id}` |
| `transcript`      | `transcription_jobs.transcript_text` | `/api/transcriptions/{id}/download` |
| `campaign`        | reserved for future stored campaigns | not stored yet |

No new database table is required in this phase; `/api/library` derives its
items from existing project-owned records.

## Export Studio

The Export Studio page (`/export-studio`) packages completed project materials
into downloadable ZIP files without running new generation jobs.

Export Studio bundles:

- **Social Bundle**: creates Instagram, Facebook, LinkedIn, and X package
  folders with project copy, scene images, video prompts, metadata, brand kit,
  and optional creative brief context.
- **Marketing Bundle**: packages product scenes, campaign copy, video prompts,
  briefs, brand kit, and project metadata for broader campaign handoff.

Export Studio endpoints:

| Method | Path                            | Purpose                         |
| ------ | ------------------------------- | ------------------------------- |
| `POST` | `/api/exports/social-bundle`    | Download a social-platform ZIP  |
| `POST` | `/api/exports/marketing-bundle` | Download a marketing handoff ZIP |

Both endpoints accept `project_id`, optional `brief_id`, optional
`campaign_bundle_id`, and optional platform names. Existing single-asset export
endpoints remain unchanged.

## Creative Director

The Creative Director page (`/creative-director`) provides planning
recommendations, not generation. It reads project context such as Brand Kit,
Creative Briefs, assets, completed scenes, copy, videos, and campaign history,
then returns campaign, scene, copy, video, and audience recommendations with
rationale and confidence.

Creative Director endpoint:

| Method | Path                                    | Purpose                         |
| ------ | --------------------------------------- | ------------------------------- |
| `POST` | `/api/creative-director/recommendations` | Return strategic recommendations |

Inputs are `project_id` and optional `brief_id`.

## Campaigns

The Campaigns page (`/campaigns`) turns a single chosen **campaign preset** into a
coordinated product scene **and** matching copy. Pick a preset, a project, and a
product asset (optionally a product name), preview what it will generate, then
launch â€” the page polls the linked scene and copy jobs until both settle.

Presets are static, in-code configuration (no database table). Each bundles a
scene preset, a recommended product-scene mode, a scene prompt template (with a
`{product}` placeholder), and a copy type/tone/audience:

| Preset | Scene | Mode | Copy | Tone |
| ------ | ----- | ---- | ---- | ---- |
| `luxury_launch` | luxury | ipadapter | product_description | luxury |
| `instagram_product_ad` | social ad | img2img | instagram_caption | playful |
| `black_friday` | social ad | img2img | facebook_ad | bold |
| `minimalist_studio` | studio | img2img | seo_title | professional |
| `outdoor_lifestyle` | outdoor | img2img | tiktok_hook | friendly |

`POST /api/campaigns/from-preset` creates a queued product-scene job and a linked
copy job (the copy references both the asset and the new scene), and returns both
in `scene_job` / `copy_job`.

Campaign endpoints:

| Method | Path                          | Purpose                              |
| ------ | ----------------------------- | ------------------------------------ |
| `GET`  | `/api/presets`                | List campaign presets                |
| `GET`  | `/api/presets/{id}`           | Get one preset                       |
| `POST` | `/api/campaigns/from-preset`  | Launch a scene + copy from a preset  |

## Campaign Builder

The Campaign Builder (`/campaign-builder`) generates a **complete campaign
package** from one click. Pick a project, a creative brief, a product asset, and
a campaign type; it orchestrates the existing scene, copy, and video generators
(applying brand-kit + creative-brief context exactly like the manual pages) and
records the result as a **campaign bundle**.

It does not add new generation logic — it creates the same job records the manual
routers do and enqueues them. Videos use the selected asset image as their source
(product scenes are still rendering asynchronously at build time), so the
mock/LTX video worker can run immediately.

Endpoint:

| Method | Path                                       | Purpose                          |
| ------ | ------------------------------------------ | -------------------------------- |
| `POST` | `/api/projects/{project_id}/campaign-builder` | Generate a campaign bundle    |

Request: `{ "brief_id": "...", "asset_id": "...", "campaign_type": "product_launch" }`.
Response includes `bundle_id`, `scene_count`, `copy_count`, `video_prompt_count`,
and the full bundle.

Campaign types and what they generate:

| Type | Scenes | Copy | Video |
| ---- | ------ | ---- | ----- |
| `product_launch` | hero + advertising + social (3) | description, IG caption, FB ad | 1 |
| `ecommerce` | hero + clean product (2) | description, SEO title | 0 |
| `social_media` | Instagram + Facebook (2) | IG caption, FB ad | 0 |
| `fashion_editorial` | editorial + storefront + magazine (3) | luxury description | 0 |
| `luxury_brand` | premium ad + editorial (2) | luxury description | 0 |
| `custom` | 1 scene | 1 description | 0 |

Each generated scene/copy/video is a normal job that appears on its own page,
in the Asset Library (the bundle itself shows as a `campaign_bundle` item), and
under the **Campaign Bundles** tab of the Project Workspace. Validation: invalid
project / brief / asset return `404`; an unknown campaign type returns `422`.

## Asset Collections

The Asset Collections page (`/collections`) groups multiple ready product assets
inside a project, then launches one collection-wide campaign from a selected
creative brief and campaign type.

Collections are lightweight records that store a name, description, asset ids,
and status. A collection campaign reuses the same Campaign Builder templates,
but repeats them for every asset in the collection. It creates normal queued
product-scene, copy, and video jobs, records the result as a campaign bundle,
and leaves all existing generation pages responsible for progress tracking.

Collection endpoints:

| Method   | Path                                                       | Purpose                         |
| -------- | ---------------------------------------------------------- | ------------------------------- |
| `GET`    | `/api/projects/{project_id}/collections`                   | List project collections        |
| `POST`   | `/api/projects/{project_id}/collections`                   | Create a collection             |
| `GET`    | `/api/projects/{project_id}/collections/{collection_id}`   | Get one collection              |
| `PUT`    | `/api/projects/{project_id}/collections/{collection_id}`   | Update a collection             |
| `DELETE` | `/api/projects/{project_id}/collections/{collection_id}`   | Delete a collection             |
| `POST`   | `/api/projects/{project_id}/collections/{collection_id}/campaign` | Generate a collection campaign |

Collection campaign requests include `collection_id`, `brief_id`, and
`campaign_type`. The backend validates project, brief, collection, and asset
ownership before queuing jobs.

## Production Studio

The Production Studio page (`/production-studio`) is a lightweight production
pipeline for AI video work:

```text
Storyboard -> Shot List -> Video Prompts -> Video Generation -> Sequence Plan -> Export
```

It does not add a full video editor. Instead, it references existing project
storyboards, shots, and video jobs, stores the selected order, and exports a ZIP
package containing production metadata, storyboards, shots, video metadata,
sequence notes, and completed video files when available.

Production endpoints:

| Method   | Path                                             | Purpose                         |
| -------- | ------------------------------------------------ | ------------------------------- |
| `GET`    | `/api/projects/{project_id}/productions`         | List production pipelines       |
| `POST`   | `/api/projects/{project_id}/productions`         | Create a production             |
| `GET`    | `/api/projects/{project_id}/productions/{id}`    | Read production workspace       |
| `PUT`    | `/api/projects/{project_id}/productions/{id}`    | Update selected sequence items  |
| `DELETE` | `/api/projects/{project_id}/productions/{id}`    | Delete a production             |
| `POST`   | `/api/projects/{project_id}/productions/{id}/export` | Download production ZIP     |

The production model stores `storyboard_ids`, `shot_ids`, `video_ids`, status,
and export URLs. All referenced records are validated against the same project
and current user before saving or exporting.

Production Studio can now create a production directly from a storyboard. That
handoff selects the storyboard, all of its shots, and any videos linked to those
shots. Selecting shots in Production Studio also pulls in linked videos so the
sequence view stays aligned with the storyboard order.

Production ZIP exports include:

- `metadata.json`
- `storyboards.json`
- `shots.json` with linked `product_scene_id` / `video_id`
- `videos.json`
- `keyframes.json`
- `sequence.txt`
- completed linked keyframe image files under `keyframes/` when present
- completed linked video files under `videos/` when present

## Storyboard Studio

The Storyboard Studio page (`/storyboard-studio`) is the Phase 5 planning layer
between Film Studio and Production Studio. It uses the existing `storyboards`
and `shots` tables; no new database table is required.

What it does:

- Selects a project and lists project storyboards.
- Creates storyboards with title, description, and status.
- Adds ordered shots with duration, description, camera notes, generation
  prompt, and character continuity guidance.
- Moves shots up/down to plan multi-scene sequencing.
- Selects a ready product asset, generates a Film Studio keyframe for an
  individual shot via the existing `/api/product-scenes` flow, and can animate
  that keyframe through the existing `/api/videos` image-to-video flow.
- Persists each shot's linked `product_scene_id` and `video_id`, so the shot
  remembers its generated keyframe and clip after page reloads.
- Copies a readable storyboard summary to the clipboard.
- Exports a storyboard shot list as plain text.
- Links directly into Film Studio for keyframe/video generation.
- Leaves final bundle assembly in Production Studio.

Storyboard export endpoint:

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/api/projects/{project_id}/storyboards/{storyboard_id}/export` | Download a text shot-list export |

The export includes the storyboard title, project name, status, description, and
all shots in shot-number order with duration, camera notes, generation prompts,
linked keyframe scene IDs, and linked video IDs.

## Film Studio

The Film Studio page (`/film-studio`) is the Phase 4 film workflow foundation.
It uses existing generation systems rather than adding a new backend model:

```text
Product asset -> Film keyframe -> Image-to-video clip -> Download
```

What it does:

- Selects a project and ready uploaded/processed asset.
- Builds a cinematic keyframe through Product Scenes with `mode=film_scene`.
- Lets you choose shot framing, look, character consistency lock, and motion
  preset.
- Sends a completed keyframe into the existing `/api/videos` `image_to_video`
  flow.
- Shows keyframe history, project video assets, and the latest generated clip
  with download support.
- Adds stronger motion preset labels for cinematic push, runway walk, parallax,
  dolly-in, subtle breathing, and product motion while preserving the same
  `VideoGenerator` interface.

What it does not do yet:

- Storyboard authoring, shot lists, or multi-shot planning. Those remain Phase 5
  Storyboard Studio work.
- Timeline editing, transitions, audio, scheduling, or cloud export.
- Automatic Wan fallback. Wan remains experimental and must report installed
  models before it can be selected.

## Film Studio Expansion Foundation

Sovereign Creative Studio now separates **product preservation** from
**creative transformation**:

- **Preserve Product**: use `segmented_composite_polished` when the goal is to
  keep the person, clothing, pose, and product details mostly unchanged.
- **Creative Edit**: use transformation modes when the goal is to change pose,
  wardrobe, styling, camera angle, lighting, environment, or cinematic framing.

Transformation-oriented Product Scene modes:

| Mode | Purpose | Current engine |
| ---- | ------- | -------------- |
| `creative_edit` | Identity-aware creative editing: pose, camera, clothing, hair, accessories, lighting, composition | Creative Fashion Edit Flux/Kontext workflow |
| `character_reimagination` | Fantasy, cyberpunk, superhero, historical, sci-fi, or age-shifted character variants | Creative Fashion Edit Flux/Kontext workflow |
| `fashion_transformation` | Outfit replacement, color changes, luxury wardrobe, editorial styling | Creative Fashion Edit Flux/Kontext workflow |
| `cinematic_scene_builder` | Film-still composition: wide/medium/close shots, dramatic angles, cinematic light | Creative Fashion Edit Flux/Kontext workflow |
| `creative_fashion_edit` | Fashion-advertising transformation with stronger edit freedom | Dedicated Creative Fashion Edit Flux/Kontext workflow |

These modes intentionally do **not** use the conservative segmented-composite
workflow. They are designed for local film-studio experimentation, not strict
catalog/product preservation.

### Local Model And Workflow Audit

Read-only audit of the current ComfyUI Desktop/CUDA setup found these useful
installed files:

| Area | Installed locally |
| ---- | ----------------- |
| Flux image/edit | `flux1-dev.safetensors`, `flux1-fill-dev.safetensors` |
| LTX video | `ltx-2.3-22b-dev-fp8.safetensors`, `ltx-2.3-22b-distilled-lora-384.safetensors`, `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` |
| Text encoders | `qwen_3_4b.safetensors` |

ComfyUI node families visible locally include Flux/Kontext, Qwen Image Edit
encoders, Wan video nodes, LTXV, Hunyuan video, Kling/Pixverse/Vidu/Runway API
nodes, Seedream/Seedance API nodes, Grok edit API nodes, Stable Audio nodes, ACE
Step audio nodes, ElevenLabs audio/voice API nodes, and Stable Audio nodes.

Important distinction: many of these are **nodes/API integrations**, not proof
that local model weights are installed. The model folders scanned did not show
Wan, Hunyuan video, Seedream, Seedance, Stable Audio, ACE Step, Qwen Image Edit
UNET/VAE, or HiDream E1 model weights.

### Install Plan First

Do not download models automatically. For each candidate, verify the official
source, expected ComfyUI folder, size, VRAM needs, and workflow compatibility:

| Candidate | Expected benefit | Current status |
| --------- | ---------------- | -------------- |
| Qwen Image Edit / Qwen Image Edit 2509 | Strong image editing, fashion/object edits, text-aware edits | Nodes present; UNET/VAE not listed locally |
| Wan 2.2 Image-to-Video | Stronger visible motion than LTX for image-to-video | Nodes present; local weights not found |
| Hunyuan Video | Alternative local video generation path | Nodes present; local weights not found |
| Seedance / Seedream | Reference-to-video and image edit candidates | API nodes present; local weights not found |
| Stable Audio / ACE Step | Music, sound effects, audio generation | Nodes present; local weights not found |
| Grok / Nano Banana / Kling / Runway / Vidu | Cloud/API image/video editing options | API nodes present; not local/offline |

Recommended next step is a dedicated **Model Install Planning** pass that ranks
these candidates by quality, disk size, VRAM requirement, license/source, and how
well they map to the app's existing generator interfaces.

## Exports

Generated outputs can be downloaded as usable marketing files. Download buttons
appear on the Product Scenes, Copy Studio, Campaigns, and Videos pages, and are
disabled until the underlying job is `completed`.

- **Scene image** â€” `GET /api/exports/scene/{id}` streams the generated image as a
  download attachment.
- **Copy text** â€” `GET /api/exports/copy/{id}` returns the copy as a `.txt`
  attachment.
- **Video** â€” `GET /api/exports/video/{id}` returns the generated video artifact
  as a download attachment.
- **Campaign bundle** â€” `POST /api/exports/campaign-bundle` with `scene_id`
  and/or `copy_id` builds a `.zip` containing the scene image (if completed), a
  `copy.txt` (if completed), and a `metadata.json` (project, asset, scene/copy
  details and timestamps).

Validation is strict and safe: only `completed` jobs export (otherwise `409`),
unknown jobs and missing files return `404`, and a bundle must reference at least
one job (`400`). Jobs are always scoped to the current user. Zip files are written
to local `EXPORT_DIR` (default `backend/storage/exports/`).

Export endpoints:

| Method | Path                              | Purpose                          |
| ------ | --------------------------------- | -------------------------------- |
| `GET`  | `/api/exports/scene/{id}`         | Download a completed scene image |
| `GET`  | `/api/exports/copy/{id}`          | Download completed copy as `.txt`|
| `GET`  | `/api/exports/video/{id}`         | Download a completed video       |
| `POST` | `/api/exports/campaign-bundle`    | Download a scene+copy `.zip`      |

## Workflow Manager

The Workflow Manager (`/workflow-manager`) lets you switch models, modes, and
backends from the UI — no `.env` edits or restarts. Selections are validated
against installed models / a live ComfyUI probe, applied to the running process,
and persisted to `backend/storage/workflow_config.json` so they survive restarts.
Environment-variable configuration still works and provides the initial defaults.

Endpoints:

| Method | Path                            | Purpose                              |
| ------ | ------------------------------- | ------------------------------------ |
| `GET`  | `/api/workflow-manager/status`  | Active model/mode/backend selections |
| `GET`  | `/api/workflow-manager/models`  | Model catalog with availability      |
| `GET`  | `/api/workflow-manager/workflows` | Detected workflow JSON files       |
| `PUT`  | `/api/workflow-manager/config`  | Update selections (validated)        |

**Selectable settings:**

- **Image model** → `flux-kontext`, `qwen-image`, `hidream-e1`, `sdxl`, `sd1.5`
  (drives `PRODUCT_SCENE_MODEL`; SDXL/SD1.5 use the legacy SD workflow).
- **Scene mode** → `img2img`, `ipadapter` (needs IPAdapter nodes), `inpaint`,
  and the creative modes `segmented_composite` / `segmented_composite_polished`
  (need RemBG), `advertising_scene`, `fashion_editorial`. Availability is live
  (workflow file + required nodes); see [Product Scenes](#product-scenes).
- **Video backend** → `mock` (default), `ltx-2.3`, `ltx-2.3.1` (ComfyUI/LTX).
- **Copy backend** → `mock` (default), `openai`, `claude`, `gemini`, `ollama`,
  `local-qwen`, `local-deepseek`. Availability is live: key-gated providers need
  their API key; Ollama providers need Ollama reachable with a matching model.
  See [Copy Studio](#copy-studio) for details.

**Active config on generation pages:** Product Scenes shows the active image
model + scene mode, Videos shows the active video backend, and Copy Studio shows
the active copy backend — each with a "Change" link to the Workflow Manager.

**Fallback behavior:** if a selection is unavailable (ComfyUI offline, model not
installed, or an unknown/unimplemented value), the update is rejected with a
warning and the previous working configuration is kept — generation never
crashes, and mock backends remain available. On startup, a persisted selection
that is no longer available is skipped (the safe default stays active).

## Database migrations

The schema is managed with **Alembic** (`backend/migrations/`). You no longer
delete `sovereign.db` when the schema changes.

- **Startup auto-migrates.** When the backend boots it brings the database to the
  latest revision: it creates everything on a fresh install, and upgrades an
  existing database in place.
- **Revisions:** `0001` is the baseline schema (through Phase 7); `0002` adds
  `product_assets.mask_url` and `product_scene_generations.mode` (Phase 8); `0003`
  adds the `copy_generations` table (Copy Studio); `0004` adds the
  `video_generations` table (image-to-video foundation); `0005` adds the project
  brand-kit fields; `0006` adds the `creative_briefs` table (campaign planning);
  `0007` adds the `campaign_bundles` table (one-click Campaign Builder);
  `0008` adds Video Studio storyboards and video modes; `0009` adds
  `asset_collections` for multi-asset campaign planning; `0010` adds
  `production_projects` for the Production Studio pipeline; `0011` adds
  product-scene target attributes; `0012` links shots to generated keyframes
  and videos.

### Fresh install

Nothing extra to do â€” `uvicorn app.main:app` creates and migrates the database on
first run.

### Upgrade an existing database

Either just start the backend (it migrates on startup), or run migrations
explicitly from `backend/` with the venv active:

```powershell
python migrate.py          # applies all pending migrations to head
# or, equivalently:
alembic upgrade head
```

This works on a **legacy database** created before Alembic existed: the runner
detects the missing `alembic_version` table, stamps the baseline, then applies the
remaining migrations â€” your data is preserved. Re-running is a safe no-op.

To target a non-default database, set `DATABASE_URL` first
(e.g. `$env:DATABASE_URL = "sqlite:///C:/path/to/sovereign.db"`).

### Reset (last resort only)

If a database is genuinely corrupt or you want a clean slate, delete
`backend/sovereign.db` and restart â€” startup recreates it at the latest schema.
This destroys all local data; prefer the upgrade path above.

## Tests And Builds

Backend:

```powershell
cd backend
.venv\Scripts\Activate.ps1
pytest -q
```

Frontend:

```powershell
cd frontend
npm run typecheck
npm run build
```

If PowerShell blocks `npm.ps1`, run `npm.cmd run typecheck` and
`npm.cmd run build`.

## Configuration

Backend env vars:

| Variable                 | Default                         | Purpose                         |
| ------------------------ | ------------------------------- | ------------------------------- |
| `DATABASE_URL`           | `sqlite:///backend/sovereign.db`| Database connection             |
| `STORAGE_DIR`            | `backend/storage`               | Generated asset storage         |
| `EXPORT_DIR`             | `backend/storage/exports`       | Generated export zips           |
| `FRONTEND_ORIGIN`        | `http://localhost:3000`         | CORS allow-origin               |
| `GENERATOR_BACKEND`      | `mock`                          | Base text-to-image backend: `mock` or `comfyui` |
| `COMFYUI_BASE_URL`       | `http://127.0.0.1:8001`         | ComfyUI API base URL            |
| `COMFYUI_WORKFLOW_PATH`  | `workflows/text_to_image.json`  | Image-gen workflow JSON path    |
| `CREDITS_PER_OPENAI_IMAGE` | `15`                          | Cost per successful OpenAI Text -> Image job |
| `CREDITS_PER_OPENAI_IMAGE_EDIT` | `15`                    | Cost per successful OpenAI Image Edit job |
| `OPENAI_DEFAULT_BASE_URL` | `https://api.openai.com/v1`    | Default OpenAI API base URL shown in admin config |
| `OPENAI_DEFAULT_IMAGE_MODEL` | `gpt-image-2`               | Default OpenAI image model |
| `OPENAI_DEFAULT_IMAGE_SIZE` | `1024x1024`                  | Default OpenAI image size |
| `OPENAI_DEFAULT_IMAGE_QUALITY` | `low`                    | Default OpenAI image quality |
| `PRODUCT_SCENE_BACKEND`  | `comfyui`                       | Product-scene backend: `mock` or `comfyui` |
| `PRODUCT_SCENE_MODEL`    | `flux-kontext`                  | ComfyUI product-scene family: `flux-kontext`, `qwen-image`, or `hidream-e1` |
| `COMFYUI_PRODUCT_SCENE_MODE` | `segmented_composite_polished` | Default product-scene mode |
| `COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH` | `workflows/product_scene.json` | img2img product-scene workflow |
| `COMFYUI_PRODUCT_SCENE_FLUX_KONTEXT_WORKFLOW_PATH` | `workflows/product_scene_flux_kontext.json` | Flux/Kontext-ready product-scene workflow |
| `COMFYUI_PRODUCT_SCENE_QWEN_IMAGE_WORKFLOW_PATH` | `workflows/product_scene_qwen_image.json` | Qwen Image product-scene workflow |
| `COMFYUI_PRODUCT_SCENE_HIDREAM_E1_WORKFLOW_PATH` | `workflows/product_scene_hidream_e1.json` | HiDream E1 product-scene workflow |
| `COMFYUI_PRODUCT_SCENE_IPADAPTER_WORKFLOW_PATH` | `workflows/product_scene_ipadapter.json` | IPAdapter product-scene workflow |
| `COMFYUI_PRODUCT_SCENE_INPAINT_WORKFLOW_PATH` | `workflows/product_scene_inpaint.json` | Inpaint product-scene workflow |
| `COMFYUI_PRODUCT_SCENE_SEGMENTED_COMPOSITE_WORKFLOW_PATH` | `workflows/product_scene_segmented_composite.json` | Segmented-composite workflow |
| `COMFYUI_PRODUCT_SCENE_SEGMENTED_COMPOSITE_POLISHED_WORKFLOW_PATH` | `workflows/product_scene_segmented_composite_polished.json` | Polished segmented-composite workflow |
| `COMFYUI_PRODUCT_SCENE_ADVERTISING_SCENE_WORKFLOW_PATH` | `workflows/product_scene_advertising_scene.json` | Advertising-scene workflow |
| `COMFYUI_PRODUCT_SCENE_FASHION_EDITORIAL_WORKFLOW_PATH` | `workflows/product_scene_fashion_editorial.json` | Fashion-editorial workflow |
| `COMFYUI_PRODUCT_SCENE_CREATIVE_FASHION_EDIT_WORKFLOW_PATH` | `workflows/product_scene_creative_fashion_edit.json` | Creative Fashion Edit workflow |
| `COMFYUI_PRODUCT_SCENE_INPAINT_FALLBACK` | `img2img`           | Mode used when inpaint has no mask: `img2img` or `ipadapter` |
| `DEFAULT_CREDITS`        | `100`                           | Starting credits for demo user  |
| `COPY_BACKEND`           | `local-qwen`                    | `mock`, `openai`, `claude`, `gemini`, `ollama`, `local-qwen`, `local-deepseek` |
| `OPENAI_API_KEY`         | _(empty)_                       | Required for the `openai` copy backend |
| `OPENAI_COPY_MODEL`      | `gpt-4o-mini`                   | OpenAI model for copy           |
| `ANTHROPIC_API_KEY`      | _(empty)_                       | Required for the `claude` copy backend |
| `ANTHROPIC_COPY_MODEL`   | `claude-3-5-sonnet-latest`      | Claude model for copy           |
| `GEMINI_API_KEY`         | _(empty)_                       | Required for the `gemini` copy backend |
| `GEMINI_COPY_MODEL`      | `gemini-1.5-flash`              | Gemini model for copy           |
| `OLLAMA_BASE_URL`        | `http://127.0.0.1:11434`        | Ollama server URL               |
| `OLLAMA_COPY_MODEL`      | `llama3.1`                      | Ollama model for `ollama` copy backend |
| `OLLAMA_QWEN_MODEL`      | `qwen3:4b`                      | Model for the `local-qwen` provider |
| `OLLAMA_DEEPSEEK_MODEL`  | `deepseek-r1`                   | Model for the `local-deepseek` provider |
| `VIDEO_BACKEND`          | `comfyui`                       | Video backend: `mock` or `comfyui` |
| `COMFYUI_VIDEO_ENGINE`   | `ltx`                           | Real ComfyUI video engine: `ltx` or experimental `wan` |
| `COMFYUI_VIDEO_WORKFLOW_PATH` | `workflows/image_to_video.json` | Image-to-video workflow JSON path |
| `COMFYUI_TEXT_TO_VIDEO_WORKFLOW_PATH` | `workflows/text_to_video_ltx.json` | Text-to-video workflow JSON path |
| `COMFYUI_VIDEO_UPSCALE_WORKFLOW_PATH` | `workflows/video_upscale_ltx.json` | Video upscale workflow JSON path |
| `COMFYUI_VIDEO_TO_VIDEO_WORKFLOW_PATH` | `workflows/video_to_video_ltx.json` | Video-to-video workflow JSON path |
| `COMFYUI_VIDEO_MODEL_NAME` | `ltx-2.3-22b-dev-fp8.safetensors` | Video model name injected into workflows using `__VIDEO_MODEL__` |
| `COMFYUI_WAN_VIDEO_WORKFLOW_PATH` | `workflows/image_to_video_wan.json` | Experimental Wan image-to-video workflow path |
| `COMFYUI_WAN_VIDEO_MODEL_NAME` | _(empty)_                 | Wan UNET/model filename injected when `COMFYUI_VIDEO_ENGINE=wan` |
| `CREDITS_PER_VIDEO`    | `10`                            | Cost per successful Local LTX video job |
| `CREDITS_PER_SEEDANCE_VIDEO` | `30`                     | Cost per successful Seedance/C-Dance video job |
| `TRANSCRIPTION_BACKEND` | `local_whisper`                | Video-to-text backend: `mock` or local `faster-whisper` adapter |
| `TRANSCRIPTION_MODEL_NAME` | `base`                      | Whisper/faster-whisper model name |
| `TRANSCRIPTION_DEVICE` | `cpu`                           | faster-whisper device; CPU/int8 is the safe local default |
| `TRANSCRIPTION_COMPUTE_TYPE` | `int8`                    | faster-whisper compute type |
| `FFMPEG_PATH` | _(empty)_                              | Optional explicit path to `ffmpeg.exe` when PATH is not refreshed |
| `TRANSCRIPTION_MAX_UPLOAD_MB` | `500`                    | Maximum uploaded video size for transcription |
| `TRANSCRIPTION_MODEL_DIR` | `backend/storage/models/whisper` | Local Whisper model cache directory |
| `CREDITS_PER_TRANSCRIPTION` | `5`                      | Cost per successful transcription job |
| `CREDITS_PER_TRANSCRIPTION_SUMMARY` | `2`              | Cost per successful optional transcript summary |
| `AVATAR_BACKEND` | `placeholder`                   | Avatar backend: `placeholder` or `comfyui_wan_infinite_talk` |
| `AVATAR_WAN_WORKFLOW_PATH` | `workflows/avatar_wan_infinite_talk.json` | Wan InfiniteTalk workflow path |
| `AVATAR_WAN_MODEL_NAME` | _(empty)_                  | Wan video diffusion filename |
| `AVATAR_INFINITETALK_PATCH_NAME` | _(empty)_          | InfiniteTalk model-patch filename |
| `AVATAR_AUDIO_ENCODER_NAME` | _(empty)_               | Audio encoder filename |
| `AVATAR_WAN_PRESET` | `tiny_test`                   | Default talking-avatar quality preset |
| `AVATAR_WAN_WIDTH` / `AVATAR_WAN_HEIGHT` | _(empty)_ | Optional server-only preset dimension override |
| `AVATAR_WAN_FRAMES` / `AVATAR_WAN_STEPS` | _(empty)_ | Optional server-only preset frame/step override |
| `AVATAR_WAN_CFG` | _(empty)_                      | Optional server-only CFG override; keep `1.0` unless validated |
| `AVATAR_WAN_MAX_RETRIES` | `0`                      | Retry count for avatar jobs; `0` prevents repeated OOM pressure |
| `SEEDANCE_DEFAULT_BASE_URL` | _(empty)_                 | Default Seedance-compatible provider base URL shown in admin config |
| `SEEDANCE_DEFAULT_MODEL_ID` | `seedance-2.0`           | Default Seedance-compatible model id |
| `SEEDANCE_DEFAULT_CREATE_ENDPOINT` | `/v1/videos`     | Default Seedance-compatible create endpoint |
| `SEEDANCE_DEFAULT_STATUS_ENDPOINT` | `/v1/videos/{task_id}` | Default Seedance-compatible polling endpoint |
| `CREDITS_PER_GENERATION` | `5`                             | Cost per completed generation   |

Frontend env vars:

| Variable              | Default                 | Purpose              |
| --------------------- | ----------------------- | -------------------- |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | Backend API base URL |

## Health & status

- `GET /api/health` â€” liveness check (`{"status": "ok"}`).
- `GET /api/status` â€” configuration summary: image/product-scene/copy/video
  backends, ComfyUI base URL + whether it's configured, whether an OpenAI key is
  set, and the storage path + writability.
- The frontend **Status** page (`/status`) shows API connection state and the
  same configuration at a glance.

On startup the backend logs clear warnings for common misconfigurations (e.g.
`COPY_BACKEND=openai` with no `OPENAI_API_KEY`, an unknown backend value, or an
unwritable storage directory) instead of failing silently.

## Troubleshooting

- **Frontend can't reach the backend / Status shows "API not reachable":** make
  sure the backend is running on port 8000, and that `NEXT_PUBLIC_API_URL` in
  `frontend/.env.local` matches it.
- **`powershell ... start-all.ps1` is blocked:** run with
  `-ExecutionPolicy Bypass` (as shown), or unblock the scripts.
- **Copy jobs fail with an API-key error:** `COPY_BACKEND=openai` needs
  `OPENAI_API_KEY`; normal local mode uses `COPY_BACKEND=local-qwen` with
  Ollama model `qwen3:4b`. Use `COPY_BACKEND=mock` only as a fallback.
- **ComfyUI features fail:** confirm ComfyUI is running at `COMFYUI_BASE_URL` and
  the required nodes/models are installed; otherwise keep the `mock` backends.
- **Real ComfyUI video fails:** normal local mode is `VIDEO_BACKEND=comfyui` with
  ComfyUI Desktop at `http://127.0.0.1:8001`, not the old
  `C:\AI\comfyui-dml` environment. Desktop is CUDA/GPU-backed on the RTX 5070 Ti
  and sees the required LTX checkpoint, Gemma text encoder, LoRA, and latent
  upscaler. Tiny LTXV app smoke tests should use the **Test/Fast** preset. Switch
  to `VIDEO_BACKEND=mock` only when ComfyUI/LTX is offline or being repaired.
- **Video to Text says transcription is not ready:** install ffmpeg with
  `winget install --id Gyan.FFmpeg --source winget --scope user`, install
  backend requirements, then restart the backend. If PATH has not refreshed, set
  `FFMPEG_PATH` to the installed `ffmpeg.exe`.
- **Schema looks out of date:** run `python migrate.py` (see
  [Database migrations](#database-migrations)). Deleting the DB is a last resort.

## Next Direction

The local research app is now feature-complete for private family trials:
product/image upload, product scene generation, AI copy generation, campaign
presets, exports, real local ComfyUI/LTX video, and real local Video to Text.
Mock backends remain available for emergency fallback and tests.
