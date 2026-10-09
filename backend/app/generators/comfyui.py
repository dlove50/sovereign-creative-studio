"""Real ComfyUI image-generation adapter.

Flow:
  1. Load the workflow graph (ComfyUI API format) and inject the prompt.
  2. POST it to {base_url}/prompt -> get a prompt_id.
  3. Poll {base_url}/history/{prompt_id} until outputs appear.
  4. Pull the first image from the SaveImage node's outputs.
  5. Download it from {base_url}/view and save under STORAGE_DIR.
  6. Return GenerationResult(file_url="/storage/<id>.png") like the mock.

The prompt is injected by replacing any CLIPTextEncode node whose text equals
the sentinel "__PROMPT__", so the adapter is not tied to specific node ids.
"""
import asyncio
import json
import random
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ..config import (
    BASE_DIR,
    COMFYUI_BASE_URL,
    COMFYUI_IMAGE_EDIT_WORKFLOW_PATH,
    COMFYUI_WORKFLOW_PATH,
    STORAGE_DIR,
)
from .base import GenerationResult, Generator

PROMPT_PLACEHOLDER = "__PROMPT__"
SOURCE_IMAGE_PLACEHOLDER = "__SOURCE_IMAGE__"
_POLL_INTERVAL_SECONDS = 1.5
_POLL_MAX_ATTEMPTS = 200  # ~5 minutes at the interval above
_HTTP_TIMEOUT_SECONDS = 60.0


