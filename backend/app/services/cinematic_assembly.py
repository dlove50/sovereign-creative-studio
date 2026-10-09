"""Lossless ordered assembly of compatible completed scene clips."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def _probe(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                             "-of", "json", str(path)], capture_output=True, text=True, check=True, timeout=30)
    return json.loads(result.stdout)


def assemble_clips(clips: list[Path], destination: Path):
    if not clips or any(p.resolve() == destination.resolve() for p in clips):
        raise ValueError("Assembly needs separate input clips and destination")
    metadata = [_probe(path) for path in clips]
    def signature(item):
        return [(s.get("codec_type"), s.get("codec_name"), s.get("width"), s.get("height"),
                 s.get("pix_fmt"), s.get("time_base"), s.get("avg_frame_rate"),
                 s.get("sample_rate"), s.get("channels"), s.get("channel_layout"))
                for s in item["streams"] if s["codec_type"] in {"video", "audio"}]
    if any(signature(item) != signature(metadata[0]) for item in metadata[1:]):
        raise ValueError("Scene formats differ. Normalize resolution, frame rate and audio before assembly; originals were not changed.")
    expected = sum(float(item["format"]["duration"]) for item in metadata)
    audio_count = sum(s["codec_type"] == "audio" for s in metadata[0]["streams"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cinematic-", dir=destination.parent) as tmp:
        folder = Path(tmp)
        # Controlled filenames avoid concat-list escaping and preserve originals.
        for index, clip in enumerate(clips):
            shutil.copyfile(clip, folder / f"clip-{index}.mp4")
        listing = folder / "clips.txt"
        listing.write_text("\n".join(f"file 'clip-{i}.mp4'" for i in range(len(clips))))
        output = folder / "joined.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "1",
                        "-i", str(listing), "-map", "0:v:0", "-map", "0:a?", "-c", "copy",
                        "-movflags", "+faststart", str(output)], capture_output=True, check=True, timeout=300)
        assembled = _probe(output)
        if abs(float(assembled["format"]["duration"]) - expected) > max(.25, len(clips) * .05):
            raise ValueError("Assembly duration verification failed")
        if sum(s["codec_type"] == "audio" for s in assembled["streams"]) != audio_count:
            raise ValueError("Assembly audio verification failed")
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-nostdin", "-i", str(output),
                        "-f", "null", "-"], capture_output=True, check=True, timeout=300)
        output.replace(destination)
