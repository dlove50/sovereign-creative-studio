"""Match a reference video's encode profile instead of hardcoding one.

`video_import.py` probes a reference for two things -- duration, and whether a
video stream exists -- and then encodes everything the same way:

    -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k

So footage graded for HDR, shot at 24fps, or mastered in 10-bit all comes out
as 8-bit yuv420p with whatever frame rate and color metadata ffmpeg decides to
infer. This module reads what the reference actually is and produces encode
arguments that preserve it.

The discipline here is the same one the VRAM estimator uses: keep what was
measured separate from what we can act on.

  1. PROBED      what ffprobe reported. May be absent, "unknown" or "N/A" --
                 ffprobe is inconsistent across containers and builds.
  2. HONOURED    the subset we can actually encode with the tools present.
  3. DROPPED     probed, but not honoured, with the reason recorded.

A probed value is used only when it can be honoured. Everything else falls
back to the existing hardcoded default, and the profile says which fields were
dropped and why. Nothing is guessed, and a reference we cannot read produces
exactly today's behaviour rather than a failure.

Colour metadata is the field that matters most and is the easiest to lose.
ffmpeg does not carry primaries/transfer/matrix across a transcode unless told
to, so footage comes out looking subtly wrong with no error anywhere.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path

# The current hardcoded behaviour of video_import.py. Every fallback lands
# here, so a reference we cannot read reproduces today's output exactly.
DEFAULT_VIDEO_ENCODER = "libx264"
DEFAULT_PRESET = "fast"
DEFAULT_CRF = "18"
DEFAULT_PIX_FMT = "yuv420p"
DEFAULT_AUDIO_ENCODER = "aac"
DEFAULT_AUDIO_BITRATE = "192k"

# Reference codec -> the encoder we would use to reproduce it. A codec absent
# from this table is reproduced with the default encoder; we never pass a
# probed codec name straight to -c:v, since ffprobe reports decoder names that
# are often not encoders at all (e.g. "prores" has several encoders, "mpeg4"
# is not what anyone wants back).
ENCODER_FOR_CODEC = {
    "h264": "libx264",
    "hevc": "libx265",
    "vp9": "libvpx-vp9",
    "av1": "libsvtav1",
}

# Pixel formats we are willing to emit, and what each costs. 10-bit output
# from libx264 additionally needs an explicit high10 profile or the encode
# fails with an unhelpful error.
SUPPORTED_PIX_FMTS = {
    "yuv420p": (),
    "yuv422p": (),
    "yuv444p": (),
    "yuv420p10le": ("-profile:v", "high10"),
    "yuv422p10le": ("-profile:v", "high422"),
}

# ffprobe writes absent fields several different ways depending on container
# and build version. Compared against a lowercased value, so every entry here
# must be lowercase -- "N/A" sat here uppercase and silently never matched.
_MISSING = {"", "unknown", "n/a", "none", "0", "nan"}

# A reference can carry an absurd bitrate for our purposes -- ProRes 4K runs
# past 800 Mbit/s, and matching that for a short import wastes disk for no
# visible gain. Above this we fall back to quality-targeted encoding (CRF),
# which is the better trade anyway.
MAX_SANE_VIDEO_BITRATE = 120_000_000
MAX_SANE_AUDIO_BITRATE = 640_000


def _clean(value: object) -> str | None:
    """Normalise one ffprobe field, collapsing its many spellings of absent."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in _MISSING else text


def _as_int(value: object) -> int | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _as_fps(value: object) -> Fraction | None:
    """Parse ffprobe's r_frame_rate, which is a fraction like '30000/1001'."""
    text = _clean(value)
    if text is None:
        return None
    try:
        rate = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    # Guard nonsense: a still image reports 0/0, and some containers claim
    # absurd rates that would make the encode unplayable.
    if rate <= 0 or rate > 1000:
        return None
    return rate


