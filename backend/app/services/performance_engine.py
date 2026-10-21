"""Multi-Performer Director: the performance engine behind duets, trios, choirs and dialogues.

One master song (or dialogue track) drives any number of performers. Each performer owns:
  * an identity picture, a stage position and a motion personality,
  * their OWN vocal stem (or slices of a shared vocal handed to them by time),
  * a track of timed regions, each in one state:
        SINGING, SPEAKING, BACKGROUND_VOCAL  (voiced: the mouth moves)
        LISTENING, MOVING, IDLE              (silent: the mouth is still)

The rule that keeps lip-sync honest: a performer's mouth is driven ONLY by the "drive audio"
built from their own voiced regions. Outside those regions the drive audio is digital silence,
so a lip-sync model has nothing to animate. A performer never sings just because the song has
vocals somewhere.

Silent stretches are resolved automatically: LISTENING while someone else is voiced, IDLE when
nobody is. A user-placed region always wins over the automatic state.

State lives in JSON under storage/performances (like the Director), so no migration is needed.
Rendering consumes `render_plan()`; this module never pretends a render happened.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import threading
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..config import STORAGE_DIR
from .music_playback import audio_duration, find_ffmpeg_tool

VOICED = ("SINGING", "SPEAKING", "BACKGROUND_VOCAL")
SILENT = ("LISTENING", "MOVING", "IDLE")
STATES = VOICED + SILENT
MODES = {
    "alternating": "A: performers take turns by verse; the other listens and reacts",
    "call_response": "B: short phrases answer each other",
    "harmony": "C: everyone sings together, each from their own stem",
    "lead_background": "D: the first performer leads; the others add backing vocals",
    "shared_stage": "E: free performance on one stage, independent motion",
}
SHOTS = ("wide", "two_shot", "close_up", "alternating")
ROLES = ("lead", "co_lead", "background", "actor")

MAX_PERFORMERS = 8
MAX_REGIONS = 2000
MAX_SECONDS = 15 * 60
DRIVE_RATE = 16000  # wav2vec-based lip-sync models (InfiniteTalk) listen at 16 kHz
FADE_SECONDS = 0.03  # soft edges so a cut-off note does not click or snap the jaw
STAGE_X = {1: [0.5], 2: [0.33, 0.67], 3: [0.25, 0.5, 0.75]}

_lock = threading.Lock()
_ID = re.compile(r"^[a-z0-9]{1,32}$")


class PerformanceError(ValueError):
    """A user-presentable reason a performance request cannot be done."""


# --- Storage -------------------------------------------------------------------------------

def _root() -> Path:
    path = STORAGE_DIR / "performances"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _check(id_: str) -> str:
    if not _ID.match(id_ or ""):
        raise PerformanceError("Invalid id.")
    return id_


def media_dir(project_id: str) -> Path:
    path = _root() / _check(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file(project_id: str) -> Path:
    return _root() / f"{_check(project_id)}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def save(project: dict[str, Any]) -> dict[str, Any]:
    validate(project)
    project["updated_at"] = _now()
    path = _file(project["id"])
    with _lock:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(project, indent=2), encoding="utf-8")
        tmp.replace(path)
    return project


def get(project_id: str) -> dict[str, Any] | None:
    path = _file(project_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_for(user_id: str) -> list[dict[str, Any]]:
    items = []
    for path in _root().glob("*.json"):
        try:
            project = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if project.get("user_id") == user_id:
            items.append(project)
    return sorted(items, key=lambda p: p.get("created_at", ""), reverse=True)


def delete(project_id: str) -> bool:
    path = _file(project_id)
    existed = path.exists()
    path.unlink(missing_ok=True)
    shutil.rmtree(_root() / project_id, ignore_errors=True)
    return existed


def create(user_id: str, title: str, performer_names: list[str], mode: str = "alternating") -> dict[str, Any]:
    if not performer_names:
        raise PerformanceError("Add at least one performer.")
    if len(performer_names) > MAX_PERFORMERS:
        raise PerformanceError(f"At most {MAX_PERFORMERS} performers.")
    if mode not in MODES:
        raise PerformanceError("Unknown performance mode.")
    xs = STAGE_X.get(len(performer_names)) or list(np.linspace(0.1, 0.9, len(performer_names)))
    performers = [
        {
            "id": _new_id(),
            "name": (name or f"Performer {chr(65 + i)}").strip()[:60],
            "role": "lead" if i == 0 else "co_lead",
            "identity_image": None,
            "stem": None,
            "voice_id": None,
            # Each performer gets their own motion seed and sway phase, so two singers never move as mirror images.
            "motion": {"seed": int(uuid.uuid4().int % 2**31), "sway": 0.5, "energy": 0.5, "phase": round(i * 0.37 % 1, 3)},
            "stage": {"x": round(float(xs[i]), 3), "scale": 1.0, "facing": "audience"},
            "regions": [],
        }
        for i, name in enumerate(performer_names)
    ]
    project = {
        "id": _new_id(),
        "user_id": user_id,
        "title": (title or "Untitled performance").strip()[:120],
        "mode": mode,
        "master_audio": None,
        "shared_vocal": None,
        "duration": 0.0,
        "performers": performers,
        "camera": [],
        "stage": {"image": None, "prompt": "", "aspect": "16:9"},
        "created_at": _now(),
        "updated_at": _now(),
    }
    return save(project)


# --- Validation -----------------------------------------------------------------------------

def performer(project: dict[str, Any], performer_id: str) -> dict[str, Any]:
    for p in project["performers"]:
        if p["id"] == performer_id:
            return p
    raise PerformanceError("Performer not found.")


def validate(project: dict[str, Any]) -> None:
    duration = float(project.get("duration") or 0)
    if duration < 0 or duration > MAX_SECONDS:
        raise PerformanceError("Duration is out of range.")
    if project.get("mode") not in MODES:
        raise PerformanceError("Unknown performance mode.")
    if not 1 <= len(project["performers"]) <= MAX_PERFORMERS:
        raise PerformanceError(f"A performance needs 1 to {MAX_PERFORMERS} performers.")
    for p in project["performers"]:
        if p.get("role") not in ROLES:
            raise PerformanceError(f"{p['name']}: unknown role.")
        regions = p["regions"]
        if len(regions) > MAX_REGIONS:
            raise PerformanceError(f"{p['name']}: too many regions.")
        last_end = -1.0
        for r in sorted(regions, key=lambda r: r["start"]):
            if r.get("state") not in STATES:
                raise PerformanceError(f"{p['name']}: unknown state {r.get('state')!r}.")
            if not 0 <= r["start"] < r["end"]:
                raise PerformanceError(f"{p['name']}: a region must end after it starts.")
            if duration and r["end"] > duration + 0.05:
                raise PerformanceError(f"{p['name']}: a region runs past the end of the song.")
            if r["start"] < last_end - 1e-6:
                raise PerformanceError(f"{p['name']}: regions overlap at {r['start']:.2f}s.")
            last_end = r["end"]
            if r["state"] in VOICED and not _voice_source(project, p, r):
                raise PerformanceError(
                    f"{p['name']}: a {r['state'].lower().replace('_', ' ')} region needs a vocal stem "
                    "for this performer (or a shared vocal) to drive the lips.")
    for shot in project.get("camera", []):
        if shot.get("shot") not in SHOTS or not 0 <= shot["start"] < shot["end"]:
            raise PerformanceError("Invalid camera shot.")


def _voice_source(project: dict[str, Any], p: dict[str, Any], region: dict[str, Any]) -> str | None:
    """Which audio file drives this performer's mouth during a voiced region."""
    if region.get("source") == "shared":
        return project.get("shared_vocal")
    return p.get("stem") or project.get("shared_vocal")


