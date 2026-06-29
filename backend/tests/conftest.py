import os

# Pin the full backend-mode stack to deterministic test defaults BEFORE app.config
# loads, so the persisted production `.env` (real ComfyUI/LTX/local-qwen stack)
# never leaks into the test suite. load_dotenv() does not override values already
# set here, so these win.
os.environ.setdefault("GENERATOR_BACKEND", "mock")
os.environ.setdefault("PRODUCT_SCENE_BACKEND", "mock")
os.environ.setdefault("PRODUCT_SCENE_MODEL", "")
os.environ.setdefault("VIDEO_BACKEND", "mock")
os.environ.setdefault("COPY_BACKEND", "mock")
os.environ.setdefault("TRANSCRIPTION_BACKEND", "mock")
os.environ.setdefault("VOICE_BACKEND", "mock")
os.environ.setdefault("AVATAR_BACKEND", "placeholder")
os.environ.setdefault("COMFYUI_PRODUCT_SCENE_MODE", "img2img")
os.environ.setdefault("COMFYUI_VIDEO_ENGINE", "ltx")