@dataclass(frozen=True)
class EncodeProfile:
    """What the reference is. Every field may be None -- see the module note.

    `dropped` records fields that were probed but could not be honoured, so a
    caller can report why the output does not match rather than leaving the
    difference invisible.
    """

    codec: str | None = None
    pix_fmt: str | None = None
    width: int | None = None
    height: int | None = None
    fps: Fraction | None = None
    video_bitrate: int | None = None
    color_primaries: str | None = None
    color_transfer: str | None = None
    color_space: str | None = None
    color_range: str | None = None
    audio_codec: str | None = None
    audio_bitrate: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    dropped: tuple[str, ...] = field(default_factory=tuple)

    def with_dropped(self, reason: str) -> "EncodeProfile":
        return replace(self, dropped=self.dropped + (reason,))

    @property
    def is_empty(self) -> bool:
        """True when nothing usable was read; the caller should use defaults."""
        return not any(
            (self.codec, self.pix_fmt, self.width, self.fps, self.color_primaries)
        )


def probe_encode_profile(
    source: Path | str, ffprobe_bin: str, *, timeout: float = 30.0
) -> EncodeProfile:
    """Read a reference's encode profile. Never raises; returns empty on failure.

    A reference we cannot read must not break an import that works today, so
    every failure path produces an empty profile and the caller falls back.
    """
    try:
        completed = subprocess.run(
            [
                ffprobe_bin, "-v", "error",
                "-show_entries",
                "format=bit_rate:stream=codec_type,codec_name,pix_fmt,width,height,"
                "r_frame_rate,bit_rate,color_primaries,color_transfer,color_space,"
                "color_range,sample_rate,channels",
                "-of", "json", str(source),
            ],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return EncodeProfile(dropped=("ffprobe could not be run",))

    if completed.returncode:
        return EncodeProfile(dropped=("ffprobe reported an error",))

    try:
        payload = json.loads(completed.stdout)
    except (ValueError, TypeError):
        return EncodeProfile(dropped=("ffprobe output was not valid JSON",))

    streams = payload.get("streams") or []
    if not isinstance(streams, list):
        return EncodeProfile(dropped=("ffprobe returned no stream list",))

    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})

    # Container bitrate is the fallback when the video stream does not carry
    # its own, which is common in MP4 written by consumer cameras.
    video_bitrate = _as_int(video.get("bit_rate"))
    if video_bitrate is None:
        video_bitrate = _as_int((payload.get("format") or {}).get("bit_rate"))

    return EncodeProfile(
        codec=_clean(video.get("codec_name")),
        pix_fmt=_clean(video.get("pix_fmt")),
        width=_as_int(video.get("width")),
        height=_as_int(video.get("height")),
        fps=_as_fps(video.get("r_frame_rate")),
        video_bitrate=video_bitrate,
        color_primaries=_clean(video.get("color_primaries")),
        color_transfer=_clean(video.get("color_transfer")),
        color_space=_clean(video.get("color_space")),
        color_range=_clean(video.get("color_range")),
        audio_codec=_clean(audio.get("codec_name")),
        audio_bitrate=_as_int(audio.get("bit_rate")),
        sample_rate=_as_int(audio.get("sample_rate")),
        channels=_as_int(audio.get("channels")),
    )


