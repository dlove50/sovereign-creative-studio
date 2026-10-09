"""Dub plate studio: waveform and tempo analysis, cue points, and a mastered render.

A dub plate is a one-off cut of a tune made for a sound system: the track is
trimmed and tuned for the dance, dropped out and thrown into echo, and carries a
voice "special" naming the sound. This module does the analysis the deck needs
(waveform, BPM, beat grid), stores hot cues and loops per song, and renders the
result with ffmpeg into a new library song.
"""
from __future__ import annotations

import base64
import json
import math
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import music, stems
from .music import MusicError, _check_id, _meta_path, _music_dir, audio_path, get_song
from .music_playback import audio_duration, find_ffmpeg_tool

PEAK_POINTS = 1800
ANALYSIS_RATE = 11025
MAX_CUES = 8
MAX_LOOPS = 8
MAX_DROPS = 16
MAX_SPECIAL_CHARS = 200
FILTER_MODES = ("off", "lowpass", "highpass")
ECHO_DIVISIONS = {"1/8": 0.5, "1/4": 1.0, "3/8": 1.5, "1/2": 2.0, "1": 4.0}
PLACEMENTS = ("none", "intro", "outro", "both")
SIDES = ("vocal", "version", "both")
SPECIAL_MODES = ("spoken", "sung")
SPECIAL_MIN_SECONDS = 12
SPECIAL_MAX_SECONDS = 24
TARGET_LUFS = -10.0


# --- Analysis ---------------------------------------------------------------------

def _analysis_path(song_id: str) -> Path:
    return _music_dir() / f"{song_id}.dub.json"


def _state_path(song_id: str) -> Path:
    return _music_dir() / f"{song_id}.dubstate.json"


def _decode_mono(song_id: str) -> "Any":
    import numpy as np
    ffmpeg = find_ffmpeg_tool("ffmpeg")
    if not ffmpeg:
        raise MusicError("ffmpeg is needed to analyse the song.")
    raw = subprocess.run([ffmpeg, "-v", "error", "-i", str(audio_path(song_id)), "-f", "s16le", "-ac", "1",
                          "-ar", str(ANALYSIS_RATE), "-"], capture_output=True, timeout=120).stdout
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size == 0:
        raise MusicError("The song contains no audio to analyse.")
    return samples


def _peaks(samples: "Any") -> bytes:
    import numpy as np
    n = len(samples)
    edges = np.linspace(0, n, PEAK_POINTS + 1).astype(int)
    out = np.zeros(PEAK_POINTS, dtype=np.float32)
    for i in range(PEAK_POINTS):
        chunk = samples[edges[i]:max(edges[i] + 1, edges[i + 1])]
        out[i] = np.abs(chunk).max() if chunk.size else 0.0
    top = float(np.percentile(out, 99.5)) or 1.0
    return np.clip(out / top * 255.0, 0, 255).astype(np.uint8).tobytes()


