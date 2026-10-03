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
        buf = io.BytesIO()
        _pptx(buf, [["Alpha"], ["Beta"], []])
        r = c.post("/api/slides/to-movie", data={"avatar_id": "a1", "rewrite": "false"},
                   files={"file": ("My Deck.pptx", buf.getvalue())})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["scenes"] == 2 and any("Slide 3" in w for w in body["warnings"])
        movie = c.get(f"/api/movies/{body['movie_id']}").json()
        assert movie["title"] == "My Deck" and movie["status"] == "draft"
        assert [s["script"] for s in movie["scenes"]] == ["Alpha", "Beta"]
        assert c.post("/api/slides/to-movie", data={"avatar_id": "a1"}, files={"file": ("x.txt", b"hi")}).status_code == 400