def encode_args(
    profile: EncodeProfile, *, available_encoders: frozenset[str] | None = None
) -> tuple[list[str], EncodeProfile]:
    """Build ffmpeg arguments that reproduce `profile` as closely as we can.

    Returns the arguments and the profile annotated with whatever was dropped.
    `available_encoders` is injected rather than discovered so the mapping is
    testable without ffmpeg present; None means "assume only the default".
    """
    if available_encoders is None:
        available_encoders = frozenset({DEFAULT_VIDEO_ENCODER, DEFAULT_AUDIO_ENCODER})

    args: list[str] = []

    # --- video encoder -----------------------------------------------------
    encoder = DEFAULT_VIDEO_ENCODER
    wanted = ENCODER_FOR_CODEC.get((profile.codec or "").lower())
    if wanted and wanted != DEFAULT_VIDEO_ENCODER:
        if wanted in available_encoders:
            encoder = wanted
        else:
            profile = profile.with_dropped(
                f"codec {profile.codec}: {wanted} is not installed, used "
                f"{DEFAULT_VIDEO_ENCODER}"
            )
    args += ["-c:v", encoder]

    # --- pixel format ------------------------------------------------------
    # A 10-bit format needs a matching encoder profile, so the extra flags
    # travel with the format rather than being bolted on afterwards.
    pix_fmt = DEFAULT_PIX_FMT
    extra_profile: tuple[str, ...] = ()
    if profile.pix_fmt:
        if profile.pix_fmt in SUPPORTED_PIX_FMTS:
            pix_fmt = profile.pix_fmt
            extra_profile = SUPPORTED_PIX_FMTS[pix_fmt]
        else:
            profile = profile.with_dropped(
                f"pix_fmt {profile.pix_fmt} is not one we emit, used {DEFAULT_PIX_FMT}"
            )
    args += ["-pix_fmt", pix_fmt]
    # The high10/high422 profiles are an libx264 spelling; other encoders
    # select bit depth from the pixel format alone.
    if extra_profile and encoder == "libx264":
        args += list(extra_profile)

    # --- rate control ------------------------------------------------------
    # Prefer matching the reference's bitrate when it is known and sane,
    # because that is what "match this reference" means. Otherwise fall back
    # to quality-targeted encoding, which is the better trade.
    if profile.video_bitrate and profile.video_bitrate <= MAX_SANE_VIDEO_BITRATE:
        args += ["-b:v", str(profile.video_bitrate)]
    else:
        if profile.video_bitrate:
            profile = profile.with_dropped(
                f"video bitrate {profile.video_bitrate} exceeds the sane ceiling, "
                f"used crf {DEFAULT_CRF}"
            )
        args += ["-preset", DEFAULT_PRESET, "-crf", DEFAULT_CRF]

    # --- frame rate --------------------------------------------------------
    if profile.fps:
        args += ["-r", str(float(profile.fps))]

    # --- colour ------------------------------------------------------------
    # The whole reason this module exists. ffmpeg drops these across a
    # transcode unless they are named, and the loss is silent.
    for flag, value in (
        ("-color_primaries", profile.color_primaries),
        ("-color_trc", profile.color_transfer),
        ("-colorspace", profile.color_space),
        ("-color_range", profile.color_range),
    ):
        if value:
            args += [flag, value]

    # --- audio -------------------------------------------------------------
    args += ["-c:a", DEFAULT_AUDIO_ENCODER]
    if profile.audio_bitrate and profile.audio_bitrate <= MAX_SANE_AUDIO_BITRATE:
        args += ["-b:a", str(profile.audio_bitrate)]
    else:
        if profile.audio_bitrate:
            profile = profile.with_dropped(
                f"audio bitrate {profile.audio_bitrate} exceeds the sane ceiling, "
                f"used {DEFAULT_AUDIO_BITRATE}"
            )
        args += ["-b:a", DEFAULT_AUDIO_BITRATE]
    if profile.sample_rate:
        args += ["-ar", str(profile.sample_rate)]
    if profile.channels:
        args += ["-ac", str(profile.channels)]

    return args, profile


def describe(profile: EncodeProfile) -> str:
    """One line for the import log, naming what was matched and what was not."""
    if profile.is_empty:
        return "reference unreadable; encoded with the standard profile"
    parts = []
    if profile.codec:
        parts.append(profile.codec)
    if profile.width and profile.height:
        parts.append(f"{profile.width}x{profile.height}")
    if profile.fps:
        parts.append(f"{float(profile.fps):g}fps")
    if profile.pix_fmt:
        parts.append(profile.pix_fmt)
    if profile.color_primaries:
        parts.append(profile.color_primaries)
    matched = ", ".join(parts) if parts else "nothing usable"
    if profile.dropped:
        return f"matched {matched}; dropped: {'; '.join(profile.dropped)}"
    return f"matched {matched}"
