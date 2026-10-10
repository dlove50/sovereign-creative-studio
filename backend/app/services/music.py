"""Music Lab service: local song generation with YuE2 through a dedicated ComfyUI.

Songs live in ``STORAGE_DIR/music`` as ``<id>.mp3`` plus a ``<id>.json`` sidecar,
so no database migration is needed. One generation runs at a time (one GPU);
extra requests wait in the "queued" state.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import config

SONG_ID_RE = re.compile(r"^[a-f0-9]{12}$")
QUALITIES = ("V0", "128k", "320k")
MIN_SECONDS = 10
MAX_SECONDS = 300
MAX_LYRICS_CHARS = 3000
MAX_STYLE_CHARS = 500
ENGINE_BOOT_TIMEOUT = 180
JOB_TIMEOUT = 1500  # the floor: no song is given less than this (director.py also waits this long for a soundtrack)
# How long songs really take on this laptop: a 60 s song took 5 min 46 s on a free card (about 6 min per song
# minute); a 3:18 song took 57 min when the card was under-used (about 17 min per song minute).
TYPICAL_MIN_PER_SONG_MIN = 6
SLOW_MIN_PER_SONG_MIN = 17
JOB_TIMEOUT_PER_SONG_SECOND = 20  # seconds of patience per second of song, above the slow case
JOB_TIMEOUT_MAX = 7200

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_gpu_lock = threading.Lock()
_engine_process: subprocess.Popen | None = None


class MusicError(Exception):
    """A user-presentable failure (engine offline, model missing, ...)."""


# --- ComfyUI helpers ---------------------------------------------------------------

def _comfy_get(path: str, timeout: float = 5.0) -> Any:
    with urllib.request.urlopen(config.MUSIC_COMFYUI_URL.rstrip("/") + path, timeout=timeout) as resp:
        return json.load(resp)


def _comfy_post(path: str, payload: dict, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(
        config.MUSIC_COMFYUI_URL.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def engine_status() -> dict[str, Any]:
    """Is the YuE2 engine reachable, and does it have what it needs?"""
    status: dict[str, Any] = {
        "online": False, "ready": False, "checkpoint": config.MUSIC_CHECKPOINT,
        "checkpoint_present": False, "nodes_present": False, "vram_free_gb": None, "detail": "",
    }
    try:
        stats = _comfy_get("/system_stats", timeout=2.0)
    except Exception as exc:  # noqa: BLE001 - any failure means "offline"
        status["detail"] = f"engine offline ({type(exc).__name__})"
        return status
    status["online"] = True
    try:
        devices = stats.get("devices") or []
        if devices:
            status["vram_free_gb"] = round(devices[0].get("vram_free", 0) / 1e9, 1)
        status["checkpoint_present"] = config.MUSIC_CHECKPOINT in _comfy_get("/models/checkpoints")
        nodes = _comfy_get("/object_info/YuE2GenerateMusic", timeout=10.0)
        status["nodes_present"] = "YuE2GenerateMusic" in nodes
    except Exception as exc:  # noqa: BLE001
        status["detail"] = f"engine check failed: {exc}"
        return status
    if not status["nodes_present"]:
        status["detail"] = "This ComfyUI has no YuE2 nodes (needs v0.37 or newer)."
    elif not status["checkpoint_present"]:
        status["detail"] = f"Model file {config.MUSIC_CHECKPOINT} was not found in checkpoints."
    else:
        status["ready"] = True
        status["detail"] = "ready"
    return status


def start_engine() -> dict[str, Any]:
    """Launch the dedicated ComfyUI instance if it is not already running."""
    global _engine_process
    if engine_status()["online"]:
        return {"started": False, "detail": "already online"}
    main_py = Path(config.MUSIC_COMFYUI_DIR) / "main.py"
    python = Path(config.MUSIC_COMFYUI_PYTHON)
    if not main_py.exists() or not python.exists():
        raise MusicError("The music engine is not installed where Sovereign expects it.")
    port = urllib.parse.urlparse(config.MUSIC_COMFYUI_URL).port or 8199
    flags = 0x08000000 | 0x00000008  # CREATE_NO_WINDOW | DETACHED_PROCESS (Windows)
    _engine_process = subprocess.Popen(
        [str(python), "-s", "main.py", "--listen", "127.0.0.1", "--port", str(port), "--disable-auto-launch"],
        cwd=str(main_py.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    from .process_power import disable_power_throttling_tree  # Windows otherwise runs the hidden engine about 8x slower

    disable_power_throttling_tree(_engine_process.pid)
    return {"started": True, "detail": f"engine starting (pid {_engine_process.pid})"}


def _wait_for_engine(job_id: str) -> None:
    _update_job(job_id, stage="starting_engine", message="Starting the music engine...")
    start_engine()
    deadline = time.time() + ENGINE_BOOT_TIMEOUT
    while time.time() < deadline:
        if engine_status()["online"]:
            return
        time.sleep(2)
    raise MusicError("The music engine did not start in time.")


# --- Workflow --------------------------------------------------------------------

def clean_text(value: str | None) -> str:
    return (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def build_workflow(
    *, style: str, lyrics: str, duration: float, seed: int, quality: str = "V0",
    mode: str = "full", filename_prefix: str = "audio/sovereign_music",
) -> dict[str, Any]:
    """ComfyUI API prompt for text-to-music with a generated score (ABC)."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": config.MUSIC_CHECKPOINT}},
        "2": {"class_type": "YuE2GenerateABC", "inputs": {
            "clip": ["1", 1], "style": style, "lyrics": lyrics, "seed": seed, "mode": mode,
            "max_abc_tokens": 8192, "temperature": 0.7, "top_p": 0.9, "top_k": 30,
            "repetition_penalty": 1.005, "penalty_window": 100}},
        "3": {"class_type": "YuE2GenerateMusic", "inputs": {
            "clip": ["1", 1], "style": style, "lyrics": lyrics, "abc": ["2", 0], "seed": seed,
            "mode": mode, "max_duration": float(duration), "temperature": 1.0, "top_p": 0.95,
            "top_k": 100, "repetition_penalty": 1.2}},
        "4": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["3", 0]}},
        "5": {"class_type": "EmptyYuE2LatentAudio", "inputs": {"seconds": ["3", 1], "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "seed": seed, "steps": 32, "cfg": 1.0, "sampler_name": "dpm_2",
            "scheduler": "sgm_uniform", "positive": ["3", 0], "negative": ["4", 0],
            "latent_image": ["5", 0], "denoise": 1.0}},
        "7": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveAudioMP3", "inputs": {
            "audio": ["7", 0], "filename_prefix": filename_prefix, "quality": quality}},
    }


