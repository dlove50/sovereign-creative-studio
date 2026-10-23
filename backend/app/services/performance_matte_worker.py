"""CPU-only performer masks, preserving each full generated frame as an alpha layer.

Run with the optional .venv-matting environment. No model is downloaded at render time.
U2Net human segmentation (Apache-2.0) via rembg (MIT); masks require real-video QA.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")


def matte_video(source: Path, target: Path) -> int:
    import numpy as np
    from PIL import Image
    from rembg import new_session, remove

    model = Path(os.environ["U2NET_HOME"]) / "u2net_human_seg.onnx"
    if not model.is_file():
        raise RuntimeError("Install the U2Net human segmentation model before rendering.")
    session = new_session("u2net_human_seg", providers=["CPUExecutionProvider"])
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height,r_frame_rate", "-of", "json", str(source)],
                           check=True, capture_output=True, text=True)
    info = json.loads(probe.stdout)["streams"][0]
    width, height = info["width"], info["height"]
    frame_bytes = width * height * 3
    # File-backed stderr avoids a blocked pipe during long renders.
    import tempfile
    with tempfile.TemporaryFile() as errors:
        reader = subprocess.Popen(["ffmpeg", "-v", "error", "-threads", "2", "-i", str(source),
                                   "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                                  stdout=subprocess.PIPE, stderr=errors)
        writer = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
                                   "-s", f"{width}x{height}", "-r", info["r_frame_rate"], "-i", "pipe:0",
                                   "-an", "-c:v", "ffv1", "-threads", "2", "-pix_fmt", "bgra", str(target)],
                                  stdin=subprocess.PIPE, stderr=errors)
        count = 0
        try:
            while True:
                raw = reader.stdout.read(frame_bytes)
                if not raw:
                    break
                if len(raw) != frame_bytes:
                    raise RuntimeError("Truncated decoded performer frame.")
                image = Image.frombytes("RGB", (width, height), raw)
                # Refine foreground RGB as well as alpha to remove the old background's
                # bright fringe. A blurred mask alone leaves a visible light outline.
                image = remove(image, session=session, alpha_matting=True, alpha_matting_erode_size=5)
                alpha = np.asarray(image)[:, :, 3]
                if not (alpha > 128).any():
                    raise RuntimeError(f"Performer segmentation is empty at frame {count}.")
                writer.stdin.write(image.tobytes())
                count += 1
                if count % 25 == 0:
                    print(json.dumps({"frames": count}), flush=True)
            writer.stdin.close()
            if reader.wait() or writer.wait() or not count:
                errors.seek(0)
                raise RuntimeError(errors.read().decode(errors="replace")[-2000:] or "No performer frames decoded.")
        finally:
            for process in (reader, writer):
                if process.poll() is None:
                    process.terminate()
                    process.wait()
    return count


if __name__ == "__main__":
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    if source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        from PIL import Image, ImageOps
        from rembg import new_session, remove
        if not (Path(os.environ["U2NET_HOME"]) / "u2net_human_seg.onnx").is_file():
            raise RuntimeError("Install the U2Net human segmentation model before rendering.")
        session = new_session("u2net_human_seg", providers=["CPUExecutionProvider"])
        with Image.open(source) as raw:
            result = remove(ImageOps.exif_transpose(raw).convert("RGB"), session=session,
                            alpha_matting=True, alpha_matting_erode_size=5)
        if result.getchannel("A").getextrema()[1] < 128:
            raise RuntimeError("Identity segmentation is empty.")
        result.save(target, "PNG")
        print(json.dumps({"images": 1}))
    else:
        print(json.dumps({"frames": matte_video(source, target)}))
