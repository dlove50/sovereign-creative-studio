"""Real ComfyUI image-to-video adapter.

ComfyUI video workflows vary a lot by node pack (VideoHelperSuite, AnimateDiff,
SVD, Wan, Hunyuan, etc.), so this adapter uses placeholders rather than hard
coding node ids. Point COMFYUI_VIDEO_WORKFLOW_PATH at a ComfyUI API-format JSON
workflow containing:

  * __SOURCE_IMAGE__ where the uploaded input image filename should go
  * __PROMPT__ where the motion/scene prompt should go
  * __MOTION_PRESET__ where the UI motion preset should go
  * __DURATION_SECONDS__ where duration should go
  * __VIDEO_MODEL__ where COMFYUI_VIDEO_MODEL_NAME should go, if needed

The mock generator remains the default fallback behind the same interface.
"""
import asyncio
import json
import mimetypes
import random
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from .extension_assembly import append_continuation

from ..config import (
    BASE_DIR,
    COMFYUI_BASE_URL,
    COMFYUI_TEXT_TO_VIDEO_WORKFLOW_PATH,
    COMFYUI_VIDEO_EXTENSION_WORKFLOW_PATH,
    COMFYUI_VIDEO_TO_VIDEO_WORKFLOW_PATH,
    COMFYUI_VIDEO_MODEL_NAME,
    COMFYUI_VIDEO_UPSCALE_MODEL_NAME,
    COMFYUI_VIDEO_UPSCALE_WORKFLOW_PATH,
    COMFYUI_VIDEO_WORKFLOW_PATH,
    STORAGE_DIR,
)
from .base import VideoGenerator, VideoResult

SOURCE_IMAGE_PLACEHOLDER = "__SOURCE_IMAGE__"
PROMPT_PLACEHOLDER = "__PROMPT__"
MOTION_PRESET_PLACEHOLDER = "__MOTION_PRESET__"
DURATION_PLACEHOLDER = "__DURATION_SECONDS__"
VIDEO_MODEL_PLACEHOLDER = "__VIDEO_MODEL__"
VIDEO_UPSCALE_MODEL_PLACEHOLDER = "__VIDEO_UPSCALE_MODEL__"
VIDEO_FPS_PLACEHOLDER = "__VIDEO_FPS__"
VIDEO_WIDTH_PLACEHOLDER = "__VIDEO_WIDTH__"
VIDEO_HEIGHT_PLACEHOLDER = "__VIDEO_HEIGHT__"
VIDEO_STEPS_PLACEHOLDER = "__VIDEO_STEPS__"
VIDEO_CFG_PLACEHOLDER = "__VIDEO_CFG__"
VIDEO_TILE_SIZE_PLACEHOLDER = "__VIDEO_TILE_SIZE__"
VIDEO_TEMPORAL_SIZE_PLACEHOLDER = "__VIDEO_TEMPORAL_SIZE__"
I2V_STRENGTH_PLACEHOLDER = "__I2V_STRENGTH__"
LTX_DISTILLED_LORA_STRENGTH_PLACEHOLDER = "__LTX_DISTILLED_LORA_STRENGTH__"
TEXT_VIDEO_LENGTH_FRAMES_PLACEHOLDER = "__TEXT_VIDEO_LENGTH_FRAMES__"
# Video Extension target length in pixel frames (LTX requires 8k+1). Computed
# from the requested extension duration; only the extension workflow uses it.
VIDEO_LENGTH_FRAMES_PLACEHOLDER = "__VIDEO_LENGTH_FRAMES__"
_EXTENSION_FPS = 24
_TEXT_TO_VIDEO_FPS = 8

