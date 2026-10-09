"""Slides to video: text extraction from PDF/PPTX and draft-movie creation."""
import io
import os
import sys
import tempfile
import zipfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import slides  # noqa: E402


def _pptx(path, slide_texts):
    with zipfile.ZipFile(path, "w") as z:
        for i, paras in enumerate(slide_texts, start=1):
            body = "".join(f"<a:p><a:r><a:t>{p}</a:t></a:r></a:p>" for p in paras)
            z.writestr(f"ppt/slides/slide{i}.xml", f"<p:sld><p:txBody>{body}</p:txBody></p:sld>")


def _pdf_bytes(texts):
    # pypdf can't draw text; build a minimal PDF by hand instead.
    objs = []
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(texts)))
    objs.append("<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(texts)} >>")
    for i, t in enumerate(texts):
        content = f"BT /F1 24 Tf 50 700 Td ({t}) Tj ET"
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>")
        objs.append(f"<< /Length {len(content)} >>\nstream\n{content}\nendstream")
    out = "%PDF-1.4\n"
    offsets = []
    for n, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    return out.encode("latin-1")


def test_pptx_text_is_read_in_slide_order_with_entities_decoded(tmp_path):
    deck = tmp_path / "d.pptx"
    _pptx(deck, [["Welcome", "Q&amp;A today"], ["Second slide"]])
    assert slides.extract_slides(deck) == ["Welcome. Q&A today", "Second slide"]


def test_pptx_with_ten_or_more_slides_sorts_numerically(tmp_path):
    deck = tmp_path / "d.pptx"
    _pptx(deck, [[f"s{i}"] for i in range(1, 12)])
    assert slides.extract_slides(deck)[9:] == ["s10", "s11"]


def test_pdf_text_is_read_per_page(tmp_path):
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(_pdf_bytes(["Hello world", "Page two"]))
    assert slides.extract_slides(pdf) == ["Hello world", "Page two"]


def test_unreadable_and_unsupported_files_raise_plain_errors(tmp_path):
    bad = tmp_path / "x.pptx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(RuntimeError, match="could not be read"):
        slides.extract_slides(bad)
    with pytest.raises(RuntimeError, match="PDF or a .pptx"):
        slides.extract_slides(tmp_path / "x.doc")


def test_fit_script_cuts_at_a_sentence_end():
    text = "One sentence here. " * 100
    out = slides.fit_script(text, 100)
    assert len(out) <= 100 and out.endswith(".")


def test_build_scripts_skips_blank_slides_and_survives_a_failed_rewrite(monkeypatch):
    def boom(script, model=None):
        raise RuntimeError("Ollama is not reachable")

    monkeypatch.setattr(slides.video_agent, "improve_delivery", boom)
    scripts, warnings = slides.build_scripts(["Intro", "  ", "Outro"], narrate=True)
    assert scripts == ["Intro", "Outro"]
    assert any("Slide 2" in w and "skipped" in w for w in warnings)
    assert any("kept its original wording" in w for w in warnings)


def test_upload_creates_a_draft_movie_with_one_scene_per_slide(monkeypatch):
    with TestClient(app) as c:
        assert c.post("/api/auth/signup", json={"username": "slides_user", "password": "slidespass1", "name": "S"}).status_code == 201
        avatar_id = c.post("/api/avatars/photo", data={"name": "Presenter"}, files={"file": ("p.png", b"\x89PNG\r\n\x1a\nfake", "image/png")}).json()["id"]
        buf = io.BytesIO()
        _pptx(buf, [["Alpha"], ["Beta"], []])
        r = c.post("/api/slides/to-movie", data={"avatar_id": avatar_id, "rewrite": "false"},
                   files={"file": ("My Deck.pptx", buf.getvalue())})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["scenes"] == 2 and any("Slide 3" in w for w in body["warnings"])
        movie = c.get(f"/api/movies/{body['movie_id']}").json()
        assert movie["title"] == "My Deck" and movie["status"] == "draft"
        assert [s["script"] for s in movie["scenes"]] == ["Alpha", "Beta"]
        assert c.post("/api/slides/to-movie", data={"avatar_id": "a1"}, files={"file": ("x.txt", b"hi")}).status_code == 400


