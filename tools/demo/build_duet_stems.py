"""Build the two-singer demo stems from one locally generated song (Phase 10 test project).

The demo song ("Two Lights On One Stage", generated locally with YuE2 in Music Lab) has one vocal.
This script turns its Demucs vocal into two singers' parts following the demo arrangement:

    0.0 - 14.6   intro            both idle (shared stage)                 Mode E
   14.6 - 27.6   verse 1          A sings, B listens                       Mode A
   27.6 - 41.6   verse 2          B sings, A listens                       Mode A
   41.6 - 50.4   chorus line 1    A lead + B harmony (own stem, +4 st)     Mode C
   50.4 - 55.3   chorus line 2a   A lead + B backing (harmony, quieter)    Mode D
   55.3 - 57.7   call             A                                        Mode B
   57.7 - 60.2   response         B                                        Mode B

B's harmony is the lead vocal pitch-shifted a major third (formants preserved) because YuE2 sings one
voice; it is labelled as such in the report. The master gets the harmony mixed in so the duet is audible.

    python tools/demo/build_duet_stems.py <song.mp3> <vocals.wav> <out_dir>
"""
from __future__ import annotations

import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

RATE = 44100
A_PARTS = [(14.6, 27.6), (41.6, 55.3), (55.3, 57.7)]
B_LEAD = [(27.6, 41.6), (57.7, 60.4)]
B_HARMONY = [(41.6, 50.4)]
B_BACKING = [(50.4, 55.3)]
HARMONY_IN_MASTER = 0.45
BACKING_GAIN = 0.45


def decode(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "2", "-ar", str(RATE), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def write(path: Path, x: np.ndarray) -> Path:
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return path


def mask(n: int, spans: list[tuple[float, float]], fade: float = 0.04) -> np.ndarray:
    m = np.zeros(n, np.float32)
    f = int(RATE * fade)
    for a, b in spans:
        i, j = int(a * RATE), min(n, int(b * RATE))
        seg = np.ones(j - i, np.float32)
        k = min(f, (j - i) // 2)
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, k, dtype=np.float32))
        seg[:k], seg[-k:] = ramp, ramp[::-1]
        m[i:j] = np.maximum(m[i:j], seg)
    return m[:, None]


def main() -> None:
    song, vocals_path, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    harmony_path = out / "harmony-major-third.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(vocals_path), "-af",
                    f"rubberband=pitch={2 ** (4 / 12):.6f}:formant=preserved:pitchq=quality", "-ar", str(RATE),
                    str(harmony_path)], check=True)
    mix, vocals, harmony = decode(song), decode(vocals_path), decode(harmony_path)
    n = min(len(mix), len(vocals), len(harmony))
    mix, vocals, harmony = mix[:n], vocals[:n], harmony[:n]

    stem_a = vocals * mask(n, A_PARTS)
    stem_b = vocals * mask(n, B_LEAD) + harmony * mask(n, B_HARMONY) + harmony * BACKING_GAIN * mask(n, B_BACKING)
    master = mix + HARMONY_IN_MASTER * (harmony * mask(n, B_HARMONY) + harmony * BACKING_GAIN * mask(n, B_BACKING))
    peak = float(np.max(np.abs(master)))
    if peak > 0.98:
        master *= 0.98 / peak

    write(out / "singer-a-stem.wav", stem_a)
    write(out / "singer-b-stem.wav", stem_b)
    write(out / "master-duet.wav", master)
    print(f"wrote {out} ({n / RATE:.1f}s)")


if __name__ == "__main__":
    main()
