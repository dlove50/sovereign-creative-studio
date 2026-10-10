"""Independent, owner-controlled video editing with durable approval checkpoints."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from .. import config
from .integrations import get_private_provider_config

MODEL = "bytedance/seedance-2.5/reference-to-video"
COMPLETE_MODEL = "bytedance/seedance-2.5/draft/complete"
MAX_UPLOAD = 200 * 1024 * 1024
MAX_OUTPUT = 1024 * 1024 * 1024
LOCK = threading.RLock()
BUSY: set[str] = set()


def root() -> Path:
    return config.STORAGE_DIR / "motion_studio"


def folder(job_id: str) -> Path:
    try:
        return root() / str(uuid.UUID(job_id))
    except ValueError:
        raise HTTPException(404, "Motion project not found") from None


def save(job: dict) -> dict:
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = folder(job["id"]) / "job.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(job, indent=2), encoding="utf-8")
    temporary.replace(path)
    return job


def read(job_id: str) -> dict:
    path = folder(job_id) / "job.json"
    if not path.is_file():
        raise HTTPException(404, "Motion project not found")
    return json.loads(path.read_text(encoding="utf-8"))


def public(job: dict) -> dict:
    result = {k: v for k, v in job.items() if k not in {"user_id", "fingerprint"}}
    result["operations"] = [{k: v for k, v in op.items() if k not in {"fingerprint"}}
                            for op in job["operations"]]
    return result


def history(user_id: str) -> list[dict]:
    jobs = []
    for path in root().glob("*/job.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            if job["user_id"] == user_id:
                jobs.append(public(job))
        except (ValueError, OSError, KeyError):
            continue
    return sorted(jobs, key=lambda j: j["updated_at"], reverse=True)[:100]


def sdk():
    import fal_client
    settings = get_private_provider_config("fal")
    key = settings.get("api_key") if settings.get("enabled") else None
    key = key or os.environ.get("FAL_KEY")
    if not key:
        raise HTTPException(409, "Add and enable a fal API key in Provider Integrations to render drafts.")
    return fal_client.SyncClient(key=key)


def readiness() -> dict:
    settings = get_private_provider_config("fal")
    return {"local_ready": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
            "cloud_ready": bool((settings.get("enabled") and settings.get("api_key")) or os.environ.get("FAL_KEY")),
            "model": MODEL, "max_seconds": 30, "max_upload_mb": 200}


def command(args: list[str], timeout: int = 180) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        raise HTTPException(422, "Media processing could not finish. Check FFmpeg and choose a shorter valid clip.") from None
    if proc.returncode:
        raise HTTPException(422, "Media processing failed. Choose a valid MP4/MOV clip with supported video and audio.")
    return proc.stdout


def probe(path: Path) -> dict:
    data = json.loads(command(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], 30))
    video = next((s for s in data.get("streams", []) if s["codec_type"] == "video"), None)
    if not video:
        raise HTTPException(422, "The uploaded file contains no video stream.")
    duration = float(data.get("format", {}).get("duration", 0))
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    if duration <= 0 or not width or not height or max(width, height) > 6000 or not .4 <= width / height <= 2.5:
        raise HTTPException(422, "Choose a video up to 6000 pixels per side with a portrait, square or landscape aspect ratio.")
    return {"duration": duration, "width": width, "height": height,
            "has_audio": any(s["codec_type"] == "audio" for s in data["streams"])}


def create(job_id: str, user_id: str, title: str, content: bytes, suffix: str, start: float, seconds: float) -> tuple[dict, bool]:
    fingerprint = hashlib.sha256(content + json.dumps([title, start, seconds]).encode()).hexdigest()
    with LOCK:
        directory = folder(job_id)
        if (directory / "job.json").exists():
            job = read(job_id)
            if job["user_id"] != user_id or job["fingerprint"] != fingerprint:
                raise HTTPException(409, "This upload ID has already been used.")
            return job, False
        directory.mkdir(parents=True)
        source = directory / ("original" + suffix)
        source.write_bytes(content)
        try:
            media = probe(source)
            duration = min(seconds, media["duration"] - start)
            if duration < 2:
                raise HTTPException(422, "Select at least two seconds within the source video.")
        except Exception:
            source.unlink(missing_ok=True)
            directory.rmdir()
            raise
        now = datetime.now(timezone.utc).isoformat()
        job = {"id": str(uuid.UUID(job_id)), "user_id": user_id, "title": title or "Untitled motion project",
               "fingerprint": fingerprint, "status": "preparing", "created_at": now,
               "source": source.name, "start": start, "seconds": duration, "media": media,
               "files": [source.name], "characters": [], "operations": [], "approved": False,
               "error": None, "selected_draft": None, "final_file": None}
        return save(job), True


def prepare(job_id: str) -> None:
    with LOCK:
        if job_id in BUSY:
            return
        BUSY.add(job_id)
    try:
        job = read(job_id)
        directory = folder(job_id)
        command(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", str(job["start"]),
                 "-i", str(directory / job["source"]), "-t", str(job["seconds"]),
                 "-map", "0:v:0", "-map", "0:a:0?", "-vf",
                 "scale=1280:1280:force_original_aspect_ratio=decrease:force_divisible_by=2,fps=24,setsar=1",
                 "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
                 "-movflags", "+faststart", str(directory / "prepared.mp4")])
        command(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(directory / "prepared.mp4"),
                 "-frames:v", "1", "-vf", "scale=640:-2", str(directory / "scene.jpg")])
        with LOCK:
            job = read(job_id)
            job.update(status="review", files=[*job["files"], "prepared.mp4", "scene.jpg"], error=None)
            save(job)
    except Exception as exc:
        with LOCK:
            job = read(job_id)
            job.update(status="failed", error=str(exc.detail) if isinstance(exc, HTTPException) else "Local preparation failed. Check the source media and FFmpeg.")
            save(job)
    finally:
        with LOCK:
            BUSY.discard(job_id)


def add_character(job_id: str, content: bytes, slot: int) -> dict:
    from PIL import Image, UnidentifiedImageError
    import io
    with LOCK:
        job = read(job_id)
        if job["status"] in {"preparing", "submitting", "rendering", "exporting"}:
            raise HTTPException(409, "Wait for the current operation to finish before changing characters.")
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.width * image.height > 40_000_000:
                    raise ValueError("Image too large")
                image.convert("RGB").save(folder(job_id) / f"character-{slot}.jpg", quality=95)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise HTTPException(422, "Choose a valid reference image below 40 megapixels.") from None
        name = f"character-{slot}.jpg"
        job["files"] = list(dict.fromkeys([*job["files"], name]))
        job["characters"] = sorted(set([*job["characters"], slot]))
        return save(job)


def approve(job_id: str) -> dict:
    with LOCK:
        job = read(job_id)
        if job["status"] not in {"review", "approved", "draft", "completed", "failed"} or "prepared.mp4" not in job["files"]:
            raise HTTPException(409, "Preparation must finish before approval.")
        job.update(approved=True, status="approved" if job["status"] == "review" else job["status"])
        return save(job)


def begin(job_id: str, operation_id: str, kind: str, prompt: str = "", scene: str = "", draft_id: str | None = None) -> tuple[dict, bool]:
    with LOCK:
        job = read(job_id)
        fingerprint = hashlib.sha256(json.dumps([kind, prompt, scene, draft_id]).encode()).hexdigest()
        previous = next((op for op in job["operations"] if op["id"] == operation_id), None)
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise HTTPException(409, "This operation ID has already been used for different input.")
            return job, False
        if job["status"] in {"preparing", "submitting", "rendering", "exporting"} or job_id in BUSY:
            raise HTTPException(409, "Wait for the current operation to finish.")
        if not job["approved"]:
            raise HTTPException(409, "Review and approve the prepared video first.")
        if kind == "draft" and 1 not in job["characters"]:
            raise HTTPException(409, "Upload the first character reference before generating a draft.")
        if kind == "final":
            draft = next((op for op in job["operations"] if op["id"] == draft_id and op["kind"] == "draft" and op["status"] == "completed"), None)
            if not draft or not draft.get("draft_id"):
                raise HTTPException(409, "Select a completed draft with its original provider draft ID.")
            if datetime.fromisoformat(draft["expires_at"]) <= datetime.now(timezone.utc):
                raise HTTPException(409, "This provider draft has expired. Generate and review a new draft.")
        sdk()  # Validate setup before reserving an operation or uploading any media.
        op = {"id": operation_id, "kind": kind, "status": "submitting", "prompt": prompt,
              "scene": scene, "parent_id": draft_id, "fingerprint": fingerprint,
              "remote_id": None, "draft_id": None, "file": None, "error": None,
              "created_at": datetime.now(timezone.utc).isoformat(),
              "model": MODEL if kind == "draft" else COMPLETE_MODEL}
        job["operations"].append(op)
        job.update(status="submitting", error=None)
        if kind == "draft":
            job["final_file"] = None
        return save(job), True


def _failure(job_id: str, operation_id: str, message: str) -> None:
    with LOCK:
        job = read(job_id)
        op = next(op for op in job["operations"] if op["id"] == operation_id)
        op.update(status="failed", error=message)
        job.update(status="failed", error=message)
        save(job)


def submit(job_id: str, operation_id: str) -> None:
    try:
        job = read(job_id)
        op = next(op for op in job["operations"] if op["id"] == operation_id)
        client = sdk()
        if op["kind"] == "draft":
            directory = folder(job_id)
            video_url = client.upload_file(directory / "prepared.mp4")
            images = [client.upload_file(directory / f"character-{slot}.jpg") for slot in job["characters"]]
            prompt = op["prompt"].strip() or "Replace the primary character in @Video1 with @Image1. Preserve the performance, movement, lip timing, camera and scene lighting."
            if len(images) > 1:
                prompt += " Replace the second character with @Image2. Keep the character identities separate."
            if op["scene"].strip():
                prompt += " Environment: " + op["scene"].strip()
            arguments = {"task": "editing", "prompt": prompt, "video_urls": [video_url],
                         "image_urls": images, "draft": True, "resolution": "480p", "generate_audio": True}
        else:
            draft = next(x for x in job["operations"] if x["id"] == op["parent_id"])
            arguments = {"draft_id": draft["draft_id"], "resolution": "1080p", "codec": "H264"}
        # No retries: a lost submit response can still represent a billable remote job.
        # Submit directly: the SDK retries some POST failures, which could duplicate a charge.
        with httpx.Client(timeout=120, follow_redirects=False) as transport:
            response = transport.post("https://queue.fal.run/" + op["model"],
                                      headers={"Authorization": f"Key {client.key}"}, json=arguments)
            response.raise_for_status()
            remote_id = response.json()["request_id"]
        with LOCK:
            job = read(job_id)
            current = next(x for x in job["operations"] if x["id"] == operation_id)
            current.update(remote_id=remote_id, status="rendering")
            job["status"] = "rendering"
            save(job)
    except Exception:
        _failure(job_id, operation_id, "Submission did not finish. Check the provider dashboard before starting another request; its billing outcome may be unknown.")


def _download(url: str, destination: Path) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid provider output URL")
    if not all(ipaddress.ip_address(item[4][0]).is_global for item in socket.getaddrinfo(parsed.hostname, 443)):
        raise ValueError("Private output URL")
    partial = destination.with_suffix(".partial")
    try:
        with httpx.Client(timeout=120, follow_redirects=False) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                if "text/" in response.headers.get("content-type", "") or "json" in response.headers.get("content-type", ""):
                    raise ValueError("Output is not media")
                total = 0
                with partial.open("wb") as stream:
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > MAX_OUTPUT:
                            raise ValueError("Output too large")
                        stream.write(chunk)
                if not total:
                    raise ValueError("Empty output")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def restore_audio(video: Path, source: Path, output: Path, has_audio: bool) -> None:
    args = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(video)]
    if has_audio:
        args += ["-i", str(source), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-shortest"]
    else:
        args += ["-map", "0:v:0", "-an"]
    command([*args, "-c:v", "copy", "-movflags", "+faststart", str(output)])


def refresh(job_id: str) -> dict:
    import fal_client
    with LOCK:
        job = read(job_id)
        if job_id in BUSY or job["status"] != "rendering":
            return job
        op = job["operations"][-1]
        BUSY.add(job_id)
    try:
        handle = sdk().get_handle(op["model"], op["remote_id"])
        remote_status = handle.status()
        if not isinstance(remote_status, fal_client.Completed):
            return read(job_id)
        if remote_status.error:
            _failure(job_id, op["id"], "The provider rejected or failed this task. Check its dashboard and revise the input before creating a new draft.")
            return read(job_id)
        result = handle.get()
        # Persist the provider's draft identity before downloading, so it survives transfer failures.
        with LOCK:
            job = read(job_id)
            current = job["operations"][-1]
            current["draft_id"] = result.get("draft_id")
            current["expires_at"] = (datetime.fromisoformat(current["created_at"]) + timedelta(days=7)).isoformat()
            current["seed"] = result.get("seed")
            save(job)
        directory = folder(job_id)
        raw = directory / f"{op['id']}-raw.mp4"
        _download(result["video"]["url"], raw)
        probe(raw)
        name = f"{op['id']}-{op['kind']}.mp4"
        restore_audio(raw, directory / "prepared.mp4", directory / name, job["media"]["has_audio"])
        raw.unlink(missing_ok=True)
        with LOCK:
            job = read(job_id)
            current = job["operations"][-1]
            current.update(status="completed", file=name)
            job["files"].append(name)
            job.update(status="draft" if op["kind"] == "draft" else "completed", error=None)
            job["selected_draft" if op["kind"] == "draft" else "final_file"] = op["id"] if op["kind"] == "draft" else name
            return save(job)
    except fal_client.FalClientHTTPError as exc:
        if exc.status_code in {400, 401, 403, 404, 422}:
            _failure(job_id, op["id"], "The provider could not complete this task. Check account permissions, input requirements and the provider dashboard.")
            return read(job_id)
        with LOCK:
            job = read(job_id)
            job["error"] = "Provider temporarily unavailable. Refresh to retrieve the existing task without submitting again."
            return save(job)
    except Exception:
        # Keep the remote ID and rendering state: refreshing is read-only remotely and may be retried.
        with LOCK:
            job = read(job_id)
            job["error"] = "Could not retrieve the provider output. Refresh to retry retrieval without generating again; check the provider dashboard if the task was rejected."
            return save(job)
    finally:
        with LOCK:
            BUSY.discard(job_id)


def recover() -> None:
    for path in root().glob("*/job.json"):
        with LOCK:
            try:
                job = read(path.parent.name)
                if job["status"] == "preparing":
                    job.update(status="failed", error="Preparation interrupted. Create a new project to prepare again.")
                    save(job)
                elif job["status"] == "submitting":
                    _failure(job["id"], job["operations"][-1]["id"], "Submission interrupted. Check the provider dashboard before submitting again.")
            except (ValueError, KeyError, OSError):
                continue