def test_pdf_visuals_keep_blank_pages_and_are_movie_owned():
    with TestClient(app) as c:
        c.post("/api/auth/signup", json={"username": "slide_visual_owner", "password": "slidespass1", "name": "S"})
        avatar = c.post("/api/avatars/photo", data={"name": "Presenter"}, files={"file": ("p.png", b"\x89PNG\r\n\x1a\nfake", "image/png")}).json()["id"]
        response = c.post("/api/slides/to-movie", data={"avatar_id": avatar, "rewrite": "false"}, files={"file": ("Visual.pdf", _pdf_bytes(["First", "", "Third"]))})
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["scenes"] == 3 and any("Slide 2" in w and "retained" in w for w in result["warnings"])
        movie = c.get(f"/api/movies/{result['movie_id']}").json()
        assert [s["script"] for s in movie["scenes"]] == ["First", "", "Third"]
        image_url = movie["scenes"][0]["slide_image_url"]
        assert c.get(image_url).content.startswith(b"\x89PNG")
        public_url = f"/storage/movie_slides/{movie['id']}/slide-1.png"
        assert c.get(public_url).status_code == 404
        saved = c.put(f"/api/movies/{movie['id']}", json={"scenes": movie["scenes"]})
        assert saved.status_code == 200 and saved.json()["scenes"][0]["slide_image_url"] == image_url
        with TestClient(app) as other:
            other.post("/api/auth/signup", json={"username": "slide_visual_other", "password": "slidespass1", "name": "O"})
            assert other.get(image_url).status_code == 404
            foreign = other.post("/api/movies", json={}).json()
            assert other.put(f"/api/movies/{foreign['id']}", json={"scenes": movie["scenes"]}).status_code == 422
            assert other.post("/api/slides/to-movie", data={"avatar_id": avatar, "rewrite": "false"}, files={"file": ("Foreign.pdf", _pdf_bytes(["Text"]))}).status_code == 404


