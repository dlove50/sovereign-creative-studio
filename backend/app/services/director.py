"""Director: turn a short brief into a finished video, unattended.

Pipeline (one film at a time, because every step needs the GPU):
plan the shots (local story planner) -> shoot each shot with the local video engine
(a keyframe picture first for vertical videos) -> join the clips -> record the narration
(local voice) -> compose a soundtrack (Music Lab) -> mix and save one MP4.

State lives in small JSON files under storage/director so no database change is needed.
A failed step never fakes output: the project ends in "error" with the reason.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from .. import config
from ..config import STORAGE_DIR
from ..database import SessionLocal
from ..models import Project, User, VideoGeneration
from . import cinematic_planner, director_templates as tpl
from .music_playback import audio_duration, find_ffmpeg_tool

PLAN_ATTEMPTS = 3
CLIP_ATTEMPTS = 2
CLIP_TIMEOUT = 1800
POLL_SECONDS = 4
MIN_CLIP, MAX_CLIP = 2, 15
PORTRAIT_SIZE, LANDSCAPE_SIZE = (576, 1024), (1024, 576)
MIN_SHOT_SECONDS, MAX_SHOT_SECONDS = 3, 8  # what the planner is asked for
KEYFRAME_STYLE = ", cinematic still, detailed, natural lighting, no text, no logos, no watermark"
FINAL_FPS = 24
PROJECT_NAME = "Director videos"

_store_lock = threading.Lock()
_run_lock = threading.Lock()
_active: set[str] = set()
_cancelled: set[str] = set()


class DirectorError(RuntimeError):
    """A user-presentable reason a film could not be made."""


class Cancelled(Exception):
    pass


# --- Storage -------------------------------------------------------------------------

def _root() -> Path:
    path = STORAGE_DIR / "director"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file(project_id: str) -> Path:
    if not project_id.isalnum() or len(project_id) > 32:
        raise DirectorError("Invalid project id.")
    return _root() / f"{project_id}.json"


def _write(project: dict[str, Any]) -> None:
    path = _file(project["id"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(project, indent=2), encoding="utf-8")
    tmp.replace(path)


def get_project(project_id: str) -> dict[str, Any] | None:
    path = _file(project_id)
    if not path.exists():
        return None
    project = json.loads(path.read_text(encoding="utf-8"))
    if project["status"] in ("queued", "running") and project_id not in _active:
        project.update(status="error", stage="error", message="Interrupted by a restart. Start it again.",
                       error="Interrupted by a restart.")
    return project


def _update(project_id: str, **fields: Any) -> dict[str, Any]:
    with _store_lock:
        project = json.loads(_file(project_id).read_text(encoding="utf-8"))
        project.update(fields)
        _write(project)
        return project


def _update_shot(project_id: str, index: int, **fields: Any) -> None:
    with _store_lock:
        project = json.loads(_file(project_id).read_text(encoding="utf-8"))
        project["shots"][index].update(fields)
        _write(project)


def list_projects(user_id: str) -> list[dict[str, Any]]:
    items = []
    for path in _root().glob("*.json"):
        if path.parent.name == "director" and not path.stem.startswith("series-"):
            project = get_project(path.stem)
            if project and project.get("user_id") == user_id:
                items.append(project)
    return sorted(items, key=lambda p: p["created_at"], reverse=True)


def delete_project(project_id: str) -> bool:
    cancel(project_id)
    path = _file(project_id)
    existed = path.exists()
    if existed:
        _drop_series_episode(project_id, json.loads(path.read_text(encoding="utf-8")).get("series_id"))
    path.unlink(missing_ok=True)
    shutil.rmtree(_root() / project_id, ignore_errors=True)  # its keyframe pictures
    result = STORAGE_DIR / "videos" / f"director-{project_id}.mp4"
    result.unlink(missing_ok=True)
    return existed


def cancel(project_id: str) -> None:
    if project_id in _active:
        _cancelled.add(project_id)


def _check_cancel(project_id: str) -> None:
    if project_id in _cancelled:
        raise Cancelled()


# --- Series (Micro Drama) -------------------------------------------------------------

def _series_file(series_id: str) -> Path:
    if not series_id.isalnum() or len(series_id) > 32:
        raise DirectorError("Invalid series id.")
    return _root() / f"series-{series_id}.json"


def get_series(series_id: str) -> dict[str, Any] | None:
    path = _series_file(series_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _save_series(series: dict[str, Any]) -> None:
    with _store_lock:
        _series_file(series["id"]).write_text(json.dumps(series, indent=2), encoding="utf-8")


def _series_context(series: dict[str, Any]) -> str:
    done = [e for e in series["episodes"] if e.get("synopsis")]
    lines = [f"This is episode {len(series['episodes']) + 1} of an ongoing series titled '{series['title']}'."]
    if series.get("characters"):
        who = "; ".join(f"{c['name']}: {c['description']}" for c in series["characters"])
        lines.append(f"Keep these characters exactly as described (same names, looks and clothing): {who}.")
    if series.get("locations"):
        lines.append("Recurring places: " + "; ".join(f"{l['name']}: {l['description']}" for l in series["locations"]) + ".")
    for episode in done:
        lines.append(f"Episode {episode['number']} so far: {episode['synopsis']}")
    lines.append("Continue directly from the last cliffhanger, resolve it, then raise a new question. End on a new cliffhanger.")
    return " ".join(lines)


def _drop_series_episode(project_id: str, series_id: str | None) -> None:
    """An episode that was cancelled, failed or deleted must not count as part of the story."""
    series = get_series(series_id) if series_id else None
    if series is None:
        return
    kept = [e for e in series["episodes"] if e["project_id"] != project_id]
    if len(kept) == len(series["episodes"]):
        return
    if not kept:
        _series_file(series["id"]).unlink(missing_ok=True)  # an empty series is just clutter
        return
    series["episodes"] = [{**e, "number": n} for n, e in enumerate(kept, start=1)]
    _save_series(series)


def _record_series_episode(project: dict[str, Any], plan: dict[str, Any]) -> None:
    series = get_series(project["series_id"]) if project.get("series_id") else None
    if series is None:
        return
    entry = next((e for e in series["episodes"] if e["project_id"] == project["id"]), None)
    if entry is not None:
        entry["synopsis"] = plan["synopsis"][:800]
    if not series.get("characters"):
        series["characters"] = [{"name": c["name"], "description": c["description"][:300]} for c in plan["characters"]]
        series["locations"] = [{"name": l["name"], "description": l["description"][:300]} for l in plan["locations"]]
    _save_series(series)


# --- Creating projects ----------------------------------------------------------------

def estimate_credits(seconds: int) -> dict[str, int]:
    """Credit range before the plan exists. Shots run 3 to 8 seconds, so clips fall between the two bounds."""
    low = max(1, math.ceil(seconds / MAX_SHOT_SECONDS))
    high = max(low, seconds // MIN_SHOT_SECONDS)
    per_clip = config.CREDITS_PER_H3_VIDEO
    return {"clips_low": low, "clips_high": high, "per_clip": per_clip, "total_low": low * per_clip, "total_high": high * per_clip}


def create_project(
    user_id: str, template_id: str, brief: dict[str, Any] | None, seconds: int, *, music: bool = True,
    narration: bool = True, voice_id: str | None = None, series_id: str | None = None, direction: str = "",
    planner: str = "fast",
) -> dict[str, Any]:
    try:
        template = tpl.get_template(template_id)
        clean = tpl.clean_brief(template, brief)
    except tpl.TemplateError as exc:
        raise DirectorError(str(exc)) from exc
    if planner not in ("fast", "best"):
        raise DirectorError("planner must be fast or best.")
    limits = template["seconds"]
    if not (limits["min"] <= seconds <= limits["max"]):
        raise DirectorError(f"{template['label']} runs {limits['min']} to {limits['max']} seconds.")
    project_id = uuid.uuid4().hex[:12]
    series = None
    if template["series"]:
        series = get_series(series_id) if series_id else None
        if series_id and series is None:
            raise DirectorError("That series was not found.")
        if series is None:
            series = {"id": uuid.uuid4().hex[:12], "user_id": user_id, "template": template_id, "brief": clean,
                      "title": "", "characters": [], "locations": [], "episodes": []}
        series["episodes"].append({"number": len(series["episodes"]) + 1, "project_id": project_id, "synopsis": ""})
        _save_series(series)
    context = _series_context({**series, "episodes": series["episodes"][:-1]}) if series and len(series["episodes"]) > 1 else None
    if context and direction.strip():
        context += " Direction for this episode: " + " ".join(direction.split())[:400]
    project = {
        "id": project_id, "user_id": user_id, "template": template_id, "label": template["label"], "brief": clean,
        "seconds": seconds, "orientation": template["orientation"], "music": bool(music and template["music"]),
        "narration": bool(narration and template["narration"]), "voice_id": voice_id,
        "planner": planner, "series_id": series["id"] if series else None, "episode": len(series["episodes"]) if series else None,
        "prompt": tpl.compose_prompt(template, clean, context, seconds), "status": "queued", "stage": "queued",
        "message": "Waiting for the GPU...", "title": f"{template['label']}", "shots": [], "plan": None,
        "notes": [], "result_url": None, "error": None, "credits_estimate": estimate_credits(seconds),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with _store_lock:
        _write(project)
    _active.add(project_id)
    threading.Thread(target=_run, args=(project_id,), daemon=True).start()
    return project


def next_episode(series_id: str, user_id: str, seconds: int | None, direction: str, music: bool, planner: str = "fast") -> dict[str, Any]:
    series = get_series(series_id)
    if series is None or series["user_id"] != user_id:
        raise DirectorError("That series was not found.")
    if any(not e.get("synopsis") for e in series["episodes"]):
        raise DirectorError("Finish the current episode before starting the next one.")
    template = tpl.get_template(series["template"])
    return create_project(user_id, series["template"], series["brief"], seconds or template["seconds"]["default"],
                          music=music, series_id=series_id, direction=direction, planner=planner)


# --- Running ----------------------------------------------------------------------------

def _run(project_id: str) -> None:
    with _run_lock:
        try:
            _check_cancel(project_id)
            _pipeline(project_id)
        except Cancelled:
            _update(project_id, status="cancelled", stage="cancelled", message="Cancelled.")
            _drop_failed_episode(project_id)
        except DirectorError as exc:
            _update(project_id, status="error", stage="error", message=str(exc), error=str(exc))
            _drop_failed_episode(project_id)
        except Exception as exc:  # noqa: BLE001 - never leave a project stuck in "running"
            _update(project_id, status="error", stage="error", message="The video could not be made.", error=repr(exc)[:400])
            _drop_failed_episode(project_id)
        finally:
            _active.discard(project_id)
            _cancelled.discard(project_id)


def _drop_failed_episode(project_id: str) -> None:
    project = json.loads(_file(project_id).read_text(encoding="utf-8"))
    _drop_series_episode(project_id, project.get("series_id"))


def fit_durations(plan: dict[str, Any], seconds: int) -> dict[str, Any]:
    """Rescale shot lengths so they add up to exactly `seconds` (small models are poor at arithmetic)."""
    shots = plan["shots"]
    total = sum(s["duration_seconds"] for s in shots)
    if total == seconds:
        return plan
    lengths = [max(MIN_CLIP, min(MAX_CLIP, round(s["duration_seconds"] * seconds / total))) for s in shots]
    step = 1 if sum(lengths) < seconds else -1
    while sum(lengths) != seconds:
        movable = [i for i, n in enumerate(lengths) if MIN_CLIP <= n + step <= MAX_CLIP]
        if not movable:
            break
        pick = max(movable, key=lambda i: lengths[i]) if step < 0 else min(movable, key=lambda i: lengths[i])
        lengths[pick] += step
    if sum(lengths) != seconds:
        raise DirectorError("The planner's shots could not be fitted to the requested length. Try again.")
    return {**plan, "shots": [{**s, "duration_seconds": n} for s, n in zip(shots, lengths)]}


def _plan(prompt: str, seconds: int, planner: str = "fast") -> dict[str, Any]:
    model = config.DIRECTOR_FAST_PLANNER_MODEL if planner == "fast" else None
    last: Exception | None = None
    for _ in range(PLAN_ATTEMPTS):
        try:
            plan = cinematic_planner.write_plan(prompt, seconds, model=model, exact=planner != "fast")
            return fit_durations(plan, seconds)
        except (RuntimeError, ValueError) as exc:
            last = exc
    raise DirectorError(str(last) if last else "The story planner did not answer.")


def _pipeline(project_id: str) -> None:
    project = _update(project_id, status="running", stage="planning", message="Planning the shots with the local story model...")
    template = tpl.get_template(project["template"])
    plan = _plan(project["prompt"], project["seconds"], project.get("planner", "fast"))
    shots = [{"id": s["id"], "duration": s["duration_seconds"], "description": s["description"][:240],
              "narration": s["narration"], "video_prompt": s["video_prompt"], "image_prompt": s["image_prompt"],
              "status": "queued", "video_id": None, "clip_url": None, "keyframe_url": None, "error": None}
             for s in plan["shots"]]
    summary = {"title": plan["title"], "synopsis": plan["synopsis"], "characters": plan["characters"],
               "locations": plan["locations"], "model": plan["model"]}
    _update(project_id, plan=summary, shots=shots, title=plan["title"], stage="clips", message=f"Shooting 1 of {len(shots)}...")
    _record_series_episode(project, plan)
    series = get_series(project["series_id"]) if project.get("series_id") else None
    if series is not None and not series["title"]:
        series["title"] = plan["title"]
        _save_series(series)
    clips: list[Path] = []
    for index in range(len(shots)):
        _check_cancel(project_id)
        _update(project_id, message=f"Shooting {index + 1} of {len(shots)}...")
        _update_shot(project_id, index, status="running")
        clips.append(_shoot(project_id, project, shots[index], index))
    _check_cancel(project_id)
    _finish(project_id, project, template, shots, clips)


# --- Shooting -----------------------------------------------------------------------------

def _owner_project_id(db, user_id: str) -> str:
    row = db.scalar(select(Project).where(Project.user_id == user_id, Project.name == PROJECT_NAME))
    if row is None:
        row = Project(user_id=user_id, name=PROJECT_NAME, description="Clips made by the Director.")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row.id


def _video_choice(portrait: bool) -> tuple[str, str]:
    """(provider, mode). MiniMax H3 (with sound) if ready, otherwise LTX; vertical always starts from a keyframe."""
    from ..routers import videos as videos_router
    h3_ready, _ = videos_router._h3_ready()
    if h3_ready:
        return "local_h3", ("image_to_video" if portrait else "text_to_video")
    text_ready, text_note = videos_router._text_to_video_ready()
    if portrait or not text_ready:
        return "local_ltx", "image_to_video"
    return "local_ltx", "text_to_video"


def _render_keyframe(prompt: str, size: tuple[int, int], dest: Path) -> None:
    """One still picture for the shot with the local z-image model (ComfyUI)."""
    import urllib.request

    workflow = json.loads((Path(__file__).resolve().parents[2] / "workflows" / "text_to_image_z_image_turbo.json").read_text(encoding="utf-8"))
    for node in workflow.values():
        for key, value in node["inputs"].items():
            if value == "__PROMPT__":
                node["inputs"][key] = prompt[:1200] + KEYFRAME_STYLE
    workflow["7"]["inputs"].update(width=size[0], height=size[1])
    workflow["8"]["inputs"]["seed"] = int(time.time() * 1000) % (2**31)
    base = config.COMFYUI_BASE_URL.rstrip("/")

    def call(path: str, payload: dict | None = None) -> bytes:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"} if data else {})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()

    prompt_id = json.loads(call("/prompt", {"prompt": workflow}))["prompt_id"]
    deadline = time.time() + 600
    while time.time() < deadline:
        entry = json.loads(call(f"/history/{prompt_id}")).get(prompt_id)
        if entry:
            if entry.get("status", {}).get("status_str") != "success":
                raise DirectorError("The keyframe picture could not be made.")
            image = entry["outputs"]["10"]["images"][0]
            query = f"filename={image['filename']}&subfolder={image.get('subfolder', '')}&type={image.get('type', 'output')}"
            dest.write_bytes(call("/view?" + query))
            return
        time.sleep(1.5)
    raise DirectorError("The keyframe picture took too long.")


def _create_clip_job(user_id: str, shot: dict[str, Any], provider: str, mode: str, source_url: str | None) -> str:
    from fastapi import HTTPException

    from ..routers import videos as videos_router
    from ..schemas_workflows import VideoCreate

    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            raise DirectorError("The account for this project no longer exists.")
        payload = VideoCreate(
            project_id=_owner_project_id(db, user_id), prompt=shot["video_prompt"][:2000], motion_preset="cinematic_push",
            duration_seconds=max(MIN_CLIP, min(MAX_CLIP, int(shot["duration"]))), mode=mode, provider=provider,
            quality_preset="h3_turbo" if provider == "local_h3" else "standard_local", source_image_url=source_url)
        try:
            return videos_router.create_video(payload, db, user).id
        except HTTPException as exc:
            raise DirectorError(str(exc.detail)) from exc


def _wait_clip(project_id: str, video_id: str) -> dict[str, str | None]:
    deadline = time.time() + CLIP_TIMEOUT
    while time.time() < deadline:
        if project_id in _cancelled:
            with SessionLocal() as db:
                video = db.get(VideoGeneration, video_id)
                if video is not None and video.status in ("queued", "running"):
                    video.status = "cancelled"
                    db.commit()
            raise Cancelled()
        with SessionLocal() as db:
            video = db.get(VideoGeneration, video_id)
            if video is None:
                raise DirectorError("A clip disappeared while it was being made.")
            if video.status == "completed" and video.result_url:
                return {"status": "completed", "url": video.result_url, "error": None}
            if video.status in ("failed", "cancelled"):
                return {"status": video.status, "url": None, "error": video.error}
        time.sleep(POLL_SECONDS)
    raise DirectorError("A clip took too long and was stopped.")


def _shoot(project_id: str, project: dict[str, Any], shot: dict[str, Any], index: int) -> Path:
    portrait = project["orientation"] == "portrait"
    provider, mode = _video_choice(portrait)
    source_url = None
    if mode == "image_to_video":
        folder = _root() / project_id
        folder.mkdir(parents=True, exist_ok=True)
        frame = folder / f"shot-{index + 1:02d}.png"
        _render_keyframe(shot["image_prompt"], PORTRAIT_SIZE if portrait else LANDSCAPE_SIZE, frame)
        source_url = f"/storage/director/{project_id}/{frame.name}"
        _update_shot(project_id, index, keyframe_url=source_url)
    last_error = "unknown error"
    for _ in range(CLIP_ATTEMPTS):
        _check_cancel(project_id)
        video_id = _create_clip_job(project["user_id"], shot, provider, mode, source_url)
        _update_shot(project_id, index, video_id=video_id)
        outcome = _wait_clip(project_id, video_id)
        if outcome["status"] == "completed":
            url = str(outcome["url"])
            _update_shot(project_id, index, status="done", clip_url=url, error=None)
            return STORAGE_DIR / url.removeprefix("/storage/")
        last_error = outcome["error"] or last_error
    _update_shot(project_id, index, status="error", error=str(last_error)[:300])
    raise DirectorError(f"Shot {index + 1} could not be made: {str(last_error)[:240]}")


# --- Finishing: join, narrate, score, mix ----------------------------------------------------

def _ffmpeg(args: list[str], timeout: int = 900) -> None:
    exe = find_ffmpeg_tool("ffmpeg")
    if not exe:
        raise DirectorError("ffmpeg is needed to finish the video.")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run([exe, "-y", "-v", "error", *args], capture_output=True, text=True, timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired as exc:
        raise DirectorError("Joining the clips took too long.") from exc
    if proc.returncode != 0:
        raise DirectorError("Joining the clips failed: " + (proc.stderr.strip().splitlines() or ["ffmpeg error"])[-1][:240])


def _probe(path: Path) -> dict[str, Any]:
    probe = find_ffmpeg_tool("ffprobe")
    if not probe:
        raise DirectorError("ffprobe is needed to finish the video.")
    out = subprocess.run([probe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True, timeout=60)
    data = json.loads(out.stdout or "{}")
    video = next((s for s in data.get("streams", []) if s["codec_type"] == "video"), None)
    if video is None:
        raise DirectorError(f"{path.name} has no picture.")
    return {"width": int(video["width"]), "height": int(video["height"]), "seconds": float(data["format"]["duration"]),
            "audio": any(s["codec_type"] == "audio" for s in data["streams"])}


def concat_clips(clips: list[Path], dest: Path) -> list[float]:
    """Join clips into one MP4 with a single size, frame rate and audio format. Returns each clip's length."""
    infos = [_probe(c) for c in clips]
    width, height = infos[0]["width"], infos[0]["height"]
    args: list[str] = []
    graph: list[str] = []
    for i, (clip, info) in enumerate(zip(clips, infos)):
        args += ["-i", str(clip)]
        graph.append(f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,"
                     f"fps={FINAL_FPS},format=yuv420p[v{i}]")
        if info["audio"]:
            graph.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo,apad,atrim=0:{info['seconds']:.3f},asetpts=PTS-STARTPTS[a{i}]")
        else:
            graph.append(f"anullsrc=r=44100:cl=stereo:d={info['seconds']:.3f}[a{i}]")
    graph.append("".join(f"[v{i}][a{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=1[v][a]")
    _ffmpeg([*args, "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dest)])
    return [info["seconds"] for info in infos]


def _narrate(shots: list[dict[str, Any]], lengths: list[float], voice_id: str | None, workdir: Path) -> list[tuple[Path, float]]:
    """Speak each shot's narration. Returns (wav file, start second) pairs; clipped to the shot's length."""
    from . import voice

    if not voice.voice_ready():
        raise DirectorError("No local voice is ready.")
    if voice_id is not None and voice_id not in {v["id"] for v in voice.list_voices()}:
        raise DirectorError("That voice is not installed.")
    pieces, start = [], 0.0
    for index, (shot, length) in enumerate(zip(shots, lengths)):
        text = " ".join((shot.get("narration") or "").split())
        if text:
            out = workdir / f"narration-{index}.wav"
            voice.generate_speech(text, out, voice_id)
            spoken = audio_duration(out) or 0.0
            if spoken > length + 0.5:  # never run into the next shot's line
                trimmed = workdir / f"narration-{index}-fit.wav"
                _ffmpeg(["-i", str(out), "-t", f"{length + 0.4:.2f}", "-af", "afade=t=out:st=%.2f:d=0.3" % max(length + 0.1, 0.1), str(trimmed)])
                out = trimmed
            pieces.append((out, start + 0.15))
        start += length
    return pieces


def _score(template: dict[str, Any], brief: dict[str, str], seconds: float) -> Path:
    """Compose an instrumental soundtrack with Music Lab and wait for it."""
    from . import music

    style = tpl.music_style(template, brief)
    if not style:
        raise DirectorError("This template has no soundtrack.")
    params = music.normalize_request(title=f"{template['label']} soundtrack", style=style, lyrics="", instrumental=True,
                                     duration=float(max(music.MIN_SECONDS, min(music.MAX_SECONDS, math.ceil(seconds)))),
                                     seed=None, quality="V0")
    job = music.create_job({**params, "auto_play": False})
    deadline = time.time() + music.JOB_TIMEOUT
    while time.time() < deadline:
        state = music.get_job(job["id"]) or {}
        if state.get("status") == "done":
            return music.audio_path(state["song_id"])
        if state.get("status") == "error":
            raise DirectorError(state.get("message") or "The soundtrack could not be made.")
        time.sleep(3)
    raise DirectorError("The soundtrack took too long.")


def mix_audio(video: Path, dest: Path, narration: list[tuple[Path, float]], music: Path | None, length: float) -> None:
    """Lay narration and music under/over the clips' own sound. Music ducks while the narrator speaks."""
    args = ["-i", str(video)]
    graph: list[str] = []
    labels: list[str] = []
    speaking = bool(narration)
    graph.append(f"[0:a]volume={0.6 if speaking else 0.9}[base]")
    labels.append("[base]")
    index = 1
    voice_labels = []
    for wav, start in narration:
        args += ["-i", str(wav)]
        ms = int(start * 1000)
        graph.append(f"[{index}:a]aformat=sample_rates=44100:channel_layouts=stereo,adelay={ms}|{ms}[n{index}]")
        voice_labels.append(f"[n{index}]")
        index += 1
    if voice_labels:
        graph.append("".join(voice_labels) + f"amix=inputs={len(voice_labels)}:normalize=0,asplit=2[narr][duck]")
        labels.append("[narr]")
    if music is not None:
        args += ["-stream_loop", "-1", "-i", str(music)]
        fade = max(length - 2.0, 0.0)
        graph.append(f"[{index}:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:{length:.2f},"
                     f"volume={0.30 if speaking else 0.45},afade=t=out:st={fade:.2f}:d=2[mus]")
        if speaking:
            graph.append("[mus][duck]sidechaincompress=threshold=0.04:ratio=8:attack=20:release=400[musd]")
            labels.append("[musd]")
        else:
            labels.append("[mus]")
    graph.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=first,alimiter=limit=0.95[out]")
    _ffmpeg([*args, "-filter_complex", ";".join(graph), "-map", "0:v", "-map", "[out]", "-c:v", "copy", "-c:a", "aac",
             "-b:a", "192k", "-movflags", "+faststart", str(dest)])


def _finish(project_id: str, project: dict[str, Any], template: dict[str, Any], shots: list[dict[str, Any]], clips: list[Path]) -> None:
    final = STORAGE_DIR / "videos" / f"director-{project_id}.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    with tempfile.TemporaryDirectory(prefix="director-") as tmp:
        work = Path(tmp)
        _update(project_id, stage="assembling", message="Joining the shots...")
        joined = work / "joined.mp4"
        lengths = concat_clips(clips, joined)
        total = sum(lengths)
        narration: list[tuple[Path, float]] = []
        if project["narration"]:
            _update(project_id, stage="narration", message="Recording the narration...")
            try:
                narration = _narrate(shots, lengths, project.get("voice_id"), work)
            except DirectorError as exc:
                notes.append(f"Narration skipped: {exc}")
        music_file: Path | None = None
        if project["music"]:
            _check_cancel(project_id)
            _update(project_id, stage="scoring", message="Composing the soundtrack...")
            try:
                music_file = _score(template, project["brief"], total)
            except Exception as exc:  # noqa: BLE001 - a missing soundtrack must not lose the film
                notes.append(f"Soundtrack skipped: {exc}")
        _check_cancel(project_id)
        if narration or music_file:
            _update(project_id, stage="mixing", message="Mixing the sound...")
            mix_audio(joined, final, narration, music_file, total)
        else:
            final.write_bytes(joined.read_bytes())
    _update(project_id, status="done", stage="done", message="Your video is ready.", notes=notes,
            result_url=f"/storage/videos/{final.name}", seconds_actual=round(total, 1))
