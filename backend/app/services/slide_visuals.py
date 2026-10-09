"""Bounded PDF page images and slide/presenter composition; original decks stay local."""
from pathlib import Path
import math
import re
import shutil
import subprocess
import threading

from .. import config
from . import avatar_comfyui

_pdf_lock = threading.Lock()  # PDFium is not thread-safe within a process.


def page_images(source: Path, destination: Path, count: int) -> list[Path]:
    import pypdfium2 as pdfium

    destination.mkdir(parents=True, exist_ok=True)
    written = []
    try:
        with _pdf_lock, pdfium.PdfDocument(source) as document:
            for index in range(min(count, len(document), 30)):
                page = document[index]
                try:
                    width, height = page.get_size()
                    if min(width, height) <= 0:
                        raise ValueError("Invalid page dimensions")
                    bitmap = page.render(scale=min(2, 1600 / max(width, height)))
                    try:
                        path = destination / f"slide-{index + 1}.png"
                        bitmap.to_pil().save(path)
                        written.append(path)
                    finally:
                        bitmap.close()
                finally:
                    page.close()
        return written
    except Exception as exc:
        for path in written:
            path.unlink(missing_ok=True)
        raise RuntimeError("PDF page images could not be rendered. Export the deck as a new PDF and try again.") from exc


def image_path(movie_id: str, url: str) -> Path:
    prefix = f"/api/movies/{movie_id}/slides/"
    if not url.startswith(prefix) or not re.fullmatch(r"slide-[1-9][0-9]?\.png", url[len(prefix):]):
        raise ValueError("Slide image must belong to this movie")
    path = config.STORAGE_DIR / "movie_slides" / movie_id / url[len(prefix):]
    if not path.is_file():
        raise ValueError("Slide image is missing. Import the PDF again.")
    return path


def compose(clip: Path, slide: Path, out: Path, orientation: str) -> None:
    """Fit the whole slide, place the presenter beside/below it, retain narration."""
    ffmpeg = avatar_comfyui._ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for slide video composition")
    probe = shutil.which("ffprobe") or str(Path(ffmpeg).with_name("ffprobe.exe" if Path(ffmpeg).suffix == ".exe" else "ffprobe"))
    duration = float(subprocess.check_output([probe, "-v", "error", "-show_entries", "format=duration",
                                             "-of", "csv=p=0", str(clip)], timeout=30))
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("Presenter clip has no valid duration")
    if orientation == "landscape":
        sw, sh, pw, ph, stack = 512, 480, 320, 480, "hstack"
    else:
        sw, sh, pw, ph, stack = 480, 456, 480, 376, "vstack"
    filters = (
        f"[1:v]scale={sw}:{sh}:force_original_aspect_ratio=decrease,"
        f"pad={sw}:{sh}:(ow-iw)/2:(oh-ih)/2:white,setsar=1[slide];"
        f"[0:v]scale={pw}:{ph}:force_original_aspect_ratio=decrease,"
        f"pad={pw}:{ph}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,tpad=stop_mode=clone:stop_duration=1[presenter];"
        f"[slide][presenter]{stack}=inputs=2:shortest=1[v]"
    )
    result = subprocess.run([
        ffmpeg, "-nostdin", "-y", "-v", "error", "-i", str(clip),
        "-loop", "1", "-framerate", "25", "-i", str(slide),
        "-filter_complex", filters, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy",
        "-t", str(duration), "-movflags", "+faststart", str(out),
    ], capture_output=True, timeout=300)
    if result.returncode:
        out.unlink(missing_ok=True)
        raise RuntimeError("Slide video composition failed; the original presenter clip was preserved")
