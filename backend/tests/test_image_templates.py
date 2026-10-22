"""Image Templates: catalogue, validation, edit-slot mapping and generation creation."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.routers import generations
from app.services import image_templates as tpl


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _png(color="red"):
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, "PNG")
    return buf.getvalue()


def test_catalogue_has_every_category_and_no_watermark_remover(client):
    data = client.get("/api/image-templates").json()
    ids = {t["id"] for t in data["templates"]}
    assert len(ids) == 48 and "watermark-remover" not in ids
    for cat in data["categories"]:
        assert any(cat in t["categories"] for t in data["templates"]), cat
    interior = next(t for t in data["templates"] if t["id"] == "interior-designer")
    room = next(f for f in interior["fields"] if f["id"] == "room_type")
    assert room["kind"] == "select" and "Home Theater" in room["options"]


def test_text_template_creates_a_generation(client):
    r = client.post("/api/image-templates/tattoo-designer/run",
                    data={"values": json.dumps({"idea": "phoenix", "style": "Japanese", "creativity": "Artistic"})})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "generation" and "phoenix" in body["generation"]["prompt"]
    assert "japanese" in body["generation"]["prompt"].lower()


def test_validation_messages(client):
    r = client.post("/api/image-templates/tattoo-designer/run",
                    data={"values": json.dumps({"idea": "lion", "style": "Baroque", "creativity": "Basic"})})
    assert r.status_code == 400 and "choose one of the options" in r.json()["detail"]
    r = client.post("/api/image-templates/sticker-maker/run", data={"values": json.dumps({"style": "Anime"})})
    assert r.status_code == 400 and "add a picture" in r.json()["detail"]
    r = client.post("/api/image-templates/sticker-maker/run", data={"values": json.dumps({"style": "Anime"})},
                    files={"photo": ("x.gif", b"GIF89a")})
    assert r.status_code == 400 and "PNG" in r.json()["detail"]
    assert client.post("/api/image-templates/nope/run", data={"values": "{}"}).status_code == 404


def test_outfit_try_on_maps_four_pictures_onto_three_edit_slots(client, monkeypatch):
    monkeypatch.setattr(generations, "_local_image_edit_ready", lambda: (True, None))
    files = [("photo", ("me.png", _png("white"), "image/png"))] + [
        ("outfits", (f"o{i}.png", _png(c), "image/png")) for i, c in enumerate(("red", "green", "blue"))]
    r = client.post("/api/image-templates/outfit-try-on/run", data={"values": "{}"}, files=files)
    assert r.status_code == 201, r.text
    from app.database import SessionLocal
    from app.models import Generation
    with SessionLocal() as db:
        gen = db.get(Generation, r.json()["generation"]["id"])
        refs = json.loads(gen.reference_image_urls)
    assert gen.source_image_url.startswith("/storage/image-edit-sources/") and len(refs) == 2


def test_too_many_pictures_is_refused(client):
    files = [("outfits", (f"o{i}.png", _png(), "image/png")) for i in range(4)] + [("photo", ("me.png", _png(), "image/png"))]
    r = client.post("/api/image-templates/outfit-try-on/run", data={"values": "{}"}, files=files)
    assert r.status_code == 400 and "at most 3" in r.json()["detail"]


def test_contact_sheet_and_slot_order(tmp_path):
    paths = []
    for i, c in enumerate(("red", "green", "blue", "yellow", "black", "white")):
        p = tmp_path / f"{i}.png"
        Image.new("RGB", (50, 80), c).save(p)
        paths.append(p)
    t = tpl.get("product-composition")
    slots = tpl.edit_images(t, {"products": paths}, tmp_path)
    assert slots[:2] == paths[:2] and len(slots) == 3 and slots[2].name == "reference-sheet.png"
    assert Image.open(slots[2]).size == (2 * 640, 2 * 640)  # the other 4 products in a 2x2 sheet


def test_enhance_template_reports_missing_model(client):
    r = client.post("/api/image-templates/skin-enhancer/run", data={"values": "{}"},
                    files={"photo": ("p.png", _png(), "image/png")})
    # GFPGAN is wired into Enhance separately; until then the template says why instead of faking a result.
    assert r.status_code in (201, 400)
    if r.status_code == 400:
        assert "GFPGAN" in r.json()["detail"]