class ComfyUIGenerator(Generator):
    def __init__(
        self,
        base_url: str = COMFYUI_BASE_URL,
        workflow_path: str = COMFYUI_WORKFLOW_PATH,
        image_edit_workflow_path: str = COMFYUI_IMAGE_EDIT_WORKFLOW_PATH,
    ):
        self.base_url = base_url.rstrip("/")
        path = Path(workflow_path)
        self.workflow_path = path if path.is_absolute() else BASE_DIR / path
        edit_path = Path(image_edit_workflow_path)
        self.image_edit_workflow_path = (
            edit_path if edit_path.is_absolute() else BASE_DIR / edit_path
        )

    # --- workflow prep -------------------------------------------------------
    def _build_workflow(
        self,
        prompt: str,
        *,
        mode: str = "text_to_image",
        source_image_name: str | None = None,
        reference_image_names: list[str] | None = None,
    ) -> dict:
        workflow_path = (
            self.image_edit_workflow_path if mode == "image_edit" else self.workflow_path
        )
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        prompt_injected = False
        source_injected = mode != "image_edit"
        for node in workflow.values():
            inputs = node.get("inputs", {})
            for key, value in list(inputs.items()):
                if isinstance(value, str) and PROMPT_PLACEHOLDER in value:
                    inputs[key] = value.replace(PROMPT_PLACEHOLDER, prompt)
                    prompt_injected = True
                if value == SOURCE_IMAGE_PLACEHOLDER:
                    if not source_image_name:
                        raise RuntimeError("Image edit source image was not uploaded.")
                    inputs[key] = source_image_name
                    source_injected = True
            if node.get("class_type") == "KSampler" and "seed" in inputs:
                inputs["seed"] = random.randint(0, 2**32 - 1)
        if reference_image_names and mode == "image_edit":
            self._add_references(workflow, reference_image_names)
        if not prompt_injected:
            raise RuntimeError(
                f"Workflow {workflow_path} has no '{PROMPT_PLACEHOLDER}' "
                "placeholder to inject the prompt into."
            )
        if not source_injected:
            raise RuntimeError(
                f"Workflow {workflow_path} has no '{SOURCE_IMAGE_PLACEHOLDER}' "
                "image node to inject the source image into."
            )
        return workflow

    @staticmethod
    def _add_references(workflow: dict, names: list[str]) -> None:
        """Feed extra images to the Qwen edit prompt nodes as image2 and image3, each scaled like the source."""
        encoders = [n for n in workflow.values() if str(n.get("class_type", "")).startswith("TextEncodeQwenImageEdit")]
        if not encoders:
            raise RuntimeError("This image edit workflow cannot take reference images.")
        next_id = max(int(k) for k in workflow if k.isdigit()) + 1
        for slot, name in enumerate(names, start=2):
            load_id, scale_id = str(next_id), str(next_id + 1)
            next_id += 2
            workflow[load_id] = {"class_type": "LoadImage", "inputs": {"image": name, "upload": "image"}}
            workflow[scale_id] = {"class_type": "ImageScaleToTotalPixels", "inputs": {
                "image": [load_id, 0], "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 8}}
            for encoder in encoders:
                encoder["inputs"][f"image{slot}"] = [scale_id, 0]

    @staticmethod
    def _resolve_storage_path(file_url: str | None) -> Path | None:
        if not file_url:
            return None
        parsed = urlparse(file_url)
        path = parsed.path if parsed.scheme else file_url
        prefix = "/storage/"
        if not path.startswith(prefix):
            return None
        relative = path[len(prefix) :].replace("\\", "/")
        candidate = (STORAGE_DIR / relative).resolve()
        try:
            candidate.relative_to(STORAGE_DIR.resolve())
        except ValueError:
            return None
        return candidate

    async def _upload_image(self, client: httpx.AsyncClient, source: Path) -> str:
        with source.open("rb") as fh:
            response = await client.post(
                "/upload/image",
                data={"overwrite": "true", "type": "input"},
                files={"image": (source.name, fh, _mime_for(source))},
            )
        response.raise_for_status()
        payload = response.json()
        name = payload.get("name")
        if not name:
            raise RuntimeError("ComfyUI image upload did not return an input filename")
        subfolder = payload.get("subfolder")
        return f"{subfolder}/{name}" if subfolder else name

    # --- ComfyUI calls -------------------------------------------------------
    async def _submit(self, client: httpx.AsyncClient, workflow: dict) -> str:
        resp = await client.post("/prompt", json={"prompt": workflow})
        resp.raise_for_status()
        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError("ComfyUI did not return a prompt_id")
        return prompt_id

    async def _await_outputs(
        self, client: httpx.AsyncClient, prompt_id: str
    ) -> dict:
        for _ in range(_POLL_MAX_ATTEMPTS):
            resp = await client.get(f"/history/{prompt_id}")
            resp.raise_for_status()
            entry = resp.json().get(prompt_id)
            if entry and (entry.get("status") or {}).get("status_str") == "error":
                for message in entry["status"].get("messages", []):
                    if not isinstance(message, (list, tuple)) or len(message) != 2:
                        continue
                    kind, payload = message
                    if kind == "execution_error" and isinstance(payload, dict):
                        node = payload.get("node_type") or payload.get("node_id") or "unknown node"
                        detail = payload.get("exception_message") or "execution failed"
                        raise RuntimeError(f"ComfyUI image workflow failed at {node}: {detail}")
                raise RuntimeError("ComfyUI image workflow failed")
            if entry and entry.get("outputs"):
                return entry["outputs"]
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        raise TimeoutError(f"ComfyUI generation {prompt_id} timed out")

    @staticmethod
    def _first_image(outputs: dict) -> dict:
        for node_output in outputs.values():
            images = node_output.get("images")
            if images:
                return images[0]
        raise RuntimeError("No image found in ComfyUI outputs")

    async def _download(
        self, client: httpx.AsyncClient, image: dict
    ) -> bytes:
        params = {
            "filename": image["filename"],
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        }
        resp = await client.get("/view", params=params)
        resp.raise_for_status()
        return resp.content

    # --- public API ----------------------------------------------------------
    async def generate(
        self,
        *,
        generation_id: str,
        prompt: str,
        media_type: str,
        mode: str = "text_to_image",
        source_image_url: str | None = None,
        reference_image_urls: list[str] | None = None,
    ) -> GenerationResult:
        if media_type != "image":
            raise ValueError("ComfyUI adapter currently supports image generation only")

        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=_HTTP_TIMEOUT_SECONDS
        ) as client:
            source_image_name = None
            reference_names: list[str] = []
            if mode == "image_edit":
                source = self._resolve_storage_path(source_image_url)
                if source is None or not source.is_file():
                    raise RuntimeError(
                        "Local image edit requires a source image stored under /storage."
                    )
                source_image_name = await self._upload_image(client, source)
                for ref_url in reference_image_urls or []:
                    ref = self._resolve_storage_path(ref_url)
                    if ref is None or not ref.is_file():
                        raise RuntimeError("A reference image is missing from storage.")
                    reference_names.append(await self._upload_image(client, ref))
            elif mode != "text_to_image":
                raise RuntimeError(f"ComfyUI image adapter does not support {mode}.")

            workflow = self._build_workflow(
                prompt, mode=mode, source_image_name=source_image_name, reference_image_names=reference_names
            )
            prompt_id = await self._submit(client, workflow)
            outputs = await self._await_outputs(client, prompt_id)
            image = self._first_image(outputs)
            data = await self._download(client, image)

        filename = f"{generation_id}.png"
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        (STORAGE_DIR / filename).write_bytes(data)
        return GenerationResult(file_url=f"/storage/{filename}")


def _mime_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"
