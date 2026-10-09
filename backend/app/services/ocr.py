"""Text recognition for scanned pages and photos of documents.

RapidOCR runs on the CPU with models that ship inside the Python package, so it needs no download, no graphics
memory and no network. Used for scanned PDFs and slides, and for image uploads.
"""
from __future__ import annotations

import threading
from pathlib import Path

MAX_OCR_PAGES = 40  # per document; a page takes about 2 seconds on the CPU
RENDER_PIXELS = 2200  # long side of a rendered PDF page: sharp enough for body text, small enough to stay fast
MIN_CONFIDENCE = 0.5
BLANK_PAGE_CHARS = 20  # fewer characters than this means the page is a picture, not text

_engine = None
_engine_lock = threading.Lock()  # the recognizer is not safe to share between threads


def available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def _recognizer():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def arrange(detections: list) -> str:
    """Reading order: lines top to bottom, boxes on the same line left to right."""
    lines = []
    for box, text, score in detections:
        if not str(text).strip() or float(score) < MIN_CONFIDENCE:
            continue
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        lines.append({"top": min(ys), "mid": (min(ys) + max(ys)) / 2, "height": max(ys) - min(ys), "left": min(xs), "text": str(text).strip()})
    lines.sort(key=lambda item: item["mid"])
    rows: list[list[dict]] = []
    for item in lines:
        if rows and abs(item["mid"] - rows[-1][-1]["mid"]) < 0.5 * max(item["height"], rows[-1][-1]["height"]):
            rows[-1].append(item)
        else:
            rows.append([item])
    return "\n".join(" ".join(part["text"] for part in sorted(row, key=lambda item: item["left"])) for row in rows)


def read_image(image) -> str:
    """Text in a PIL image, one line of text per line, or an empty string."""
    import numpy as np

    pixels = np.array(image.convert("RGB"))
    with _engine_lock:
        detections, _timings = _recognizer()(pixels)
    return arrange(detections or [])


def read_pdf_pages(path: Path, page_numbers: list[int]) -> dict[int, str]:
    """OCR the given zero-based pages of a PDF. Pages beyond MAX_OCR_PAGES are skipped."""
    import pypdfium2 as pdfium

    from .slide_visuals import _pdf_lock

    found: dict[int, str] = {}
    for index in page_numbers[:MAX_OCR_PAGES]:
        with _pdf_lock, pdfium.PdfDocument(str(path)) as document:
            if not 0 <= index < len(document):
                continue
            page = document[index]
            try:
                width, height = page.get_size()
                bitmap = page.render(scale=RENDER_PIXELS / max(width, height, 1))
                try:
                    picture = bitmap.to_pil()
                finally:
                    bitmap.close()
            finally:
                page.close()
        found[index] = read_image(picture)
    return found
