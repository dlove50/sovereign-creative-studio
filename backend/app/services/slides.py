"""Slides to video: turn a PDF or PowerPoint deck into draft movie scenes, one per slide.

Text comes from the file itself (pypdf for PDF; PPTX is a zip of XML, so no extra library).
Optionally the local Qwen model rewrites each slide's text so it sounds natural spoken aloud.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

from . import movies, video_agent

MAX_SLIDES = movies.MAX_SCENES
SCRIPT_LIMIT = 1500
_PPTX_SLIDE = re.compile(r"ppt/slides/slide(\d+)\.xml$")
_PPTX_PARAGRAPH = re.compile(r"<a:p[ >].*?</a:p>", re.S)
_PPTX_TEXT = re.compile(r"<a:t>(.*?)</a:t>", re.S)
_XML_ENTITIES = (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&"))


def _unescape(text: str) -> str:
    for entity, char in _XML_ENTITIES:
        text = text.replace(entity, char)
    return text


def _squash(text: str) -> str:
    return " ".join(text.split())


def pdf_pages(path: Path) -> list[str]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        return [_squash(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 - pypdf raises many types for broken files
        raise RuntimeError("That PDF could not be read. Try exporting it again.") from exc


def pptx_slides(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as deck:
            names = sorted(
                (int(m.group(1)), n) for n in deck.namelist() if (m := _PPTX_SLIDE.search(n))
            )
            slides = []
            for _, name in names:
                xml = deck.read(name).decode("utf-8", errors="replace")
                paragraphs = [
                    _squash(_unescape("".join(_PPTX_TEXT.findall(p)))) for p in _PPTX_PARAGRAPH.findall(xml)
                ]
                slides.append(". ".join(p.rstrip(".") for p in paragraphs if p))
            return slides
    except zipfile.BadZipFile as exc:
        raise RuntimeError("That PowerPoint file could not be read. Save it as .pptx and try again.") from exc


def extract_slides(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return pdf_pages(path)
    if suffix == ".pptx":
        return pptx_slides(path)
    raise RuntimeError("Upload a PDF or a .pptx PowerPoint file.")


_DOCX_PARAGRAPH = re.compile(r"<w:p[ >].*?</w:p>", re.S)
_DOCX_TEXT = re.compile(r"<w:t(?: [^>]*)?>(.*?)</w:t>", re.S)
_DOCX_BREAKS = re.compile(r"<w:(?:tab|br)[ /]")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
DOCUMENT_SUFFIXES = {".pdf", ".pptx", ".docx", ".txt", ".md"} | IMAGE_SUFFIXES
MAX_DOCUMENT_CHARS = 200_000


def ocr_blank_pages(path: Path, pages: list[str]) -> tuple[list[str], list[int]]:
    """Fill PDF pages that have no text layer (scans, pictures of slides) by reading them with OCR.
    Returns the pages and the zero-based numbers of the ones that were read this way. Without the OCR engine
    the pages are returned unchanged."""
    from . import ocr

    blank = [i for i, text in enumerate(pages) if len(text.strip()) < ocr.BLANK_PAGE_CHARS]
    if not blank or not ocr.available():
        return pages, []
    try:
        recognised = ocr.read_pdf_pages(path, blank)
    except Exception as exc:  # noqa: BLE001 - a damaged page must not lose the whole document
        raise RuntimeError("The scanned pages could not be read. Try exporting the PDF again.") from exc
    filled = list(pages)
    done = []
    for index, text in recognised.items():
        text = _squash(text)
        if text:
            filled[index] = text
            done.append(index)
    return filled, done


def docx_paragraphs(path: Path) -> list[str]:
    """Paragraph text from a Word .docx (a zip of XML, so no extra library)."""
    try:
        with zipfile.ZipFile(path) as document:
            xml = document.read("word/document.xml").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise RuntimeError("That Word file could not be read. Save it as .docx and try again.") from exc
    paragraphs = []
    for block in _DOCX_PARAGRAPH.findall(xml):
        block = _DOCX_BREAKS.sub("<w:t> </w:t><w:x ", block)
        text = _squash(_unescape("".join(_DOCX_TEXT.findall(block))))
        if text:
            paragraphs.append(text)
    return paragraphs


def extract_document_text(path: Path) -> str:
    """The whole readable text of a document (see extract_document)."""
    return extract_document(path)[0]


def extract_document(path: Path) -> tuple[str, int]:
    """(text, number of pages read with OCR) for a PDF, PowerPoint, Word, .txt or .md file, or a picture of a
    page. Paragraphs are on separate lines. Scanned PDF pages and pictures are read with the local OCR engine."""
    from . import ocr

    suffix = path.suffix.lower()
    ocr_pages = 0
    if suffix in IMAGE_SUFFIXES:
        if not ocr.available():
            raise RuntimeError("Reading pictures of documents needs the OCR engine, which is not installed.")
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(path) as picture:
                parts, ocr_pages = [ocr.read_image(picture)], 1
        except (UnidentifiedImageError, OSError) as exc:
            raise RuntimeError("That picture could not be read.") from exc
    elif suffix == ".pdf":
        parts, done = ocr_blank_pages(path, pdf_pages(path))
        ocr_pages = len(done)
    elif suffix == ".pptx":
        parts = pptx_slides(path)
    elif suffix == ".docx":
        parts = docx_paragraphs(path)
    elif suffix in {".txt", ".md"}:
        parts = [_squash(line) for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
    else:
        raise RuntimeError("Upload a PDF, PowerPoint, Word, .txt or .md file, or a picture of a page.")
    text = "\n".join(part for part in parts if part)
    if not text.strip():
        raise RuntimeError("No readable text was found in that file, even with OCR. Check that the pages are sharp and upright.")
    if len(text) > MAX_DOCUMENT_CHARS:
        raise RuntimeError(f"That document is too long ({len(text):,} characters; the limit is {MAX_DOCUMENT_CHARS:,}). Split it and try again.")
    return text, ocr_pages


def fit_script(text: str, limit: int = SCRIPT_LIMIT) -> str:
    """Trim to `limit` characters at a sentence end (or word end) so the voice never stops mid-word."""
    text = _squash(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if end >= limit // 2:
        return cut[: end + 1]
    return cut[: cut.rfind(" ")] if " " in cut else cut


def build_scripts(slides: list[str], *, narrate: bool, model: str | None = None) -> tuple[list[str], list[str]]:
    """(scripts, warnings). Blank slides are skipped; a failed rewrite keeps the slide's own text."""
    scripts: list[str] = []
    warnings: list[str] = []
    for number, text in enumerate(slides, start=1):
        if not text.strip():
            warnings.append(f"Slide {number} has no text, so it was skipped.")
            continue
        script = fit_script(text)
        if narrate:
            try:
                script = fit_script(video_agent.improve_delivery(script, model)["script"])
            except RuntimeError as exc:
                warnings.append(f"Slide {number} kept its original wording: {exc}")
        scripts.append(script)
    return scripts, warnings
