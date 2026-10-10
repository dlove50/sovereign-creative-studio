"""Scene-by-scene movies: voice + talking avatar per scene, joined into one video.

Each scene reuses the proven per-video path (voice clip, then the chunked
InfiniteTalk renderer via avatar_jobs), so credits are charged per successful
scene exactly like single videos. One background thread renders movies in order.
"""
from __future__ import annotations

import hashlib
import json
import logging
import queue
import threading
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from .. import config
from ..database import SessionLocal
from ..models import AvatarAsset, AvatarJob, Movie, User, VoiceAsset
from . import avatar_comfyui, avatar_jobs
from . import voice as voice_provider

logger = logging.getLogger(__name__)

ORIENTATION_PRESETS = {"portrait": "portrait_480p", "landscape": "landscape_480p"}
MAX_SCENES = 30
SCENE_FIELDS = ("id", "avatar_id", "tts_voice_id", "script", "slide_image_url")

_queue: "queue.Queue[str]" = queue.Queue()
_worker: threading.Thread | None = None
_lock = threading.Lock()


def load_scenes(movie: Movie) -> list[dict]:
    try:
        scenes = json.loads(movie.scenes_json or "[]")
    except json.JSONDecodeError:
        return []
    return scenes if isinstance(scenes, list) else []


def save_scenes(movie: Movie, scenes: list[dict]) -> None:
    movie.scenes_json = json.dumps(scenes)


def clean_scene(raw: dict) -> dict:
    """Keep only editable fields; render state is set by the worker."""
    scene = {k: raw.get(k) for k in SCENE_FIELDS}
    scene["id"] = str(scene["id"] or uuid.uuid4().hex[:12])[:32]
    scene["script"] = str(scene["script"] or "")[:1500]
    scene["status"] = "draft"
    return scene


def cost_estimate(scenes: list[dict]) -> int:
    per_scene = config.CREDITS_PER_VOICE_GENERATION + config.CREDITS_PER_AVATAR_VIDEO
    return per_scene * sum(1 for s in scenes if s.get("script", "").strip())


def scene_fingerprint(movie: Movie, scene: dict) -> str:
    content = {key: scene.get(key) for key in SCENE_FIELDS}
    content["orientation"] = movie.orientation
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def completed_scene_clip(db: Session, movie: Movie, scene: dict) -> Path | None:
    """Reuse only a durable owned result for exactly the same scene inputs."""
    if scene.get("render_fingerprint") != scene_fingerprint(movie, scene):
        return None
    job = db.get(AvatarJob, scene.get("avatar_job_id") or "")
    if (job is None or job.user_id != movie.user_id or job.status != "completed"
            or job.avatar_id != scene.get("avatar_id") or job.script_text != scene.get("script")
            or job.avatar_preset != ORIENTATION_PRESETS.get(movie.orientation, "portrait_480p")
            or not job.output_video_path):
        return None
    path = config.STORAGE_DIR / "avatar_videos" / Path(job.output_video_path).name
    return path if path.is_file() and path.stat().st_size > 0 else None


def remaining_cost(db: Session, movie: Movie, scenes: list[dict]) -> int:
    return cost_estimate([s for s in scenes if completed_scene_clip(db, movie, s) is None])


def enqueue(movie_id: str) -> None:
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_loop, daemon=True, name="movie-worker")
            _worker.start()
    _queue.put(movie_id)


def _loop() -> None:
    while True:
        movie_id = _queue.get()
        try:
            render_movie(movie_id)
        except Exception:  # noqa: BLE001 - one bad movie must not kill the worker
            logger.exception("Movie %s crashed", movie_id)


def _set_scene(db: Session, movie: Movie, index: int, **fields) -> None:
    scenes = load_scenes(movie)
    scenes[index].update(fields)
    save_scenes(movie, scenes)
    db.commit()


def _fail(db: Session, movie: Movie, message: str) -> None:
    movie.status = "failed"
    movie.error_message = message
    db.commit()


def _voice_clip(db: Session, user: User, text: str, tts_voice_id: str | None) -> VoiceAsset:
    is_clone = bool(tts_voice_id and tts_voice_id.startswith(voice_provider.VIBEVOICE_PREFIX))
    out_name = f"{uuid.uuid4().hex}.wav"
    voice_provider.generate_speech(text, config.STORAGE_DIR / "voices" / out_name, voice_id=tts_voice_id)
    provider = "vibevoice" if is_clone else "piper"
    voice = VoiceAsset(
        user_id=user.id, name="Movie scene voice", voice_type="local_tts", provider=provider,
        sample_file_path=f"/storage/voices/{out_name}", status="ready",
    )
    db.add(voice)
    db.flush()
    avatar_jobs.charge_for_voice(db, user, related_id=voice.id, provider=f"{provider}:{tts_voice_id or 'default'}")
    db.commit()
    return voice


