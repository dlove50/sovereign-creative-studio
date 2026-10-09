import hashlib
import shutil
import subprocess
from array import array

import pytest

from app.video_generators.extension_assembly import append_continuation, _probe

pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required"
)


def run(*arguments):
    return subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *map(str, arguments)],
                          capture_output=True, check=True, timeout=30).stdout


@pytest.mark.parametrize("audio", [True, False])
def test_append_preserves_source_picture_and_audio_and_handles_different_formats(tmp_path, audio):
    source, continuation, output = [tmp_path / name for name in ("source.mp4", "next.mp4", "extended.mp4")]
    args = ["-f", "lavfi", "-i", "color=red:s=160x120:r=25:d=1"]
    if audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "aac"]
    run(*args, "-c:v", "libx264", "-pix_fmt", "yuv420p", source)
    run("-f", "lavfi", "-i", "color=blue:s=128x72:r=24:d=1", "-c:v", "libx264", continuation)
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (source, continuation)]
    assert append_continuation(source, continuation, output) == pytest.approx(2, abs=0.05)
    metadata, duration, has_audio = _probe(output)
    assert (metadata["width"], metadata["height"]) == (160, 120)
    assert duration == pytest.approx(2, abs=0.1)
    assert has_audio
    # Decode the whole product, then sample source/continuation colors across the seam.
    run("-i", output, "-f", "null", "-")
    for when, channel in ((0.4, 0), (1.4, 2)):
        pixels = run("-ss", when, "-i", output, "-frames:v", 1, "-vf", "crop=32:32", "-pix_fmt", "rgb24", "-f", "rawvideo", "-")
        assert sum(pixels[channel::3]) / len(pixels[channel::3]) > 220
    samples = array("h", run("-i", output, "-ac", 1, "-ar", 48000, "-f", "s16le", "-"))
    def rms(start, end):
        part = samples[int(start * 48000):int(end * 48000)]
        return (sum(value * value for value in part) / len(part)) ** 0.5
    assert rms(0.2, 0.8) > 1000 if audio else rms(0.2, 0.8) < 2
    assert rms(1.3, 1.8) < 2
    assert hashes == [hashlib.sha256(path.read_bytes()).hexdigest() for path in (source, continuation)]


def test_refuses_overwriting_original(tmp_path):
    source = tmp_path / "source.mp4"
    with pytest.raises(ValueError, match="differ"):
        append_continuation(source, tmp_path / "next.mp4", source)
