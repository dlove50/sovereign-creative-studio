"""Split a song into vocals and instrumental with Demucs (htdemucs).

Run as a script by the stems venv (it needs PyTorch, which the Sovereign backend
itself does not load):

    python stems_worker.py <input audio> <output folder>

Writes vocals.wav and instrumental.wav (16-bit stereo, 44.1 kHz) to the folder and
prints one JSON line with the device used. The backend never imports this module.
"""
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

RATE = 44100
MODEL = "htdemucs"


def _find_ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    hits = sorted((Path.home() / "AppData/Local/Microsoft/WinGet/Packages").glob("*FFmpeg*/**/bin/ffmpeg.exe"))
    if not hits:
        raise SystemExit("ffmpeg was not found.")
    return str(hits[0])


def _read(path: Path):
    import numpy as np
    raw = subprocess.run([_find_ffmpeg(), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(RATE), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.copy()


def _write(path: Path, audio) -> None:
    import numpy as np
    pcm = (np.clip(audio, -1.0, 1.0).T * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def main() -> None:
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    source, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    mix = torch.from_numpy(_read(source))
    ref = mix.mean(0)
    normalized = (mix - ref.mean()) / (ref.std() + 1e-8)
    model = get_model(MODEL)
    model.eval()
    sources = list(model.sources)
    for device in (["cuda"] if torch.cuda.is_available() else []) + ["cpu"]:
        try:
            with torch.no_grad():
                out = apply_model(model, normalized[None], device=device, split=True, overlap=0.25, progress=False)[0]
            break
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
    else:
        raise SystemExit("Not enough memory to separate this song.")
    out = out * (ref.std() + 1e-8) + ref.mean()
    vocals = out[sources.index("vocals")]
    instrumental = sum(out[i] for i, name in enumerate(sources) if name != "vocals")
    _write(out_dir / "vocals.wav", vocals.cpu().numpy())
    _write(out_dir / "instrumental.wav", instrumental.cpu().numpy())
    print(json.dumps({"device": device, "model": MODEL, "seconds": round(mix.shape[1] / RATE, 2)}))


if __name__ == "__main__":
    main()