def render_movie(movie_id: str) -> None:
    with SessionLocal() as db:
        movie = db.get(Movie, movie_id)
        if movie is None or movie.deleted_at is not None or movie.status != "rendering":
            return
        user = db.get(User, movie.user_id)
        scenes = [s for s in load_scenes(movie) if s.get("script", "").strip()]
        if user is None or not scenes:
            _fail(db, movie, "Add a script to at least one scene.")
            return
        needed = remaining_cost(db, movie, scenes)
        if user.credits < needed:
            _fail(db, movie, f"Not enough credits: the remaining scenes need {needed}.")
            return
        save_scenes(movie, scenes)
        db.commit()

        preset = ORIENTATION_PRESETS.get(movie.orientation, "portrait_480p")
        clips: list[Path] = []
        for i, scene in enumerate(scenes):
            completed = completed_scene_clip(db, movie, scene)
            if completed is not None:
                _set_scene(db, movie, i, status="completed", error=None)
                clips.append(completed)
                continue
            avatar = db.get(AvatarAsset, scene.get("avatar_id") or "")
            if avatar is None or avatar.deleted_at is not None or avatar.user_id != user.id or not avatar.source_file_path:
                _set_scene(db, movie, i, status="failed", error="Pick an avatar look for this scene.")
                _fail(db, movie, f"Scene {i + 1} has no avatar look.")
                return
            try:
                _set_scene(db, movie, i, status="voice", error=None,
                           render_fingerprint=scene_fingerprint(movie, scene))
                voice = _voice_clip(db, user, scene["script"], scene.get("tts_voice_id"))
                job = AvatarJob(
                    user_id=user.id, avatar_id=avatar.id, voice_id=voice.id, job_type="avatar_talking",
                    script_text=scene["script"], provider=config.AVATAR_BACKEND, avatar_preset=preset,
                    status="queued", credits_cost=0,
                )
                db.add(job)
                db.commit()
                _set_scene(db, movie, i, status="video", voice_id=voice.id, avatar_job_id=job.id)
                avatar_jobs._run_avatar_video(job.id)
                db.refresh(job)
            except Exception as exc:  # noqa: BLE001
                _set_scene(db, movie, i, status="failed", error=str(exc)[:300])
                _fail(db, movie, f"Scene {i + 1} failed: {str(exc)[:200]}")
                return
            if job.status != "completed" or not job.output_video_path:
                _set_scene(db, movie, i, status="failed", error=job.error_message)
                _fail(db, movie, f"Scene {i + 1} failed: {job.error_message or 'render did not finish'}")
                return
            _set_scene(db, movie, i, status="completed")
            clips.append(config.STORAGE_DIR / "avatar_videos" / Path(job.output_video_path).name)

        out = config.STORAGE_DIR / "avatar_videos" / f"movie_{movie.id}_{uuid.uuid4().hex[:8]}.mp4"
        composed: list[Path] = []
        try:
            from . import slide_visuals
            for i, scene in enumerate(scenes):
                if scene.get("slide_image_url"):
                    image = slide_visuals.image_path(movie.id, scene["slide_image_url"])
                    composite = out.with_name(f"slide_{uuid.uuid4().hex}.mp4")
                    composed.append(composite)
                    slide_visuals.compose(clips[i], image, composite, movie.orientation)
                    clips[i] = composite
            join_clips(clips, out)
        except Exception as exc:  # noqa: BLE001
            _fail(db, movie, f"Joining the scenes failed: {exc}")
            return
        finally:
            for composite in composed:
                composite.unlink(missing_ok=True)
        movie.output_video_path = f"/storage/avatar_videos/{out.name}"
        movie.status = "completed"
        movie.error_message = None
        db.commit()


def join_clips(clips: list[Path], out: Path) -> None:
    """Concatenate scene videos (same size/fps from one preset) with their audio."""
    if len(clips) == 1:
        out.write_bytes(clips[0].read_bytes())
        return
    from .plex_worker import join_on_plex
    if join_on_plex(clips, out):
        return
    inputs: list[str] = []
    for clip in clips:
        inputs += ["-i", str(clip)]
    streams = "".join(f"[{i}:v][{i}:a]" for i in range(len(clips)))
    avatar_comfyui._run_ffmpeg([
        *inputs, "-filter_complex", f"{streams}concat=n={len(clips)}:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", str(out),
    ])
