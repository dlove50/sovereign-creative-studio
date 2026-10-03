"""MiniMax H3 video generator (local, via ComfyUI's native H3 nodes).

H3 makes a clip with synchronized audio from a prompt, optionally anchored on a
first frame. One workflow covers both text->video and image->video. Frame counts
snap to the model's 17k+5 grid at 24 fps. The 4-step turbo LoRA is on by default
so a clip takes 4 sampler steps; quality_preset "h3_full" turns it off (20 steps).
"""
from __future__ import annotations

import asyncio
import random
import re
import subprocess
import tempfile
from pathlib import Path

import httpx

from .. import config
from ..config import STORAGE_DIR
from .base import VideoResult
from .comfyui import ComfyUIVideoGenerator

H3_FPS = 24
H3_MIN_SECONDS, H3_MAX_SECONDS = 2, 15
_POLL_SECONDS = 3.0
_GRID = 17


def h3_length_frames(duration_seconds: float) -> int:
    """Frame count on H3's 17k+5 grid for `duration_seconds` at 24 fps."""
    seconds = min(max(duration_seconds, H3_MIN_SECONDS), H3_MAX_SECONDS)
    n = max(5, round(seconds * H3_FPS))
    return n + (5 - n % _GRID) % _GRID


def h3_size(portrait: bool) -> tuple[int, int]:
    """(width, height), multiples of 32, from the configured long/short sides."""
    long_side, short_side = config.H3_LONG_SIDE, config.H3_SHORT_SIDE
    return (short_side, long_side) if portrait else (long_side, short_side)


def h3_size_for_aspect(aspect: float) -> tuple[int, int]:
    """(width, height) with the source's aspect ratio and about the configured pixel
    area, in multiples of 32, so a square or tall image is never stretched to 16:9."""
    area = config.H3_LONG_SIDE * config.H3_SHORT_SIDE
    height = (area / aspect) ** 0.5
    snap = lambda v: max(256, round(v / 32) * 32)  # noqa: E731
    return snap(height * aspect), snap(height)


def build_h3_workflow(
    *, prompt: str, width: int, height: int, length: int, image_name: str | None,
    turbo: bool = True, seed: int | None = None, reference: bool = False,
    control_video_name: str | None = None, control_strength: float | None = None,
) -> dict:
    """ComfyUI API workflow for one H3 clip (mirrors ComfyUI's own i2v / r2v templates).

    reference=True uses the ref2va model: the image is a subject reference (<Picture 1>)
    that keeps its identity, instead of the clip's first frame.
    control_video_name (an already-prepared 24 fps clip in ComfyUI's input folder) turns on
    the Fun ControlNet: the clip's Canny edges steer the motion and layout, while the
    prompt decides the look.
    """
    model_ref: list = ["1", 0]
    unet = config.H3_REF_UNET_NAME if reference else config.H3_UNET_NAME
    workflow: dict = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": config.H3_TEXT_ENCODER_NAME, "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": config.H3_VIDEO_VAE_NAME}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": config.H3_AUDIO_VAE_NAME}},
    }
    cond_inputs: dict = {
        "clip": ["2", 0], "vae": ["3", 0], "prompt": prompt, "width": width, "height": height, "length": length,
    }
    if image_name:
        workflow["5"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    if reference:
        if not image_name:
            raise RuntimeError("Reference-to-video needs a reference image.")
        cond_inputs.update({"audio_vae": ["4", 0], "ref_image_size": "match", "ref_images.ref_image_0": ["5", 0]})
        if "<Picture 1>" not in prompt:
            cond_inputs["prompt"] = f"{prompt}\nThe main subject is the person in <Picture 1>."
        workflow["7"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": cond_inputs}
    else:
        if image_name:
            cond_inputs["first_frame"] = ["5", 0]
        workflow["7"] = {"class_type": "MiniMaxH3ImageToVideo", "inputs": cond_inputs}
    if turbo:
        lora = config.H3_REF_TURBO_LORA_NAME if reference else config.H3_TURBO_LORA_NAME
        workflow["6"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["1", 0], "lora_name": lora, "strength_model": 1.0}}
        model_ref = ["6", 0]
    if control_video_name:
        workflow.update({
            "20": {"class_type": "LoadVideo", "inputs": {"file": control_video_name}},
            "21": {"class_type": "GetVideoComponents", "inputs": {"video": ["20", 0]}},
            "22": {"class_type": "Canny", "inputs": {"image": ["21", 0], "low_threshold": 0.4, "high_threshold": 0.8}},
            "23": {"class_type": "ModelPatchLoader", "inputs": {"name": config.H3_CONTROLNET_NAME}},
            "24": {"class_type": "MiniMaxH3FunControlNetApply", "inputs": {
                "model": model_ref, "model_patch": ["23", 0], "vae": ["3", 0],
                "strength": control_strength if control_strength is not None else config.H3_CONTROL_STRENGTH,
                "start_percent": 0.0, "end_percent": 1.0, "control_video": ["22", 0]}},
        })
        model_ref = ["24", 0]
    steps = config.H3_TURBO_STEPS if turbo else config.H3_FULL_STEPS
    seed = seed if seed is not None else random.randint(0, 2**32 - 1)
    workflow.update({
        "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "9": {"class_type": "BasicGuider", "inputs": {"model": model_ref, "conditioning": ["7", 0]}},
        "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "11": {"class_type": "BasicScheduler", "inputs": {"model": model_ref, "scheduler": "simple", "steps": steps, "denoise": 1.0}},
        "12": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["8", 0], "guider": ["9", 0], "sampler": ["10", 0], "sigmas": ["11", 0], "latent_image": ["7", 1]}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
        "14": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}},
        "15": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "audio": ["14", 0], "fps": H3_FPS}},
        "16": {"class_type": "SaveVideo", "inputs": {"video": ["15", 0], "filename_prefix": "video/Sovereign_H3", "format": "auto", "codec": "auto"}},
    })
    return workflow