# --- Song store -------------------------------------------------------------------

def _music_dir() -> Path:
    config.MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    return config.MUSIC_DIR


def _meta_path(song_id: str) -> Path:
    return _music_dir() / f"{song_id}.json"


def audio_path(song_id: str) -> Path:
    return _music_dir() / f"{song_id}.mp3"


def _check_id(song_id: str) -> str:
    if not SONG_ID_RE.match(song_id or ""):
        raise MusicError("Invalid song id.")
    return song_id


def get_song(song_id: str) -> dict[str, Any] | None:
    _check_id(song_id)
    path = _meta_path(song_id)
    if not path.exists() or not audio_path(song_id).exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_songs() -> list[dict[str, Any]]:
    songs = []
    for meta in _music_dir().glob("*.json"):
        if SONG_ID_RE.match(meta.stem) and audio_path(meta.stem).exists():
            try:
                songs.append(json.loads(meta.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    songs.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return songs


def update_song(song_id: str, **changes: Any) -> dict[str, Any] | None:
    song = get_song(song_id)
    if song is None:
        return None
    for key in ("title", "favorite"):
        if key in changes and changes[key] is not None:
            song[key] = changes[key]
    _meta_path(song_id).write_text(json.dumps(song, indent=2), encoding="utf-8")
    return song


def delete_song(song_id: str) -> bool:
    _check_id(song_id)
    found = False
    sidecars = [p for p in _music_dir().glob(f"{song_id}.*") if p.suffix in (".json", ".mp3")]
    for path in (_meta_path(song_id), audio_path(song_id), *sidecars):
        if path.exists():
            path.unlink()
            found = True
    for folder in (_music_dir() / f"{song_id}.stems", _music_dir() / f"{song_id}.stems.partial"):
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)
            found = True
    return found


def _save_song(audio_bytes: bytes, params: dict[str, Any], seconds: float) -> dict[str, Any]:
    song_id = uuid.uuid4().hex[:12]
    audio_path(song_id).write_bytes(audio_bytes)
    song = {
        "id": song_id,
        "title": params["title"],
        "style": params["style"],
        "lyrics": params["lyrics"],
        "instrumental": params["instrumental"],
        "duration_requested": params["duration"],
        "seed": params["seed"],
        "quality": params["quality"],
        "provider": "yue2",
        "favorite": False,
        "size_bytes": len(audio_bytes),
        "generation_seconds": round(seconds, 1),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _meta_path(song_id).write_text(json.dumps(song, indent=2), encoding="utf-8")
    return song


# --- Jobs ---------------------------------------------------------------------------

def normalize_request(
    *, title: str | None, style: str, lyrics: str | None, instrumental: bool,
    duration: float, seed: int | None, quality: str,
) -> dict[str, Any]:
    style = clean_text(style)
    lyrics = clean_text(lyrics)
    if not style:
        raise MusicError("Describe the style of the song (genre, mood, instruments, vocals).")
    if len(style) > MAX_STYLE_CHARS:
        raise MusicError(f"Style is too long (max {MAX_STYLE_CHARS} characters).")
    if len(lyrics) > MAX_LYRICS_CHARS:
        raise MusicError(f"Lyrics are too long (max {MAX_LYRICS_CHARS} characters).")
    if not instrumental and not lyrics:
        raise MusicError("Add lyrics, or switch on Instrumental.")
    if quality not in QUALITIES:
        raise MusicError(f"quality must be one of {', '.join(QUALITIES)}.")
    if not (MIN_SECONDS <= duration <= MAX_SECONDS):
        raise MusicError(f"duration must be between {MIN_SECONDS} and {MAX_SECONDS} seconds.")
    if instrumental:
        lyrics = ""
        if "instrumental" not in style.lower():
            style = f"{style}, instrumental"
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)
    return {
        "title": clean_text(title) or style.split(",")[0].strip().title()[:60] or "Untitled",
        "style": style, "lyrics": lyrics, "instrumental": instrumental,
        "duration": float(duration), "seed": int(seed), "quality": quality,
    }


def _update_job(job_id: str, **fields: Any) -> None:
    with _jobs_lock:
        _jobs[job_id].update(fields)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def normalize_idea(
    *, idea: str, genre: str | None, instrumental: bool, duration: float, seed: int | None,
    quality: str, auto_play: bool,
) -> dict[str, Any]:
    """Validate a 'describe a song' request; lyrics are written later by the lyric writer."""
    idea = clean_text(idea)
    if not idea:
        raise MusicError("Tell me what the song should be about.")
    if len(idea) > 600:
        raise MusicError("Keep the idea under 600 characters.")
    if quality not in QUALITIES:
        raise MusicError(f"quality must be one of {', '.join(QUALITIES)}.")
    if not (MIN_SECONDS <= duration <= MAX_SECONDS):
        raise MusicError(f"duration must be between {MIN_SECONDS} and {MAX_SECONDS} seconds.")
    return {
        "compose": {"idea": idea, "genre": clean_text(genre) or None},
        "title": idea[:60], "instrumental": instrumental, "duration": float(duration),
        "seed": int(seed) if seed is not None else int(time.time() * 1000) % (2**31),
        "quality": quality, "auto_play": auto_play,
    }


def create_job(params: dict[str, Any]) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id, "status": "queued", "stage": "queued", "message": "Waiting for the GPU...",
        "song_id": None, "error": None, "title": params["title"], "created_at": time.time(),
    }
    with _jobs_lock:
        _jobs[job_id] = job
        # Keep memory bounded: forget the oldest finished jobs.
        done = sorted((j for j in _jobs.values() if j["status"] in ("done", "error")), key=lambda j: j["created_at"])
        for old in done[:-50]:
            _jobs.pop(old["id"], None)
    threading.Thread(target=_run_job, args=(job_id, params), daemon=True).start()
    return dict(job)


