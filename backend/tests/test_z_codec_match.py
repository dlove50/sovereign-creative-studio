"""Codec matching: what the reference is, versus what we can reproduce.

The failure these guard against is silent. An encode that drops colour
metadata or a frame rate still produces a playable file, so nothing errors --
the footage just looks subtly wrong, and nobody can say why. So the assertions
below care as much about what lands in the argument list as about the parsing.

ffprobe output is modelled as fixtures rather than invoking ffprobe, because
the inconsistency being handled IS the subject: the same field arrives as
absent, "unknown", "N/A" or "0" depending on container and build.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from fractions import Fraction

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402

from app.services import codec_match as cm  # noqa: E402


def _probe_output(*, video=None, audio=None, fmt=None) -> str:
    streams = []
    if video is not None:
        streams.append({"codec_type": "video", **video})
    if audio is not None:
        streams.append({"codec_type": "audio", **audio})
    return json.dumps({"streams": streams, "format": fmt or {}})


@pytest.fixture
def fake_ffprobe(monkeypatch):
    """Install a stand-in ffprobe returning `stdout`, with `returncode`."""
    def _install(stdout="", returncode=0, raises=None):
        def _run(cmd, **kwargs):
            if raises is not None:
                raise raises
            return subprocess.CompletedProcess(cmd, returncode, stdout, "")
        monkeypatch.setattr(cm.subprocess, "run", _run)
    return _install


# --------------------------------------------------------------------------
# Parsing: ffprobe's many spellings of "absent"
# --------------------------------------------------------------------------

@pytest.mark.parametrize("absent", [None, "", "unknown", "N/A", "none", "0", "nan"])
def test_absent_fields_do_not_become_literal_values(absent, fake_ffprobe):
    """'unknown' must not be passed to ffmpeg as a colour primary."""
    fake_ffprobe(_probe_output(video={
        "codec_name": "h264", "color_primaries": absent, "pix_fmt": "yuv420p",
    }))
    profile = cm.probe_encode_profile("ref.mp4", "ffprobe")

    assert profile.color_primaries is None, (
        f"ffprobe's {absent!r} was taken as a real value")
    args, _ = cm.encode_args(profile)
    assert "-color_primaries" not in args


def test_frame_rate_fraction_is_parsed():
    """29.97fps arrives as '30000/1001'; float(30000) would be catastrophic."""
    assert cm._as_fps("30000/1001") == Fraction(30000, 1001)
    assert cm._as_fps("25/1") == Fraction(25)


@pytest.mark.parametrize("bad", ["0/0", "", None, "N/A", "99999/1", "-30/1"])
def test_nonsense_frame_rates_are_refused(bad):
    """A still image reports 0/0; some containers claim unplayable rates."""
    assert cm._as_fps(bad) is None


def test_container_bitrate_is_used_when_the_stream_lacks_one(fake_ffprobe):
    """Consumer-camera MP4 commonly carries bitrate only on the container."""
    fake_ffprobe(_probe_output(
        video={"codec_name": "h264"}, fmt={"bit_rate": "8000000"},
    ))
    profile = cm.probe_encode_profile("ref.mp4", "ffprobe")
    assert profile.video_bitrate == 8_000_000


def test_stream_bitrate_wins_over_the_container(fake_ffprobe):
    fake_ffprobe(_probe_output(
        video={"codec_name": "h264", "bit_rate": "5000000"},
        fmt={"bit_rate": "9000000"},
    ))
    assert cm.probe_encode_profile("r.mp4", "ffprobe").video_bitrate == 5_000_000


# --------------------------------------------------------------------------
# Failure paths: never break an import that works today
# --------------------------------------------------------------------------

@pytest.mark.parametrize("failure", [
    {"returncode": 1},
    {"stdout": "not json at all"},
    {"stdout": json.dumps({"streams": "not a list"})},
    {"raises": OSError("ffprobe missing")},
    {"raises": subprocess.TimeoutExpired("ffprobe", 30)},
])
def test_unreadable_reference_yields_an_empty_profile(failure, fake_ffprobe):
    fake_ffprobe(**failure)
    profile = cm.probe_encode_profile("ref.mp4", "ffprobe")

    assert profile.is_empty, "an unreadable reference must not look readable"
    assert profile.dropped, "the reason must be recorded, not silently swallowed"


def test_empty_profile_reproduces_todays_hardcoded_behaviour():
    """The whole safety property: no reference, no change in output."""
    args, _ = cm.encode_args(cm.EncodeProfile())

    assert args == [
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
    ], "an unreadable reference changed the encode"


# --------------------------------------------------------------------------
# Colour: the field this module exists for
# --------------------------------------------------------------------------

def test_colour_metadata_reaches_the_encoder():
    """ffmpeg drops these across a transcode unless named. Silent loss."""
    profile = cm.EncodeProfile(
        color_primaries="bt2020", color_transfer="smpte2084",
        color_space="bt2020nc", color_range="tv",
    )
    args, _ = cm.encode_args(profile)

    for flag, value in (
        ("-color_primaries", "bt2020"), ("-color_trc", "smpte2084"),
        ("-colorspace", "bt2020nc"), ("-color_range", "tv"),
    ):
        assert flag in args, f"{flag} was dropped; the footage will look wrong"
        assert args[args.index(flag) + 1] == value


# --------------------------------------------------------------------------
# Encoder mapping: never pass a probed codec name straight through
# --------------------------------------------------------------------------

def test_a_known_codec_maps_to_its_encoder_when_installed():
    args, profile = cm.encode_args(
        cm.EncodeProfile(codec="hevc"),
        available_encoders=frozenset({"libx264", "libx265"}),
    )
    assert args[args.index("-c:v") + 1] == "libx265"
    assert not profile.dropped


def test_a_missing_encoder_falls_back_and_says_so():
    args, profile = cm.encode_args(
        cm.EncodeProfile(codec="av1"), available_encoders=frozenset({"libx264"}),
    )
    assert args[args.index("-c:v") + 1] == "libx264"
    assert any("av1" in reason for reason in profile.dropped), (
        "a silent downgrade is the bug; the reason must be recorded")


def test_an_unknown_codec_never_reaches_the_command_line():
    """ffprobe reports decoder names that are not encoders."""
    args, _ = cm.encode_args(cm.EncodeProfile(codec="prores"))
    assert args[args.index("-c:v") + 1] == "libx264"
    assert "prores" not in args


# --------------------------------------------------------------------------
# Pixel format: 10-bit needs a matching profile or the encode fails
# --------------------------------------------------------------------------

def test_ten_bit_carries_the_profile_libx264_requires():
    args, _ = cm.encode_args(cm.EncodeProfile(pix_fmt="yuv420p10le"))
    assert "-pix_fmt" in args and args[args.index("-pix_fmt") + 1] == "yuv420p10le"
    assert "-profile:v" in args and args[args.index("-profile:v") + 1] == "high10", (
        "libx264 refuses 10-bit output without an explicit high10 profile")


def test_the_high10_profile_is_not_applied_to_other_encoders():
    """high10 is an libx264 spelling; libx265 picks depth from the format."""
    args, _ = cm.encode_args(
        cm.EncodeProfile(codec="hevc", pix_fmt="yuv420p10le"),
        available_encoders=frozenset({"libx264", "libx265"}),
    )
    assert args[args.index("-c:v") + 1] == "libx265"
    assert "-profile:v" not in args


def test_an_unsupported_pixel_format_falls_back_and_says_so():
    args, profile = cm.encode_args(cm.EncodeProfile(pix_fmt="yuv444p16le"))
    assert args[args.index("-pix_fmt") + 1] == "yuv420p"
    assert any("yuv444p16le" in r for r in profile.dropped)


# --------------------------------------------------------------------------
# Rate control
# --------------------------------------------------------------------------

def test_a_sane_bitrate_is_matched_rather_than_re_quantised():
    args, _ = cm.encode_args(cm.EncodeProfile(video_bitrate=8_000_000))
    assert args[args.index("-b:v") + 1] == "8000000"
    assert "-crf" not in args, "bitrate and crf together is ambiguous"


def test_an_absurd_bitrate_falls_back_to_quality_targeting():
    """ProRes 4K runs past 800 Mbit/s; matching it wastes disk for no gain."""
    args, profile = cm.encode_args(cm.EncodeProfile(video_bitrate=800_000_000))
    assert "-b:v" not in args
    assert args[args.index("-crf") + 1] == "18"
    assert any("ceiling" in r for r in profile.dropped)


def test_audio_bitrate_has_its_own_ceiling():
    args, profile = cm.encode_args(cm.EncodeProfile(audio_bitrate=5_000_000))
    assert args[args.index("-b:a") + 1] == "192k"
    assert any("audio bitrate" in r for r in profile.dropped)


def test_frame_rate_is_emitted_as_a_decimal():
    args, _ = cm.encode_args(cm.EncodeProfile(fps=Fraction(30000, 1001)))
    assert "-r" in args
    assert args[args.index("-r") + 1].startswith("29.97")


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def test_describe_names_the_drop_rather_than_hiding_it():
    _, profile = cm.encode_args(
        cm.EncodeProfile(codec="av1", video_bitrate=900_000_000),
        available_encoders=frozenset({"libx264"}),
    )
    line = cm.describe(profile)
    assert "dropped" in line
    assert "av1" in line


def test_describe_is_explicit_when_the_reference_was_unreadable():
    assert "unreadable" in cm.describe(cm.EncodeProfile())


def test_a_full_profile_round_trips_into_arguments(fake_ffprobe):
    """One realistic reference, end to end."""
    fake_ffprobe(_probe_output(
        video={
            "codec_name": "h264", "pix_fmt": "yuv420p10le",
            "width": 3840, "height": 2160, "r_frame_rate": "24000/1001",
            "bit_rate": "60000000", "color_primaries": "bt709",
            "color_transfer": "bt709", "color_space": "bt709", "color_range": "tv",
        },
        audio={"codec_name": "aac", "bit_rate": "320000",
               "sample_rate": "48000", "channels": "2"},
    ))
    profile = cm.probe_encode_profile("ref.mov", "ffprobe")
    args, profile = cm.encode_args(profile)

    assert profile.width == 3840 and profile.height == 2160
    assert args[args.index("-b:v") + 1] == "60000000"
    assert args[args.index("-pix_fmt") + 1] == "yuv420p10le"
    assert args[args.index("-profile:v") + 1] == "high10"
    assert args[args.index("-ar") + 1] == "48000"
    assert args[args.index("-ac") + 1] == "2"
    assert args[args.index("-b:a") + 1] == "320000"
    assert not profile.dropped, f"nothing should have been dropped: {profile.dropped}"
