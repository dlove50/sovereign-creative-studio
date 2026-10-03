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