def _image_aspect(image_path) -> float | None:
    """width / height of the source image via ffmpeg (no Pillow in the backend venv)."""
    from ..services.audio_merge import _ffmpeg

    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return None
    out = subprocess.run([ffmpeg, "-hide_banner", "-i", str(image_path)], capture_output=True, text=True).stderr
    m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", out)
    return int(m.group(1)) / int(m.group(2)) if m else None


def h3_result_output(outputs: dict) -> dict:
    """The saved clip (SaveVideo, node "16").

    ComfyUI's history also lists loader previews of INPUT files (LoadVideo reports the
    control clip with type "input") ahead of the real result; taking the first video
    would silently return the control clip instead of the generated one.
    """
    for item in (outputs.get("16") or {}).get("images") or []:
        if isinstance(item, dict) and item.get("filename"):
            return item
    raise RuntimeError("ComfyUI finished but produced no saved video.")


def prepare_control_video(src: Path, out: Path, width: int, height: int, length: int) -> None:
    """Make the control clip the ControlNet expects: 24 fps, exactly width x height
    (center-cropped, never stretched), `length` frames, no audio."""
    from ..services.audio_merge import _ffmpeg

    ffmpeg = _ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to prepare the control video.")
    vf = f"fps={H3_FPS},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    result = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", str(src), "-an", "-vf", vf, "-frames:v", str(length),
         "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(out)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not out.is_file():
        raise RuntimeError(f"Could not prepare the control video: {result.stderr.strip()[-300:]}")


class MiniMaxH3VideoGenerator(ComfyUIVideoGenerator):
    """Reuses the ComfyUI adapter's upload/submit/download plumbing."""

    async def _await_h3(self, client: httpx.AsyncClient, prompt_id: str) -> dict:
        for _ in range(int(config.H3_TIMEOUT_SECONDS / _POLL_SECONDS)):
            resp = await self._request(client.get, f"/history/{prompt_id}")
            entry = resp.json().get(prompt_id)
            if entry:
                self._raise_history_error(entry)
                if entry.get("outputs"):
                    return entry["outputs"]
            await asyncio.sleep(_POLL_SECONDS)
        raise TimeoutError(f"MiniMax H3 generation {prompt_id} timed out")

    async def generate(
        self, *, video_id: str, source_image_url: str, prompt: str, motion_preset: str,
        duration_seconds: int, mode: str = "image_to_video", quality_preset: str | None = None,
    ) -> VideoResult:
        if mode not in {"text_to_video", "image_to_video", "video_to_video"}:
            raise RuntimeError("MiniMax H3 supports Text, Image and Video (ControlNet) -> Video.")
        source = None if mode == "text_to_video" else self._resolve_source_image(source_image_url)
        reference = quality_preset == "h3_reference"
        if reference and mode != "image_to_video":
            raise RuntimeError("H3 reference mode needs an image: use Image -> Video.")
        aspect = _image_aspect(source) if source else None
        width, height = h3_size_for_aspect(aspect) if aspect else h3_size(portrait=False)
        control = mode == "video_to_video"
        seconds = duration_seconds
        if control:
            from ..services.speech_cleanup import probe

            seconds = min(duration_seconds, probe(source)[0])  # control frames can't outlast the source
        length = h3_length_frames(seconds)
        with tempfile.TemporaryDirectory() as tmp:
            control_file = None
            if control:
                control_file = Path(tmp) / f"control_{video_id}.mp4"
                prepare_control_video(source, control_file, width, height, length)
            async with httpx.AsyncClient(base_url=self.base_url, timeout=60.0) as client:
                upload = control_file if control else source
                image_name = await self._upload_image(client, upload) if upload else None
                workflow = build_h3_workflow(
                    prompt=prompt, width=width, height=height, length=length,
                    image_name=None if control else image_name, turbo=quality_preset != "h3_full",
                    reference=reference, control_video_name=image_name if control else None,
                )
                prompt_id = await self._submit(client, workflow)
                outputs = await self._await_h3(client, prompt_id)
                output = h3_result_output(outputs)
                data = await self._download(client, output)
        out_dir = STORAGE_DIR / "videos"
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{video_id}{self._output_suffix(output)}"
        (out_dir / filename).write_bytes(data)
        return VideoResult(result_url=f"/storage/videos/{filename}")