_STORAGE_URL_PREFIX = "/storage/"
_POLL_INTERVAL_SECONDS = 1.5
_POLL_MAX_ATTEMPTS = 240  # ~6 minutes at the interval above
_HTTP_TIMEOUT_SECONDS = 60.0
_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".gif", ".webp", ".avi", ".mkv"}
_VIDEO_OUTPUT_KEYS = ("videos", "gifs", "animated", "animations", "files", "images")
_VIDEO_NODE_HINTS = (
    "video",
    "vhs",
    "animate",
    "animated",
    "svd",
    "wan",
    "hunyuan",
    "ltx",
    "webp",
    "gif",
)
_WORKFLOW_REQUIRED_NODE_KEYS = {"class_type", "inputs"}
_META_NODE_HINTS = ("meta", "note", "comment", "sticky", "annotation", "helper")


@dataclass(frozen=True)
class VideoQualitySettings:
    width: int
    height: int
    fps: int
    steps: int
    cfg: float
    tile_size: int
    temporal_size: int
    i2v_strength: float
    distilled_lora_strength: float


_QUALITY_PRESETS: dict[str, VideoQualitySettings] = {
    # Fast compatibility preset: intentionally close to the old smoke-test path.
    "safe_preview": VideoQualitySettings(
        width=256,
        height=256,
        fps=8,
        steps=8,
        cfg=3.0,
        tile_size=256,
        temporal_size=8,
        i2v_strength=0.85,
        distilled_lora_strength=0.5,
    ),
    # Recommended local default for RTX 5070 Ti 16 GB: visibly larger than the
    # smoke workflow while keeping short clips practical.
    "standard_local": VideoQualitySettings(
        width=512,
        height=320,
        fps=8,
        steps=12,
        cfg=3.0,
        tile_size=512,
        temporal_size=8,
        i2v_strength=0.9,
        distilled_lora_strength=0.5,
    ),
    # Wan 2.1 1.3B text-to-video: native 16 fps, so motion plays at natural speed. A 4 s clip is 65 frames,
    # about 77 s and 7 GB of graphics memory on the 8 GB laptop GPU. Steps and cfg are set in the workflow.
    "wan_smooth": VideoQualitySettings(
        width=512,
        height=320,
        fps=16,
        steps=20,
        cfg=6.0,
        tile_size=512,
        temporal_size=8,
        i2v_strength=0.9,
        distilled_lora_strength=0.5,
    ),
    "best_local": VideoQualitySettings(
        width=640,
        height=384,
        fps=8,
        steps=16,
        cfg=3.0,
        tile_size=512,
        temporal_size=8,
        i2v_strength=0.9,
        distilled_lora_strength=0.5,
    ),
    "image_to_video_best": VideoQualitySettings(
        width=640,
        height=384,
        fps=8,
        steps=16,
        cfg=3.0,
        tile_size=512,
        temporal_size=8,
        i2v_strength=0.95,
        distilled_lora_strength=0.5,
    ),
}
_DEFAULT_QUALITY_PRESET = "standard_local"