@pytest.mark.parametrize("orientation,size", [("landscape", (832, 480)), ("portrait", (480, 832))])
def test_pdf_page_composes_with_presenter_and_preserves_audio(tmp_path, orientation, size):
    import json
    import shutil
    import subprocess
    from app.services import avatar_comfyui, slide_visuals
    ffmpeg = avatar_comfyui._ffmpeg()
    if not ffmpeg:
        pytest.skip("FFmpeg unavailable")
    source = tmp_path / "deck.pdf"
    source.write_bytes(_pdf_bytes(["Visible slide"]))
    image = slide_visuals.page_images(source, tmp_path / "pages", 1)[0]
    clip, output = tmp_path / "presenter.mp4", tmp_path / "composed.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=blue:s=320x320:r=25", "-f", "lavfi", "-i", "sine=duration=1", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip)], check=True)
    slide_visuals.compose(clip, image, output, orientation)
    ffprobe = shutil.which("ffprobe") or ffmpeg.replace("ffmpeg", "ffprobe")
    meta = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)]))
    video = next(s for s in meta["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == size
    assert any(s["codec_type"] == "audio" for s in meta["streams"])
    assert .9 < float(meta["format"]["duration"]) < 1.2
    subprocess.run([ffmpeg, "-v", "error", "-xerror", "-i", str(output), "-f", "null", "-"], check=True)


def test_extract_text_reads_text_and_decks_and_rejects_other_files():
    with TestClient(app) as c:
        assert c.post("/api/auth/signup", json={"username": "kn_user", "password": "knowledge1pw", "name": "K"}).status_code == 201
        txt = c.post("/api/slides/extract-text", files={"file": ("notes.md", b"# Title  Some   facts here.")})
        assert txt.status_code == 200 and txt.json()["text"] == "# Title Some facts here." and txt.json()["truncated"] is False
        buf = io.BytesIO()
        _pptx(buf, [["Alpha"], ["Beta"]])
        deck = c.post("/api/slides/extract-text", files={"file": ("d.pptx", buf.getvalue())})
        assert deck.json()["text"] == "Alpha Beta"
        long = c.post("/api/slides/extract-text", files={"file": ("big.txt", b"word " * 3000)})
        assert long.json()["truncated"] is True and len(long.json()["text"]) == 5000
        assert c.post("/api/slides/extract-text", files={"file": ("x.exe", b"MZ")}).status_code == 400
        assert c.post("/api/slides/extract-text", files={"file": ("empty.txt", b"   ")}).status_code == 422


def _docx(path, paragraphs, tabbed=False):
    body = "".join(
        f"<w:p><w:pPr/><w:r><w:t xml:space=\"preserve\">{p}</w:t></w:r>"
        + ("<w:r><w:tab/><w:t>col two</w:t></w:r>" if tabbed and p else "") + "</w:p>"
        for p in paragraphs)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f"<w:document><w:body>{body}<w:sectPr/></w:body></w:document>")


def test_word_documents_are_read_paragraph_by_paragraph(tmp_path):
    source = tmp_path / "plan.docx"
    _docx(source, ["Quarterly plan", "Revenue &amp; costs grew.", ""], tabbed=True)
    assert slides.docx_paragraphs(source) == ["Quarterly plan col two", "Revenue & costs grew. col two"]
    assert slides.extract_document_text(source) == "Quarterly plan col two\nRevenue & costs grew. col two"
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"not a zip")
    with pytest.raises(RuntimeError, match="Word file"):
        slides.extract_document_text(broken)
    empty = tmp_path / "empty.txt"
    empty.write_text("  \n ")
    with pytest.raises(RuntimeError, match="even with OCR"):
        slides.extract_document_text(empty)
    huge = tmp_path / "huge.txt"
    huge.write_text("x " * (slides.MAX_DOCUMENT_CHARS // 2 + 10))
    with pytest.raises(RuntimeError, match="too long"):
        slides.extract_document_text(huge)


def test_condense_passes_short_text_and_summarises_long_text_in_sections(monkeypatch):
    from app.services import presentation
    assert presentation.condense("  A short brief.  ") == ("A short brief.", False)
    seen = []
    monkeypatch.setattr(presentation, "_free_comfyui_vram", lambda: None)
    monkeypatch.setattr(presentation, "_summarize_section", lambda section, limit: seen.append((len(section), limit)) or f"S{len(seen)}")
    text = "\n".join(f"Paragraph {i} " + "word " * 200 for i in range(40))  # about 42,000 characters
    brief, condensed = presentation.condense(text)
    assert condensed is True and 2 <= len(seen) <= 8
    assert brief == "\n\n".join(f"S{i}" for i in range(1, len(seen) + 1)) and len(brief) < presentation.BRIEF_LIMIT
    assert all(limit <= presentation.BRIEF_LIMIT // len(seen) for _, limit in seen)

    def broken(section, limit):
        import httpx
        raise httpx.ConnectError("model offline")

    monkeypatch.setattr(presentation, "_summarize_section", broken)
    with pytest.raises(RuntimeError, match="local model could not read"):
        presentation.condense(text)


def test_document_brief_endpoint_handles_word_pdf_text_and_bad_files(monkeypatch):
    from app.services import presentation
    monkeypatch.setattr(presentation, "_free_comfyui_vram", lambda: None)
    monkeypatch.setattr(presentation, "_summarize_section", lambda section, limit: "Summary.")
    with TestClient(app) as c:
        assert c.post("/api/auth/signup", json={"username": "doc_brief_user", "password": "docbrief1pw", "name": "D"}).status_code == 201
        buf = io.BytesIO()
        _docx(buf, ["Launch plan", "We ship in March."])
        word = c.post("/api/slides/document-brief", files={"file": ("plan.docx", buf.getvalue())})
        assert word.status_code == 200, word.text
        body = word.json()
        assert body["brief"] == "Launch plan\nWe ship in March." and body["condensed"] is False and body["suggested_slides"] == 3
        pdf = c.post("/api/slides/document-brief", files={"file": ("a.pdf", _pdf_bytes(["Hello world"]))})
        assert pdf.status_code == 200 and "Hello world" in pdf.json()["brief"]
        big = c.post("/api/slides/document-brief", files={"file": ("big.txt", ("Line of text. " * 30 + "\n") * 60)})
        assert big.status_code == 200 and big.json()["condensed"] is True and big.json()["source_chars"] > 25000
        assert big.json()["suggested_slides"] == 10 and big.json()["brief"].startswith("Summary.")
        assert c.post("/api/slides/document-brief", files={"file": ("x.exe", b"MZ")}).status_code == 400
        assert c.post("/api/slides/document-brief", files={"file": ("empty.txt", b"  ")}).status_code == 422


def test_section_summary_reads_the_json_reply_and_rejects_cut_off_or_empty_answers(monkeypatch):
    import json
    from app.services import presentation

    class Reply:
        def __init__(self, content, done_reason="stop"):
            self.content, self.done_reason = content, done_reason

        def raise_for_status(self):
            pass

        def json(self):
            return {"done_reason": self.done_reason, "message": {"content": self.content}}

    sent = {}

    def post(url, json=None, timeout=None):
        sent.update(json or {})
        return replies.pop(0)

    monkeypatch.setattr(presentation.httpx, "post", post)
    replies = [Reply(json.dumps({"summary": "  Sales  rose\n 12%.  "}))]
    assert presentation._summarize_section("text", 500) == "Sales rose 12%."
    assert sent["format"]["required"] == ["summary"] and sent["think"] is False
    for bad in (Reply("{}"), Reply(json.dumps({"summary": "  "})), Reply(json.dumps({"summary": "x"}), "length"), Reply("not json")):
        replies = [bad]
        with pytest.raises((KeyError, ValueError)):
            presentation._summarize_section("text", 500)


def _scan(path, lines_per_page):
    """A scanned document: pages that are only pictures of text, so the PDF has no text layer."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 46) if os.path.exists("C:/Windows/Fonts/arial.ttf") else ImageFont.load_default(46)
    pages = []
    for lines in lines_per_page:
        page = Image.new("RGB", (1240, 1754), "white")
        draw = ImageDraw.Draw(page)
        for row, line in enumerate(lines):
            draw.text((90, 120 + row * 110), line, font=font, fill="black")
        pages.append(page)
    pages[0].save(path, "PDF", save_all=True, append_images=pages[1:], resolution=150)


ocr_ready = pytest.mark.skipif(not __import__("app.services.ocr", fromlist=["available"]).available(), reason="OCR engine not installed")


@ocr_ready
def test_scanned_pdf_pages_are_read_with_ocr_and_text_pages_are_left_alone(tmp_path):
    from app.services import ocr
    scan = tmp_path / "scan.pdf"
    _scan(scan, [["Quarterly service report", "Electric vehicles serviced: 42"], ["Technician certification due January"]])
    assert slides.pdf_pages(scan) == ["", ""]  # no text layer at all
    text, read_with_ocr = slides.extract_document(scan)
    assert read_with_ocr == 2
    flat = text.lower()
    assert "quarterly service report" in flat and "serviced: 42" in flat and "certification due january" in flat
    assert text.index("Quarterly") < text.index("Technician")  # pages stay in order
    filled, done = slides.ocr_blank_pages(scan, ["A page that already has plenty of real text.", ""])
    assert done == [1] and filled[0] == "A page that already has plenty of real text." and "technician" in filled[1].lower()
    assert ocr.arrange([([[0, 0], [100, 0], [100, 20], [0, 20]], "left", 0.9), ([[200, 2], [300, 2], [300, 22], [200, 22]], "right", 0.9),
                        ([[0, 60], [100, 60], [100, 80], [0, 80]], "below", 0.9), ([[0, 120], [50, 120], [50, 140], [0, 140]], "noise", 0.1)]) == "left right\nbelow"


@ocr_ready
def test_document_brief_reads_scans_and_pictures_and_scanned_decks_become_scenes(tmp_path):
    from PIL import Image, ImageDraw, ImageFont
    scan = tmp_path / "deck.pdf"
    _scan(scan, [["Safety basics"], ["Wear protective gloves"]])
    picture = tmp_path / "page.png"
    page = Image.new("RGB", (1200, 400), "white")
    ImageDraw.Draw(page).text((60, 120), "Opening hours are nine to five", font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 50), fill="black")
    page.save(picture)
    with TestClient(app) as c:
        assert c.post("/api/auth/signup", json={"username": "ocr_user", "password": "ocrpass12", "name": "O"}).status_code == 201
        brief = c.post("/api/slides/document-brief", files={"file": ("deck.pdf", scan.read_bytes())})
        assert brief.status_code == 200, brief.text
        assert brief.json()["ocr_pages"] == 2 and "safety basics" in brief.json()["brief"].lower()
        photo = c.post("/api/slides/document-brief", files={"file": ("page.png", picture.read_bytes())})
        assert photo.status_code == 200 and photo.json()["ocr_pages"] == 1 and "nine to five" in photo.json()["brief"].lower()
        assert c.post("/api/slides/document-brief", files={"file": ("junk.png", b"not a picture")}).status_code == 422
        blank = tmp_path / "blank.png"
        Image.new("RGB", (600, 300), "white").save(blank)
        assert c.post("/api/slides/document-brief", files={"file": ("blank.png", blank.read_bytes())}).status_code == 422

        avatar = c.post("/api/avatars/photo", data={"name": "Presenter"}, files={"file": ("p.png", b"\x89PNG\r\n\x1a\nfake", "image/png")}).json()["id"]
        made = c.post("/api/slides/to-movie", data={"avatar_id": avatar, "rewrite": "false"}, files={"file": ("Scanned.pdf", scan.read_bytes())})
        assert made.status_code == 201, made.text
        result = made.json()
        assert result["scenes"] == 2 and sum("read with OCR" in w for w in result["warnings"]) == 2
        scenes = c.get(f"/api/movies/{result['movie_id']}").json()["scenes"]
        assert "safety basics" in scenes[0]["script"].lower() and "protective gloves" in scenes[1]["script"].lower()
        assert all(s["slide_image_url"] for s in scenes)  # the page picture is still shown beside the presenter


def test_without_the_ocr_engine_scans_get_a_clear_message(tmp_path, monkeypatch):
    from app.services import ocr
    scan = tmp_path / "scan.pdf"
    _scan(scan, [["Hidden text"]])
    monkeypatch.setattr(ocr, "available", lambda: False)
    assert slides.ocr_blank_pages(scan, [""]) == ([""], [])
    with pytest.raises(RuntimeError, match="even with OCR"):
        slides.extract_document_text(scan)
    picture = tmp_path / "p.png"
    picture.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="needs the OCR engine"):
        slides.extract_document_text(picture)