def estimate_tempo(samples: "Any") -> dict[str, float]:
    """BPM and first-beat offset from the onset envelope (autocorrelation, 60-180 BPM)."""
    import numpy as np
    hop = 256
    frame = 512
    n = (len(samples) - frame) // hop
    if n < 64:
        return {"bpm": 0.0, "beat_offset": 0.0, "confidence": 0.0}
    window = np.hanning(frame)
    mags = np.empty((n, frame // 2 + 1), dtype=np.float32)
    for i in range(n):
        mags[i] = np.abs(np.fft.rfft(samples[i * hop:i * hop + frame] * window))
    flux = np.maximum(0.0, np.diff(np.log1p(mags * 20.0), axis=0)).sum(axis=1)
    flux = flux - flux.mean()
    fps = ANALYSIS_RATE / hop
    lags = np.arange(int(fps * 60 / 180), int(fps * 60 / 60) + 1)
    ac = np.array([np.dot(flux[:-lag], flux[lag:]) for lag in lags])
    if not np.any(ac > 0):
        return {"bpm": 0.0, "beat_offset": 0.0, "confidence": 0.0}
    # Favour tempos that also have energy at double the lag (the bar), which settles half/double ambiguity.
    score = ac.copy()
    for k, lag in enumerate(lags):
        if lag * 2 < len(flux) - 1:
            score[k] += 0.5 * np.dot(flux[:-lag * 2], flux[lag * 2:])
    best = int(np.argmax(score))
    bpm = 60.0 * fps / lags[best]
    confidence = float(ac[best] / (np.dot(flux, flux) or 1.0))
    period = fps * 60.0 / bpm
    phases = np.arange(int(period))
    totals = [flux[int(p)::max(1, int(round(period)))].sum() for p in phases]
    offset = float(phases[int(np.argmax(totals))] / fps)
    return {"bpm": round(float(bpm), 1), "beat_offset": round(offset, 3), "confidence": round(confidence, 3)}


_KEY_MAJOR = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
_KEY_MINOR = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


def estimate_key(samples: "Any") -> int:
    """Tonic pitch class (C=0) as a major-key equivalent: a minor key is mapped to its relative major."""
    import numpy as np
    n, hop = 8192, 4096
    freqs = np.fft.rfftfreq(n, 1.0 / ANALYSIS_RATE)
    band = (freqs >= 65) & (freqs <= 2000)
    pitch_class = np.round(69 + 12 * np.log2(freqs[band] / 440.0)).astype(int) % 12
    window = np.hanning(n)
    chroma = np.zeros(12)
    for i in range(0, max(len(samples) - n, 1), hop):
        frame = samples[i:i + n]
        if len(frame) < n:
            frame = np.pad(frame, (0, n - len(frame)))
        np.add.at(chroma, pitch_class, np.abs(np.fft.rfft(frame * window))[band] ** 2)
    if chroma.sum() <= 0:
        return 0
    best_score, best_tonic, best_minor = -2.0, 0, False
    for tonic in range(12):
        for minor, profile in ((False, _KEY_MAJOR), (True, _KEY_MINOR)):
            score = float(np.corrcoef(np.roll(profile, tonic), chroma)[0, 1])
            if score > best_score:
                best_score, best_tonic, best_minor = score, tonic, minor
    return (best_tonic + 3) % 12 if best_minor else best_tonic


def analyze(song_id: str) -> dict[str, Any]:
    """Waveform peaks (uint8, base64), duration, BPM and beat offset. Cached per song."""
    _check_id(song_id)
    if get_song(song_id) is None:
        raise MusicError("Song not found.")
    cache = _analysis_path(song_id)
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    samples = _decode_mono(song_id)
    tempo = estimate_tempo(samples)
    data = {"duration": round(len(samples) / ANALYSIS_RATE, 2), "points": PEAK_POINTS,
            "peaks": base64.b64encode(_peaks(samples)).decode("ascii"), **tempo}
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


# --- Cues and loops ---------------------------------------------------------------

def _clean_state(state: dict[str, Any], duration: float) -> dict[str, Any]:
    def t(value: Any) -> float:
        return round(max(0.0, min(float(value), duration)), 3)

    cues, seen = [], set()
    for cue in (state.get("cues") or [])[:MAX_CUES]:
        slot = int(cue["slot"])
        if 0 <= slot < MAX_CUES and slot not in seen:
            seen.add(slot)
            cues.append({"slot": slot, "time": t(cue["time"]), "label": str(cue.get("label") or "")[:24]})
    loops = []
    for loop in (state.get("loops") or [])[:MAX_LOOPS]:
        start, end = t(loop["start"]), t(loop["end"])
        if end - start >= 0.1:
            loops.append({"start": start, "end": end, "label": str(loop.get("label") or "")[:24]})
    bpm = float(state.get("bpm") or 0)
    return {"cues": sorted(cues, key=lambda c: c["slot"]), "loops": loops,
            "bpm": round(max(0.0, min(bpm, 300.0)), 1), "beat_offset": t(state.get("beat_offset") or 0)}


def get_state(song_id: str) -> dict[str, Any]:
    """Saved cues/loops plus the analysis defaults (BPM and beat grid unless you adjusted them)."""
    analysis = analyze(song_id)
    path = _state_path(song_id)
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    state = _clean_state({"cues": [], "loops": [], "bpm": analysis["bpm"], "beat_offset": analysis["beat_offset"],
                          **saved}, analysis["duration"])
    return state


def save_state(song_id: str, state: dict[str, Any]) -> dict[str, Any]:
    analysis = analyze(song_id)
    clean = _clean_state(state, analysis["duration"])
    _state_path(song_id).write_text(json.dumps(clean), encoding="utf-8")
    return clean


# --- Render -------------------------------------------------------------------------

def _num(value: Any, low: float, high: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MusicError(f"{name} must be a number.") from exc
    if not (low <= number <= high):
        raise MusicError(f"{name} must be between {low:g} and {high:g}.")
    return number


def normalize_params(params: dict[str, Any], duration: float, bpm: float) -> dict[str, Any]:
    """Validate and clamp render settings. Only numbers and fixed words ever reach ffmpeg."""
    start = _num(params.get("start", 0), 0, duration, "start")
    end_raw = params.get("end")
    end = duration if end_raw is None else _num(end_raw, 0, duration, "end")
    if end - start < 2.0:
        raise MusicError("The cut must be at least 2 seconds long.")
    filter_mode = params.get("filter_mode", "off")
    if filter_mode not in FILTER_MODES:
        raise MusicError("filter_mode must be off, lowpass or highpass.")
    division = params.get("echo_division", "1/4")
    if division not in ECHO_DIVISIONS:
        raise MusicError("echo_division must be one of " + ", ".join(ECHO_DIVISIONS) + ".")
    placement = params.get("special_placement", "none")
    if placement not in PLACEMENTS:
        raise MusicError("special_placement must be none, intro, outro or both.")
    text = " ".join(str(params.get("special_text") or "").split())[:MAX_SPECIAL_CHARS]
    if placement != "none" and not text:
        raise MusicError("Write the special (what the voice should say), or set the voice drop to none.")
    sides = params.get("sides", "vocal")
    if sides not in SIDES:
        raise MusicError("sides must be vocal, version or both.")
    special_mode = params.get("special_mode", "spoken")
    if special_mode not in SPECIAL_MODES:
        raise MusicError("special_mode must be spoken or sung.")
    special_song_id = params.get("special_song_id") or None
    if special_song_id is not None:
        _check_id(special_song_id)
    if placement != "none" and special_mode == "sung":
        if special_song_id is None or get_song(special_song_id) is None:
            raise MusicError("Make the sung special first (Voice special, Make the sung special).")
    drops = []
    for drop in (params.get("drops") or [])[:MAX_DROPS]:
        at = _num(drop["at"], 0, duration, "drop position")
        beats = _num(drop.get("beats", 4), 0.25, 32, "drop length")
        drops.append({"at": at, "beats": beats})
    return {
        "start": start, "end": end,
        "tempo_pct": _num(params.get("tempo_pct", 0), -16, 16, "tempo"),
        "pitch": _num(params.get("pitch", 0), -6, 6, "pitch"),
        "eq_low": _num(params.get("eq_low", 0), -12, 12, "low EQ"),
        "eq_mid": _num(params.get("eq_mid", 0), -12, 12, "mid EQ"),
        "eq_high": _num(params.get("eq_high", 0), -12, 12, "high EQ"),
        "filter_mode": filter_mode,
        "filter_hz": _num(params.get("filter_hz", 1000), 40, 16000, "filter frequency"),
        "echo": bool(params.get("echo", False)),
        "echo_division": division,
        "echo_feedback": _num(params.get("echo_feedback", 0.45), 0, 0.85, "echo feedback"),
        "echo_mix": _num(params.get("echo_mix", 0.4), 0, 1, "echo mix"),
        "reverb": _num(params.get("reverb", 0), 0, 1, "reverb"),
        "drops": sorted(drops, key=lambda d: d["at"]),
        "fade_in": _num(params.get("fade_in", 0), 0, 20, "fade in"),
        "fade_out": _num(params.get("fade_out", 2), 0, 30, "fade out"),
        "master": bool(params.get("master", True)),
        "special_text": text, "special_placement": placement,
        "special_voice": params.get("special_voice") or None,
        "sides": sides, "special_mode": special_mode, "special_song_id": special_song_id,
        "special_volume": _num(params.get("special_volume", 1.0), 0.3, 2.0, "voice level"),
        "sound_name": " ".join(str(params.get("sound_name") or "").split())[:60],
        "title": " ".join(str(params.get("title") or "").split())[:80],
        "bpm": bpm,
    }


def _synthesize_special(p: dict[str, Any], workdir: Path) -> tuple[Path, float]:
    from . import voice
    voice_id = p["special_voice"]
    if voice_id is not None and voice_id not in {v["id"] for v in voice.list_voices()}:
        raise MusicError("That voice is not installed.")
    if not voice.voice_ready():
        raise MusicError("No local voice is ready for the special. Check Voice settings, or set the voice drop to none.")
    out = workdir / "special.wav"
    try:
        voice.generate_speech(p["special_text"], out, voice_id)
    except Exception as exc:  # noqa: BLE001 - surface the engine's own message to the user
        raise MusicError(f"The voice drop could not be made: {exc}") from exc
    seconds = audio_duration(out)
    if not seconds:
        raise MusicError("The voice drop came out empty.")
    return out, seconds


def _closest_ratio(target: float, source: float) -> float:
    """Tempo multiplier that brings `source` to `target`, allowing for half/double-time detection."""
    if target <= 0 or source <= 0:
        return 1.0
    ratio = min((target / source, target / (source * 2), target * 2 / source), key=lambda r: abs(math.log(r)))
    return ratio if 0.7 <= ratio <= 1.4 else 1.0


def fit_special(special_id: str, song_id: str, target_bpm: float, workdir: Path) -> tuple[Path, float, dict[str, Any]]:
    """Take the sung special's isolated vocal and fit it to the riddim: trim silence, match tempo and key."""
    vocals = stems.ensure_stems(special_id)["vocals"]
    special_mix = _decode_mono(special_id)
    ratio = _closest_ratio(target_bpm, estimate_tempo(special_mix)["bpm"])
    shift = ((estimate_key(_decode_mono(song_id)) - estimate_key(special_mix) + 6) % 12) - 6
    out = workdir / "special_sung.wav"
    trim = "silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.08"
    chain = [trim, "areverse", trim, "areverse"]
    if abs(ratio - 1) > 0.005 or shift:
        chain.append(f"rubberband=tempo={ratio:.4f}:pitch={2 ** (shift / 12):.5f}:formant=preserved")
    chain.append("loudnorm=I=-16:TP=-1.5:LRA=7")
    _run_ffmpeg(["-i", str(vocals), "-af", ",".join(chain), "-ar", "44100", "-ac", "2", str(out)])
    seconds = audio_duration(out)
    if not seconds or seconds < 0.5:
        raise MusicError("The sung special came out empty. Try making it again.")
    return out, seconds, {"tempo_ratio": round(ratio, 3), "key_shift": shift}


def _prepare_special(p: dict[str, Any], song_id: str, workdir: Path) -> tuple[Path, float, dict[str, Any]]:
    if p["special_mode"] == "sung":
        tempo = 1.0 + p["tempo_pct"] / 100.0
        return fit_special(p["special_song_id"], song_id, p["bpm"] * tempo, workdir)
    path, seconds = _synthesize_special(p, workdir)
    return path, seconds, {}


def build_filter_graph(p: dict[str, Any], special_seconds: float | None) -> tuple[str, bool]:
    """ffmpeg filter graph for the settings. Returns (graph, uses_special_input)."""
    tempo = 1.0 + p["tempo_pct"] / 100.0
    length = (p["end"] - p["start"]) / tempo
    chain = [f"atrim=start={p['start']:.3f}:end={p['end']:.3f}", "asetpts=PTS-STARTPTS"]
    if abs(p["tempo_pct"]) > 0.01 or abs(p["pitch"]) > 0.01:
        chain.append(f"rubberband=tempo={tempo:.4f}:pitch={2 ** (p['pitch'] / 12):.5f}")
    for freq, gain in ((90, p["eq_low"]), (1000, p["eq_mid"]), (8000, p["eq_high"])):
        if abs(gain) > 0.05:
            chain.append(f"equalizer=f={freq}:width_type=o:width=1.4:g={gain:.1f}")
    if p["filter_mode"] != "off":
        chain.append(f"{p['filter_mode']}=f={p['filter_hz']:.0f}:poles=2")
    for drop in p["drops"]:
        a = (drop["at"] - p["start"]) / tempo
        beat = 60.0 / (p["bpm"] * tempo) if p["bpm"] else 0.5
        b = a + drop["beats"] * beat
        if b > 0 and a < length:
            chain.append(f"volume=enable='between(t,{max(a, 0):.3f},{b:.3f})':volume=0")
    graph = "[0:a]" + ",".join(chain) + "[dry]"
    last = "dry"
    wet_taps = []
    if p["echo"] and p["bpm"]:
        beat_ms = 60000.0 / (p["bpm"] * tempo)
        delay = max(30.0, min(beat_ms * ECHO_DIVISIONS[p["echo_division"]], 2000.0))
        fb = p["echo_feedback"]
        wet_taps.append((f"aecho=1:1:{delay:.0f}|{delay * 2:.0f}|{delay * 3:.0f}|{delay * 4:.0f}:"
                         f"{fb:.2f}|{fb ** 2:.2f}|{fb ** 3:.2f}|{fb ** 4:.2f}", p["echo_mix"]))
    if p["reverb"] > 0.01:
        r = p["reverb"]
        wet_taps.append((f"aecho=1:1:37|61|97|151|233:{0.55 * r:.2f}|{0.45 * r:.2f}|{0.35 * r:.2f}|{0.25 * r:.2f}|{0.18 * r:.2f}",
                         0.5 * r + 0.15))
    for i, (fx, level) in enumerate(wet_taps):
        graph += f";[{last}]asplit[d{i}][w{i}];[w{i}]{fx},volume={level:.2f}[wet{i}];[d{i}][wet{i}]amix=inputs=2:normalize=0[fx{i}]"
        last = f"fx{i}"
    tail = []
    if p["fade_in"] > 0:
        tail.append(f"afade=t=in:st=0:d={p['fade_in']:.2f}")
    if p["fade_out"] > 0:
        tail.append(f"afade=t=out:st={max(length - p['fade_out'], 0):.2f}:d={min(p['fade_out'], length):.2f}")
    uses_special = special_seconds is not None and p["special_placement"] != "none"
    if uses_special:
        slots = []
        if p["special_placement"] in ("intro", "both"):
            slots.append(0.4)
        if p["special_placement"] in ("outro", "both"):
            slots.append(max(length - special_seconds - 0.8, 0.4))
        duck = ",".join(f"volume=enable='between(t,{s - 0.1:.2f},{s + special_seconds + 0.3:.2f})':volume=0.45" for s in slots)
        graph += f";[{last}]{duck}[duck]"
        graph += f";[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={p['special_volume']:.2f}"
        graph += f",asplit={len(slots)}" + "".join(f"[v{i}]" for i in range(len(slots)))
        for i, s in enumerate(slots):
            ms = int(s * 1000)
            graph += f";[v{i}]adelay={ms}|{ms}[vd{i}]"
        mix_in = "[duck]" + "".join(f"[vd{i}]" for i in range(len(slots)))
        graph += f";{mix_in}amix=inputs={1 + len(slots)}:duration=first:normalize=0[mixed]"
        last = "mixed"
    if tail:
        graph += f";[{last}]{','.join(tail)}[faded]"
        last = "faded"
    if p["master"]:
        graph += f";[{last}]loudnorm=I={TARGET_LUFS}:TP=-1.0:LRA=8,alimiter=limit=0.97[out]"
    else:
        graph += f";[{last}]alimiter=limit=0.97[out]"
    return graph, uses_special


def _run_ffmpeg(args: list[str]) -> None:
    ffmpeg = find_ffmpeg_tool("ffmpeg")
    if not ffmpeg:
        raise MusicError("ffmpeg is needed to render a dub plate.")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run([ffmpeg, "-y", "-v", "error", *args], capture_output=True, text=True, timeout=300,
                              creationflags=flags)
    except subprocess.TimeoutExpired as exc:
        raise MusicError("The render took too long and was stopped.") from exc
    if proc.returncode != 0:
        raise MusicError("The render failed: " + (proc.stderr.strip().splitlines() or ["ffmpeg error"])[-1][:300])


def _source_for(song_id: str, side: str) -> Path:
    """The audio a side is cut from: the full song, or its instrumental (the version side)."""
    song = get_song(song_id)
    if side == "version" and not (song or {}).get("instrumental"):
        return stems.ensure_stems(song_id)["instrumental"]
    return audio_path(song_id)


def _render_to(song_id: str, params: dict[str, Any], out: Path, bitrate: str, side: str = "vocal") -> dict[str, Any]:
    analysis = analyze(song_id)
    state = get_state(song_id)
    p = normalize_params(params, analysis["duration"], state["bpm"] or analysis["bpm"])
    if side == "version":
        p["special_placement"] = "none"  # the version side is the riddim alone
    with tempfile.TemporaryDirectory(prefix="dubplate-") as tmp:
        special = None
        seconds = None
        if p["special_placement"] != "none":
            special, seconds, fit = _prepare_special(p, song_id, Path(tmp))
            p["special_fit"] = fit
        graph, uses_special = build_filter_graph(p, seconds)
        args = ["-i", str(_source_for(song_id, side))]
        if uses_special and special is not None:
            args += ["-i", str(special)]
        args += ["-filter_complex", graph, "-map", "[out]", "-ar", "44100", "-ac", "2", "-b:a", bitrate, str(out)]
        _run_ffmpeg(args)
    return p


def preview_path(song_id: str) -> Path:
    return _music_dir() / f"{_check_id(song_id)}.dubpreview.mp3"


def render_preview(song_id: str, params: dict[str, Any], side: str = "vocal") -> Path:
    """Render exactly what the export would sound like (smaller file) so it can be auditioned."""
    if side not in ("vocal", "version"):
        raise MusicError("side must be vocal or version.")
    out = preview_path(song_id)
    _render_to(song_id, params, out, "128k", side)
    return out


def _press_side(song_id: str, source: dict[str, Any], params: dict[str, Any], side: str) -> dict[str, Any]:
    new_id = uuid.uuid4().hex[:12]
    out = audio_path(new_id)
    try:
        p = _render_to(song_id, params, out, "320k", side)
    except Exception:
        out.unlink(missing_ok=True)
        raise
    sound = p["sound_name"]
    base = p["title"] or (f"{source['title']} (Dubplate for {sound})" if sound else f"{source['title']} (Dubplate)")
    version = side == "version"
    style = ("Dubplate version" if version else "Dubplate") + (f" for {sound}" if sound else "") + " · " + source["style"]
    song = {
        "id": new_id, "title": (base + (" - Version" if version else ""))[:80], "style": style[:500],
        "lyrics": "" if version else p["special_text"],
        "instrumental": True if version else source.get("instrumental", False),
        "duration_requested": audio_duration(out) or round((p["end"] - p["start"]) / (1 + p["tempo_pct"] / 100), 1),
        "seed": source.get("seed", 0), "quality": "320k", "provider": "dubplate", "favorite": False,
        "size_bytes": out.stat().st_size, "generation_seconds": 0.0,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parent_id": song_id, "side": side, "dub": {k: v for k, v in p.items() if k != "title"},
    }
    _meta_path(new_id).write_text(json.dumps(song, indent=2), encoding="utf-8")
    return song


def render_dubplate(song_id: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Press the dub plate into the library: the vocal side, the version side, or both (linked by pair_id)."""
    source = get_song(song_id)
    if source is None:
        raise MusicError("Song not found.")
    sides = params.get("sides", "vocal")
    if sides not in SIDES:
        raise MusicError("sides must be vocal, version or both.")
    wanted = ["vocal", "version"] if sides == "both" else [sides]
    made: list[dict[str, Any]] = []
    try:
        for side in wanted:
            made.append(_press_side(song_id, source, params, side))
    except Exception:
        for song in made:  # all or nothing: do not leave half a plate behind
            music.delete_song(song["id"])
        raise
    if len(made) == 2:
        for song, other in ((made[0], made[1]), (made[1], made[0])):
            song["pair_id"] = other["id"]
            _meta_path(song["id"]).write_text(json.dumps(song, indent=2), encoding="utf-8")
    return made


# --- Sung special -------------------------------------------------------------------

def _special_lyrics(text: str) -> tuple[str, int]:
    lines = [part.strip(" ,;") for part in re.split(r"[.!?;\n]+", text) if part.strip(" ,;")]
    lines = [line[:70] for line in lines][:4] or [text[:70]]
    body = "[verse]\n" + "\n".join(lines)
    if sum(len(line.split()) for line in lines) < 12:
        body += "\n\n[chorus]\n" + lines[-1]
        lines = lines + [lines[-1]]
    return body, len(lines)


def make_sung_special(song_id: str, text: str, sound_name: str) -> dict[str, Any]:
    """Queue a short YuE2 song in the riddim's style that sings the special; its vocal is isolated for the mix."""
    source = get_song(song_id)
    if source is None:
        raise MusicError("Song not found.")
    text = " ".join(str(text or "").split())[:MAX_SPECIAL_CHARS]
    if not text:
        raise MusicError("Write the special first (what the singer should sing).")
    lyrics, line_count = _special_lyrics(text)
    tags = [t.strip() for t in source["style"].split(",")]
    style = ", ".join(t for t in tags if t and t.lower() != "instrumental")
    style = (style + ", dubplate special, shout-out vocal, clear singing")[:500]
    duration = float(max(SPECIAL_MIN_SECONDS, min(SPECIAL_MAX_SECONDS, 4 + 3.2 * line_count)))
    sound = " ".join(str(sound_name or "").split())[:40]
    params = music.normalize_request(
        title=f"Special: {sound}" if sound else "Dubplate special", style=style, lyrics=lyrics, instrumental=False,
        duration=duration, seed=source.get("seed"), quality="V0")

    def tag_and_split(song: dict[str, Any]) -> dict[str, Any]:
        stems.ensure_stems(song["id"], gpu_locked=True)
        song = {**song, "special_for": song_id, "special_text": text}
        _meta_path(song["id"]).write_text(json.dumps(song, indent=2), encoding="utf-8")
        return song

    params.update(after_save=tag_and_split, after_save_message="Isolating the singer's voice...", auto_play=False)
    return music.create_job(params)
