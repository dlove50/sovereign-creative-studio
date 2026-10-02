import os
import tempfile

# Never let tests touch the real sovereign.db or storage, whichever test file
# happens to import app.config first (running a subset of files once wrote test
# users and charges into the production database).
_TEST_TMP = tempfile.mkdtemp(prefix="sovereign_tests_")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TEST_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TEST_TMP, "storage"))

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
os.environ.setdefault("AVATAR_WAN_PRESET", "tiny_test")
os.environ.setdefault("AVATAR_WAN_LORA_NAME", "")
os.environ.setdefault("COMFYUI_PRODUCT_SCENE_MODE", "img2img")
os.environ.setdefault("COMFYUI_VIDEO_ENGINE", "ltx")
