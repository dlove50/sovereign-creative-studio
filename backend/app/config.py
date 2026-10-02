"""Central configuration. All values are env-overridable so the same code
runs locally (SQLite + mock generator) and, later, against real services."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load backend/.env if present. Does not override variables already set in the
# environment (so tests and explicit exports win).
load_dotenv(BASE_DIR / ".env")

# --- Storage -----------------------------------------------------------------
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage")))
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Local scratch space for generated export files (zips). Created on demand.
EXPORT_DIR = Path(os.getenv("EXPORT_DIR", str(STORAGE_DIR / "exports")))

# --- Database ----------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'sovereign.db'}")

# --- CORS --------------------------------------------------------------------
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

# --- Generator backend -------------------------------------------------------
# "mock" (default/fallback) or "comfyui" for the real adapter.
GENERATOR_BACKEND = os.getenv("GENERATOR_BACKEND", "mock")
COMFYUI_BASE_URL = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8001")
COMFYUI_WORKFLOW_PATH = os.getenv(
    "COMFYUI_WORKFLOW_PATH", "workflows/text_to_image.json"
)
COMFYUI_IMAGE_EDIT_WORKFLOW_PATH = os.getenv(
    "COMFYUI_IMAGE_EDIT_WORKFLOW_PATH", "workflows/image_edit_qwen_2509.json"
)

# --- Image quality presets (local text-to-image model selection) -------------
# The default keeps the current safe local model (SD1.5 / current workflow).
# "local_fast" | "flux2_klein" | "flux1_dev" | "sdxl". FLUX.2-dev (32B) is NOT a
# preset on purpose — it is too heavy for 16 GB VRAM / 32 GB RAM here.
IMAGE_QUALITY_PRESET = os.getenv("IMAGE_QUALITY_PRESET", "local_fast")
IMAGE_WORKFLOW_FLUX2_KLEIN = os.getenv(
    "IMAGE_WORKFLOW_FLUX2_KLEIN", "workflows/text_to_image_flux2_klein.json"
)
IMAGE_WORKFLOW_FLUX1_DEV = os.getenv(
    "IMAGE_WORKFLOW_FLUX1_DEV", "workflows/text_to_image_flux1_dev.json"
)
IMAGE_WORKFLOW_FLUX1_KREA = os.getenv(
    "IMAGE_WORKFLOW_FLUX1_KREA", "workflows/text_to_image_flux1_krea.json"
)
IMAGE_WORKFLOW_SDXL = os.getenv(
    "IMAGE_WORKFLOW_SDXL", "workflows/text_to_image_sdxl.json"
)
IMAGE_WORKFLOW_ILLUSTRIOUS = os.getenv(
    "IMAGE_WORKFLOW_ILLUSTRIOUS", "workflows/text_to_image_illustrious.json"
)
IMAGE_WORKFLOW_KREA2_TURBO = os.getenv(
    "IMAGE_WORKFLOW_KREA2_TURBO", "workflows/text_to_image_krea2_turbo.json"
)
IMAGE_WORKFLOW_Z_IMAGE_TURBO = os.getenv(
    "IMAGE_WORKFLOW_Z_IMAGE_TURBO", "workflows/text_to_image_z_image_turbo.json"
)
IMAGE_WORKFLOW_NETAYUME = os.getenv(
    "IMAGE_WORKFLOW_NETAYUME", "workflows/text_to_image_netayume.json"
)
# Face / subject refinement (detect -> inpaint/refine -> upscale). Architecture is
# in place but disabled until the refinement workflow + detector are installed.
FACE_REFINE_ENABLED = os.getenv("FACE_REFINE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
IMAGE_WORKFLOW_FACE_REFINE = os.getenv(
    "IMAGE_WORKFLOW_FACE_REFINE", "workflows/face_subject_refine.json"
)
# FLUX.2 Klein 4B model file name in ComfyUI diffusion_models (Comfy-Org/flux2-klein-4B,
# distilled flux-2-klein-4b.safetensors). Uses the already-present qwen_3_4b text encoder
# (CLIPLoader type=flux2) + flux2-vae.safetensors. FLUX.2-dev (Mistral-24B) and Klein 9B
# are intentionally NOT used here — too heavy for 16 GB VRAM / 32 GB RAM.
FLUX2_KLEIN_MODEL_NAME = os.getenv("FLUX2_KLEIN_MODEL_NAME", "flux-2-klein-4b.safetensors")
FLUX1_KREA_MODEL_NAME = os.getenv(
    "FLUX1_KREA_MODEL_NAME", "flux1-krea-dev_fp8_scaled.safetensors"
)
KREA2_TURBO_MODEL_NAME = os.getenv("KREA2_TURBO_MODEL_NAME", "krea2_turbo_fp8_scaled.safetensors")
KREA2_TEXT_ENCODER_NAME = os.getenv("KREA2_TEXT_ENCODER_NAME", "qwen3vl_4b_fp8_scaled.safetensors")
KREA2_VAE_NAME = os.getenv("KREA2_VAE_NAME", "qwen_image_vae.safetensors")

# --- Product-scene backend ---------------------------------------------------
# "mock" (fallback/testing) or "comfyui" for the real product-scene adapter.
PRODUCT_SCENE_BACKEND = os.getenv("PRODUCT_SCENE_BACKEND", "comfyui")
# Optional model family for the ComfyUI product-scene adapter:
# "flux-kontext" | "qwen-image" | "hidream-e1". When unset, the adapter uses
# the legacy SD1.5 workflows selected by COMFYUI_PRODUCT_SCENE_MODE.
PRODUCT_SCENE_MODEL = os.getenv("PRODUCT_SCENE_MODEL", "flux-kontext")
# Default product-scene mode. Per-request mode (from the UI) overrides this.
# "img2img" | "ipadapter" | "inpaint".
COMFYUI_PRODUCT_SCENE_MODE = os.getenv(
    "COMFYUI_PRODUCT_SCENE_MODE", "segmented_composite_polished"
)
COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH", "workflows/product_scene.json"
)
COMFYUI_PRODUCT_SCENE_FLUX_KONTEXT_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_FLUX_KONTEXT_WORKFLOW_PATH",
    "workflows/product_scene_flux_kontext.json",
)
COMFYUI_PRODUCT_SCENE_QWEN_IMAGE_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_QWEN_IMAGE_WORKFLOW_PATH",
    "workflows/product_scene_qwen_image.json",
)
COMFYUI_PRODUCT_SCENE_HIDREAM_E1_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_HIDREAM_E1_WORKFLOW_PATH",
    "workflows/product_scene_hidream_e1.json",
)
COMFYUI_PRODUCT_SCENE_IPADAPTER_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_IPADAPTER_WORKFLOW_PATH",
    "workflows/product_scene_ipadapter.json",
)
COMFYUI_PRODUCT_SCENE_INPAINT_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_INPAINT_WORKFLOW_PATH",
    "workflows/product_scene_inpaint.json",
)
# Creative scene-mode workflows (Phase C9).
COMFYUI_PRODUCT_SCENE_SEGMENTED_COMPOSITE_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_SEGMENTED_COMPOSITE_WORKFLOW_PATH",
    "workflows/product_scene_segmented_composite.json",
)
COMFYUI_PRODUCT_SCENE_SEGMENTED_COMPOSITE_POLISHED_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_SEGMENTED_COMPOSITE_POLISHED_WORKFLOW_PATH",
    "workflows/product_scene_segmented_composite_polished.json",
)
COMFYUI_PRODUCT_SCENE_ADVERTISING_SCENE_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_ADVERTISING_SCENE_WORKFLOW_PATH",
    "workflows/product_scene_advertising_scene.json",
)
COMFYUI_PRODUCT_SCENE_FASHION_EDITORIAL_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_FASHION_EDITORIAL_WORKFLOW_PATH",
    "workflows/product_scene_fashion_editorial.json",
)
COMFYUI_PRODUCT_SCENE_CREATIVE_FASHION_EDIT_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_CREATIVE_FASHION_EDIT_WORKFLOW_PATH",
    "workflows/product_scene_creative_fashion_edit.json",
)
# --- Film Studio: transformation-first routing (Path 2) ----------------------
# Creative Edit workflows default to Transform Mode (Qwen Image Edit). Preserve
# Mode (Flux Kontext) must be selected explicitly. "transform" | "preserve".
CREATIVE_DEFAULT_POLICY = os.getenv("CREATIVE_DEFAULT_POLICY", "transform")
# Which Qwen creative workflow Transform Mode uses: "gguf" (default, faster,
# more VRAM headroom on 16 GB) or "fp8" (higher fidelity, needs RAM offload).
CREATIVE_QWEN_PRECISION = os.getenv("CREATIVE_QWEN_PRECISION", "gguf")
# Transform-mode Qwen Image Edit workflows (GGUF "Fast" + fp8 "Quality").
COMFYUI_PRODUCT_SCENE_CREATIVE_QWEN_EDIT_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_CREATIVE_QWEN_EDIT_WORKFLOW_PATH",
    "workflows/product_scene_creative_qwen_edit.json",
)
COMFYUI_PRODUCT_SCENE_CREATIVE_QWEN_EDIT_FP8_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_CREATIVE_QWEN_EDIT_FP8_WORKFLOW_PATH",
    "workflows/product_scene_creative_qwen_edit_fp8.json",
)
# Clothing & Style Edit: dedicated targeted-edit workflow (Qwen Edit Plus +
# strong negative) tuned to change only the requested garment.
COMFYUI_PRODUCT_SCENE_CLOTHING_STYLE_EDIT_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_CLOTHING_STYLE_EDIT_WORKFLOW_PATH",
    "workflows/product_scene_clothing_style_edit.json",
)
# Masked Attribute Editor: generic targeted edit that regenerates only inside a
# supplied/segmented mask (pants, shirt, hair, glasses, ...) and composites the
# original back outside it, so identity/pose/background are locked.
COMFYUI_PRODUCT_SCENE_MASKED_ATTRIBUTE_EDIT_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_MASKED_ATTRIBUTE_EDIT_WORKFLOW_PATH",
    "workflows/product_scene_masked_attribute_edit.json",
)
# Mask-preview (segmentation only, no Qwen edit) workflows for the UI preview.
COMFYUI_MASKPREVIEW_HUMANPARSE_WORKFLOW_PATH = os.getenv(
    "COMFYUI_MASKPREVIEW_HUMANPARSE_WORKFLOW_PATH",
    "workflows/maskpreview_humanparse.json",
)
COMFYUI_MASKPREVIEW_AUTOSEG_WORKFLOW_PATH = os.getenv(
    "COMFYUI_MASKPREVIEW_AUTOSEG_WORKFLOW_PATH",
    "workflows/maskpreview_autoseg.json",
)
# Human-parsing attribute edit: SCHP LIP/ATR produces a precise class mask
# (pants, hair, face, shoes, dress, single upper garment) for the masked edit.
COMFYUI_PRODUCT_SCENE_ATTRIBUTE_EDIT_HUMANPARSE_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_ATTRIBUTE_EDIT_HUMANPARSE_WORKFLOW_PATH",
    "workflows/product_scene_attribute_edit_humanparse.json",
)
# Auto-seg attribute edit: GroundingDINO+SAM generate the mask from a text
# target, then the masked Qwen edit runs. Two variants: plain, and a
# face-protected one (subtracts a "face" mask) for hair/beard/head edits.
COMFYUI_PRODUCT_SCENE_ATTRIBUTE_EDIT_AUTOSEG_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_ATTRIBUTE_EDIT_AUTOSEG_WORKFLOW_PATH",
    "workflows/product_scene_attribute_edit_autoseg.json",
)
COMFYUI_PRODUCT_SCENE_ATTRIBUTE_EDIT_AUTOSEG_FACEPROTECT_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_ATTRIBUTE_EDIT_AUTOSEG_FACEPROTECT_WORKFLOW_PATH",
    "workflows/product_scene_attribute_edit_autoseg_faceprotect.json",
)
# Pose Mode fallback: two-stage hybrid (SDXL + OpenPose -> Qwen refine) in one graph.
COMFYUI_PRODUCT_SCENE_POSE_EDIT_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_POSE_EDIT_WORKFLOW_PATH",
    "workflows/product_scene_pose_edit.json",
)
# Identity Pose: SDXL + OpenPose + IPAdapter -> Qwen refine. Preset skeleton
# drives the pose; reference photo is DWPose-d first.
COMFYUI_PRODUCT_SCENE_POSE_IDENTITY_PRESET_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_POSE_IDENTITY_PRESET_WORKFLOW_PATH",
    "workflows/product_scene_pose_identity_preset.json",
)
COMFYUI_PRODUCT_SCENE_POSE_IDENTITY_REFERENCE_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_POSE_IDENTITY_REFERENCE_WORKFLOW_PATH",
    "workflows/product_scene_pose_identity_reference.json",
)
# Stylized Pose fallback: preset skeleton drives the pose; reference photo is DWPose-d first.
COMFYUI_PRODUCT_SCENE_POSE_PRESET_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_POSE_PRESET_WORKFLOW_PATH",
    "workflows/product_scene_pose_preset.json",
)
COMFYUI_PRODUCT_SCENE_POSE_REFERENCE_WORKFLOW_PATH = os.getenv(
    "COMFYUI_PRODUCT_SCENE_POSE_REFERENCE_WORKFLOW_PATH",
    "workflows/product_scene_pose_reference.json",
)
# Bundled preset skeleton PNGs live under STORAGE_DIR/pose_presets/<name>.png.
POSE_PRESETS = (
    "standing",
    "walking",
    "sitting",
    "runway",
    "crossed_arms",
    "hands_in_pockets",
    "action",
)
# Film Mode (future): Wan 2.2 image-to-video template, consumed by Video Studio.
COMFYUI_FILM_WAN_WORKFLOW_PATH = os.getenv(
    "COMFYUI_FILM_WAN_WORKFLOW_PATH", "workflows/image_to_video_wan.json"
)
# When inpaint mode is requested but no mask is available, fall back to this
# mode: "img2img" (default) or "ipadapter".
COMFYUI_PRODUCT_SCENE_INPAINT_FALLBACK = os.getenv(
    "COMFYUI_PRODUCT_SCENE_INPAINT_FALLBACK", "img2img"
)

# --- Copy generator ----------------------------------------------------------
# "mock" (fallback/testing), "openai", "ollama", "claude", "gemini",
# "local-qwen", or "local-deepseek". All implement the same CopyGenerator
# interface; mock is always available.
COPY_BACKEND = os.getenv("COPY_BACKEND", "local-qwen")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_COPY_MODEL = os.getenv("OPENAI_COPY_MODEL", "gpt-4o-mini")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_COPY_MODEL = os.getenv("OLLAMA_COPY_MODEL", "llama3.1")
# Local Ollama presets for the "local-qwen" / "local-deepseek" providers.
OLLAMA_QWEN_MODEL = os.getenv("OLLAMA_QWEN_MODEL", "qwen3:4b")
# Video agent script writer. The 27B writes noticeably better scripts (~75 s);
# set VIDEO_AGENT_MODEL=qwen3:4b for speed (~15 s).
VIDEO_AGENT_MODEL = os.getenv("VIDEO_AGENT_MODEL", "qwen3.8:27b")
OLLAMA_DEEPSEEK_MODEL = os.getenv("OLLAMA_DEEPSEEK_MODEL", "qwen3.6:35b")
# Anthropic (Claude) and Google (Gemini) — optional; no key required at startup.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_COPY_MODEL = os.getenv("ANTHROPIC_COPY_MODEL", "claude-3-5-sonnet-latest")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_COPY_MODEL = os.getenv("GEMINI_COPY_MODEL", "gemini-1.5-flash")

# --- Video generator ---------------------------------------------------------
# "mock" (fallback/testing) or "comfyui" for the real image-to-video adapter.
VIDEO_BACKEND = os.getenv("VIDEO_BACKEND", "comfyui")
# ComfyUI video engine used when VIDEO_BACKEND=comfyui. "ltx" keeps the proven
# LTX path; "wan" uses the experimental Wan image-to-video workflow.
COMFYUI_VIDEO_ENGINE = os.getenv("COMFYUI_VIDEO_ENGINE", "ltx")
COMFYUI_VIDEO_WORKFLOW_PATH = os.getenv(
    "COMFYUI_VIDEO_WORKFLOW_PATH", "workflows/image_to_video.json"
)
COMFYUI_TEXT_TO_VIDEO_WORKFLOW_PATH = os.getenv(
    "COMFYUI_TEXT_TO_VIDEO_WORKFLOW_PATH", "workflows/text_to_video_ltx.json"
)
COMFYUI_VIDEO_UPSCALE_WORKFLOW_PATH = os.getenv(
    "COMFYUI_VIDEO_UPSCALE_WORKFLOW_PATH", "workflows/video_upscale_ltx.json"
)
COMFYUI_VIDEO_TO_VIDEO_WORKFLOW_PATH = os.getenv(
    "COMFYUI_VIDEO_TO_VIDEO_WORKFLOW_PATH", "workflows/video_to_video_ltx.json"
)
COMFYUI_VIDEO_EXTENSION_WORKFLOW_PATH = os.getenv(
    "COMFYUI_VIDEO_EXTENSION_WORKFLOW_PATH", "workflows/video_extension_ltx.json"
)
COMFYUI_VIDEO_MODEL_NAME = os.getenv("COMFYUI_VIDEO_MODEL_NAME", "")
COMFYUI_VIDEO_UPSCALE_MODEL_NAME = os.getenv(
    "COMFYUI_VIDEO_UPSCALE_MODEL_NAME",
    "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
)
COMFYUI_WAN_VIDEO_WORKFLOW_PATH = os.getenv(
    "COMFYUI_WAN_VIDEO_WORKFLOW_PATH", COMFYUI_FILM_WAN_WORKFLOW_PATH
)
COMFYUI_WAN_VIDEO_MODEL_NAME = os.getenv(
    "COMFYUI_WAN_VIDEO_MODEL_NAME", "wan2.1_i2v_480p_14B_fp8_scaled.safetensors"
)

# --- Credits -----------------------------------------------------------------
DEFAULT_CREDITS = int(os.getenv("DEFAULT_CREDITS", "100"))
CREDITS_PER_GENERATION = int(os.getenv("CREDITS_PER_GENERATION", "5"))
# Flat credit cost for any real video generation (all modes), charged on success.
CREDITS_PER_VIDEO = int(os.getenv("CREDITS_PER_VIDEO", "10"))
CREDITS_PER_SEEDANCE_VIDEO = int(os.getenv("CREDITS_PER_SEEDANCE_VIDEO", "30"))
CREDITS_PER_OPENAI_IMAGE = int(os.getenv("CREDITS_PER_OPENAI_IMAGE", "15"))
CREDITS_PER_OPENAI_IMAGE_EDIT = int(os.getenv("CREDITS_PER_OPENAI_IMAGE_EDIT", "15"))
CREDITS_PER_TRANSCRIPTION = int(os.getenv("CREDITS_PER_TRANSCRIPTION", "5"))
CREDITS_PER_TRANSCRIPTION_SUMMARY = int(
    os.getenv("CREDITS_PER_TRANSCRIPTION_SUMMARY", "2")
)
CREDITS_PER_VOICE_GENERATION = int(os.getenv("CREDITS_PER_VOICE_GENERATION", "2"))
CREDITS_PER_AVATAR_VIDEO = int(os.getenv("CREDITS_PER_AVATAR_VIDEO", "15"))

# --- Voice / local TTS (Phase 16A foundation) --------------------------------
# Local-first: "mock" until a local TTS (Piper) is installed. Cloud TTS is never
# the default. When Piper is present, the preset greeting audio can be generated
# locally.
VOICE_ENABLED = os.getenv("VOICE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
VOICE_BACKEND = os.getenv("VOICE_BACKEND", "mock")  # "mock" | "piper"
VOICE_MODEL_NAME = os.getenv("VOICE_MODEL_NAME", "")
PIPER_BINARY = os.getenv("PIPER_BINARY", "piper")
VOICE_MODEL_DIR = Path(os.getenv("VOICE_MODEL_DIR", str(STORAGE_DIR / "models" / "piper")))
# Explicit path to a Piper .onnx voice model. If empty, the adapter searches
# VOICE_MODEL_DIR for <VOICE_MODEL_NAME>.onnx (or the first .onnx present).
VOICE_MODEL_PATH = os.getenv("VOICE_MODEL_PATH", "")
# Optional cloned voices from the separate local VibeVoice Studio app. Its voices
# are listed as "vibevoice:<name>" when the app is running; Piper stays the default.
VIBEVOICE_BASE_URL = os.getenv("VIBEVOICE_BASE_URL", "http://127.0.0.1:8010")
VIBEVOICE_TIMEOUT_SECONDS = int(os.getenv("VIBEVOICE_TIMEOUT_SECONDS", "1800"))

# --- Avatar animation (Phase 16A foundation) ---------------------------------
# No local talking-avatar model is wired by default -> "placeholder". Avatar/voice
# assets can still be created; real animation is "setup required" until a provider
# (LivePortrait / SadTalker / Wav2Lip / Wan InfiniteTalk) is installed and selected.
AVATAR_ENABLED = os.getenv("AVATAR_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
AVATAR_BACKEND = os.getenv("AVATAR_BACKEND", "placeholder")
AVATAR_MAX_UPLOAD_MB = int(os.getenv("AVATAR_MAX_UPLOAD_MB", "200"))
GREETING_TEXT = os.getenv("GREETING_TEXT", "Welcome, let's create something amazing!")
# Wan InfiniteTalk talking-avatar (Phase 16C). Nodes ship with ComfyUI; the model
# weights below are NOT installed by default, so readiness reports setup_required
# until they exist and AVATAR_BACKEND is set to comfyui_wan_infinite_talk.
AVATAR_WAN_WORKFLOW_PATH = os.getenv("AVATAR_WAN_WORKFLOW_PATH", "workflows/avatar_wan_infinite_talk.json")
AVATAR_WAN_MODEL_NAME = os.getenv("AVATAR_WAN_MODEL_NAME", "")  # Wan 2.x video diffusion (.safetensors)
AVATAR_INFINITETALK_PATCH_NAME = os.getenv("AVATAR_INFINITETALK_PATCH_NAME", "")  # InfiniteTalk model_patch
AVATAR_AUDIO_ENCODER_NAME = os.getenv("AVATAR_AUDIO_ENCODER_NAME", "")  # wav2vec2 audio encoder
# Optional Wan step-distill LoRA (e.g. lightx2v) — sharp output at 4-8 steps, CFG 1.
AVATAR_WAN_LORA_NAME = os.getenv("AVATAR_WAN_LORA_NAME", "")
AVATAR_WAN_LORA_STRENGTH = float(os.getenv("AVATAR_WAN_LORA_STRENGTH", "1.0"))
AVATAR_WAN_PRESET = os.getenv("AVATAR_WAN_PRESET", "tiny_test")


def _optional_int_env(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else None


def _optional_float_env(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else None


AVATAR_WAN_WIDTH = _optional_int_env("AVATAR_WAN_WIDTH")
AVATAR_WAN_HEIGHT = _optional_int_env("AVATAR_WAN_HEIGHT")
AVATAR_WAN_FRAMES = _optional_int_env("AVATAR_WAN_FRAMES")
AVATAR_WAN_STEPS = _optional_int_env("AVATAR_WAN_STEPS")
AVATAR_WAN_CFG = _optional_float_env("AVATAR_WAN_CFG")
AVATAR_WAN_MAX_RETRIES = int(os.getenv("AVATAR_WAN_MAX_RETRIES", "0"))
TRANSCRIPTION_BACKEND = os.getenv("TRANSCRIPTION_BACKEND", "local_whisper")
TRANSCRIPTION_MODEL_NAME = os.getenv(
    "TRANSCRIPTION_MODEL_NAME", os.getenv("TRANSCRIPTION_MODEL_SIZE", "base")
)
TRANSCRIPTION_DEVICE = os.getenv("TRANSCRIPTION_DEVICE", "cpu")
TRANSCRIPTION_COMPUTE_TYPE = os.getenv("TRANSCRIPTION_COMPUTE_TYPE", "int8")
TRANSCRIPTION_MAX_UPLOAD_MB = int(os.getenv("TRANSCRIPTION_MAX_UPLOAD_MB", "500"))
TRANSCRIPTION_MODEL_DIR = Path(
    os.getenv("TRANSCRIPTION_MODEL_DIR", str(STORAGE_DIR / "models" / "whisper"))
)
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "")

# Generic configurable Seedance-compatible REST defaults. The admin
# integrations screen stores the actual API key and can override endpoint/model
# fields without exposing secrets to the browser.
SEEDANCE_DEFAULT_BASE_URL = os.getenv("SEEDANCE_DEFAULT_BASE_URL", "")
SEEDANCE_DEFAULT_MODEL_ID = os.getenv("SEEDANCE_DEFAULT_MODEL_ID", "seedance-2.0")
SEEDANCE_DEFAULT_CREATE_ENDPOINT = os.getenv(
    "SEEDANCE_DEFAULT_CREATE_ENDPOINT", "/v1/videos"
)
SEEDANCE_DEFAULT_STATUS_ENDPOINT = os.getenv(
    "SEEDANCE_DEFAULT_STATUS_ENDPOINT", "/v1/videos/{task_id}"
)
OPENAI_DEFAULT_BASE_URL = os.getenv("OPENAI_DEFAULT_BASE_URL", "https://api.openai.com/v1")
OPENAI_DEFAULT_IMAGE_MODEL = os.getenv("OPENAI_DEFAULT_IMAGE_MODEL", "gpt-image-2")
OPENAI_DEFAULT_IMAGE_SIZE = os.getenv("OPENAI_DEFAULT_IMAGE_SIZE", "1024x1024")
OPENAI_DEFAULT_IMAGE_QUALITY = os.getenv("OPENAI_DEFAULT_IMAGE_QUALITY", "low")


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


# --- Accounts / auth ---------------------------------------------------------
PUBLIC_SIGNUP_ENABLED = _flag("PUBLIC_SIGNUP_ENABLED", "true")
# Local-first convenience: when true, a request with no session cookie falls back
# to the local owner/admin (so David's own machine works without logging in).
# MUST be false before exposing the app beyond this machine — otherwise anonymous
# requests get owner/admin access.
OWNER_FALLBACK_ENABLED = _flag("OWNER_FALLBACK_ENABLED", "true")
DEFAULT_SIGNUP_CREDITS = int(os.getenv("DEFAULT_SIGNUP_CREDITS", "20"))
SIGNUP_REQUIRES_ADMIN_APPROVAL = _flag("SIGNUP_REQUIRES_ADMIN_APPROVAL", "false")
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "scs_session")
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(60 * 60 * 24 * 14)))

# Backend-only secrets folder (session signing key, provider API keys). Never
# served to the browser; excluded from backups; gitignored.
SECRETS_DIR = Path(os.getenv("SECRETS_DIR", str(STORAGE_DIR / "secrets")))
