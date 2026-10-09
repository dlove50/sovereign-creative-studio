import json
from types import SimpleNamespace
import pytest
from PIL import Image

from app.services import presentation
from app.models import AvatarAsset, Movie
from test_cinematic_plan_storage import stored_api


def deck():
    return presentation.Deck(title="A concise presentation", slides=[
        presentation.Slide(title="Plan your video", bullets=["Choose an audience", "Write a clear brief"], narration="Start with a clear brief for your audience."),
        presentation.Slide(title="Review before rendering", bullets=["Check the facts", "Choose a presenter"], narration="Review the facts and choose your presenter.")])


def test_generation_validates_local_model_output(monkeypatch):
    monkeypatch.setattr(presentation, "_free_comfyui_vram", lambda: None)
    payload = {"message":{"content":deck().model_dump_json()}, "done_reason":"stop"}
    def post(url, **kwargs):
        assert kwargs["json"]["think"] is False
        assert kwargs["json"]["options"]["num_predict"] == 4096
        return SimpleNamespace(raise_for_status=lambda:None, json=lambda:payload)
    monkeypatch.setattr(presentation.httpx, "post", post)
    assert len(presentation.draft("An original video workflow",2).slides) == 2
    with pytest.raises(RuntimeError, match="complete presentation"):
        presentation.draft("Brief",3)
    payload["done_reason"] = "length"
    with pytest.raises(RuntimeError, match="output limit"):
        presentation.draft("Brief",2)


def test_generated_images_and_owned_draft(stored_api, tmp_path, monkeypatch):
    client, owner, sessions = stored_api
    from app.routers import slides
    monkeypatch.setattr(slides.config,"STORAGE_DIR",tmp_path)
    calls = []
    monkeypatch.setattr(presentation,"draft",lambda *args: (calls.append(args) or deck()))
    with sessions() as db:
        db.add(AvatarAsset(id="presenter", user_id="alice", name="Presenter", source_file_path="/storage/photo.png", avatar_type="photo_avatar"))
        db.commit()
    payload = {"prompt":"Create an introduction to video production", "slide_count":2, "avatar_id":"presenter"}
    made = client.post("/api/slides/generate",json=payload)
    assert made.status_code == 201, made.text
    with sessions() as db:
        movie = db.get(Movie,made.json()["movie_id"])
        scenes = json.loads(movie.scenes_json)
        assert movie.status == "draft" and len(scenes) == 2
        assert scenes[0]["script"] == deck().slides[0].narration
    for path in (tmp_path / "movie_slides" / made.json()["movie_id"]).glob("*.png"):
        with Image.open(path) as img:
            assert img.size == (1600,900)
    assert len(list((tmp_path / "movie_slides").rglob("*.png"))) == 2
    owner[0] = "bob"
    assert client.post("/api/slides/generate",json=payload).status_code == 404
    assert len(calls) == 1  # Ownership is checked before invoking the model.


def test_wrap_breaks_at_words_and_only_splits_a_word_or_unspaced_text_when_it_must():
    from PIL import ImageDraw
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = presentation._font(40)
    width = 700
    fits = lambda lines: all(draw.textlength(line, font=font) <= width for line in lines)

    sentence = "Approximately forty electric vehicles serviced monthly in first quarter"
    lines = presentation._wrap(draw, sentence, font, width)
    assert len(lines) > 1 and fits(lines)
    assert " ".join(lines) == sentence and all(not line.startswith(" ") and not line.endswith(" ") for line in lines)
    assert set(" ".join(lines).split()) == set(sentence.split())  # no word was cut in two

    url = "https://example.com/" + "very-long-path-segment/" * 6
    pieces = presentation._wrap(draw, f"See {url} now", font, width)
    assert fits(pieces) and "".join(pieces).replace(" ", "") == f"See{url}now".replace(" ", "")

    cjk = "这是一个没有空格的很长的句子用于测试自动换行功能是否正常工作" * 3
    wrapped = presentation._wrap(draw, cjk, font, width)
    assert len(wrapped) > 1 and fits(wrapped) and "".join(wrapped) == cjk

    assert presentation._wrap(draw, "   ", font, width) == [] and presentation._wrap(draw, "Short", font, width) == ["Short"]
