"""Official cloud APIs; no model extraction, automatic retries or paid fallbacks.

Requests have a local idempotency key. Remote job IDs are persisted before polling;
an interrupted submit is never replayed, since its billing outcome may be unknown.
Only owner administrators can access the router or the protected output files.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from .. import config
from .integrations import get_private_provider_config

ORIGINS = {"heygen": "https://api.heygen.com", "elevenlabs": "https://api.elevenlabs.io"}
MAX_UPLOAD = 100 * 1024 * 1024
MAX_OUTPUT = 1024 * 1024 * 1024
_lock = threading.RLock()
_polling: set[str] = set()


def root() -> Path:
    return config.STORAGE_DIR / "cloud"


def folder(job_id: str) -> Path:
    try:
        canonical = str(uuid.UUID(job_id))
    except ValueError:
        raise HTTPException(404, "Cloud job not found") from None
    return root() / canonical


def save(job: dict) -> dict:
    path = folder(job["id"]) / "job.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return job


def read(job_id: str) -> dict:
    path = folder(job_id) / "job.json"
    if not path.is_file():
        raise HTTPException(404, "Cloud job not found")
    return json.loads(path.read_text(encoding="utf-8"))


def history() -> list[dict]:
    jobs = []
    for path in root().glob("*/job.json"):
        try:
            jobs.append(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return sorted(jobs, key=lambda j: j["created_at"], reverse=True)[:200]


def public(job: dict) -> dict:
    return {k: v for k, v in job.items() if k not in {"fingerprint"}}


def credentials(provider: str) -> dict:
    settings = get_private_provider_config(provider)
    if not settings["enabled"] or not settings["api_key"]:
        raise HTTPException(409, f"Configure and enable {provider} in Provider Integrations first.")
    return settings


def headers(provider: str, key: str) -> dict:
    return {"X-Api-Key" if provider == "heygen" else "xi-api-key": key}


def check(response: httpx.Response) -> None:
    if not response.is_success:
        # Never forward response bodies: providers can echo request text or secrets.
        messages = {
            401: "API key was rejected. Update it in Provider Integrations.",
            403: "This API key or account does not have permission for this feature.",
            402: "The provider requires credits or a different plan.",
            429: "Provider rate or quota limit reached. Check the account before retrying.",
            400: "Provider rejected the input. Check the profile, language and media format.",
            422: "Provider rejected the input. Check the profile, language and media format.",
        }
        raise HTTPException(502, messages.get(response.status_code, f"Provider returned HTTP {response.status_code}. Check its dashboard."))


def call(provider: str, method: str, path: str, *, key: str | None = None, **kwargs) -> httpx.Response:
    key = key or credentials(provider)["api_key"]
    try:
        with httpx.Client(timeout=httpx.Timeout(300, connect=20), follow_redirects=False) as client:
            response = client.request(method, ORIGINS[provider] + path, headers=headers(provider, key), **kwargs)
        check(response)
        return response
    except httpx.HTTPError:
        raise HTTPException(502, "Provider connection interrupted. Check job history and the provider dashboard before submitting again.") from None


def connection_test(provider: str, key: str) -> str:
    try:
        path = "/v3/avatars/looks?limit=1" if provider == "heygen" else "/v2/voices?page_size=1"
        call(provider, "GET", path, key=key)
        return "Connected. Catalog access verified; generation permissions and credits depend on your account."
    except HTTPException as exc:
        return str(exc.detail)


def catalog(provider: str, kind: str, token: str = "", ownership: str = "public", search: str = "") -> dict:
    if provider == "heygen":
        params = {"limit": 50, "token": token} if token else {"limit": 50}
        params["ownership" if kind == "avatars" else "type"] = ownership
        data = call(provider, "GET", "/v3/avatars/looks" if kind == "avatars" else "/v3/voices", params=params).json()
        rows = data.get("data", [])
        next_token = data.get("next_token")
    else:
        if kind != "voices":
            raise HTTPException(400, "ElevenLabs provides voices, not avatar looks.")
        params = {"page_size": 100, "search": search}
        if token:
            params["next_page_token"] = token
        data = call(provider, "GET", "/v2/voices", params=params).json()
        rows, next_token = data.get("voices", []), data.get("next_page_token")
    if not isinstance(rows, list):
        raise HTTPException(502, "Provider returned an unexpected catalog format.")
    items = [{
        "id": r.get("id") or r.get("voice_id"), "name": r.get("name", "Unnamed"),
        "image_url": safe_preview(r.get("preview_image_url")),
        "audio_url": safe_preview(r.get("preview_audio_url") or r.get("preview_url")),
        "default_voice_id": r.get("default_voice_id"),
        "engines": r.get("supported_api_engines") or [],
        "tags": r.get("tags") or [], "category": r.get("category") or r.get("avatar_type"),
    } for r in rows if isinstance(r, dict) and (r.get("id") or r.get("voice_id"))]
    return {"items": items, "next_token": next_token if data.get("has_more") else None}


def safe_preview(url: str | None) -> str | None:
    return url if url and urlparse(url).scheme == "https" else None


def create(payload: dict, upload: bytes | None = None, suffix: str = "") -> tuple[dict, bool]:
    provider = "heygen" if payload["operation"] == "avatar-video" else "elevenlabs"
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode() + (upload or b"")).hexdigest()
    with _lock:
        path = folder(payload["request_id"])
        if (path / "job.json").exists():
            job = read(payload["request_id"])
            if job["fingerprint"] != fingerprint:
                raise HTTPException(409, "This request ID has already been used for different input.")
            return job, False
        credentials(provider)
        if sum(j["status"] in {"queued", "submitting"} for j in history()) >= 3:
            raise HTTPException(429, "Three cloud requests are already submitting. Wait for one to finish.")
        path.mkdir(parents=True, exist_ok=False)
        if upload is not None:
            (path / ("input" + suffix)).write_bytes(upload)
        job = {
            "id": str(uuid.UUID(payload["request_id"])), "provider": provider,
            "operation": payload["operation"], "title": payload.get("title") or payload["operation"],
            "status": "queued", "created_at": datetime.now(timezone.utc).isoformat(),
            "remote_id": None, "files": [], "error": None, "fingerprint": fingerprint,
            "target_lang": payload.get("target_lang"),
        }
        return save(job), True


def add_file(job: dict, name: str, content: bytes) -> None:
    if not content or len(content) > MAX_OUTPUT:
        raise HTTPException(502, "Provider output is empty or exceeds the 1 GB download limit.")
    (folder(job["id"]) / name).write_bytes(content)
    job["files"] = list(dict.fromkeys([*job["files"], name]))


def binary(job: dict, method: str, path: str, *, extension: str = ".mp3", **kwargs) -> None:
    settings = credentials(job["provider"])
    destination = folder(job["id"]) / "output.partial"
    try:
        with httpx.Client(timeout=httpx.Timeout(600, connect=20), follow_redirects=False) as client:
            with client.stream(method, ORIGINS[job["provider"]] + path,
                               headers=headers(job["provider"], settings["api_key"]), **kwargs) as response:
                check(response)
                content_type = response.headers.get("content-type", "").split(";")[0]
                extension = {"video/mp4": ".mp4", "audio/wav": ".wav", "audio/x-wav": ".wav",
                             "audio/mpeg": ".mp3"}.get(content_type, extension)
                if content_type in {"application/json", "text/html"}:
                    raise HTTPException(502, "Provider returned an unexpected media response.")
                write_stream(response, destination)
        name = "output" + extension
        destination.replace(folder(job["id"]) / name)
        job["files"] = [name]
    except httpx.HTTPError:
        raise HTTPException(502, "Provider transfer interrupted. Check the provider dashboard before submitting again.") from None
    finally:
        destination.unlink(missing_ok=True)


def write_stream(response: httpx.Response, destination: Path) -> None:
    total = 0
    with destination.open("wb") as stream:
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > MAX_OUTPUT:
                raise HTTPException(502, "Output exceeds the 1 GB local download limit.")
            stream.write(chunk)
    if not total:
        raise HTTPException(502, "Provider returned an empty output.")


def execute(job_id: str, payload: dict, suffix: str = "") -> None:
    job = read(job_id)
    job["status"] = "submitting"
    save(job)
    try:
        settings = credentials(job["provider"])
        op = job["operation"]
        voice = payload.get("voice_id", "")
        if op == "avatar-video":
            body = {"type": "avatar", "avatar_id": payload["avatar_id"], "script": payload["text"],
                    "title": job["title"], "resolution": "720p", "aspect_ratio": payload["aspect_ratio"],
                    "engine": {"type": payload["engine"]}}
            if voice:
                body["voice_id"] = voice
            data = call("heygen", "POST", "/v3/videos", json=body).json()
            job["remote_id"] = data["data"]["video_id"]
            job["status"] = "processing"
        elif op == "music":
            binary(job, "POST", "/v1/music", json={
                "prompt": payload["text"], "music_length_ms": payload["music_seconds"] * 1000,
                "force_instrumental": payload["instrumental"], "model_id": "music_v1",
            }, params={"output_format": "mp3_44100_128"})
            job["status"] = "completed"
        elif op in {"tts", "sound-effects"}:
            body = {"text": payload["text"]}
            if op == "tts":
                body["model_id"] = settings["tts_model"]
                endpoint = f"/v1/text-to-speech/{voice}"
            else:
                body.update(model_id="eleven_text_to_sound_v2", duration_seconds=payload["duration_seconds"], loop=payload["loop"])
                endpoint = "/v1/sound-generation"
            binary(job, "POST", endpoint, json=body, params={"output_format": "mp3_44100_128"})
            job["status"] = "completed"
        else:
            with (folder(job_id) / ("input" + suffix)).open("rb") as stream:
                file = ("input" + suffix, stream, "application/octet-stream")
                if op == "align":
                    data = call("elevenlabs", "POST", "/v1/forced-alignment", files={"file": file},
                                data={"text": payload["text"]}).json()
                    add_file(job, "alignment.json", json.dumps(data, ensure_ascii=False, indent=2).encode())
                    add_file(job, "transcript.txt", payload["text"].encode())
                    job["status"] = "completed"
                elif op == "transcribe":
                    data = call("elevenlabs", "POST", "/v1/speech-to-text", files={"file": file},
                                data={"model_id": settings["transcription_model"], "diarize": "true"}).json()
                    add_file(job, "transcript.json", json.dumps(data, ensure_ascii=False, indent=2).encode())
                    add_file(job, "transcript.txt", (data.get("text") or "[No speech detected]").encode())
                    job["status"] = "completed"
                elif op == "dubbing":
                    data = call("elevenlabs", "POST", "/v1/dubbing", files={"file": file}, data={
                        "target_lang": payload["target_lang"], "name": job["title"], "watermark": "true",
                    }).json()
                    job["remote_id"] = data["dubbing_id"]
                    job["status"] = "processing"
                elif op == "voice-changer":
                    binary(job, "POST", f"/v1/speech-to-speech/{voice}", files={"audio": file},
                           data={"model_id": settings["sts_model"]}, params={"output_format": "mp3_44100_128"})
                    job["status"] = "completed"
                elif op == "isolate":
                    binary(job, "POST", "/v1/audio-isolation", files={"audio": file}, extension=".wav")
                    job["status"] = "completed"
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc.detail) if isinstance(exc, HTTPException) else "Cloud request could not be completed. Check the provider dashboard before resubmitting."
    finally:
        # Uploaded source is only needed while submitting, not kept as a second library.
        if suffix:
            (folder(job_id) / ("input" + suffix)).unlink(missing_ok=True)
        save(job)


def download_heygen(job: dict, url: str) -> None:
    # Only authenticated provider responses supply URLs. Never forward API keys to a CDN.
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in {None, 443} or not (
        parsed.hostname and (parsed.hostname.endswith(".heygen.ai") or parsed.hostname.endswith(".heygen.com"))
    ):
        raise HTTPException(502, "HeyGen returned an unsupported download host. Download this video from your HeyGen dashboard.")
    destination = folder(job["id"]) / "output.partial"
    try:
        with httpx.Client(timeout=600, follow_redirects=False) as client:
            with client.stream("GET", url) as response:
                check(response)
                write_stream(response, destination)
        destination.replace(folder(job["id"]) / "output.mp4")
        job["files"] = ["output.mp4"]
    except httpx.HTTPError:
        raise HTTPException(502, "Video download interrupted. Refresh this job to retry the download without regenerating.") from None
    finally:
        destination.unlink(missing_ok=True)


def refresh(job_id: str) -> dict:
    with _lock:
        job = read(job_id)
        if job["status"] != "processing" or job_id in _polling:
            return job
        _polling.add(job_id)
    try:
        remote = job["remote_id"]
        if not isinstance(remote, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", remote):
            raise HTTPException(502, "Provider returned an invalid job ID.")
        if job["provider"] == "heygen":
            data = call("heygen", "GET", f"/v3/videos/{remote}").json()["data"]
            status = data["status"]
            if status == "completed":
                download_heygen(job, data["video_url"])
                job["status"] = "completed"
        else:
            data = call("elevenlabs", "GET", f"/v1/dubbing/{remote}").json()
            status = data["status"]
            if status == "dubbed":
                binary(job, "GET", f"/v1/dubbing/{remote}/audio/{job['target_lang']}")
                job["status"] = "completed"
        job["error"] = None
        if status == "failed":
            job.update(status="failed", error="Provider could not finish this job. See its dashboard for details.")
        return save(job)
    finally:
        with _lock:
            _polling.discard(job_id)


def recover() -> None:
    for job in history():
        if job["status"] in {"queued", "submitting"}:
            job.update(status="failed", error="Sovereign restarted during submission. Check the provider dashboard before creating another job; this request was not replayed.")
            save(job)
            for source in folder(job["id"]).glob("input.*"):
                source.unlink(missing_ok=True)