def set_regions(project: dict[str, Any], performer_id: str, regions: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace a performer's track with user-edited regions (drag, resize, relabel)."""
    p = performer(project, performer_id)
    clean = []
    for r in regions:
        clean.append({
            "id": r.get("id") or _new_id(),
            "start": round(float(r["start"]), 3),
            "end": round(float(r["end"]), 3),
            "state": r["state"],
            "intensity": round(float(r.get("intensity", 0.6)), 3),
            "lyric": str(r.get("lyric", ""))[:300],
            "source": r.get("source") if r.get("source") in ("own", "shared") else "own",
            "manual": True,
        })
    p["regions"] = sorted(clean, key=lambda r: r["start"])
    return project


# --- Audio ----------------------------------------------------------------------------------

def decode(path: Path | str, rate: int = DRIVE_RATE) -> np.ndarray:
    """Any audio file -> mono float32 at `rate` (via ffmpeg)."""
    ffmpeg = find_ffmpeg_tool("ffmpeg")
    if not ffmpeg:
        raise PerformanceError("FFmpeg is not installed.")
    proc = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"],
                          capture_output=True, timeout=300)
    if proc.returncode != 0:
        raise PerformanceError(f"Could not read the audio file: {proc.stderr.decode(errors='replace').strip()[-200:]}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def write_wav(path: Path, samples: np.ndarray, rate: int = DRIVE_RATE) -> Path:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm.tobytes())
    return path


def envelope_db(samples: np.ndarray, rate: int, frame: float = 0.02) -> np.ndarray:
    hop = max(1, int(rate * frame))
    n = len(samples) // hop
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    rms = np.sqrt(np.mean(samples[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    return (20 * np.log10(rms)).astype(np.float32)


def detect_voice(samples: np.ndarray, rate: int = DRIVE_RATE, *, frame: float = 0.02, min_on: float = 0.25,
                 merge_gap: float = 0.35, pad: float = 0.05, floor_db: float = -45.0) -> list[dict[str, float]]:
    """Find where a vocal stem actually has voice.

    Adaptive threshold between the stem's noise floor and its loud passages, with hysteresis so
    a sustained, decaying note is not chopped into pieces. Short breaths inside a phrase are merged.
    Returns [{start, end, intensity}] with intensity 0..1 (loudness relative to the stem's peak).
    """
    db = envelope_db(samples, rate, frame)
    if db.size == 0:
        return []
    low, high = np.percentile(db, 20), np.percentile(db, 97)
    if high - low < 6:  # no real contrast: silence, or a constant tone
        return [] if high < floor_db else [{"start": 0.0, "end": round(db.size * frame, 3), "intensity": 1.0}]
    on = max(floor_db, low + 0.35 * (high - low))
    off = on - 4.0
    active = np.zeros(db.size, dtype=bool)
    state = False
    for i, value in enumerate(db):
        state = value >= on if not state else value >= off
        active[i] = state
    spans: list[list[float]] = []
    i = 0
    while i < db.size:
        if active[i]:
            j = i
            while j < db.size and active[j]:
                j += 1
            spans.append([i * frame, j * frame])
            i = j
        else:
            i += 1
    merged: list[list[float]] = []
    for span in spans:
        if merged and span[0] - merged[-1][1] <= merge_gap:
            merged[-1][1] = span[1]
        else:
            merged.append(span)
    total = db.size * frame
    out = []
    for start, end in merged:
        if end - start < min_on:
            continue
        a, b = int(start / frame), max(int(start / frame) + 1, int(end / frame))
        loud = float(np.mean(db[a:b]))
        intensity = float(np.clip((loud - on) / max(1e-6, high - on) * 0.7 + 0.3, 0.0, 1.0))
        out.append({"start": round(max(0.0, start - pad), 3), "end": round(min(total, end + pad), 3),
                    "intensity": round(intensity, 3)})
    return out


def gate(samples: np.ndarray, spans: list[tuple[float, float]], rate: int = DRIVE_RATE,
         fade: float = FADE_SECONDS) -> np.ndarray:
    """Keep audio only inside `spans` (soft-edged); digital silence everywhere else."""
    mask = np.zeros(len(samples), dtype=np.float32)
    f = max(1, int(rate * fade))
    for start, end in spans:
        a, b = max(0, int(start * rate)), min(len(samples), int(end * rate))
        if b <= a:
            continue
        n = min(f, (b - a) // 2)
        span = np.ones(b - a, dtype=np.float32)
        if n > 0:
            ramp = 0.5 - 0.5 * np.cos(np.linspace(0, math.pi, n, dtype=np.float32))
            span[:n], span[-n:] = ramp, ramp[::-1]
        mask[a:b] = np.maximum(mask[a:b], span)
    return samples * mask


# --- Analysis and arrangement --------------------------------------------------------------

def set_duration_from(project: dict[str, Any], path: Path | str) -> None:
    seconds = audio_duration(Path(path))
    if seconds is None:
        seconds = len(decode(path)) / DRIVE_RATE
    if seconds > MAX_SECONDS:
        raise PerformanceError(f"Songs longer than {MAX_SECONDS // 60} minutes are not supported.")
    project["duration"] = round(float(seconds), 3)


def _voiced_state(project: dict[str, Any], p: dict[str, Any]) -> str:
    if p["role"] == "actor":
        return "SPEAKING"
    if project["mode"] == "lead_background" and p["role"] == "background":
        return "BACKGROUND_VOCAL"
    return "SINGING"


def analyze_stems(project: dict[str, Any], *, keep_manual: bool = True) -> dict[str, Any]:
    """Build each performer's voiced regions from THEIR OWN stem. Manual regions are kept."""
    analyzed = 0
    for p in project["performers"]:
        if not p.get("stem"):
            continue
        found = detect_voice(decode(p["stem"]))
        manual = [r for r in p["regions"] if r.get("manual")] if keep_manual else []
        auto = [
            {"id": _new_id(), "start": s["start"], "end": s["end"], "state": _voiced_state(project, p),
             "intensity": s["intensity"], "lyric": "", "source": "own", "manual": False}
            for s in found
            if not any(s["start"] < m["end"] and m["start"] < s["end"] for m in manual)
        ]
        p["regions"] = sorted(manual + auto, key=lambda r: r["start"])
        analyzed += 1
    if not analyzed:
        raise PerformanceError("No performer has a vocal stem yet. Add a stem per performer, "
                               "or use hand-offs on a shared vocal.")
    if not project.get("camera"):
        project["camera"] = auto_camera(project)
    return project


def assign_handoffs(project: dict[str, Any], handoffs: list[dict[str, Any]]) -> dict[str, Any]:
    """Split ONE shared vocal between performers by time (for songs without per-singer stems).

    handoffs: [{start, end, performers: [id, ...], state?}] -- only the voiced parts of the shared
    vocal inside each window are given to the listed performers.
    """
    if not project.get("shared_vocal"):
        raise PerformanceError("Add the song's vocal first (or split it from the master).")
    voiced = detect_voice(decode(project["shared_vocal"]))
    ids = {p["id"] for p in project["performers"]}
    for p in project["performers"]:
        p["regions"] = [r for r in p["regions"] if r.get("manual") and r.get("source") != "shared"]
    for h in sorted(handoffs, key=lambda h: h["start"]):
        if not set(h["performers"]) <= ids:
            raise PerformanceError("A hand-off names an unknown performer.")
        for pid in h["performers"]:
            p = performer(project, pid)
            state = h.get("state") or _voiced_state(project, p)
            for v in voiced:
                start, end = max(v["start"], h["start"]), min(v["end"], h["end"])
                if end - start >= 0.1:
                    p["regions"].append({"id": _new_id(), "start": round(start, 3), "end": round(end, 3),
                                         "state": state, "intensity": v["intensity"], "lyric": "",
                                         "source": "shared", "manual": False})
    for p in project["performers"]:
        p["regions"].sort(key=lambda r: r["start"])
    project["camera"] = auto_camera(project)
    return project


def apply_mode(project: dict[str, Any], mode: str) -> dict[str, Any]:
    """Switch the performance mode: re-labels roles/states and re-plans the camera."""
    if mode not in MODES:
        raise PerformanceError("Unknown performance mode.")
    project["mode"] = mode
    for i, p in enumerate(project["performers"]):
        if p["role"] == "actor":
            continue
        p["role"] = ("lead" if i == 0 else "background") if mode == "lead_background" else (
            "lead" if i == 0 else "co_lead")
        for r in p["regions"]:
            if r["state"] in VOICED and not r.get("manual"):
                r["state"] = _voiced_state(project, p)
    project["camera"] = auto_camera(project)
    return project


# --- Resolving states -----------------------------------------------------------------------

def _boundaries(project: dict[str, Any]) -> list[float]:
    points = {0.0, float(project["duration"] or 0)}
    for p in project["performers"]:
        for r in p["regions"]:
            points.update((r["start"], r["end"]))
    for c in project.get("camera", []):
        points.update((c["start"], c["end"]))
    return sorted(x for x in points if 0 <= x <= (project["duration"] or max(points)))


def _explicit(p: dict[str, Any], t: float) -> dict[str, Any] | None:
    for r in p["regions"]:
        if r["start"] <= t < r["end"]:
            return r
    return None


def state_at(project: dict[str, Any], performer_id: str, t: float) -> str:
    p = performer(project, performer_id)
    region = _explicit(p, t)
    if region:
        return region["state"]
    others_voiced = any(
        (r := _explicit(o, t)) is not None and r["state"] in VOICED
        for o in project["performers"] if o["id"] != performer_id)
    return "LISTENING" if others_voiced else "IDLE"


def timeline(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Every stretch where nobody's state or the shot changes: the director sheet's rows."""
    points = _boundaries(project)
    rows: list[dict[str, Any]] = []
    for a, b in zip(points, points[1:]):
        if b - a < 1e-3:
            continue
        mid = (a + b) / 2
        states = {p["id"]: state_at(project, p["id"], mid) for p in project["performers"]}
        shot = next((c for c in project.get("camera", []) if c["start"] <= mid < c["end"]), None)
        row = {"start": round(a, 3), "end": round(b, 3), "states": states,
               "camera": {"shot": shot["shot"], "focus": shot.get("focus")} if shot else None}
        if rows and rows[-1]["states"] == states and rows[-1]["camera"] == row["camera"]:
            rows[-1]["end"] = row["end"]
        else:
            rows.append(row)
    return rows


def auto_camera(project: dict[str, Any]) -> list[dict[str, Any]]:
    """A first-cut camera plan: close on a solo voice, wider when voices overlap or nobody sings."""
    project = {**project, "camera": []}
    shots: list[dict[str, Any]] = []
    for row in timeline(project):
        voiced = [pid for pid, s in row["states"].items() if s in VOICED]
        leads = [pid for pid in voiced if row["states"][pid] != "BACKGROUND_VOCAL"]
        if project["mode"] == "shared_stage" or not voiced:
            shot, focus = "wide", None
        elif len(leads) == 1:
            shot, focus = "close_up", leads[0]
        else:
            shot, focus = "two_shot", None
        if shots and shots[-1]["shot"] == shot and shots[-1]["focus"] == focus:
            shots[-1]["end"] = row["end"]
        else:
            shots.append({"start": row["start"], "end": row["end"], "shot": shot, "focus": focus})
    # Hold a cut for at least 1.5 s; very short shots fold into the previous one.
    steady: list[dict[str, Any]] = []
    for s in shots:
        if steady and s["end"] - s["start"] < 1.5:
            steady[-1]["end"] = s["end"]
        else:
            steady.append(s)
    return steady


def director_sheet(project: dict[str, Any]) -> list[dict[str, Any]]:
    names = {p["id"]: p["name"] for p in project["performers"]}
    sheet = []
    for row in timeline(project):
        cam = row["camera"]
        sheet.append({
            "start": row["start"], "end": row["end"],
            "performers": {names[pid]: state for pid, state in row["states"].items()},
            "camera": (f"{cam['shot'].replace('_', ' ')}" + (f" on {names[cam['focus']]}" if cam.get("focus") else ""))
            if cam else "",
        })
    return sheet


# --- Lip-sync drive audio and motion cues ---------------------------------------------------

def drive_spans(project: dict[str, Any], p: dict[str, Any]) -> dict[str, list[tuple[float, float]]]:
    """Voiced spans per audio source for one performer."""
    spans: dict[str, list[tuple[float, float]]] = {}
    for r in p["regions"]:
        if r["state"] in VOICED:
            src = _voice_source(project, p, r)
            spans.setdefault(src, []).append((r["start"], r["end"]))
    return spans


def build_drive_audio(project: dict[str, Any], performer_id: str) -> Path:
    """The audio that animates ONE performer's mouth: their voiced regions only, silence elsewhere."""
    p = performer(project, performer_id)
    length = int(round(float(project["duration"]) * DRIVE_RATE))
    if length <= 0:
        raise PerformanceError("Add the master song first so the performance has a length.")
    out = np.zeros(length, dtype=np.float32)
    for src, spans in drive_spans(project, p).items():
        audio = decode(src)
        audio = np.pad(audio, (0, max(0, length - len(audio))))[:length]
        out += gate(audio, spans)
    path = media_dir(project["id"]) / f"drive-{p['id']}.wav"
    write_wav(path, np.clip(out, -1, 1))
    p["drive_audio"] = str(path)
    return path


def motion_cues(project: dict[str, Any], performer_id: str) -> list[dict[str, Any]]:
    """Stage directions per stretch: what the body does, not just the mouth."""
    p = performer(project, performer_id)
    others = [o for o in project["performers"] if o["id"] != performer_id]
    cues = []
    for row in timeline(project):
        state = row["states"][performer_id]
        voiced_other = next((o for o in others if row["states"][o["id"]] in VOICED), None)
        region = _explicit(p, (row["start"] + row["end"]) / 2)
        energy = (region or {}).get("intensity", p["motion"]["energy"])
        if state == "SINGING":
            text = "sings with expressive face, natural head movement and hand gestures on strong notes"
        elif state == "BACKGROUND_VOCAL":
            text = "sings softly in the background, small head movement, steady posture"
        elif state == "SPEAKING":
            text = "speaks naturally with conversational gestures"
        elif state == "LISTENING":
            text = (f"mouth closed, listens to {voiced_other['name']}, glances toward them, "
                    "sways gently to the music, small reactions") if voiced_other else "mouth closed, listens"
        elif state == "MOVING":
            text = "mouth closed, moves across the stage"
        else:
            text = "mouth closed, relaxed, sways slightly to the beat"
        cues.append({"start": row["start"], "end": row["end"], "state": state, "energy": round(float(energy), 3),
                     "direction": text, "look_at": voiced_other["id"] if voiced_other and state == "LISTENING" else None})
    return cues


def render_plan(project: dict[str, Any]) -> dict[str, Any]:
    """What the renderer must do, and what is still missing. Nothing here claims a render exists."""
    missing = []
    if not project.get("master_audio"):
        missing.append("master song")
    passes = []
    for p in project["performers"]:
        if not p.get("identity_image"):
            missing.append(f"{p['name']}: identity picture")
        passes.append({
            "performer_id": p["id"], "name": p["name"], "identity_image": p.get("identity_image"),
            "drive_audio": p.get("drive_audio"), "seed": p["motion"]["seed"], "stage": p["stage"],
            "cues": motion_cues(project, p["id"]),
            "voiced_seconds": round(sum(e - s for spans in drive_spans(project, p).values() for s, e in spans), 2),
        })
    two_up = len(project["performers"]) == 2
    return {
        "ready": not missing,
        "missing": missing,
        # Two performers can share one multi-person lip-sync render (one camera, one light, no seams);
        # more than two are rendered as separate passes and composited on the shared stage.
        "strategy": "multi_person_single_pass" if two_up else "per_performer_passes_composited",
        "duration": project["duration"],
        "camera": project.get("camera", []),
        "stage": project.get("stage"),
        "passes": passes,
    }