class ComfyUIVideoGenerator(VideoGenerator):
    def __init__(
        self,
        base_url: str = COMFYUI_BASE_URL,
        workflow_path: str = COMFYUI_VIDEO_WORKFLOW_PATH,
        model_name: str = COMFYUI_VIDEO_MODEL_NAME,
        text_to_video_workflow_path: str = COMFYUI_TEXT_TO_VIDEO_WORKFLOW_PATH,
        video_upscale_workflow_path: str = COMFYUI_VIDEO_UPSCALE_WORKFLOW_PATH,
        upscale_model_name: str = COMFYUI_VIDEO_UPSCALE_MODEL_NAME,
        video_to_video_workflow_path: str = COMFYUI_VIDEO_TO_VIDEO_WORKFLOW_PATH,
        video_extension_workflow_path: str = COMFYUI_VIDEO_EXTENSION_WORKFLOW_PATH,
    ):
        self.base_url = base_url.rstrip("/")
        path = Path(workflow_path)
        self.workflow_path = path if path.is_absolute() else BASE_DIR / path
        text_path = Path(text_to_video_workflow_path)
        self.text_to_video_workflow_path = (
            text_path if text_path.is_absolute() else BASE_DIR / text_path
        )
        upscale_path = Path(video_upscale_workflow_path)
        self.video_upscale_workflow_path = (
            upscale_path if upscale_path.is_absolute() else BASE_DIR / upscale_path
        )
        v2v_path = Path(video_to_video_workflow_path)
        self.video_to_video_workflow_path = (
            v2v_path if v2v_path.is_absolute() else BASE_DIR / v2v_path
        )
        ext_path = Path(video_extension_workflow_path)
        self.video_extension_workflow_path = (
            ext_path if ext_path.is_absolute() else BASE_DIR / ext_path
        )
        self.model_name = model_name
        self.upscale_model_name = upscale_model_name

    # --- local files ---------------------------------------------------------
    def _resolve_source_image(self, source_image_url: str) -> Path:
        if not source_image_url.startswith(_STORAGE_URL_PREFIX):
            raise RuntimeError(
                f"Cannot resolve source image url '{source_image_url}' to a "
                "local file (expected a /storage/ path)."
            )
        local = STORAGE_DIR / source_image_url[len(_STORAGE_URL_PREFIX) :]
        if not local.is_file():
            raise RuntimeError(f"Source image file not found: {local}")
        return local

    # --- workflow prep -------------------------------------------------------
    def _workflow_path_for_mode(self, mode: str) -> Path:
        if mode == "text_to_video":
            return self.text_to_video_workflow_path
        if mode == "video_upscale":
            return self.video_upscale_workflow_path
        if mode == "video_to_video":
            return self.video_to_video_workflow_path
        if mode == "video_extension":
            return self.video_extension_workflow_path
        return self.workflow_path

    @staticmethod
    def _extension_length_frames(duration_seconds: int) -> int:
        # LTX latent video length must be 8k+1 frames; map the requested
        # extension duration onto that grid (with a small floor).
        frames = max(2, int(duration_seconds)) * _EXTENSION_FPS
        return frames - (frames % 8) + 1

    @staticmethod
    def _ltx_length_frames(duration_seconds: int, fps: int = _TEXT_TO_VIDEO_FPS) -> int:
        # Native LTX latent video length uses the 8k+1 grid. Round requested
        # duration up to the next valid frame count so 5s is not silently
        # encoded as the old 9-frame/3s smoke-test clip.
        frames = max(2, int(duration_seconds)) * fps
        return frames - (frames % 8) + 1

    @staticmethod
    def _quality_settings(
        mode: str, quality_preset: str | None
    ) -> VideoQualitySettings:
        preset_id = quality_preset or (
            "image_to_video_best" if mode == "image_to_video" else _DEFAULT_QUALITY_PRESET
        )
        return _QUALITY_PRESETS.get(preset_id, _QUALITY_PRESETS[_DEFAULT_QUALITY_PRESET])

    def _load_workflow_raw(self, mode: str = "image_to_video") -> dict:
        workflow_path = self._workflow_path_for_mode(mode)
        if not workflow_path.is_file():
            raise RuntimeError(
                f"ComfyUI video workflow not found: {workflow_path}. "
                "Set COMFYUI_VIDEO_WORKFLOW_PATH to a ComfyUI API JSON workflow."
            )
        raw = json.loads(workflow_path.read_text(encoding="utf-8"))
        return self._sanitize_api_workflow(raw, workflow_path)

    def _sanitize_api_workflow(self, workflow: dict, workflow_path: Path) -> dict:
        """Return executable ComfyUI API workflow JSON.

        ComfyUI UI exports can include helper metadata entries (for example
        ``4_meta``) that are useful in the editor but invalid for ``/prompt``.
        Remove obvious metadata/helper entries and fail early for any remaining
        non-API nodes so ComfyUI does not return a vague invalid_prompt error.
        """
        if not isinstance(workflow, dict):
            raise RuntimeError(
                f"Workflow {workflow_path} must be a ComfyUI API JSON object."
            )
        if "nodes" in workflow or "links" in workflow:
            raise RuntimeError(
                f"Workflow {workflow_path} appears to be a ComfyUI UI export. "
                "Export it with Save (API Format), or remove UI-only nodes/links."
            )

        sanitized: dict[str, dict] = {}
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                raise RuntimeError(
                    f"Workflow {workflow_path} node {node_id} is not an API node."
                )
            if "class_type" not in node:
                node_id_text = str(node_id).lower()
                node_keys = {str(key).lower() for key in node}
                if any(hint in node_id_text for hint in _META_NODE_HINTS) or not (
                    _WORKFLOW_REQUIRED_NODE_KEYS & node_keys
                ):
                    continue
                raise RuntimeError(
                    f"Workflow {workflow_path} node {node_id} is missing "
                    "class_type. Use ComfyUI API-format JSON."
                )
            sanitized[str(node_id)] = node

        if not sanitized:
            raise RuntimeError(
                f"Workflow {workflow_path} has no executable API nodes."
            )
        return sanitized

    def _validate_workflow_config(self, mode: str = "image_to_video") -> None:
        workflow_path = self._workflow_path_for_mode(mode)
        workflow = self._load_workflow_raw(mode)
        workflow_text = json.dumps(workflow)
        if mode != "text_to_video" and SOURCE_IMAGE_PLACEHOLDER not in workflow_text:
            raise RuntimeError(
                f"Workflow {workflow_path} has no '{SOURCE_IMAGE_PLACEHOLDER}' "
                "placeholder for the uploaded source image."
            )
        if PROMPT_PLACEHOLDER not in workflow_text:
            raise RuntimeError(
                f"Workflow {workflow_path} has no '{PROMPT_PLACEHOLDER}' "
                "placeholder for the video prompt."
            )
        if VIDEO_MODEL_PLACEHOLDER in workflow_text and not self.model_name:
            raise RuntimeError(
                "COMFYUI_VIDEO_MODEL_NAME is required because the video workflow "
                f"uses '{VIDEO_MODEL_PLACEHOLDER}'."
            )
        if (
            VIDEO_UPSCALE_MODEL_PLACEHOLDER in workflow_text
            and not self.upscale_model_name
        ):
            raise RuntimeError(
                "COMFYUI_VIDEO_UPSCALE_MODEL_NAME is required because the video "
                f"workflow uses '{VIDEO_UPSCALE_MODEL_PLACEHOLDER}'."
            )
        if not self._looks_like_video_workflow(workflow):
            raise RuntimeError(
                f"Workflow {workflow_path} does not appear to contain video "
                "nodes/models. Point COMFYUI_VIDEO_WORKFLOW_PATH at an "
                "image-to-video workflow with the required video custom nodes."
            )

    def _build_workflow(
        self,
        *,
        prompt: str,
        motion_preset: str,
        duration_seconds: int,
        image_name: str | None,
        mode: str = "image_to_video",
        quality_preset: str | None = None,
    ) -> dict:
        workflow_path = self._workflow_path_for_mode(mode)
        workflow = self._load_workflow_raw(mode)
        settings = self._quality_settings(mode, quality_preset)
        counters = {
            SOURCE_IMAGE_PLACEHOLDER: 0,
            PROMPT_PLACEHOLDER: 0,
            MOTION_PRESET_PLACEHOLDER: 0,
            DURATION_PLACEHOLDER: 0,
            VIDEO_MODEL_PLACEHOLDER: 0,
            VIDEO_UPSCALE_MODEL_PLACEHOLDER: 0,
            VIDEO_FPS_PLACEHOLDER: 0,
            VIDEO_WIDTH_PLACEHOLDER: 0,
            VIDEO_HEIGHT_PLACEHOLDER: 0,
            VIDEO_STEPS_PLACEHOLDER: 0,
            VIDEO_CFG_PLACEHOLDER: 0,
            VIDEO_TILE_SIZE_PLACEHOLDER: 0,
            VIDEO_TEMPORAL_SIZE_PLACEHOLDER: 0,
            I2V_STRENGTH_PLACEHOLDER: 0,
            LTX_DISTILLED_LORA_STRENGTH_PLACEHOLDER: 0,
            TEXT_VIDEO_LENGTH_FRAMES_PLACEHOLDER: 0,
            VIDEO_LENGTH_FRAMES_PLACEHOLDER: 0,
        }
        replacements: dict[str, Any] = {
            SOURCE_IMAGE_PLACEHOLDER: image_name or "",
            PROMPT_PLACEHOLDER: prompt,
            MOTION_PRESET_PLACEHOLDER: motion_preset,
            DURATION_PLACEHOLDER: duration_seconds,
            VIDEO_MODEL_PLACEHOLDER: self.model_name,
            VIDEO_UPSCALE_MODEL_PLACEHOLDER: self.upscale_model_name,
            VIDEO_FPS_PLACEHOLDER: settings.fps,
            VIDEO_WIDTH_PLACEHOLDER: settings.width,
            VIDEO_HEIGHT_PLACEHOLDER: settings.height,
            VIDEO_STEPS_PLACEHOLDER: settings.steps,
            VIDEO_CFG_PLACEHOLDER: settings.cfg,
            VIDEO_TILE_SIZE_PLACEHOLDER: settings.tile_size,
            VIDEO_TEMPORAL_SIZE_PLACEHOLDER: settings.temporal_size,
            I2V_STRENGTH_PLACEHOLDER: settings.i2v_strength,
            LTX_DISTILLED_LORA_STRENGTH_PLACEHOLDER: settings.distilled_lora_strength,
            TEXT_VIDEO_LENGTH_FRAMES_PLACEHOLDER: self._ltx_length_frames(
                duration_seconds, settings.fps
            ),
            VIDEO_LENGTH_FRAMES_PLACEHOLDER: self._extension_length_frames(duration_seconds),
        }

        def replace(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: replace(item) for key, item in value.items()}
            if isinstance(value, list):
                return [replace(item) for item in value]
            if isinstance(value, str):
                for placeholder, replacement in replacements.items():
                    if value == placeholder:
                        counters[placeholder] += 1
                        return replacement
                    if placeholder in value:
                        if placeholder == DURATION_PLACEHOLDER:
                            replacement = str(replacement)
                        counters[placeholder] += value.count(placeholder)
                        value = value.replace(placeholder, str(replacement))
                return value
            return value

        workflow = replace(workflow)
        for node in workflow.values():
            inputs = node.get("inputs", {})
            if node.get("class_type") == "SaveVideo":
                # Prompts may contain Windows path characters or exceed MAX_PATH.
                # Keep user prose in conditioning, never in output filenames.
                inputs["filename_prefix"] = "sovereign_video_" + str(random.getrandbits(64))
            if node.get("class_type") == "KSampler" and "seed" in inputs:
                inputs["seed"] = random.randint(0, 2**32 - 1)

        if mode != "text_to_video" and counters[SOURCE_IMAGE_PLACEHOLDER] == 0:
            raise RuntimeError(
                f"Workflow {workflow_path} has no '{SOURCE_IMAGE_PLACEHOLDER}' "
                "placeholder for the uploaded source image."
            )
        if counters[PROMPT_PLACEHOLDER] == 0:
            raise RuntimeError(
                f"Workflow {workflow_path} has no '{PROMPT_PLACEHOLDER}' "
                "placeholder for the video prompt."
            )
        if counters[VIDEO_MODEL_PLACEHOLDER] > 0 and not self.model_name:
            raise RuntimeError(
                "COMFYUI_VIDEO_MODEL_NAME is required because the video workflow "
                f"uses '{VIDEO_MODEL_PLACEHOLDER}'."
            )
        if counters[VIDEO_UPSCALE_MODEL_PLACEHOLDER] > 0 and not self.upscale_model_name:
            raise RuntimeError(
                "COMFYUI_VIDEO_UPSCALE_MODEL_NAME is required because the video "
                f"workflow uses '{VIDEO_UPSCALE_MODEL_PLACEHOLDER}'."
            )
        if not self._looks_like_video_workflow(workflow):
            raise RuntimeError(
                f"Workflow {workflow_path} does not appear to contain video "
                "nodes/models. Point COMFYUI_VIDEO_WORKFLOW_PATH at an "
                "image-to-video workflow with the required video custom nodes."
            )
        return workflow

    @staticmethod
    def _looks_like_video_workflow(workflow: dict) -> bool:
        for node in workflow.values():
            class_type = str(node.get("class_type", "")).lower()
            if any(hint in class_type for hint in _VIDEO_NODE_HINTS):
                return True
        return False

    # --- ComfyUI calls -------------------------------------------------------
    async def _upload_image(self, client: httpx.AsyncClient, local_path: Path) -> str:
        content_type = mimetypes.guess_type(local_path.name)[0] or "image/png"
        files = {"image": (local_path.name, local_path.read_bytes(), content_type)}
        resp = await self._request(
            client.post,
            "/upload/image",
            files=files,
            data={"overwrite": "true"},
        )
        body = resp.json()
        name = body.get("name")
        if not name:
            raise RuntimeError("ComfyUI did not return an uploaded image name")
        subfolder = body.get("subfolder")
        return f"{subfolder}/{name}" if subfolder else name

    async def _submit(self, client: httpx.AsyncClient, workflow: dict) -> str:
        resp = await self._request(client.post, "/prompt", json={"prompt": workflow})
        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError("ComfyUI did not return a prompt_id")
        return prompt_id

    async def _await_outputs(
        self, client: httpx.AsyncClient, prompt_id: str
    ) -> dict:
        for _ in range(_POLL_MAX_ATTEMPTS):
            resp = await self._request(client.get, f"/history/{prompt_id}")
            entry = resp.json().get(prompt_id)
            if entry:
                self._raise_history_error(entry)
                if entry.get("outputs"):
                    return entry["outputs"]
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        raise TimeoutError(f"ComfyUI video generation {prompt_id} timed out")

    @staticmethod
    def _raise_history_error(entry: dict) -> None:
        status = entry.get("status") or {}
        if status.get("status_str") != "error":
            return
        for kind, payload in status.get("messages", []):
            if kind != "execution_error" or not isinstance(payload, dict):
                continue
            node = payload.get("node_type") or payload.get("node_id") or "unknown node"
            message = payload.get("exception_message") or "ComfyUI execution failed"
            raise RuntimeError(f"ComfyUI video workflow failed at {node}: {message}")
        raise RuntimeError("ComfyUI video workflow failed")

    async def _download(self, client: httpx.AsyncClient, output: dict) -> bytes:
        params = {
            "filename": output["filename"],
            "subfolder": output.get("subfolder", ""),
            "type": output.get("type", "output"),
        }
        resp = await self._request(client.get, "/view", params=params)
        return resp.content

    async def _request(self, method, *args, **kwargs) -> httpx.Response:
        try:
            resp = await method(*args, **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.ConnectError as exc:
            raise RuntimeError(f"ComfyUI is offline at {self.base_url}") from exc
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"ComfyUI request timed out at {self.base_url}") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"ComfyUI request failed with HTTP {exc.response.status_code}: "
                f"{exc.response.text}"
            ) from exc

    # --- output extraction ---------------------------------------------------
    @staticmethod
    def _first_video_output(outputs: dict) -> dict:
        for node_output in outputs.values():
            for key in _VIDEO_OUTPUT_KEYS:
                candidates = node_output.get(key)
                if not candidates:
                    continue
                if isinstance(candidates, dict):
                    candidates = [candidates]
                for item in candidates:
                    if not isinstance(item, dict) or not item.get("filename"):
                        continue
                    if item.get("type") == "input":
                        continue
                    suffix = Path(item["filename"]).suffix.lower()
                    if suffix in _VIDEO_EXTENSIONS or key != "images":
                        return item
        raise RuntimeError(
            "No output video found in ComfyUI history. Check that the workflow "
            "saves a video/animation output node."
        )

    @staticmethod
    def _output_suffix(output: dict) -> str:
        suffix = Path(output.get("filename", "")).suffix.lower()
        return suffix if suffix in _VIDEO_EXTENSIONS else ".mp4"

    # --- public API ----------------------------------------------------------
    @staticmethod
    def _preserve_upscale_frames(workflow: dict, frame_count: int) -> None:
        """Pad LTX's temporal input to 8n+1, then remove only added frames."""
        if frame_count < 1:
            raise RuntimeError("Source video has no readable frames.")
        padding = (1 - frame_count) % 8
        if padding:
            workflow["upscale_last"] = {"class_type": "ImageFromBatch", "inputs": {"image": ["3", 0], "batch_index": -1, "length": 1}}
            workflow["upscale_repeat"] = {"class_type": "RepeatImageBatch", "inputs": {"image": ["upscale_last", 0], "amount": padding}}
            workflow["upscale_pad"] = {"class_type": "ImageBatch", "inputs": {"image1": ["3", 0], "image2": ["upscale_repeat", 0]}}
            workflow["4"]["inputs"]["pixels"] = ["upscale_pad", 0]
        workflow["upscale_trim"] = {"class_type": "ImageFromBatch", "inputs": {"image": ["7", 0], "batch_index": 0, "length": frame_count}}
        workflow["8"]["inputs"]["images"] = ["upscale_trim", 0]

    async def generate(
        self,
        *,
        video_id: str,
        source_image_url: str,
        prompt: str,
        motion_preset: str,
        duration_seconds: int,
        mode: str = "image_to_video",
        quality_preset: str | None = None,
    ) -> VideoResult:
        self._validate_workflow_config(mode)
        source_image = (
            None if mode == "text_to_video" else self._resolve_source_image(source_image_url)
        )
        expected_duration = duration_seconds
        source_frame_count = None
        if mode in ("video_to_video", "video_upscale") and source_image is not None:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-count_frames", "-show_entries", "stream=duration,nb_read_frames:format=duration", "-of", "json", str(source_image)],
                capture_output=True, text=True, check=True, timeout=30,
            )
            metadata = json.loads(probe.stdout)
            stream = next(iter(metadata.get("streams", [])), {})
            duration = stream.get("duration")
            if duration in (None, "N/A"):
                duration = metadata.get("format", {}).get("duration")
            expected_duration = float(duration)
            if not 0 < expected_duration < float("inf"):
                raise RuntimeError("Source video has no valid duration.")
            if mode == "video_upscale":
                source_frame_count = int(stream.get("nb_read_frames", 0))

        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=_HTTP_TIMEOUT_SECONDS
        ) as client:
            image_name = (
                None if source_image is None else await self._upload_image(client, source_image)
            )
            workflow = self._build_workflow(
                prompt=prompt,
                motion_preset=motion_preset,
                duration_seconds=duration_seconds,
                image_name=image_name,
                mode=mode,
                quality_preset=quality_preset,
            )
            if mode == "video_upscale" and workflow.get("6", {}).get("class_type") == "LTXVLatentUpsampler":
                self._preserve_upscale_frames(workflow, source_frame_count)
            prompt_id = await self._submit(client, workflow)
            outputs = await self._await_outputs(client, prompt_id)
            output = self._first_video_output(outputs)
            data = await self._download(client, output)

        output_dir = STORAGE_DIR / "videos"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{video_id}{'.mp4' if mode == 'video_extension' else self._output_suffix(output)}"
        output_path = output_dir / filename
        if mode == "video_extension":
            with tempfile.TemporaryDirectory(prefix="continuation-", dir=output_dir) as temporary:
                segment = Path(temporary) / f"segment{self._output_suffix(output)}"
                segment.write_bytes(data)
                self._validate_output_video(segment, duration_seconds)
                expected_duration = await asyncio.to_thread(
                    append_continuation, source_image, segment, output_path
                )
        else:
            output_path.write_bytes(data)
        self._validate_output_video(output_path, expected_duration)
        return VideoResult(result_url=f"/storage/videos/{filename}")

    # --- output validation --------------------------------------------------
    @staticmethod
    def _iter_mp4_boxes(data: bytes, start: int = 0, end: int | None = None):
        end = len(data) if end is None else end
        pos = start
        while pos + 8 <= end:
            size = struct.unpack(">I", data[pos : pos + 4])[0]
            box_type = data[pos + 4 : pos + 8].decode("latin1")
            header_size = 8
            if size == 1:
                if pos + 16 > end:
                    break
                size = struct.unpack(">Q", data[pos + 8 : pos + 16])[0]
                header_size = 16
            if size == 0:
                size = end - pos
            if size < header_size or pos + size > end:
                break
            yield box_type, pos + header_size, pos + size
            pos += size

    @classmethod
    def _find_mp4_boxes(
        cls, data: bytes, path: tuple[str, ...], start: int = 0, end: int | None = None
    ):
        if not path:
            return
        for box_type, content_start, box_end in cls._iter_mp4_boxes(data, start, end):
            if box_type != path[0]:
                continue
            if len(path) == 1:
                yield content_start, box_end
            else:
                yield from cls._find_mp4_boxes(
                    data, path[1:], content_start, box_end
                )

    @classmethod
    def _inspect_mp4(cls, data: bytes) -> dict[str, float | int | None]:
        duration_seconds: float | None = None
        width: float | None = None
        height: float | None = None
        sample_count = 0

        for start, _end in cls._find_mp4_boxes(data, ("moov", "mvhd")):
            version = data[start]
            if version == 0:
                timescale = struct.unpack(">I", data[start + 12 : start + 16])[0]
                duration = struct.unpack(">I", data[start + 16 : start + 20])[0]
            else:
                timescale = struct.unpack(">I", data[start + 20 : start + 24])[0]
                duration = struct.unpack(">Q", data[start + 24 : start + 32])[0]
            if timescale:
                duration_seconds = duration / timescale
            break

        for trak_start, trak_end in cls._find_mp4_boxes(data, ("moov", "trak")):
            handler = None
            for hdlr_start, _hdlr_end in cls._find_mp4_boxes(
                data, ("mdia", "hdlr"), trak_start, trak_end
            ):
                handler = data[hdlr_start + 8 : hdlr_start + 12].decode("latin1")
                break
            if handler != "vide":
                continue
            for tkhd_start, tkhd_end in cls._find_mp4_boxes(
                data, ("tkhd",), trak_start, trak_end
            ):
                width = struct.unpack(">I", data[tkhd_end - 8 : tkhd_end - 4])[0] / 65536
                height = struct.unpack(">I", data[tkhd_end - 4 : tkhd_end])[0] / 65536
                break
            for stsz_start, _stsz_end in cls._find_mp4_boxes(
                data, ("mdia", "minf", "stbl", "stsz"), trak_start, trak_end
            ):
                sample_count = struct.unpack(">I", data[stsz_start + 8 : stsz_start + 12])[0]
                break
            break

        return {
            "duration_seconds": duration_seconds,
            "width": width,
            "height": height,
            "sample_count": sample_count,
        }

    @classmethod
    def _validate_output_video(cls, output_path: Path, requested_duration: float) -> None:
        if not output_path.is_file() or output_path.stat().st_size < 1024:
            raise RuntimeError("ComfyUI returned an empty or tiny video file.")
        if output_path.suffix.lower() != ".mp4":
            return

        info = cls._inspect_mp4(output_path.read_bytes())
        duration = info["duration_seconds"]
        samples = info["sample_count"]
        width = info["width"]
        height = info["height"]
        if not duration or duration <= 0 or not samples or samples <= 0:
            raise RuntimeError("ComfyUI returned an MP4 with no readable video frames.")
        if not width or not height or width <= 0 or height <= 0:
            raise RuntimeError("ComfyUI returned an MP4 with invalid dimensions.")

        min_duration = max(1.0, requested_duration * 0.7)
        if duration < min_duration:
            raise RuntimeError(
                "ComfyUI returned a shorter-than-requested video "
                f"({duration:.1f}s for {requested_duration}s requested)."
            )
