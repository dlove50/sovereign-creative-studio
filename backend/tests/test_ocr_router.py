"""OCR Studio API: reads text from a page image with the local RapidOCR engine."""
import base64
import io
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import ocr  # noqa: E402

needs_engine = pytest.mark.skipif(not ocr.available(), reason="RapidOCR not installed")


def _client(name):
    c = TestClient(app)
    assert c.post("/api/auth/signup", json={"username": name, "password": "ocrpass12", "name": name}).status_code == 201
    return c


def _page_with_text(text: str) -> str:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (900, 200), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 64)
    except OSError:
        font = ImageFont.load_default(64)
    draw.text((30, 60), text, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def test_status_and_bad_input_are_handled():
    with TestClient(app):
        c = _client("ocr_user_a")
        status = c.get("/api/ocr/status")
        assert status.status_code == 200 and "available" in status.json()
        if ocr.available():
            assert c.post("/api/ocr/read", json={"image": "not base64 at all!!" * 4}).status_code == 422
            assert c.post("/api/ocr/read", json={"image": base64.b64encode(b"just some bytes, not a picture").decode()}).status_code == 422


@needs_engine
def test_text_in_a_page_image_is_read():
    with TestClient(app):
        c = _client("ocr_user_b")
        result = c.post("/api/ocr/read", json={"image": _page_with_text("Invoice 4821 paid")})
        assert result.status_code == 200, result.text
        assert "4821" in result.json()["text"]