def _free_engine_memory() -> None:
    """Best effort: ask the music engine to release GPU memory before the lyric model loads."""
    try:
        if engine_status()["online"]:
            _comfy_post("/free", {"unload_models": True, "free_memory": True}, timeout=10.0)
    except Exception:  # noqa: BLE001 - purely an optimisation
        pass


def _release_main_engine() -> None:
    """Before a song, make the main image/video ComfyUI (COMFYUI_BASE_URL) drop its models.

    The song engine and the main engine are separate processes sharing one GPU. On a 16 GB card both fit; on an
    8 GB card a resident image or video model leaves the song model too little memory and it crawls (measured:
    21-38% GPU use instead of 88%, and a song that never finished). Not running is fine; a render in progress is
    never interrupted, the song waits to be started again instead.
    """
    base = config.COMFYUI_BASE_URL.rstrip("/")
    try:
        with urllib.request.urlopen(base + "/queue", timeout=5.0) as resp:
            queue = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return  # the main engine is not running, so it holds no GPU memory
    if not isinstance(queue, dict) or queue.get("queue_running") or queue.get("queue_pending"):
        raise MusicError("The image and video engine is busy rendering. Wait for it to finish, then make the song again.")
    try:
        request = urllib.request.Request(
            base + "/free", data=json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(request, timeout=10.0).close()
        time.sleep(1.5)  # ComfyUI unloads on its next loop pass
    except (urllib.error.URLError, OSError):
        pass  # purely an optimisation: the song still runs, possibly slower


def _write_lyrics(job_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Fill in title/style/lyrics from a one-line idea using the local lyric writer."""
    from .music_compose import compose_song  # local import: music_compose depends on this module

    idea = params["compose"]
    _update_job(job_id, status="running", stage="writing_lyrics", message="Writing the lyrics...")
    _free_engine_memory()
    song = compose_song(idea["idea"], idea.get("genre"), params["duration"])
    filled = normalize_request(
        title=song["title"], style=song["style"], lyrics=song["lyrics"], instrumental=params["instrumental"],
        duration=params["duration"], seed=params["seed"], quality=params["quality"])
    filled["auto_play"] = params.get("auto_play", False)
    _update_job(job_id, title=filled["title"])
    return filled


def _run_job(job_id: str, params: dict[str, Any]) -> None:
    try:
        if params.get("compose"):
            params = _write_lyrics(job_id, params)
        with _gpu_lock:
            started = time.time()
            if not engine_status()["online"]:
                _wait_for_engine(job_id)
            status = engine_status()
            if not status["ready"]:
                raise MusicError(status["detail"])
            if _engine_process is not None:
                from .process_power import disable_power_throttling_tree

                disable_power_throttling_tree(_engine_process.pid)  # the real engine is a child of the launcher
            _release_main_engine()
            from .music_compose import unload_models  # local import: music_compose depends on this module

            unload_models()  # the songwriting chat keeps its model loaded; YuE2 needs that graphics memory
            _update_job(job_id, status="running", stage="generating", message="Composing your song...")
            builder = params.get("build_workflow")
            workflow = builder(job_id, params) if builder else build_workflow(
                style=params["style"], lyrics=params["lyrics"], duration=params["duration"],
                seed=params["seed"], quality=params["quality"], filename_prefix=f"audio/sov_{job_id}")
            try:
                prompt_id = _comfy_post("/prompt", {"prompt": workflow})["prompt_id"]
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                raise MusicError(f"The engine rejected the request: {detail}") from exc
            output = _await_output(prompt_id, started, job_timeout(float(params.get("duration") or MAX_SECONDS)))
            _update_job(job_id, stage="saving", message="Saving the song...")
            query = urllib.parse.urlencode(output)
            url = config.MUSIC_COMFYUI_URL.rstrip("/") + "/view?" + query
            with urllib.request.urlopen(url, timeout=60) as resp:
                audio_bytes = resp.read()
            song = _save_song(audio_bytes, params, time.time() - started)
            after_save = params.get("after_save")
            if after_save:
                _update_job(job_id, stage="saving", message=params.get("after_save_message", "Finishing up..."))
                song = after_save(song) or song
            message = "Your song is ready."
            if params.get("auto_play"):
                from .music_playback import play_song  # local import: avoids a circular import

                try:
                    play_song(song["id"])
                    message = "Your song is ready and playing."
                except MusicError as exc:
                    message = f"Your song is ready, but it could not be played automatically: {exc}"
            _update_job(job_id, status="done", stage="done", message=message, song_id=song["id"])
    except MusicError as exc:
        _update_job(job_id, status="error", stage="error", message=str(exc), error=str(exc))
    except Exception as exc:  # noqa: BLE001
        _update_job(job_id, status="error", stage="error", message="Song generation failed.", error=repr(exc))
    finally:
        cleanup = params.get("cleanup")
        if cleanup:
            cleanup()


def job_timeout(duration: float) -> float:
    """Seconds to wait for the engine: scales with the song length, never below ``JOB_TIMEOUT``."""
    return float(min(JOB_TIMEOUT_MAX, max(JOB_TIMEOUT, duration * JOB_TIMEOUT_PER_SONG_SECOND)))


def _cancel_engine_job(prompt_id: str) -> None:
    """Stop a job the app has given up on, so it does not keep the graphics card busy or block the next song."""
    for path, payload in (("/queue", {"delete": [prompt_id]}), ("/interrupt", {"prompt_id": prompt_id})):
        try:
            _comfy_post(path, payload, timeout=10.0)  # an empty reply is normal for /queue
        except Exception:  # noqa: BLE001 - best effort; the message below still tells the truth
            pass


def _await_output(prompt_id: str, started: float, timeout: float = JOB_TIMEOUT) -> dict[str, str]:
    while time.time() - started < timeout:
        history = _comfy_get(f"/history/{prompt_id}")
        entry = history.get(prompt_id)
        if entry:
            state = entry.get("status", {})
            if state.get("status_str") != "success":
                messages = state.get("messages", [])
                raise MusicError(f"Generation failed in the engine: {str(messages[-1])[:300] if messages else 'unknown error'}")
            files = (entry.get("outputs", {}).get("8") or {}).get("audio") or []
            if not files:
                raise MusicError("The engine finished but produced no audio.")
            f = files[0]
            return {"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")}
        time.sleep(1.5)
    _cancel_engine_job(prompt_id)
    minutes = max(1, round(timeout / 60))
    raise MusicError(
        f"The song was still not ready after {minutes} minute{'s' if minutes != 1 else ''}, so it was stopped and the graphics card "
        "was freed. Try a shorter song, close other programs that use the graphics card, then press Create song again."
    )
